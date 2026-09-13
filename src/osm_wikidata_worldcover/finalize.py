"""Assemble region shards into the published dataset.

Two kinds of duplicate are removed here, and they are not the same thing.
Geofabrik's regional extracts overlap, so one OSM object can appear in several
regions under different ``polygon_id`` values; those are the *same* object and
only one copy should survive. Separately, distinct objects can carry
byte-identical articles under the same label, which would let a model score on
text it memorised; those collapse too.

Splitting happens last, on H3 cells rather than rows, so every article about a
place -- and every nearby place -- shares one split.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.domain import manifest as manifest_module
from osm_wikidata_worldcover.domain.manifest import DatasetCounts, GeographicCoverage
from osm_wikidata_worldcover.domain.splits import SplitRatios, assign_cell, cell_for
from osm_wikidata_worldcover.domain.text import dedup_key
from osm_wikidata_worldcover.domain.validation import ValidationReport, validate

__all__ = ["StreamedBuild", "finalize_shards"]

PROVENANCE_COLUMNS = (
    "h3_cell",
    "split",
    "dataset_version",
    "source_dataset",
    "source_revision",
    "worldcover_version",
    "worldcover_year",
)


def _assign_splits(
    frame: pd.DataFrame, config: Config, ratios: SplitRatios | None = None
) -> pd.DataFrame:
    """Attach an H3 cell to every row and split on the cell, never on the row."""
    ratios = ratios or SplitRatios(config.train_ratio, config.validation_ratio, config.test_ratio)
    cells = [
        cell_for(lat, lon, config.h3_resolution)
        for lat, lon in zip(frame["lat"], frame["lon"], strict=True)
    ]
    frame = frame.assign(h3_cell=cells)
    # One lookup per distinct cell, so every row in a cell gets the same split.
    split_of = {cell: assign_cell(cell, ratios, config.split_seed).value for cell in set(cells)}
    return frame.assign(split=[split_of[cell] for cell in cells])


def _attach_provenance(frame: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Record which inputs and settings produced each row."""
    return frame.assign(
        dataset_version=config.dataset_version,
        source_dataset=config.source_dataset,
        source_revision=config.source_revision,
        worldcover_version=config.worldcover_version,
        worldcover_year=config.worldcover_year,
    )


def _counts(frame: pd.DataFrame, rejections: dict[str, int]) -> DatasetCounts:
    """Aggregate the finished frame into the numbers the manifest reports."""
    by_split = frame.groupby("split")
    quantiles = frame["dominant_fraction"].quantile([0.5, 0.9, 0.99])
    return DatasetCounts(
        examples=by_split.size().to_dict(),
        polygons=by_split["polygon_id"].nunique().to_dict(),
        documents=by_split["document_id"].nunique().to_dict(),
        class_distribution={
            int(k): int(v) for k, v in frame["worldcover_code"].value_counts().items()
        },
        language_distribution={str(k): int(v) for k, v in frame["language"].value_counts().items()},
        dominant_fraction_quantiles={
            "p50": round(float(quantiles.loc[0.5]), 6),
            "p90": round(float(quantiles.loc[0.9]), 6),
            "p99": round(float(quantiles.loc[0.99]), 6),
        },
        coverage=GeographicCoverage(
            h3_cells=int(frame["h3_cell"].nunique()),
            bbox=(
                float(frame["lon"].min()),
                float(frame["lat"].min()),
                float(frame["lon"].max()),
                float(frame["lat"].max()),
            ),
            regions=int(frame["region"].nunique()),
        ),
        rejections=dict(sorted(rejections.items())),
    )


@dataclass(slots=True)
class StreamedBuild:
    """A finished build assembled without holding every shard in memory."""

    rows: int
    frames: dict[str, pd.DataFrame]
    manifest: dict[str, Any]
    report: ValidationReport
    duplicates_across_regions: int = 0
    duplicate_examples: int = 0
    documents_split_across_splits: int = 0


def finalize_shards(
    shard_dir: Path,
    config: Config,
    work_dir: Path,
    rejections: dict[str, int] | None = None,
) -> StreamedBuild:
    """Assemble region shards into the published dataset, one shard at a time.

    A global build is roughly 10 GB of DataFrame, more than the machine that
    produces it. Everything row-local -- the H3 cell, the split, the duplicate
    keys -- is computed per shard, where memory is bounded by one region. The
    genuinely global work, which is only de-duplication and ordering, is then
    left to DuckDB over the enriched files.
    """
    work_dir = Path(work_dir)
    enriched = work_dir / "enriched"
    enriched.mkdir(parents=True, exist_ok=True)

    total = _enrich_shards(Path(shard_dir), enriched, config)
    if total == 0:
        return StreamedBuild(0, {}, {}, validate([]))

    frames, dropped_objects, dropped_examples, dropped_documents = _deduplicate(enriched)
    rows = sum(len(f) for f in frames.values())
    report = _validate_frames(frames, config)
    counts = _counts(pd.concat(frames.values(), ignore_index=True), rejections or {})
    return StreamedBuild(
        rows=rows,
        frames=frames,
        manifest=manifest_module.build(counts, config.as_manifest_settings()),
        report=report,
        duplicates_across_regions=dropped_objects,
        duplicate_examples=dropped_examples,
        documents_split_across_splits=dropped_documents,
    )


def _enrich_shards(shard_dir: Path, enriched: Path, config: Config) -> int:
    """Add the row-local columns to each shard in turn. Returns rows seen."""
    ratios = SplitRatios(config.train_ratio, config.validation_ratio, config.test_ratio)
    total = 0
    for path in sorted(shard_dir.glob("*.parquet")):
        frame = pd.read_parquet(path)
        if len(frame) == 0 or "polygon_id" not in frame.columns:
            continue
        frame = _assign_splits(frame, config, ratios)
        frame = _attach_provenance(frame, config)
        frame["_dedup_key"] = [
            dedup_key(text, str(code))
            for text, code in zip(frame["text"], frame["worldcover_code"], strict=True)
        ]
        frame.to_parquet(enriched / path.name, index=False)
        total += len(frame)
    return total


def _deduplicate(enriched: Path) -> tuple[dict[str, pd.DataFrame], int, int, int]:
    """Collapse duplicates and split conflicts across every shard, using DuckDB.

    Three distinct problems, applied in order, each counted separately:

    1. Geofabrik extracts overlap, so one OSM object appears in several regions
       under different ``polygon_id`` values. One region is chosen per object,
       so an object wears a single id for all of its documents.
    2. Distinct objects can carry byte-identical text under the same label.
    3. One article can describe several distant places, which fall in different
       cells and therefore different splits. The split holding most of that
       document's rows keeps them; the rest are dropped, because moving them
       instead would break the geographic blocking.

    Every ordering is fully specified, so no survivor depends on file order.
    """
    import duckdb

    pattern = str(enriched / "*.parquet")
    con = duckdb.connect()
    before = _count(con, f"SELECT count(*) FROM read_parquet('{pattern}')")

    con.execute(
        f"""
        CREATE TEMP TABLE objects AS
        WITH home_region AS (
            SELECT osm_type, osm_id, region AS _home_region
            FROM (
                SELECT osm_type, osm_id, region, row_number() OVER (
                    PARTITION BY osm_type, osm_id ORDER BY region
                ) AS _rank
                FROM (SELECT DISTINCT osm_type, osm_id, region FROM read_parquet('{pattern}'))
            ) WHERE _rank = 1
        ),
        canonical AS (
            SELECT r.* FROM read_parquet('{pattern}') r
            JOIN home_region h USING (osm_type, osm_id)
            WHERE r.region = h._home_region
        )
        SELECT * EXCLUDE (_rank) FROM (
            SELECT *, row_number() OVER (
                PARTITION BY osm_type, osm_id, document_id ORDER BY polygon_id
            ) AS _rank
            FROM canonical
        ) WHERE _rank = 1
        """
    )
    after_objects = _count(con, "SELECT count(*) FROM objects")

    con.execute(
        """
        CREATE TEMP TABLE examples AS
        SELECT * EXCLUDE (_rank, _dedup_key) FROM (
            SELECT *, row_number() OVER (
                PARTITION BY _dedup_key ORDER BY polygon_id, document_id
            ) AS _rank
            FROM objects
        ) WHERE _rank = 1
        """
    )
    after_examples = _count(con, "SELECT count(*) FROM examples")

    con.execute(
        """
        CREATE TEMP TABLE kept AS
        WITH document_home AS (
            SELECT document_id, split AS _home FROM (
                SELECT document_id, split, count(*) AS n, row_number() OVER (
                    PARTITION BY document_id ORDER BY count(*) DESC, split
                ) AS _rank
                FROM examples GROUP BY document_id, split
            ) WHERE _rank = 1
        )
        SELECT e.* FROM examples e
        JOIN document_home h USING (document_id)
        WHERE e.split = h._home
        """
    )
    after = _count(con, "SELECT count(*) FROM kept")

    frames = {
        split: con.execute(
            "SELECT * FROM kept WHERE split = ? ORDER BY polygon_id, document_id", [split]
        ).df()
        for split in manifest_module.SPLIT_ORDER
    }
    con.close()
    return frames, before - after_objects, after_objects - after_examples, after_examples - after


def _validate_frames(frames: dict[str, pd.DataFrame], config: Config) -> ValidationReport:
    """Validate every split without materialising them all as dicts at once."""

    def rows() -> Iterable[dict[str, Any]]:
        for frame in frames.values():
            yield from frame.to_dict("records")

    return validate(rows(), threshold=config.threshold, min_words=config.min_words)


def _count(connection: Any, sql: str) -> int:
    """Run a counting query, refusing the empty result a count cannot produce."""
    row = connection.execute(sql).fetchone()
    if row is None:
        raise RuntimeError(f"count query returned no row: {sql}")
    return int(row[0])

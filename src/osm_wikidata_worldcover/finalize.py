"""Assemble region shards into the published dataset.

Three different problems are resolved here, and conflating them would get at
least one of them wrong:

* Geofabrik's regional extracts overlap, so one OSM object appears in several
  regions under different ``polygon_id`` values. Those are the *same* object,
  and one region is chosen for all of its documents.
* Distinct objects can carry byte-identical articles under the same label,
  which would let a model score on text it had memorised.
* One article can describe several distant places. Those fall in different
  cells and therefore different splits, which would put the document in train
  *and* test.

Nothing is ever held whole. A global build is several times the memory of the
machine that produces it, so row-local work happens a shard at a time, the
global work is left to DuckDB over files, and the result is streamed to Parquet
in batches rather than collected first.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from osm_wikidata_worldcover.adapters.writer import write_batches, write_manifest
from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.domain import manifest as manifest_module
from osm_wikidata_worldcover.domain.manifest import DatasetCounts, GeographicCoverage
from osm_wikidata_worldcover.domain.splits import SplitRatios, assign_cell, cell_for
from osm_wikidata_worldcover.domain.text import dedup_key
from osm_wikidata_worldcover.domain.validation import (
    REQUIRED_COLUMNS,
    ValidationReport,
    validate,
)

__all__ = ["StreamedBuild", "finalize_shards"]


@dataclass(slots=True)
class StreamedBuild:
    """A finished build, written to disk without ever being held in memory."""

    rows: int
    paths: list[Path]
    manifest: dict[str, Any]
    report: ValidationReport
    duplicates_across_regions: int = 0
    duplicate_examples: int = 0
    documents_split_across_splits: int = 0


def finalize_shards(
    shard_dir: Path,
    config: Config,
    work_dir: Path,
    out_dir: Path,
    rejections: dict[str, int] | None = None,
) -> StreamedBuild:
    """Assemble region shards into the dataset written under ``out_dir``."""
    work_dir, out_dir = Path(work_dir), Path(out_dir)
    enriched = work_dir / "enriched"
    enriched.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"v{config.dataset_version}"
    target.mkdir(parents=True, exist_ok=True)

    if _enrich_shards(Path(shard_dir), enriched, config) == 0:
        return StreamedBuild(0, [], {}, validate([]))

    connection, dropped = _deduplicate(enriched)
    try:
        paths, rows = _write_splits(connection, target)
        counts = _aggregate(connection, rejections or {}, dropped)
    finally:
        connection.close()

    manifest = manifest_module.build(counts, config.as_manifest_settings())
    report = _validate_written(paths, config)
    paths.append(write_manifest(manifest, target / "manifest.json"))
    return StreamedBuild(
        rows=rows,
        paths=paths,
        manifest=manifest,
        report=report,
        duplicates_across_regions=dropped["duplicate_objects_across_regions"],
        duplicate_examples=dropped["duplicate_examples"],
        documents_split_across_splits=dropped["documents_split_across_splits"],
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


def _deduplicate(enriched: Path) -> tuple[Any, dict[str, int]]:
    """Collapse duplicates and split conflicts across every shard, using DuckDB.

    The open connection is returned so the surviving rows can be streamed out
    rather than collected. Every ordering is fully specified, so no survivor
    depends on the order files happened to be read in.
    """
    import duckdb

    pattern = str(enriched / "*.parquet")
    connection = duckdb.connect()
    before = _count(connection, f"SELECT count(*) FROM read_parquet('{pattern}')")

    # One region per OSM object, so an object cannot wear two polygon_ids.
    connection.execute(
        f"""
        CREATE TEMP TABLE objects AS
        WITH home_region AS (
            SELECT osm_type, osm_id, region AS _home_region FROM (
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
    after_objects = _count(connection, "SELECT count(*) FROM objects")

    # One row per (text, label).
    connection.execute(
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
    after_examples = _count(connection, "SELECT count(*) FROM examples")

    # One split per document: the one holding most of its rows.
    connection.execute(
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
    after = _count(connection, "SELECT count(*) FROM kept")
    connection.execute("DROP TABLE objects")
    connection.execute("DROP TABLE examples")

    return connection, {
        "duplicate_objects_across_regions": before - after_objects,
        "duplicate_examples": after_objects - after_examples,
        "documents_split_across_splits": after_examples - after,
    }


def _write_splits(connection: Any, target: Path) -> tuple[list[Path], int]:
    """Stream each split from DuckDB into its own Parquet file."""
    paths: list[Path] = []
    rows = 0
    for split in manifest_module.SPLIT_ORDER:
        path = target / f"{split}.parquet"
        reader = connection.execute(
            "SELECT * FROM kept WHERE split = ? ORDER BY polygon_id, document_id",
            [split],
        ).to_arrow_reader()
        rows += write_batches(reader, path)
        paths.append(path)
    return paths, rows


def _validate_written(paths: Sequence[Path], config: Config) -> ValidationReport:
    """Validate the dataset that was actually written, by streaming it back."""

    def rows() -> Iterable[dict[str, Any]]:
        for path in paths:
            batches = pq.ParquetFile(path).iter_batches(
                batch_size=8192, columns=list(REQUIRED_COLUMNS)
            )
            for batch in batches:
                yield from batch.to_pylist()

    return validate(rows(), threshold=config.threshold, min_words=config.min_words)


def _aggregate(
    connection: Any, rejections: dict[str, int], dropped: dict[str, int]
) -> DatasetCounts:
    """Compute every manifest number in SQL, so no frame is ever built."""
    quantiles = connection.execute(
        "SELECT quantile_cont(dominant_fraction, [0.5, 0.9, 0.99]) FROM kept"
    ).fetchone()[0]
    bbox = connection.execute("SELECT min(lon), min(lat), max(lon), max(lat) FROM kept").fetchone()
    return DatasetCounts(
        examples=_by_split(connection, "count(*)"),
        polygons=_by_split(connection, "count(DISTINCT polygon_id)"),
        documents=_by_split(connection, "count(DISTINCT document_id)"),
        class_distribution=_tally(connection, "worldcover_code", int),
        language_distribution=_tally(connection, "language", str),
        dominant_fraction_quantiles={
            "p50": round(float(quantiles[0]), 6),
            "p90": round(float(quantiles[1]), 6),
            "p99": round(float(quantiles[2]), 6),
        },
        coverage=GeographicCoverage(
            h3_cells=_count(connection, "SELECT count(DISTINCT h3_cell) FROM kept"),
            bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
            regions=_count(connection, "SELECT count(DISTINCT region) FROM kept"),
        ),
        rejections=dict(sorted(rejections.items())),
        deduplication=dict(sorted(dropped.items())),
    )


def _by_split(connection: Any, expression: str) -> dict[str, int]:
    """Evaluate ``expression`` per split."""
    rows = connection.execute(f"SELECT split, {expression} FROM kept GROUP BY 1").fetchall()
    return {str(split): int(value) for split, value in rows}


def _tally(connection: Any, column: str, cast: Any) -> dict[Any, int]:
    """Count rows per distinct value of ``column``."""
    rows = connection.execute(
        f"SELECT {column}, count(*) FROM kept GROUP BY 1 ORDER BY 1"
    ).fetchall()
    return {cast(value): int(n) for value, n in rows}


def _count(connection: Any, sql: str) -> int:
    """Run a counting query, refusing the empty result a count cannot produce."""
    row = connection.execute(sql).fetchone()
    if row is None:
        raise RuntimeError(f"count query returned no row: {sql}")
    return int(row[0])

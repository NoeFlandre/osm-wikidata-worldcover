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
from typing import Any

import pandas as pd

from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.domain import manifest as manifest_module
from osm_wikidata_worldcover.domain.manifest import DatasetCounts, GeographicCoverage
from osm_wikidata_worldcover.domain.splits import SplitRatios, assign_cell, cell_for
from osm_wikidata_worldcover.domain.text import dedup_key
from osm_wikidata_worldcover.domain.validation import ValidationReport, validate

__all__ = ["BuildResult", "finalize"]

#: Identifies one physical OSM object, independent of which region it came from.
_OBJECT_KEY = ["osm_type", "osm_id", "document_id"]

PROVENANCE_COLUMNS = (
    "h3_cell",
    "split",
    "dataset_version",
    "source_dataset",
    "source_revision",
    "worldcover_version",
    "worldcover_year",
)


@dataclass(slots=True)
class BuildResult:
    """A finished build and what had to be discarded to get there."""

    frame: pd.DataFrame
    manifest: dict[str, Any]
    report: ValidationReport
    duplicates_across_regions: int = 0
    duplicate_examples: int = 0


def finalize(
    shards: Iterable[pd.DataFrame],
    config: Config,
    rejections: dict[str, int] | None = None,
) -> BuildResult:
    """Combine region shards into the published dataset."""
    frame = _concat(shards)
    if len(frame) == 0:
        return BuildResult(frame, {}, validate([]))

    frame, across_regions = _drop_repeated_objects(frame)
    frame, repeated_text = _drop_repeated_examples(frame)
    frame = _assign_splits(frame, config)
    frame = _attach_provenance(frame, config)
    frame = frame.sort_values(["polygon_id", "document_id"]).reset_index(drop=True)

    report = validate(
        frame.to_dict("records"), threshold=config.threshold, min_words=config.min_words
    )
    counts = _counts(frame, rejections or {})
    return BuildResult(
        frame=frame,
        manifest=manifest_module.build(counts, config.as_manifest_settings()),
        report=report,
        duplicates_across_regions=across_regions,
        duplicate_examples=repeated_text,
    )


def _concat(shards: Iterable[pd.DataFrame]) -> pd.DataFrame:
    frames = [s for s in shards if len(s) > 0]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _drop_repeated_objects(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Keep one copy of each OSM object, choosing the region deterministically."""
    before = len(frame)
    kept = (
        frame.sort_values([*_OBJECT_KEY, "region", "polygon_id"])
        .drop_duplicates(subset=_OBJECT_KEY, keep="first")
        .reset_index(drop=True)
    )
    return kept, before - len(kept)


def _drop_repeated_examples(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Collapse examples whose text and label are both identical."""
    before = len(frame)
    keys = [
        dedup_key(text, str(code))
        for text, code in zip(frame["text"], frame["worldcover_code"], strict=True)
    ]
    kept = (
        frame.assign(_key=keys)
        .sort_values(["_key", "polygon_id", "document_id"])
        .drop_duplicates(subset="_key", keep="first")
        .drop(columns="_key")
        .reset_index(drop=True)
    )
    return kept, before - len(kept)


def _assign_splits(frame: pd.DataFrame, config: Config) -> pd.DataFrame:
    """Attach an H3 cell to every row and split on the cell, never on the row."""
    ratios = SplitRatios(config.train_ratio, config.validation_ratio, config.test_ratio)
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

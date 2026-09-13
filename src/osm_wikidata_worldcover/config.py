"""Run configuration.

Every knob that changes the published data lives here and is copied into the
manifest, so a dataset can always be traced back to the settings that made it.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Self

import yaml

from osm_wikidata_worldcover.domain.dominance import DEFAULT_THRESHOLD
from osm_wikidata_worldcover.domain.splits import DEFAULT_RATIOS, DEFAULT_RESOLUTION, DEFAULT_SEED
from osm_wikidata_worldcover.domain.text import DEFAULT_MIN_WORDS

__all__ = ["DEFAULT_SOURCE_DATASET", "Config"]

DEFAULT_SOURCE_DATASET = "NoeFlandre/osm-polygon-wikidata-and-wikipedia"

#: Polygons larger than this are refused before any raster is read.
#: At 100,000 km2 a polygon already spans several 3-degree tiles; the largest
#: in the source is 10.2 million km2, which would need ~100 tiles (~10 GB) and
#: 10^11 pixels for a single row. Such polygons are countries and continents,
#: whose articles describe history and governance rather than the ground.
#: This excludes 238 of 1,259,424 polygons (0.019%).
DEFAULT_MAX_POLYGON_AREA_M2 = 1e11

#: Equal-area projection used whenever a real-world area is needed.
EQUAL_AREA_CRS = "EPSG:6933"


@dataclass(frozen=True, slots=True)
class Config:
    """Settings for one dataset build."""

    out_dir: Path = Path("data/out")
    cache_dir: Path = Path("data/cache")

    worldcover_version: str = "v200"
    worldcover_year: int = 2021

    source_dataset: str = DEFAULT_SOURCE_DATASET
    source_revision: str | None = None
    regions: tuple[str, ...] | None = None

    threshold: float = DEFAULT_THRESHOLD
    max_polygon_area_m2: float | None = DEFAULT_MAX_POLYGON_AREA_M2
    min_words: int = DEFAULT_MIN_WORDS
    h3_resolution: int = DEFAULT_RESOLUTION
    split_seed: int = DEFAULT_SEED
    train_ratio: float = DEFAULT_RATIOS.train
    validation_ratio: float = DEFAULT_RATIOS.validation
    test_ratio: float = DEFAULT_RATIOS.test

    dataset_version: str = "1.0.0"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """Load a config from ``path``, filling unset keys with defaults."""
        raw = yaml.safe_load(path.read_text()) or {}
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Self:
        """Build a config from a plain mapping, rejecting unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**_coerce(dict(raw)))

    def with_overrides(self, **over: Any) -> Self:
        """Return a copy with ``over`` applied, ignoring ``None`` values."""
        return replace(self, **{k: v for k, v in over.items() if v is not None})

    def as_manifest_settings(self) -> dict[str, Any]:
        """The subset of settings recorded in the manifest."""
        return {
            "dataset_version": self.dataset_version,
            "worldcover_version": self.worldcover_version,
            "worldcover_year": self.worldcover_year,
            "source_dataset": self.source_dataset,
            "source_revision": self.source_revision,
            "dominance_threshold": self.threshold,
            "max_polygon_area_m2": self.max_polygon_area_m2,
            "min_words": self.min_words,
            "h3_resolution": self.h3_resolution,
            "split_seed": self.split_seed,
            "split_ratios": {
                "train": self.train_ratio,
                "validation": self.validation_ratio,
                "test": self.test_ratio,
            },
            "equal_area_crs": EQUAL_AREA_CRS,
        }


def _coerce(data: dict[str, Any]) -> dict[str, Any]:
    """Turn YAML's strings and lists into the types the dataclass declares."""
    for key in ("out_dir", "cache_dir"):
        if key in data:
            data[key] = Path(data[key])
    regions = data.get("regions")
    if regions is not None:
        data["regions"] = tuple(regions)
    return data

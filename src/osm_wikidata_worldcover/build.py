"""Run a whole build: fetch each region, label it, assemble the dataset.

Regions are processed one at a time and their shards kept in memory only as
long as the build runs. Tiles are fetched and released inside each region, so
peak disk stays near a single raster even though a global run touches
thousands of them.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from osm_wikidata_worldcover.adapters import hub
from osm_wikidata_worldcover.adapters.source import RegionTables
from osm_wikidata_worldcover.adapters.worldcover import WorldCoverTiles
from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.finalize import BuildResult, finalize
from osm_wikidata_worldcover.pipeline import RegionOutcome, run_region

__all__ = ["BuildReport", "run_build"]

Progress = Callable[[str], None]


@dataclass(slots=True)
class BuildReport:
    """The outcome of a whole build."""

    result: BuildResult
    regions: list[RegionOutcome] = field(default_factory=list)

    @property
    def rejections(self) -> dict[str, int]:
        """Why polygons were refused, summed over every region."""
        total: Counter[str] = Counter()
        for region in self.regions:
            total.update(region.rejections)
        return dict(total)


def run_build(
    config: Config,
    regions: Sequence[str] | None = None,
    keep_tiles: bool = False,
    progress: Progress = lambda _: None,
) -> BuildReport:
    """Build the dataset from the configured source revision."""
    revision = config.source_revision or hub.resolve_revision(config.source_dataset)
    config = config.with_overrides(source_revision=revision)

    stems = list(
        regions or config.regions or hub.list_region_stems(config.source_dataset, revision)
    )
    tiles = WorldCoverTiles(
        Path(config.cache_dir) / "worldcover",
        version=config.worldcover_version,
        year=config.worldcover_year,
    )
    raw = Path(config.cache_dir) / "source"

    shards: list[pd.DataFrame] = []
    outcomes: list[RegionOutcome] = []
    for index, stem in enumerate(stems, start=1):
        progress(f"[{index}/{len(stems)}] {stem}")
        hub.snapshot_region(config.source_dataset, revision, stem, raw)
        tables = RegionTables.load(raw, stem)
        examples, outcome = run_region(config, tables, tiles, keep_tiles=keep_tiles)
        if len(examples):
            shards.append(examples)
        outcomes.append(outcome)
        progress(
            f"    {outcome.polygons_seen} polygons -> "
            f"{outcome.polygons_accepted} labelled -> {outcome.examples} examples"
        )

    report = BuildReport(result=finalize([], config), regions=outcomes)
    report.result = finalize(shards, config, rejections=report.rejections)
    return report

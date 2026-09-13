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

__all__ = ["BuildReport", "ShardStore", "run_build"]


class ShardStore:
    """Per-region results held on disk between the region pass and assembly.

    A global run produces more text than is comfortable to keep in memory, and
    takes long enough that it will sometimes be interrupted. Writing each
    region as it completes solves both: memory stays bounded by one region, and
    a restart skips whatever already finished.

    A region that produced no examples still writes a file. That is a finished
    result, and without it every restart would retry the empty regions forever.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, stem: str) -> Path:
        return self.directory / f"{stem}.parquet"

    def has(self, stem: str) -> bool:
        """Whether ``stem`` has already been processed to completion."""
        path = self.path_for(stem)
        return path.exists() and path.stat().st_size > 0

    def write(self, stem: str, frame: pd.DataFrame) -> None:
        """Record ``stem``'s result, atomically."""
        path = self.path_for(stem)
        partial = path.with_suffix(path.suffix + ".part")
        frame.to_parquet(partial, index=False)
        partial.rename(path)

    def read(self) -> list[pd.DataFrame]:
        """Read every non-empty shard, in a deterministic order."""
        frames = [pd.read_parquet(p) for p in sorted(self.directory.glob("*.parquet"))]
        return [f for f in frames if len(f) > 0]


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
        max_cached_tiles=config.cached_tiles,
    )
    raw = Path(config.cache_dir) / "source"

    shards = ShardStore(Path(config.cache_dir) / "shards")
    outcomes = _run_regions(config, revision, stems, raw, tiles, shards, keep_tiles, progress)

    report = BuildReport(result=finalize([], config), regions=outcomes)
    report.result = finalize(shards.read(), config, rejections=report.rejections)
    return report


def _run_regions(
    config: Config,
    revision: str,
    stems: Sequence[str],
    raw: Path,
    tiles: WorldCoverTiles,
    shards: ShardStore,
    keep_tiles: bool,
    progress: Progress,
) -> list[RegionOutcome]:
    """Process each region that has not already finished."""
    outcomes: list[RegionOutcome] = []
    for index, stem in enumerate(stems, start=1):
        done = shards.has(stem)
        # Announced as each region starts, not up front, so a long run shows
        # where it actually is.
        progress(_label(index, len(stems), stem, done=done))
        if not done:
            outcomes.append(
                _process_region(config, revision, stem, raw, tiles, shards, keep_tiles, progress)
            )
    return outcomes


def _label(index: int, total: int, stem: str, done: bool) -> str:
    """The progress line for one region."""
    suffix = " (already done)" if done else ""
    return f"[{index}/{total}] {stem}{suffix}"


def _process_region(
    config: Config,
    revision: str,
    stem: str,
    raw: Path,
    tiles: WorldCoverTiles,
    shards: ShardStore,
    keep_tiles: bool,
    progress: Progress,
) -> RegionOutcome:
    """Fetch, label and record one region."""
    hub.snapshot_region(config.source_dataset, revision, stem, raw)
    tables = RegionTables.load(raw, stem)
    examples, outcome = run_region(config, tables, tiles, keep_tiles=keep_tiles)
    shards.write(stem, examples)
    _release_source(raw, stem)
    progress(
        f"    {outcome.polygons_seen} polygons -> "
        f"{outcome.polygons_accepted} labelled -> {outcome.examples} examples"
    )
    return outcome


def _release_source(raw: Path, stem: str) -> None:
    """Delete a region's downloaded tables once its shard is written.

    The full source snapshot is ~21 GB and none of it is needed again.
    """
    for path in hub.region_files(stem):
        (raw / path).unlink(missing_ok=True)

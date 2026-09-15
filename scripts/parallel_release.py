"""Run one pinned release in isolated region workers, then assemble once."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from huggingface_hub import HfApi

from osm_worldcover.build import run_build
from osm_worldcover.config import Config
from osm_worldcover.finalize import finalize_shards

SOURCE = "description"
REVISION = "fec858b679f5ee7e87f0ecfaaa6b7223b2a7f5e2"
WORKERS = 6
ROOT = Path("data/releases/description/parallel")


def _stems() -> list[str]:
    """Read the pinned source's region stems."""
    files = HfApi().list_repo_files(
        "NoeFlandre/osm-polygon-description-tag",
        repo_type="dataset",
        revision=REVISION,
    )
    return sorted(
        Path(path).stem for path in files if path.startswith("data/") and path.endswith(".parquet")
    )


def _run_group(payload: tuple[int, list[str]]) -> tuple[int, dict[str, int]]:
    """Build one isolated group and return its rejection counters."""
    index, stems = payload
    config = Config(
        source=SOURCE,
        out_dir=ROOT / "groups" / f"group-{index}",
        cache_dir=ROOT / "cache" / f"group-{index}",
        cached_tiles=8,
        source_revision=REVISION,
        dataset_version="1.0.0",
    )
    report = run_build(
        config,
        regions=stems,
        progress=lambda message: print(f"[group {index}] {message}", flush=True),
    )
    if not report.result.report.ok:
        raise RuntimeError(f"group {index} failed validation: {report.result.report.violations}")
    return index, report.rejections


def _combine_shards(groups: int) -> Path:
    """Create one deterministic symlink view over every worker's shards."""
    combined = ROOT / "combined-shards"
    combined.mkdir(parents=True, exist_ok=True)
    for index in range(groups):
        source = ROOT / "cache" / f"group-{index}" / "shards"
        for shard in sorted(source.glob("*.parquet")):
            (combined / f"group-{index}__{shard.name}").symlink_to(shard.resolve())
    return combined


def main() -> None:
    """Build all workers and perform the single global finalization."""
    stems = _stems()
    groups = [stems[index::WORKERS] for index in range(WORKERS)]
    print(f"regions: {len(stems)}; workers: {WORKERS}", flush=True)
    rejections: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_run_group, (index, group)) for index, group in enumerate(groups)]
        for future in as_completed(futures):
            index, counters = future.result()
            print(f"[group {index}] complete", flush=True)
            for reason, count in counters.items():
                rejections[reason] = rejections.get(reason, 0) + count

    config = Config(
        source=SOURCE,
        out_dir=ROOT / "final-out",
        cache_dir=ROOT / "final-cache",
        cached_tiles=8,
        source_revision=REVISION,
        dataset_version="1.0.0",
    )
    result = finalize_shards(
        _combine_shards(WORKERS),
        config,
        ROOT / "final-cache" / "assembly",
        ROOT / "final-out",
        rejections,
    )
    if not result.report.ok:
        raise RuntimeError(f"final build failed validation: {result.report.violations}")
    print(f"final rows: {result.rows}", flush=True)
    print(f"final directory: {ROOT / 'final-out' / 'v1.0.0'}", flush=True)


if __name__ == "__main__":
    main()

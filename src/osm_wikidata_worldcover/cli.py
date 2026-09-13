"""Command line interface."""

import shutil
from pathlib import Path
from typing import Annotated

import typer

from osm_wikidata_worldcover.adapters.writer import read_manifest, write_dataset
from osm_wikidata_worldcover.build import run_build
from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.finalize import StreamedBuild, finalize_shards

app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def build(
    out: Annotated[Path, typer.Option(help="Directory to write the dataset into.")] = Path(
        "data/out"
    ),
    cache: Annotated[Path, typer.Option(help="Scratch directory for source and tiles.")] = Path(
        "data/cache"
    ),
    region: Annotated[
        list[str] | None, typer.Option(help="Region stem to build; repeatable.")
    ] = None,
    regions_file: Annotated[
        Path | None,
        typer.Option(help="File of region stems, one per line; # starts a comment."),
    ] = None,
    threshold: Annotated[float, typer.Option(help="Minimum dominant-class share.")] = 0.8,
    max_area_km2: Annotated[
        float, typer.Option(help="Refuse polygons larger than this, in km2.")
    ] = 10_000.0,
    revision: Annotated[
        str | None, typer.Option(help="Pin the source dataset to this commit.")
    ] = None,
    cached_tiles: Annotated[
        int,
        typer.Option(help="Released tiles kept on disk (~94 MB each) to avoid re-downloading."),
    ] = 8,
    keep_tiles: Annotated[
        bool, typer.Option(help="Keep downloaded tiles instead of discarding them.")
    ] = False,
    dataset_version: Annotated[str, typer.Option(help="Version of the output.")] = "1.0.0",
) -> None:
    """Build the dataset and write it to disk."""
    config = _build_config(
        out, cache, threshold, max_area_km2, cached_tiles, revision, dataset_version
    )
    regions = list(region or []) + _read_regions(regions_file)
    report = run_build(config, regions=regions or None, keep_tiles=keep_tiles, progress=typer.echo)
    _publish_locally(report.result, out, dataset_version)


def _read_regions(path: Path | None) -> list[str]:
    """Read region stems from ``path``, ignoring blanks and ``#`` comments."""
    if path is None:
        return []
    lines = (line.split("#", 1)[0].strip() for line in path.read_text().splitlines())
    return [line for line in lines if line]


@app.command()
def assemble(
    shard_dirs: Annotated[
        list[Path], typer.Argument(help="Directories of region shards to combine.")
    ],
    out: Annotated[Path, typer.Option(help="Directory to write the dataset into.")] = Path(
        "data/out"
    ),
    work: Annotated[Path, typer.Option(help="Scratch directory for assembly.")] = Path(
        "data/cache/assembly"
    ),
    threshold: Annotated[float, typer.Option(help="Minimum dominant-class share.")] = 0.8,
    revision: Annotated[str | None, typer.Option(help="Source commit to record.")] = None,
    dataset_version: Annotated[str, typer.Option(help="Version of the output.")] = "1.0.0",
) -> None:
    """Combine region shards into the published dataset.

    Separate from `build` so a run split across processes -- each producing its
    own shards -- can be assembled once, in one place.
    """
    config = Config(
        out_dir=out,
        threshold=threshold,
        source_revision=revision,
        dataset_version=dataset_version,
    )
    result = finalize_shards(_gather(shard_dirs, work), config, work)
    if result.rows == 0:
        typer.echo(f"no rows found in {[str(d) for d in shard_dirs]}", err=True)
        raise typer.Exit(1)
    _publish_locally(result, out, dataset_version)


def _build_config(
    out: Path,
    cache: Path,
    threshold: float,
    max_area_km2: float,
    cached_tiles: int,
    revision: str | None,
    dataset_version: str,
) -> Config:
    """Gather the CLI's options into one settings object."""
    return Config(
        out_dir=out,
        cache_dir=cache,
        threshold=threshold,
        max_polygon_area_m2=max_area_km2 * 1e6,
        cached_tiles=cached_tiles,
        source_revision=revision,
        dataset_version=dataset_version,
    )


def _publish_locally(result: StreamedBuild, out: Path, dataset_version: str) -> None:
    """Write a finished build and report it, failing if a guarantee broke."""
    paths = write_dataset(result.frames, result.manifest, out, dataset_version)
    typer.echo(f"\nexamples: {result.rows:,}")
    for name, count in result.manifest.get("counts", {}).get("examples", {}).items():
        typer.echo(f"  {name}: {count:,}")
    typer.echo(f"written: {paths[-1].parent}")
    if result.report.ok:
        return
    for violation in result.report.violations:
        typer.echo(f"  FAILED {violation.check.value}: {violation.count}", err=True)
    raise typer.Exit(1)


def _gather(shard_dirs: list[Path], work: Path) -> Path:
    """Link every shard into one directory, so assembly sees a single source.

    Names are prefixed with their directory, because two workers can each
    produce a shard for the same region name. The directory is emptied first so
    a previous assembly's shards cannot leak into this one.
    """
    if len(shard_dirs) == 1:
        return shard_dirs[0]
    combined = Path(work) / "shards"
    if combined.exists():
        shutil.rmtree(combined)
    combined.mkdir(parents=True)
    # The directory was just emptied, so no name can already be taken.
    for directory in shard_dirs:
        for shard in sorted(Path(directory).glob("*.parquet")):
            (combined / f"{Path(directory).name}__{shard.name}").symlink_to(shard.resolve())
    return combined


@app.command()
def verify(
    build_dir: Annotated[Path, typer.Argument(help="A versioned build directory.")],
    threshold: Annotated[float, typer.Option()] = 0.8,
) -> None:
    """Re-check a build on disk against every dataset guarantee."""
    from osm_wikidata_worldcover.domain.validation import validate

    rows = _load_splits(build_dir)
    if rows is None:
        typer.echo(f"no splits found in {build_dir}", err=True)
        raise typer.Exit(1)
    report = validate(rows, threshold=threshold)
    typer.echo(f"rows: {report.rows:,}")
    if report.ok:
        typer.echo("OK: every guarantee holds")
        return
    for violation in report.violations:
        typer.echo(f"FAILED {violation.check.value}: {violation.count} {violation.examples}")
    raise typer.Exit(1)


def _load_splits(build_dir: Path) -> list[dict] | None:
    """Read every split written under ``build_dir``, or ``None`` if there are none."""
    import pandas as pd

    frames = [
        pd.read_parquet(build_dir / f"{split}.parquet")
        for split in ("train", "validation", "test")
        if (build_dir / f"{split}.parquet").exists()
    ]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True).to_dict("records")


@app.command()
def publish(
    build_dir: Annotated[Path, typer.Argument(help="A versioned build directory.")],
    repo_id: Annotated[str, typer.Argument(help="Target dataset repo, e.g. user/name.")],
    private: Annotated[bool, typer.Option(help="Create the dataset private.")] = False,
) -> None:
    """Upload a build to the Hugging Face Hub with a generated dataset card."""
    from osm_wikidata_worldcover.adapters.publish import publish_dataset

    url = publish_dataset(build_dir, repo_id, private=private)
    typer.echo(f"published: {url}")


@app.command()
def info(build_dir: Annotated[Path, typer.Argument(help="A versioned build directory.")]) -> None:
    """Summarise a build's manifest."""
    manifest = read_manifest(build_dir)
    counts = manifest["counts"]["examples"]
    typer.echo(
        f"examples: {counts['total']:,}  "
        f"(train {counts['train']:,} / val {counts['validation']:,} / test {counts['test']:,})"
    )
    typer.echo("\nclasses:")
    for entry in manifest["class_distribution"]:
        typer.echo(
            f"  {entry['code']:>3} {entry['label']:<26} {entry['examples']:>9,}  "
            f"{entry['share'] * 100:5.1f}%"
        )
    typer.echo("\ntop languages:")
    for entry in manifest["language_distribution"][:10]:
        typer.echo(
            f"  {entry['language']:<6} {entry['examples']:>9,}  {entry['share'] * 100:5.1f}%"
        )


if __name__ == "__main__":
    app()

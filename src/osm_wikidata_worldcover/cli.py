"""Command line interface."""

from pathlib import Path
from typing import Annotated

import typer

from osm_wikidata_worldcover.adapters.writer import read_manifest, write_dataset
from osm_wikidata_worldcover.build import run_build
from osm_wikidata_worldcover.config import Config

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
    threshold: Annotated[float, typer.Option(help="Minimum dominant-class share.")] = 0.8,
    max_area_km2: Annotated[
        float, typer.Option(help="Refuse polygons larger than this, in km2.")
    ] = 100_000.0,
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
    config = Config(
        out_dir=out,
        cache_dir=cache,
        threshold=threshold,
        max_polygon_area_m2=max_area_km2 * 1e6,
        cached_tiles=cached_tiles,
        source_revision=revision,
        dataset_version=dataset_version,
    )
    report = run_build(config, regions=region, keep_tiles=keep_tiles, progress=typer.echo)
    paths = write_dataset(report.result.frame, report.result.manifest, out, dataset_version)

    typer.echo(f"\nexamples: {len(report.result.frame):,}")
    for name, count in report.result.manifest.get("counts", {}).get("examples", {}).items():
        typer.echo(f"  {name}: {count:,}")
    typer.echo(f"written: {paths[-1].parent}")
    if not report.result.report.ok:
        for violation in report.result.report.violations:
            typer.echo(f"  FAILED {violation.check.value}: {violation.count}", err=True)
        raise typer.Exit(1)


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

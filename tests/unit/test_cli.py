"""Command line behaviour."""

import json

import pandas as pd
from typer.testing import CliRunner

from osm_wikidata_worldcover import cli
from osm_wikidata_worldcover.domain.validation import Check, ValidationReport, Violation
from osm_wikidata_worldcover.finalize import StreamedBuild

runner = CliRunner()

MANIFEST = {
    "counts": {"examples": {"train": 2, "validation": 1, "test": 1, "total": 4}},
    "class_distribution": [
        {"code": 10, "label": "Tree cover", "examples": 3, "share": 0.75},
        {"code": 50, "label": "Built-up", "examples": 1, "share": 0.25},
    ],
    "language_distribution": [{"language": "en", "examples": 4, "share": 1.0}],
}


def split_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        name: frame[frame["split"] == name].reset_index(drop=True)
        for name in ("train", "validation", "test")
    }


def frame(n: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "polygon_id": [f"p{i}" for i in range(n)],
            "document_id": [f"d{i}" for i in range(n)],
            # Distinct text per row: identical text under one label is a
            # duplicate, which verify is right to reject.
            "text": [" ".join(["word"] * 20) + f" {i}" for i in range(n)],
            "worldcover_code": [10] * n,
            "worldcover_label": ["Tree cover"] * n,
            "dominant_fraction": [0.95] * n,
            "split": ["train", "train", "validation", "test"][:n],
        }
    )


def test_build_writes_a_dataset_and_reports_counts(tmp_path, monkeypatch) -> None:
    result = StreamedBuild(4, split_frames(frame()), MANIFEST, ValidationReport(4))
    monkeypatch.setattr(cli, "run_build", lambda *a, **k: type("R", (), {"result": result})())
    outcome = runner.invoke(cli.app, ["build", "--out", str(tmp_path), "--cache", str(tmp_path)])
    assert outcome.exit_code == 0, outcome.output
    assert "examples: 4" in outcome.output
    assert (tmp_path / "v1.0.0" / "train.parquet").exists()


def test_build_fails_when_a_guarantee_is_broken(tmp_path, monkeypatch) -> None:
    report = ValidationReport(4, [Violation(Check.POLYGON_LEAKAGE, 2, ("p1",))])
    result = StreamedBuild(4, split_frames(frame()), MANIFEST, report)
    monkeypatch.setattr(cli, "run_build", lambda *a, **k: type("R", (), {"result": result})())
    outcome = runner.invoke(cli.app, ["build", "--out", str(tmp_path), "--cache", str(tmp_path)])
    assert outcome.exit_code == 1
    assert "polygon_leakage" in outcome.output


def test_verify_accepts_a_sound_build(tmp_path) -> None:
    build = tmp_path / "v1.0.0"
    build.mkdir(parents=True)
    for split in ("train", "validation", "test"):
        frame()[frame()["split"] == split].to_parquet(build / f"{split}.parquet", index=False)
    outcome = runner.invoke(cli.app, ["verify", str(build)])
    assert outcome.exit_code == 0
    assert "every guarantee holds" in outcome.output


def test_verify_rejects_a_build_that_breaks_a_guarantee(tmp_path) -> None:
    build = tmp_path / "v1.0.0"
    build.mkdir(parents=True)
    bad = frame(2)
    bad.loc[:, "dominant_fraction"] = 0.4
    bad.to_parquet(build / "train.parquet", index=False)
    outcome = runner.invoke(cli.app, ["verify", str(build)])
    assert outcome.exit_code == 1
    assert "below_threshold" in outcome.output


def test_verify_refuses_a_directory_with_no_splits(tmp_path) -> None:
    outcome = runner.invoke(cli.app, ["verify", str(tmp_path)])
    assert outcome.exit_code == 1
    assert "no splits" in outcome.output


def test_info_summarises_a_manifest(tmp_path) -> None:
    build = tmp_path / "v1.0.0"
    build.mkdir(parents=True)
    (build / "manifest.json").write_text(json.dumps(MANIFEST))
    outcome = runner.invoke(cli.app, ["info", str(build)])
    assert outcome.exit_code == 0
    assert "Tree cover" in outcome.output
    assert "examples: 4" in outcome.output

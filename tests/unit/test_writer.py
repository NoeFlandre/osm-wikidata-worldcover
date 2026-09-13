"""Writing a build to disk."""

import json

import pandas as pd
import pytest

from osm_wikidata_worldcover.adapters.writer import read_manifest, write_dataset


def result(n: int = 3) -> tuple[pd.DataFrame, dict]:
    frame = pd.DataFrame(
        {
            "polygon_id": [f"p{i}" for i in range(n)],
            "document_id": [f"d{i}" for i in range(n)],
            "text": ["t"] * n,
            "worldcover_code": [10] * n,
            "split": ["train", "validation", "test"][:n] + ["train"] * max(0, n - 3),
        }
    )
    return frame, {"counts": {"examples": {"total": n}}}


def test_each_split_is_written_as_its_own_parquet(tmp_path) -> None:
    paths = write_dataset(*result(), tmp_path, "1.0.0")
    for split in ("train", "validation", "test"):
        assert (tmp_path / "v1.0.0" / f"{split}.parquet").exists()
    assert all(p.exists() for p in paths)


def test_written_rows_round_trip(tmp_path) -> None:
    write_dataset(*result(), tmp_path, "1.0.0")
    train = pd.read_parquet(tmp_path / "v1.0.0" / "train.parquet")
    assert train["split"].tolist() == ["train"]


def test_manifest_is_written_and_readable(tmp_path) -> None:
    write_dataset(*result(), tmp_path, "1.0.0")
    manifest = read_manifest(tmp_path / "v1.0.0")
    assert manifest["counts"]["examples"]["total"] == 3


def test_manifest_is_written_as_readable_json(tmp_path) -> None:
    write_dataset(*result(), tmp_path, "1.0.0")
    text = (tmp_path / "v1.0.0" / "manifest.json").read_text()
    assert text.endswith("\n")
    assert json.loads(text)["counts"]["examples"]["total"] == 3


def test_versions_are_written_side_by_side(tmp_path) -> None:
    write_dataset(*result(), tmp_path, "1.0.0")
    write_dataset(*result(2), tmp_path, "1.1.0")
    assert (tmp_path / "v1.0.0" / "manifest.json").exists()
    assert (tmp_path / "v1.1.0" / "manifest.json").exists()


def test_writing_twice_is_byte_identical(tmp_path) -> None:
    """A rebuild of the same data must not produce a different file."""
    a = write_dataset(*result(), tmp_path / "a", "1.0.0")
    b = write_dataset(*result(), tmp_path / "b", "1.0.0")
    for left, right in zip(a, b, strict=True):
        assert left.read_bytes() == right.read_bytes()


def test_an_empty_split_still_produces_a_file(tmp_path) -> None:
    write_dataset(*result(1), tmp_path, "1.0.0")
    assert (tmp_path / "v1.0.0" / "test.parquet").exists()
    assert len(pd.read_parquet(tmp_path / "v1.0.0" / "test.parquet")) == 0


def test_read_manifest_rejects_a_missing_build(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        read_manifest(tmp_path / "nope")

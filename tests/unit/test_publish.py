"""Publishing a build to the Hub."""

import json
from pathlib import Path

import pandas as pd
import pytest

from osm_wikidata_worldcover.adapters.publish import files_to_publish, publish_dataset

MANIFEST = {
    "counts": {
        "examples": {"train": 1, "validation": 0, "test": 0, "total": 1},
        "polygons": {"train": 1, "validation": 0, "test": 0, "total": 1},
        "documents": {"train": 1, "validation": 0, "test": 0, "total": 1},
    },
    "class_distribution": [{"code": 10, "label": "Tree cover", "examples": 1, "share": 1.0}],
    "language_distribution": [{"language": "en", "examples": 1, "share": 1.0}],
    "settings": {"dominance_threshold": 0.8},
}


@pytest.fixture
def build(tmp_path: Path) -> Path:
    target = tmp_path / "v1.0.0"
    target.mkdir()
    for split in ("train", "validation", "test"):
        pd.DataFrame({"polygon_id": ["p"], "text": ["t"]}).to_parquet(
            target / f"{split}.parquet", index=False
        )
    (target / "manifest.json").write_text(json.dumps(MANIFEST))
    return target


def test_every_split_and_the_manifest_are_published(build) -> None:
    names = {path.name for path in files_to_publish(build)}
    assert names == {"train.parquet", "validation.parquet", "test.parquet", "manifest.json"}


def test_a_build_without_splits_is_refused(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        files_to_publish(tmp_path)


def test_publish_writes_a_card_and_uploads_every_file(build, monkeypatch) -> None:
    uploaded: dict[str, object] = {}

    class FakeApi:
        def __init__(self, token=None):
            uploaded["token"] = token

        def create_repo(self, repo_id, **kwargs):
            uploaded["repo"] = repo_id
            uploaded["private"] = kwargs.get("private")

        def upload_folder(self, **kwargs):
            uploaded["folder"] = kwargs["folder_path"]
            uploaded["repo_type"] = kwargs["repo_type"]

    monkeypatch.setattr("osm_wikidata_worldcover.adapters.publish.HfApi", FakeApi)
    url = publish_dataset(build, "someone/thing")

    assert uploaded["repo"] == "someone/thing"
    assert uploaded["repo_type"] == "dataset"
    assert (build / "README.md").exists()
    assert "Tree cover" in (build / "README.md").read_text()
    assert url.endswith("someone/thing")


def test_publish_defaults_to_a_public_dataset(build, monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeApi:
        def __init__(self, token=None):
            seen["token"] = token

        def create_repo(self, repo_id, **kwargs):
            seen["private"] = kwargs.get("private")

        def upload_folder(self, **kwargs):
            return None

    monkeypatch.setattr("osm_wikidata_worldcover.adapters.publish.HfApi", FakeApi)
    publish_dataset(build, "someone/thing")
    assert seen["private"] is False

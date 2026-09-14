"""Repository access, without touching the network."""

from pathlib import Path

import pytest

from osm_worldcover.adapters import hub


class FakeInfo:
    def __init__(self, sha):
        self.sha = sha


def test_resolve_revision_returns_the_commit(monkeypatch) -> None:
    monkeypatch.setattr(
        hub, "HfApi", lambda: type("A", (), {"dataset_info": lambda *a, **k: FakeInfo("abc")})()
    )
    assert hub.resolve_revision("repo") == "abc"


def test_resolve_revision_refuses_a_repository_without_a_commit(monkeypatch) -> None:
    monkeypatch.setattr(
        hub, "HfApi", lambda: type("A", (), {"dataset_info": lambda *a, **k: FakeInfo(None)})()
    )
    with pytest.raises(ValueError, match="no commit"):
        hub.resolve_revision("repo")


def test_list_region_stems_keeps_only_polygon_tables(monkeypatch) -> None:
    files = [
        "polygons/beta-latest.parquet",
        "polygons/alpha-latest.parquet",
        "wikipedia/documents/alpha-latest.parquet",
        "README.md",
    ]
    monkeypatch.setattr(
        hub, "HfApi", lambda: type("A", (), {"list_repo_files": lambda *a, **k: files})()
    )
    assert hub.list_region_stems("repo", "rev") == ["alpha-latest", "beta-latest"]


def test_list_region_stems_follows_the_description_data_prefix(monkeypatch) -> None:
    files = [
        "data/beta-latest.parquet",
        "data/alpha-latest.parquet",
        "language-v1/data/alpha-latest.parquet",
        "README.md",
    ]
    monkeypatch.setattr(
        hub, "HfApi", lambda: type("A", (), {"list_repo_files": lambda *a, **k: files})()
    )
    assert hub.list_region_stems("repo", "rev", source="description") == [
        "alpha-latest",
        "beta-latest",
    ]


def test_snapshot_region_downloads_every_table(tmp_path, monkeypatch) -> None:
    calls = []

    def fake_download(repo_id, path, **kwargs):
        calls.append(path)
        target = Path(kwargs["local_dir"]) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return str(target)

    monkeypatch.setattr(hub, "hf_hub_download", fake_download)
    paths = hub.snapshot_region("repo", "rev", "alpha-latest", tmp_path)
    assert len(paths) == 4
    assert calls == hub.region_files("alpha-latest")


def test_snapshot_region_skips_tables_the_repository_omits(tmp_path, monkeypatch) -> None:
    """Wikivoyage sidecars do not exist for every region; that is not a failure."""

    def fake_download(repo_id, path, **kwargs):
        if "wikivoyage" in path:
            raise hub.EntryNotFoundError("absent")
        target = Path(kwargs["local_dir"]) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return str(target)

    monkeypatch.setattr(hub, "hf_hub_download", fake_download)
    assert len(hub.snapshot_region("repo", "rev", "alpha-latest", tmp_path)) == 3

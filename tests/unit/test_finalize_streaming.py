"""Assembly must not depend on the whole dataset fitting in memory.

At ~4.9 KB per row a global build is roughly 10 GB of DataFrame, so the final
pass reads shards one at a time and does the global work in DuckDB over files.
"""

import pandas as pd
import pytest

from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.finalize import finalize_shards

TEXT = " ".join(["word"] * 30)


def shard(path, n=1, start=0, region="luxembourg", code=10, text=None):
    pd.DataFrame(
        {
            "polygon_id": [f"{region}-latest:way:{i}" for i in range(start, start + n)],
            "osm_type": ["way"] * n,
            "osm_id": list(range(start, start + n)),
            "region": [region] * n,
            "name": ["N"] * n,
            "wikidata": ["Q1"] * n,
            "document_id": [f"d{i}" for i in range(start, start + n)],
            "project": ["wikipedia"] * n,
            "language": ["en"] * n,
            "title": ["T"] * n,
            "url": ["u"] * n,
            "text": [text or f"{TEXT} {i}" for i in range(start, start + n)],
            "lead_text": ["lead"] * n,
            "text_words": [31] * n,
            "worldcover_code": [code] * n,
            "worldcover_label": ["Tree cover" if code == 10 else "Built-up"] * n,
            "dominant_fraction": [0.95] * n,
            "observed_fraction": [1.0] * n,
            "lat": [49.6] * n,
            "lon": [6.1] * n,
            "centroid_wkt": ["POINT (6.1 49.6)"] * n,
            "polygon_area_m2": [1000.0] * n,
            "source_pbf": [f"{region}-latest.osm.pbf"] * n,
        }
    ).to_parquet(path, index=False)


@pytest.fixture
def shards(tmp_path):
    d = tmp_path / "shards"
    d.mkdir()
    return d


def test_a_single_shard_becomes_a_dataset(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=3)
    result = finalize_shards(shards, Config(), tmp_path / "work")
    assert result.rows == 3
    assert set(result.frames) == {"train", "validation", "test"}


def test_every_row_gets_a_cell_and_a_split(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=3)
    result = finalize_shards(shards, Config(), tmp_path / "work")
    all_rows = pd.concat(result.frames.values())
    assert all_rows["split"].isin(["train", "validation", "test"]).all()
    assert all_rows["h3_cell"].str.len().gt(0).all()


def test_the_same_object_from_two_regions_is_kept_once(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=1, region="luxembourg")
    shard(shards / "b.parquet", n=1, region="belgium")
    result = finalize_shards(shards, Config(), tmp_path / "work")
    assert result.rows == 1
    assert result.duplicates_across_regions == 1


def test_cross_region_dedup_is_deterministic(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=1, region="luxembourg")
    shard(shards / "b.parquet", n=1, region="belgium")
    first = finalize_shards(shards, Config(), tmp_path / "w1")
    second = finalize_shards(shards, Config(), tmp_path / "w2")
    kept = pd.concat(first.frames.values())["region"].tolist()
    assert kept == pd.concat(second.frames.values())["region"].tolist()
    assert kept == ["belgium"]


def test_identical_text_and_label_collapses(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=1, start=0, text="same text here " * 5)
    shard(shards / "b.parquet", n=1, start=9, text="same text here " * 5)
    result = finalize_shards(shards, Config(), tmp_path / "work")
    assert result.rows == 1
    assert result.duplicate_examples == 1


def test_identical_text_under_different_labels_is_kept(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=1, start=0, text="same text here " * 5, code=10)
    shard(shards / "b.parquet", n=1, start=9, text="same text here " * 5, code=50)
    assert finalize_shards(shards, Config(), tmp_path / "work").rows == 2


def test_the_result_validates(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=5)
    assert finalize_shards(shards, Config(), tmp_path / "work").report.ok


def test_manifest_counts_match_the_rows(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=7)
    result = finalize_shards(shards, Config(), tmp_path / "work")
    assert result.manifest["counts"]["examples"]["total"] == result.rows


def test_provenance_is_attached(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=1)
    result = finalize_shards(shards, Config(source_revision="abc"), tmp_path / "work")
    row = pd.concat(result.frames.values()).iloc[0]
    assert row["source_revision"] == "abc"
    assert row["worldcover_version"] == "v200"


def test_output_is_sorted_deterministically(shards, tmp_path) -> None:
    shard(shards / "a.parquet", n=6)
    a = finalize_shards(shards, Config(), tmp_path / "w1")
    b = finalize_shards(shards, Config(), tmp_path / "w2")
    for split in a.frames:
        assert a.frames[split]["polygon_id"].tolist() == b.frames[split]["polygon_id"].tolist()


def test_an_empty_shard_directory_is_reported(shards, tmp_path) -> None:
    result = finalize_shards(shards, Config(), tmp_path / "work")
    assert result.rows == 0
    assert not result.report.ok


def test_empty_shards_are_ignored(shards, tmp_path) -> None:
    pd.DataFrame().to_parquet(shards / "empty.parquet", index=False)
    shard(shards / "a.parquet", n=2)
    assert finalize_shards(shards, Config(), tmp_path / "work").rows == 2


def test_shards_are_never_all_held_in_memory(shards, tmp_path, monkeypatch) -> None:
    """Guard the property that matters: one shard is read at a time."""
    import osm_wikidata_worldcover.finalize as module

    live = 0
    peak = 0
    original = pd.read_parquet

    def counting_read(*args, **kwargs):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        frame = original(*args, **kwargs)
        live -= 1
        return frame

    monkeypatch.setattr(module.pd, "read_parquet", counting_read)
    for i in range(5):
        shard(shards / f"s{i}.parquet", n=2, start=i * 10)
    finalize_shards(shards, Config(), tmp_path / "work")
    assert peak == 1

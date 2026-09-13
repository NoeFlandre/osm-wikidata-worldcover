"""Global assembly: cross-region dedup, splitting, validation and manifest."""

import pandas as pd

from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.finalize import finalize

TEXT = " ".join(["word"] * 30)


def shard(**over) -> pd.DataFrame:
    base = {
        "polygon_id": ["luxembourg-latest:way:1"],
        "osm_type": ["way"],
        "osm_id": [1],
        "region": ["luxembourg"],
        "name": ["N"],
        "wikidata": ["Q1"],
        "document_id": ["d1"],
        "project": ["wikipedia"],
        "language": ["en"],
        "title": ["T"],
        "url": ["u"],
        "text": [TEXT],
        "lead_text": ["lead"],
        "text_words": [30],
        "worldcover_code": [10],
        "worldcover_label": ["Tree cover"],
        "dominant_fraction": [0.95],
        "observed_fraction": [1.0],
        "lat": [49.6],
        "lon": [6.1],
        "centroid_wkt": ["POINT (6.1 49.6)"],
        "polygon_area_m2": [1000.0],
        "source_pbf": ["luxembourg-latest.osm.pbf"],
    }
    return pd.DataFrame(base | over)


def test_every_row_gets_a_cell_and_a_split() -> None:
    result = finalize([shard()], Config())
    assert result.frame["split"].isin(["train", "validation", "test"]).all()
    assert result.frame["h3_cell"].str.len().gt(0).all()


def test_the_same_osm_object_from_two_regions_is_kept_once() -> None:
    a = shard()
    b = shard(polygon_id=["belgium-latest:way:1"], region=["belgium"])
    result = finalize([a, b], Config())
    assert len(result.frame) == 1
    assert result.duplicates_across_regions == 1


def test_cross_region_dedup_keeps_a_deterministic_region() -> None:
    a = shard()
    b = shard(polygon_id=["belgium-latest:way:1"], region=["belgium"])
    assert finalize([a, b], Config()).frame["region"].iloc[0] == "belgium"
    assert finalize([b, a], Config()).frame["region"].iloc[0] == "belgium"


def test_exact_duplicate_text_and_label_is_removed() -> None:
    a = shard()
    b = shard(polygon_id=["x:way:2"], osm_id=[2], document_id=["d2"])
    result = finalize([a, b], Config())
    assert len(result.frame) == 1
    assert result.duplicate_examples == 1


def test_same_text_under_a_different_label_is_kept() -> None:
    a = shard()
    b = shard(
        polygon_id=["x:way:2"],
        osm_id=[2],
        document_id=["d2"],
        worldcover_code=[50],
        worldcover_label=["Built-up"],
    )
    assert len(finalize([a, b], Config()).frame) == 2


def test_nearby_polygons_land_in_the_same_split() -> None:
    a = shard()
    b = shard(
        polygon_id=["x:way:2"],
        osm_id=[2],
        document_id=["d2"],
        lat=[49.601],
        lon=[6.101],
        text=[TEXT + " more"],
    )
    frame = finalize([a, b], Config()).frame
    assert frame["split"].nunique() == 1


def test_the_result_validates() -> None:
    assert finalize([shard()], Config()).report.ok


def test_output_is_sorted_deterministically() -> None:
    rows = [
        shard(polygon_id=[f"x:way:{i}"], osm_id=[i], document_id=[f"d{i}"], text=[f"{TEXT} {i}"])
        for i in range(5)
    ]
    first = finalize(rows, Config()).frame["polygon_id"].tolist()
    second = finalize(list(reversed(rows)), Config()).frame["polygon_id"].tolist()
    assert first == second == sorted(first)


def test_manifest_counts_match_the_frame() -> None:
    result = finalize([shard()], Config())
    assert result.manifest["counts"]["examples"]["total"] == len(result.frame)


def test_manifest_records_the_settings() -> None:
    config = Config(source_revision="abc123", threshold=0.9)
    manifest = finalize([shard(dominant_fraction=[0.95])], config).manifest
    assert manifest["settings"]["source_revision"] == "abc123"
    assert manifest["settings"]["dominance_threshold"] == 0.9


def test_provenance_columns_are_attached() -> None:
    config = Config(source_revision="abc123")
    row = finalize([shard()], config).frame.iloc[0]
    assert row["source_revision"] == "abc123"
    assert row["worldcover_version"] == "v200"


def test_an_empty_build_is_reported_rather_than_crashing() -> None:
    result = finalize([], Config())
    assert len(result.frame) == 0
    assert not result.report.ok


def test_rows_below_the_threshold_are_refused_by_validation() -> None:
    result = finalize([shard(dominant_fraction=[0.5])], Config())
    assert not result.report.ok

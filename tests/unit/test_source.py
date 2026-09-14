"""Reading the source dataset's tables from a local snapshot."""

import pandas as pd
import pytest

from osm_worldcover.adapters.source import (
    RegionTables,
    load_documents,
    load_links,
    load_polygons,
    region_stems,
)


@pytest.fixture
def snapshot(tmp_path):
    """A miniature copy of the source repository's on-disk layout."""
    (tmp_path / "polygons").mkdir()
    (tmp_path / "polygon_document_links").mkdir()
    (tmp_path / "wikipedia" / "documents").mkdir(parents=True)
    (tmp_path / "wikivoyage" / "documents").mkdir(parents=True)

    pd.DataFrame(
        {
            "polygon_id": ["r:1", "r:2"],
            "lat": [49.6, 49.7],
            "lon": [6.1, 6.2],
            "geometry": ['{"type":"Point","coordinates":[6.1,49.6]}'] * 2,
            "area_m2": [100.0, 200.0],
        }
    ).to_parquet(tmp_path / "polygons" / "luxembourg-latest.parquet")
    pd.DataFrame(
        {"polygon_id": ["r:1"], "document_id": ["d1"], "project": ["wikipedia"], "language": ["en"]}
    ).to_parquet(tmp_path / "polygon_document_links" / "luxembourg-latest.parquet")
    pd.DataFrame(
        {
            "document_id": ["d1"],
            "full_text": ["hello"],
            "fetch_status": ["ok"],
            "language": ["en"],
            "title": ["T"],
            "url": ["u"],
            "lead_text": ["l"],
        }
    ).to_parquet(tmp_path / "wikipedia" / "documents" / "luxembourg-latest.parquet")
    return tmp_path


def test_region_stems_are_discovered_and_sorted(snapshot) -> None:
    (snapshot / "polygons" / "andorra-latest.parquet").write_bytes(
        (snapshot / "polygons" / "luxembourg-latest.parquet").read_bytes()
    )
    assert region_stems(snapshot) == ["andorra-latest", "luxembourg-latest"]


def test_region_stems_ignores_non_parquet_files(snapshot) -> None:
    (snapshot / "polygons" / "notes.txt").write_text("ignore me")
    assert region_stems(snapshot) == ["luxembourg-latest"]


def test_polygons_are_loaded_with_their_columns(snapshot) -> None:
    frame = load_polygons(snapshot, "luxembourg-latest")
    assert list(frame.polygon_id) == ["r:1", "r:2"]
    assert "geometry" in frame.columns


def test_links_are_loaded(snapshot) -> None:
    assert list(load_links(snapshot, "luxembourg-latest").document_id) == ["d1"]


def test_documents_are_loaded_for_a_project(snapshot) -> None:
    assert list(load_documents(snapshot, "luxembourg-latest", "wikipedia").full_text) == ["hello"]


def test_a_missing_project_file_yields_an_empty_frame_not_an_error(snapshot) -> None:
    """Wikivoyage sidecars do not exist for every region; that is normal."""
    frame = load_documents(snapshot, "luxembourg-latest", "wikivoyage")
    assert len(frame) == 0
    assert "full_text" in frame.columns


def test_region_tables_bundles_the_three_reads(snapshot) -> None:
    tables = RegionTables.load(snapshot, "luxembourg-latest")
    assert len(tables.polygons) == 2
    assert len(tables.links) == 1
    assert len(tables.documents) == 1


def test_region_tables_concatenates_both_projects(snapshot) -> None:
    pd.DataFrame(
        {
            "document_id": ["d2"],
            "full_text": ["voyage"],
            "fetch_status": ["ok"],
            "language": ["fr"],
            "title": ["V"],
            "url": ["u2"],
            "lead_text": ["l2"],
        }
    ).to_parquet(snapshot / "wikivoyage" / "documents" / "luxembourg-latest.parquet")
    tables = RegionTables.load(snapshot, "luxembourg-latest")
    assert set(tables.documents.document_id) == {"d1", "d2"}
    assert set(tables.documents.project) == {"wikipedia", "wikivoyage"}

"""Addressing files in the source repository."""

import pytest

from osm_wikidata_worldcover.adapters.hub import region_files, split_repo_path


def test_region_files_lists_every_table_for_a_region() -> None:
    assert region_files("luxembourg-latest") == [
        "polygons/luxembourg-latest.parquet",
        "polygon_document_links/luxembourg-latest.parquet",
        "wikipedia/documents/luxembourg-latest.parquet",
        "wikivoyage/documents/luxembourg-latest.parquet",
    ]


def test_region_files_is_deterministic() -> None:
    assert region_files("a") == region_files("a")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("polygons/a.parquet", ("polygons", "a")),
        ("wikipedia/documents/a-latest.parquet", ("wikipedia/documents", "a-latest")),
    ],
)
def test_split_repo_path_separates_table_from_region(path, expected) -> None:
    assert split_repo_path(path) == expected

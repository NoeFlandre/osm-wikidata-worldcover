"""Dataset card rendering."""

import pytest

from osm_wikidata_worldcover.domain.card import render

MANIFEST = {
    "counts": {
        "examples": {"train": 800, "validation": 100, "test": 100, "total": 1000},
        "polygons": {"train": 400, "validation": 50, "test": 50, "total": 500},
        "documents": {"train": 700, "validation": 90, "test": 90, "total": 880},
    },
    "class_distribution": [
        {"code": 10, "label": "Tree cover", "examples": 600, "share": 0.6},
        {"code": 50, "label": "Built-up", "examples": 400, "share": 0.4},
    ],
    "language_distribution": [
        {"language": "en", "examples": 700, "share": 0.7},
        {"language": "fr", "examples": 300, "share": 0.3},
    ],
    "dominant_fraction": {"p50": 0.97, "p90": 1.0, "p99": 1.0},
    "geographic_coverage": {
        "h3_cells": 120,
        "regions": 8,
        "bbox": {"min_lon": -9.0, "min_lat": 36.0, "max_lon": 31.0, "max_lat": 71.0},
    },
    "rejections": {"below_threshold": 50, "too_large": 3},
    "settings": {
        "dominance_threshold": 0.8,
        "source_dataset": "NoeFlandre/osm-polygon-wikidata-and-wikipedia",
        "source_revision": "abc123",
        "worldcover_version": "v200",
        "worldcover_year": 2021,
        "split_seed": 20180101,
        "h3_resolution": 5,
        "max_polygon_area_m2": 1e10,
        "min_words": 10,
    },
}


def card() -> str:
    return render(MANIFEST)


def test_card_starts_with_yaml_front_matter() -> None:
    assert card().startswith("---\n")
    assert "license:" in card().split("---")[1]


def test_front_matter_declares_the_three_splits() -> None:
    front = card().split("---")[1]
    for split in ("train", "validation", "test"):
        assert split in front


def test_card_reports_the_totals() -> None:
    assert "1,000" in card()


def test_card_embeds_the_centroid_coverage_map() -> None:
    text = card()
    assert "worldcover_centroids.png" in text
    assert "500 distinct polygons" in text
    assert "polygon centroid" in text


def test_card_lists_every_class_with_its_share() -> None:
    text = card()
    assert "Tree cover" in text
    assert "Built-up" in text
    assert "60.0%" in text


def test_card_names_the_source_and_pinned_revision() -> None:
    text = card()
    assert "NoeFlandre/osm-polygon-wikidata-and-wikipedia" in text
    assert "abc123" in text


def test_card_states_the_dominance_threshold() -> None:
    assert "80" in card()


def test_card_warns_that_the_label_describes_the_place_not_the_feature() -> None:
    """The most important caveat must not be buried or omitted."""
    assert "containing" in card()


def test_card_documents_the_leakage_guarantees() -> None:
    text = card().lower()
    assert "leak" in text or "split" in text


def test_card_is_deterministic() -> None:
    assert render(MANIFEST) == render(MANIFEST)


def test_card_handles_an_empty_class_distribution() -> None:
    manifest = {**MANIFEST, "class_distribution": []}
    assert render(manifest)


def test_card_requires_a_manifest_with_counts() -> None:
    with pytest.raises(KeyError):
        render({})

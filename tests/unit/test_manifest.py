"""Manifest assembly."""

import json

import pytest

from osm_wikidata_worldcover.domain.manifest import DatasetCounts, GeographicCoverage, build


@pytest.fixture
def counts() -> DatasetCounts:
    return DatasetCounts(
        examples={"train": 80, "validation": 10, "test": 10},
        polygons={"train": 40, "validation": 5, "test": 5},
        documents={"train": 70, "validation": 9, "test": 9},
        class_distribution={10: 60, 50: 40},
        language_distribution={"en": 70, "fr": 30},
        dominant_fraction_quantiles={"p50": 0.97, "p90": 1.0},
        coverage=GeographicCoverage(h3_cells=12, bbox=(-9.0, 36.0, 31.0, 71.0), regions=3),
    )


def test_manifest_reports_totals(counts) -> None:
    manifest = build(counts, settings={"dominance_threshold": 0.8})
    assert manifest["counts"]["examples"]["total"] == 100
    assert manifest["counts"]["examples"]["train"] == 80


def test_manifest_carries_the_settings_verbatim(counts) -> None:
    manifest = build(counts, settings={"dominance_threshold": 0.8, "split_seed": 1})
    assert manifest["settings"]["dominance_threshold"] == 0.8
    assert manifest["settings"]["split_seed"] == 1


def test_class_distribution_is_labelled_and_ordered_by_code(counts) -> None:
    classes = build(counts, settings={})["class_distribution"]
    assert [c["code"] for c in classes] == [10, 50]
    assert classes[0]["label"] == "Tree cover"
    assert classes[0]["examples"] == 60
    assert classes[0]["share"] == pytest.approx(0.6)


def test_language_distribution_is_ordered_by_count_then_name(counts) -> None:
    counts.language_distribution = {"de": 30, "fr": 30, "en": 70}
    languages = build(counts, settings={})["language_distribution"]
    assert [entry["language"] for entry in languages] == ["en", "de", "fr"]


def test_geographic_coverage_is_reported(counts) -> None:
    coverage = build(counts, settings={})["geographic_coverage"]
    assert coverage["h3_cells"] == 12
    assert coverage["regions"] == 3
    assert coverage["bbox"] == {"min_lon": -9.0, "min_lat": 36.0, "max_lon": 31.0, "max_lat": 71.0}


def test_manifest_is_json_serialisable(counts) -> None:
    json.dumps(build(counts, settings={"dominance_threshold": 0.8}))


def test_manifest_is_deterministic(counts) -> None:
    a = json.dumps(build(counts, settings={"x": 1}))
    b = json.dumps(build(counts, settings={"x": 1}))
    assert a == b


def test_an_unknown_class_code_is_refused(counts) -> None:
    counts.class_distribution = {999: 1}
    with pytest.raises(KeyError):
        build(counts, settings={})


def test_empty_dataset_reports_zero_without_dividing_by_zero(counts) -> None:
    counts.examples = {"train": 0, "validation": 0, "test": 0}
    counts.class_distribution = {}
    manifest = build(counts, settings={})
    assert manifest["counts"]["examples"]["total"] == 0
    assert manifest["class_distribution"] == []

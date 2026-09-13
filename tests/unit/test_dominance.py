"""Dominant-class decision over per-class intersected areas."""

import pytest

from osm_wikidata_worldcover.domain.dominance import (
    DEFAULT_THRESHOLD,
    OverlappingCoverageError,
    RejectionReason,
    class_fractions,
    decide,
)


def test_fractions_are_relative_to_the_polygon_area_not_the_covered_area() -> None:
    # Half the polygon is not covered by CORINE at all; the covered half is one class.
    fractions = class_fractions({10: 50.0}, polygon_area=100.0)
    assert fractions == {10: pytest.approx(0.5)}


def test_dominant_class_is_accepted_at_or_above_threshold() -> None:
    outcome = decide({10: 80.0, 50: 20.0}, polygon_area=100.0, threshold=0.8)
    assert outcome.accepted
    assert outcome.code == 10
    assert outcome.fraction == pytest.approx(0.8)
    assert outcome.reason is None


def test_below_threshold_is_rejected_but_still_reports_the_best_class() -> None:
    outcome = decide({10: 79.0, 50: 21.0}, polygon_area=100.0, threshold=0.8)
    assert not outcome.accepted
    assert outcome.code == 10
    assert outcome.fraction == pytest.approx(0.79)
    assert outcome.reason is RejectionReason.BELOW_THRESHOLD


def test_uncovered_area_can_push_a_polygon_below_threshold() -> None:
    # 100% of the *covered* part is 311, but only 60% of the polygon is covered.
    outcome = decide({10: 60.0}, polygon_area=100.0, threshold=0.8)
    assert not outcome.accepted
    assert outcome.reason is RejectionReason.BELOW_THRESHOLD


def test_nodata_cannot_win_but_still_consumes_the_polygon() -> None:
    # 0 is WorldCover's no-data value: not a land-cover observation.
    outcome = decide({0: 90.0, 10: 10.0}, polygon_area=100.0, threshold=0.8)
    assert not outcome.accepted
    assert outcome.code == 10
    assert outcome.fraction == pytest.approx(0.1)


def test_only_nodata_coverage_is_rejected_with_no_class() -> None:
    outcome = decide({0: 100.0}, polygon_area=100.0, threshold=0.8)
    assert not outcome.accepted
    assert outcome.code is None
    assert outcome.reason is RejectionReason.NO_VALID_CLASS


def test_no_intersection_at_all_is_rejected() -> None:
    outcome = decide({}, polygon_area=100.0, threshold=0.8)
    assert not outcome.accepted
    assert outcome.code is None
    assert outcome.reason is RejectionReason.NO_VALID_CLASS


@pytest.mark.parametrize("bad_area", [0.0, -1.0])
def test_non_positive_polygon_area_is_rejected(bad_area: float) -> None:
    outcome = decide({10: 10.0}, polygon_area=bad_area, threshold=0.8)
    assert not outcome.accepted
    assert outcome.reason is RejectionReason.EMPTY_POLYGON


def test_ties_break_deterministically_on_the_lowest_code() -> None:
    a = decide({20: 50.0, 10: 50.0}, polygon_area=100.0, threshold=0.5)
    b = decide({10: 50.0, 20: 50.0}, polygon_area=100.0, threshold=0.5)
    assert a.code == b.code == 10


def test_float_noise_over_full_coverage_is_clamped_to_one() -> None:
    outcome = decide({10: 100.0000000001}, polygon_area=100.0, threshold=0.8)
    assert outcome.accepted
    assert outcome.fraction == pytest.approx(1.0)
    assert outcome.fraction <= 1.0


def test_default_threshold_is_the_specified_eighty_percent() -> None:
    assert DEFAULT_THRESHOLD == 0.8


@pytest.mark.parametrize("bad", [-0.1, 0.0, 1.1])
def test_threshold_must_be_in_the_unit_interval(bad: float) -> None:
    with pytest.raises(ValueError):
        decide({10: 10.0}, polygon_area=100.0, threshold=bad)


def test_coverage_exceeding_the_polygon_is_a_loud_error() -> None:
    """A pixel belongs to exactly one class, so areas summing past the polygon
    is an upstream bug (double-counted coverage) and must not be clamped away."""
    with pytest.raises(OverlappingCoverageError):
        decide({10: 60.0, 50: 60.0}, polygon_area=100.0, threshold=0.8)


def test_small_float_overshoot_is_tolerated_not_raised() -> None:
    outcome = decide({10: 80.0, 50: 20.2}, polygon_area=100.0, threshold=0.8)
    assert outcome.accepted


def test_class_fractions_also_guards_overlapping_coverage() -> None:
    with pytest.raises(OverlappingCoverageError):
        class_fractions({10: 60.0, 50: 60.0}, polygon_area=100.0)

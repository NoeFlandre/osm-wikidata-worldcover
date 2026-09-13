"""Invariants of the dominance decision across generated edge cases."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from osm_wikidata_worldcover.domain.dominance import (
    OverlappingCoverageError,
    RejectionReason,
    class_fractions,
    decide,
)
from osm_wikidata_worldcover.domain.nomenclature import CLASS_LABELS, NODATA, is_valid_code

CODES = [*CLASS_LABELS, NODATA]

polygon_areas = st.floats(min_value=1e-3, max_value=1e12, allow_nan=False, allow_infinity=False)
thresholds = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def coverage(draw: st.DrawFn) -> tuple[list[tuple[str, float]], float]:
    """A polygon area plus non-overlapping per-class areas summing to at most it.

    This mirrors reality: every pixel carries exactly one class, so a polygon's
    classes partition it and any remainder is simply unobserved.
    """
    polygon_area = draw(polygon_areas)
    codes = draw(st.lists(st.sampled_from(CODES), max_size=6, unique=True))
    shares = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=len(codes),
            max_size=len(codes),
        )
    )
    total = sum(shares)
    if total > 1.0:  # normalise so the parts never exceed the whole
        shares = [s / total for s in shares]
    return [(c, s * polygon_area) for c, s in zip(codes, shares, strict=True)], polygon_area


@given(coverage())
def test_fractions_always_lie_in_the_unit_interval(case) -> None:
    pairs, polygon_area = case
    for fraction in class_fractions(dict(pairs), polygon_area).values():
        assert 0.0 <= fraction <= 1.0


@given(coverage(), thresholds)
def test_acceptance_implies_a_valid_class_at_or_above_threshold(case, threshold) -> None:
    pairs, polygon_area = case
    outcome = decide(dict(pairs), polygon_area, threshold)
    if outcome.accepted:
        assert outcome.code is not None
        assert is_valid_code(outcome.code)
        assert outcome.fraction >= threshold
        assert outcome.reason is None
    else:
        assert outcome.reason is not None


@given(coverage(), thresholds)
def test_rejection_reason_matches_the_state_it_describes(case, threshold) -> None:
    pairs, polygon_area = case
    outcome = decide(dict(pairs), polygon_area, threshold)
    if outcome.reason is RejectionReason.NO_VALID_CLASS:
        assert outcome.code is None
    if outcome.reason is RejectionReason.BELOW_THRESHOLD:
        assert outcome.code is not None
        assert outcome.fraction < threshold


@given(coverage(), thresholds)
def test_decision_is_independent_of_insertion_order(case, threshold) -> None:
    pairs, polygon_area = case
    forward = decide(dict(pairs), polygon_area, threshold)
    backward = decide(dict(reversed(pairs)), polygon_area, threshold)
    assert forward == backward


@given(coverage())
@settings(max_examples=300)
def test_above_one_half_at_most_one_class_can_dominate(case) -> None:
    pairs, polygon_area = case
    threshold = 0.51
    fractions = class_fractions(dict(pairs), polygon_area)
    winners = [c for c, f in fractions.items() if is_valid_code(c) and f >= threshold]
    assert len(winners) <= 1
    assert decide(dict(pairs), polygon_area, threshold).accepted == bool(winners)


@given(coverage(), thresholds)
def test_decision_is_deterministic(case, threshold) -> None:
    pairs, polygon_area = case
    assert decide(dict(pairs), polygon_area, threshold) == decide(
        dict(pairs), polygon_area, threshold
    )


@given(
    st.lists(st.sampled_from(CODES), min_size=2, max_size=4, unique=True),
    polygon_areas,
)
def test_double_counted_coverage_always_raises(codes, polygon_area) -> None:
    # Every class alone already fills the polygon: unambiguously double counted.
    with pytest.raises(OverlappingCoverageError):
        decide({c: polygon_area for c in codes}, polygon_area, 0.8)

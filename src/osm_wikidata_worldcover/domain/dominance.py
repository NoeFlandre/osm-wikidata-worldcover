"""Decide whether one WorldCover class dominates an OSM polygon.

Fractions are taken against the **polygon's own area**, not against the area
that was actually observed. A polygon straddling a gap in coverage -- or one
mostly covered by no-data pixels -- therefore fails the dominance test rather
than being labelled from whichever sliver was classified. Refusing is the
honest outcome when most of the polygon was never observed.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final

from osm_wikidata_worldcover.domain.nomenclature import is_valid_code

__all__ = [
    "COVERAGE_TOLERANCE",
    "DEFAULT_THRESHOLD",
    "DominanceOutcome",
    "OverlappingCoverageError",
    "RejectionReason",
    "class_fractions",
    "decide",
]

DEFAULT_THRESHOLD: Final[float] = 0.8

#: Relative slack allowed on total coverage before it is treated as a bug.
#: Absorbs floating-point noise from partial-pixel coverage, nothing more.
COVERAGE_TOLERANCE: Final[float] = 0.01


class OverlappingCoverageError(ValueError):
    """Raised when intersected areas sum to more than the polygon's own area.

    WorldCover assigns each pixel exactly one class, so a pixel's area cannot
    count towards two classes. This means the caller double-counted coverage.
    Clamping it away would silently manufacture two dominant classes for one
    polygon, so it fails loudly instead.
    """


class RejectionReason(Enum):
    """Why a polygon did not yield a label."""

    EMPTY_POLYGON = "empty_polygon"
    TOO_LARGE = "too_large"
    NO_VALID_CLASS = "no_valid_class"
    BELOW_THRESHOLD = "below_threshold"


@dataclass(frozen=True, slots=True)
class DominanceOutcome:
    """The dominance verdict for a single polygon.

    ``code``/``fraction`` describe the best thematic class found even when the
    polygon is rejected, so rejections stay auditable.
    """

    accepted: bool
    code: int | None
    fraction: float
    reason: RejectionReason | None = None


def class_fractions(areas_by_code: Mapping[int, float], polygon_area: float) -> dict[int, float]:
    """Return each code's share of ``polygon_area``, clamped to ``[0, 1]``."""
    if polygon_area <= 0.0:
        return {}
    total = sum(areas_by_code.values())
    if total > polygon_area * (1.0 + COVERAGE_TOLERANCE):
        raise OverlappingCoverageError(
            f"intersected areas sum to {total!r}, exceeding polygon area {polygon_area!r}"
        )
    return {code: min(max(area / polygon_area, 0.0), 1.0) for code, area in areas_by_code.items()}


def decide(
    areas_by_code: Mapping[int, float],
    polygon_area: float,
    threshold: float = DEFAULT_THRESHOLD,
) -> DominanceOutcome:
    """Return the dominance verdict for one polygon.

    ``areas_by_code`` maps a WorldCover class code to the area of the polygon
    covered by it, in the same unit as ``polygon_area``.
    """
    if not 0.0 < threshold <= 1.0:
        raise ValueError(f"threshold must be in (0, 1], got {threshold!r}")
    if polygon_area <= 0.0:
        return DominanceOutcome(False, None, 0.0, RejectionReason.EMPTY_POLYGON)

    thematic = _thematic(areas_by_code, polygon_area)
    if not thematic:
        return DominanceOutcome(False, None, 0.0, RejectionReason.NO_VALID_CLASS)

    code = _winner(thematic)
    fraction = thematic[code]
    if fraction >= threshold:
        return DominanceOutcome(True, code, fraction)
    return DominanceOutcome(False, code, fraction, RejectionReason.BELOW_THRESHOLD)


def _thematic(areas_by_code: Mapping[int, float], polygon_area: float) -> dict[int, float]:
    """Return the shares of real land-cover classes, discarding no-data."""
    return {
        code: fraction
        for code, fraction in class_fractions(areas_by_code, polygon_area).items()
        if is_valid_code(code)
    }


def _winner(thematic: Mapping[int, float]) -> int:
    """Return the dominant code.

    The highest fraction wins; equal fractions break on the lowest code, so the
    result never depends on mapping iteration order.
    """
    return min(thematic, key=lambda code: (-thematic[code], code))

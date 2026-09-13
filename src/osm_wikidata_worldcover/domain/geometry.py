"""Polygon validity screening.

Invalid polygons are dropped rather than repaired. Repair (``make_valid``)
would silently alter the very shape whose area fraction becomes the label, so
the dataset prefers a smaller, trustworthy set of polygons over a larger one
built on geometries the source did not actually assert.
"""

import math

from shapely.geometry.base import BaseGeometry

__all__ = ["AREAL_TYPES", "InvalidGeometryError", "is_usable_polygon", "screen"]

AREAL_TYPES = frozenset({"Polygon", "MultiPolygon"})


class InvalidGeometryError(ValueError):
    """Raised when a geometry cannot support an area-fraction computation."""


def is_usable_polygon(geom: BaseGeometry | None) -> bool:
    """Return whether ``geom`` is an areal, simple, finite, non-degenerate polygon."""
    if geom is None or geom.is_empty:
        return False
    if geom.geom_type not in AREAL_TYPES:
        return False
    if not _all_finite(geom):
        return False
    return geom.is_valid and geom.area > 0.0


def screen(geom: BaseGeometry | None) -> BaseGeometry:
    """Return ``geom`` unchanged, or raise :class:`InvalidGeometryError`."""
    if not is_usable_polygon(geom):
        raise InvalidGeometryError(f"unusable geometry: {geom!r}")
    assert geom is not None
    return geom


def _all_finite(geom: BaseGeometry) -> bool:
    """Return whether every coordinate is finite.

    NaN coordinates make ``is_valid`` and ``area`` unreliable, so they are
    screened out before either is consulted.
    """
    try:
        bounds = geom.bounds
    except Exception:
        return False
    return all(math.isfinite(value) for value in bounds)

"""Polygon validity screening."""

import pytest
from shapely import wkt
from shapely.geometry import GeometryCollection, LineString, Point, Polygon

from osm_wikidata_worldcover.domain.geometry import is_usable_polygon

SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
BOWTIE = wkt.loads("POLYGON ((0 0, 1 1, 1 0, 0 1, 0 0))")


def test_a_simple_square_is_usable() -> None:
    assert is_usable_polygon(SQUARE)


def test_none_is_not_usable() -> None:
    assert not is_usable_polygon(None)


def test_empty_geometry_is_not_usable() -> None:
    assert not is_usable_polygon(Polygon())
    assert not is_usable_polygon(GeometryCollection())


@pytest.mark.parametrize("geom", [Point(0, 0), LineString([(0, 0), (1, 1)])])
def test_non_areal_geometry_is_not_usable(geom) -> None:
    assert not is_usable_polygon(geom)


def test_self_intersecting_polygon_is_not_usable() -> None:
    assert not is_usable_polygon(BOWTIE)


def test_zero_area_polygon_is_not_usable() -> None:
    assert not is_usable_polygon(Polygon([(0, 0), (1, 1), (2, 2), (0, 0)]))


def test_non_finite_coordinates_are_not_usable() -> None:
    assert not is_usable_polygon(Polygon([(0, 0), (0, 1), (float("nan"), 1), (1, 0)]))


def test_multipolygon_is_usable() -> None:
    from shapely.geometry import MultiPolygon

    assert is_usable_polygon(MultiPolygon([SQUARE, Polygon([(2, 2), (2, 3), (3, 3)])]))

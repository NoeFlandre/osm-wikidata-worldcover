"""WorldCover tile addressing and class-coverage extraction."""

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from osm_wikidata_worldcover.adapters.worldcover import WorldCoverTiles, class_coverage
from osm_wikidata_worldcover.domain.tiling import Tile


def one(geom) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"polygon_id": ["p"]}, geometry=[geom], crs="EPSG:4326")


class TestTileAddressing:
    def test_url_follows_the_published_naming_scheme(self, tmp_path) -> None:
        tiles = WorldCoverTiles(tmp_path)
        assert tiles.url_for(Tile(48, 6)).endswith(
            "/v200/2021/map/ESA_WorldCover_10m_2021_v200_N48E006_Map.tif"
        )

    def test_version_and_year_are_reflected_in_the_url(self, tmp_path) -> None:
        tiles = WorldCoverTiles(tmp_path, version="v100", year=2020)
        url = tiles.url_for(Tile(-3, -6))
        assert "/v100/2020/map/" in url
        assert url.endswith("ESA_WorldCover_10m_2020_v100_S03W006_Map.tif")

    def test_cache_path_is_derived_from_the_tile_name(self, tmp_path) -> None:
        tiles = WorldCoverTiles(tmp_path)
        assert tiles.path_for(Tile(48, 6)).parent == tmp_path
        assert "N48E006" in tiles.path_for(Tile(48, 6)).name


class TestClassCoverage:
    def test_a_polygon_split_between_two_classes(self, half_and_half, square) -> None:
        assert class_coverage([half_and_half], square) == [
            {10: pytest.approx(0.5), 50: pytest.approx(0.5)}
        ]

    def test_a_polygon_inside_one_class_is_wholly_that_class(self, half_and_half) -> None:
        left = one(Polygon([(0, 0), (0, 4), (2, 4), (2, 0)]))
        assert class_coverage([half_and_half], left) == [{10: pytest.approx(1.0)}]

    def test_partial_pixels_are_weighted_by_area_not_counted_whole(self, half_and_half) -> None:
        # Spans 1.5 columns of class 10 and 0.5 of class 50.
        strip = one(Polygon([(0.5, 0), (0.5, 4), (2.5, 4), (2.5, 0)]))
        assert class_coverage([half_and_half], strip) == [
            {10: pytest.approx(0.75), 50: pytest.approx(0.25)}
        ]

    def test_nodata_is_absent_and_leaves_the_polygon_only_half_covered(
        self, with_nodata, square
    ) -> None:
        """No-data is not a class, so it is reported as missing coverage.

        Renormalising over observed pixels would label a half-unobserved
        polygon with full confidence; leaving the gap lets dominance refuse it.
        """
        coverage = class_coverage([with_nodata], square)[0]
        assert coverage == {10: pytest.approx(0.5)}
        assert sum(coverage.values()) == pytest.approx(0.5)

    def test_a_polygon_outside_the_raster_has_no_coverage(self, half_and_half) -> None:
        far = one(Polygon([(50, 50), (50, 51), (51, 51), (51, 50)]))
        assert class_coverage([half_and_half], far) == [{}]

    def test_coverage_beyond_the_raster_edge_is_not_counted_as_observed(
        self, half_and_half
    ) -> None:
        """Half the polygon lies off the raster, so classes must cover only half of it.

        Reporting 1.0 here would let an unobserved polygon pass the dominance
        test on the strength of the sliver that happened to be on the tile.
        """
        overhang = one(Polygon([(2, 0), (2, 4), (6, 4), (6, 0)]))
        assert sum(class_coverage([half_and_half], overhang)[0].values()) == pytest.approx(0.5)

    def test_several_polygons_keep_their_input_order(self, half_and_half) -> None:
        frame = gpd.GeoDataFrame(
            {"polygon_id": ["a", "b"]},
            geometry=[
                Polygon([(0, 0), (0, 4), (2, 4), (2, 0)]),
                Polygon([(2, 0), (2, 4), (4, 4), (4, 0)]),
            ],
            crs="EPSG:4326",
        )
        assert class_coverage([half_and_half], frame) == [
            {10: pytest.approx(1.0)},
            {50: pytest.approx(1.0)},
        ]

    def test_an_empty_frame_yields_no_rows(self, half_and_half) -> None:
        empty = gpd.GeoDataFrame({"polygon_id": []}, geometry=[], crs="EPSG:4326")
        assert class_coverage([half_and_half], empty) == []

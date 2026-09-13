"""Region pipeline: geometry preparation, labelling and example assembly."""

import pandas as pd
import pytest

from osm_wikidata_worldcover.adapters.source import RegionTables
from osm_wikidata_worldcover.config import Config
from osm_wikidata_worldcover.domain.tiling import Tile
from osm_wikidata_worldcover.pipeline import (
    RegionOutcome,
    label_polygons,
    prepare_polygons,
    run_region,
    to_examples,
)

SQUARE_GEOJSON = '{"type":"Polygon","coordinates":[[[0,0],[0,4],[4,4],[4,0],[0,0]]]}'
LEFT_GEOJSON = '{"type":"Polygon","coordinates":[[[0,0],[0,4],[2,4],[2,0],[0,0]]]}'
BOWTIE_GEOJSON = '{"type":"Polygon","coordinates":[[[0,0],[1,1],[1,0],[0,1],[0,0]]]}'


class FixedTiles:
    """A tile source that always serves one raster and records its calls."""

    def __init__(self, path):
        self.path = path
        self.ensured: list[Tile] = []
        self.discarded: list[Tile] = []

    def ensure(self, tile: Tile):
        self.ensured.append(tile)
        return self.path

    def discard(self, tile: Tile) -> None:
        self.discarded.append(tile)


def polygons_frame(**over) -> pd.DataFrame:
    base = {
        "polygon_id": ["p1"],
        "region": ["r"],
        "osm_type": ["way"],
        "osm_id": [1],
        "wikidata": ["Q1"],
        "name": ["N"],
        "lat": [2.0],
        "lon": [2.0],
        "geometry": [SQUARE_GEOJSON],
        "area_m2": [1000.0],
        "source_pbf": ["r.osm.pbf"],
    }
    return pd.DataFrame(base | over)


class TestPreparePolygons:
    def test_valid_geometry_is_parsed(self) -> None:
        frame, invalid = prepare_polygons(polygons_frame())
        assert invalid == 0
        assert frame.geometry.iloc[0].area == pytest.approx(16.0)

    def test_invalid_geometry_is_dropped_and_counted(self) -> None:
        frame, invalid = prepare_polygons(polygons_frame(geometry=[BOWTIE_GEOJSON]))
        assert len(frame) == 0
        assert invalid == 1

    def test_an_empty_table_yields_an_empty_frame(self) -> None:
        frame, invalid = prepare_polygons(polygons_frame().iloc[0:0])
        assert len(frame) == 0
        assert invalid == 0


class TestLabelPolygons:
    def test_a_dominated_polygon_is_labelled(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON]))
        outcome = RegionOutcome("r")
        labelled = label_polygons(frame, FixedTiles(half_and_half), 0.8, outcome)
        assert labelled["worldcover_code"].tolist() == [10]
        assert labelled["dominant_fraction"].iloc[0] == pytest.approx(1.0)
        assert outcome.polygons_accepted == 1

    def test_an_evenly_split_polygon_is_rejected_below_threshold(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame())
        outcome = RegionOutcome("r")
        labelled = label_polygons(frame, FixedTiles(half_and_half), 0.8, outcome)
        assert len(labelled) == 0
        assert outcome.rejections["below_threshold"] == 1

    def test_a_half_unobserved_polygon_is_rejected(self, with_nodata) -> None:
        frame, _ = prepare_polygons(polygons_frame())
        outcome = RegionOutcome("r")
        labelled = label_polygons(frame, FixedTiles(with_nodata), 0.8, outcome)
        assert len(labelled) == 0
        assert outcome.rejections["below_threshold"] == 1

    def test_tiles_are_released_after_use(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON]))
        tiles = FixedTiles(half_and_half)
        label_polygons(frame, tiles, 0.8, RegionOutcome("r"))
        assert tiles.discarded == tiles.ensured

    def test_tiles_are_kept_when_asked(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON]))
        tiles = FixedTiles(half_and_half)
        label_polygons(frame, tiles, 0.8, RegionOutcome("r"), keep_tiles=True)
        assert tiles.discarded == []


def tables_for(labelled_id: str = "p1", **over) -> RegionTables:
    documents = pd.DataFrame(
        {
            "document_id": ["d1"],
            "language": ["en"],
            "title": ["T"],
            "url": ["u"],
            "lead_text": ["lead"],
            "full_text": [" ".join(["word"] * 40)],
            "article_length_words": [40],
            "fetch_status": ["ok"],
            "license": ["CC BY-SA 4.0"],
            "project": ["wikipedia"],
        }
    )
    for key, value in over.items():
        documents[key] = value
    return RegionTables(
        stem="r",
        polygons=polygons_frame(),
        links=pd.DataFrame(
            {
                "polygon_id": [labelled_id],
                "document_id": ["d1"],
                "project": ["wikipedia"],
                "language": ["en"],
                "link_sources": ["[]"],
            }
        ),
        documents=documents,
    )


class TestToExamples:
    def _labelled(self) -> pd.DataFrame:
        frame = polygons_frame()
        frame["worldcover_code"] = [10]
        frame["dominant_fraction"] = [1.0]
        frame["observed_fraction"] = [1.0]
        return frame

    def test_one_row_per_polygon_document_pair(self) -> None:
        rows = to_examples(self._labelled(), tables_for(), min_words=10)
        assert len(rows) == 1
        assert rows["document_id"].iloc[0] == "d1"

    def test_failed_fetches_are_dropped(self) -> None:
        rows = to_examples(self._labelled(), tables_for(fetch_status="error"), min_words=10)
        assert len(rows) == 0

    def test_short_text_is_dropped(self) -> None:
        rows = to_examples(self._labelled(), tables_for(full_text="too short"), min_words=10)
        assert len(rows) == 0

    def test_a_polygon_with_no_links_yields_nothing(self) -> None:
        rows = to_examples(self._labelled(), tables_for(labelled_id="other"), min_words=10)
        assert len(rows) == 0

    def test_no_labelled_polygons_yields_nothing(self) -> None:
        assert len(to_examples(pd.DataFrame(), tables_for(), min_words=10)) == 0


class TestRunRegion:
    def test_a_region_produces_shaped_examples(self, half_and_half) -> None:
        tables = tables_for()
        tables = RegionTables(
            stem="r",
            polygons=polygons_frame(geometry=[LEFT_GEOJSON]),
            links=tables.links,
            documents=tables.documents,
        )
        config = Config()
        examples, outcome = run_region(config, tables, FixedTiles(half_and_half))
        assert outcome.polygons_seen == 1
        assert outcome.examples == 1
        row = examples.iloc[0]
        assert row["worldcover_code"] == 10
        assert row["worldcover_label"] == "Tree cover"
        assert row["dominant_fraction"] == pytest.approx(1.0)
        assert row["text_words"] == 40
        assert row["centroid_wkt"] == "POINT (2 2)"
        assert row["polygon_area_m2"] == 1000.0

    def test_a_region_whose_polygons_are_all_rejected_yields_no_examples(
        self, half_and_half
    ) -> None:
        examples, outcome = run_region(Config(), tables_for(), FixedTiles(half_and_half))
        assert len(examples) == 0
        assert outcome.examples == 0


class TestTileDeduplication:
    """Regression: one raster serving several tiles must not be read twice.

    Reading it twice doubles every coverage share, which trips the overlapping
    coverage guard and silently rejects a perfectly good polygon.
    """

    def test_a_polygon_spanning_tiles_is_not_double_counted(self, half_and_half) -> None:
        # The fixture raster spans two tile rows, so this polygon's tile set
        # resolves to the same file twice.
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON]))
        outcome = RegionOutcome("r")
        labelled = label_polygons(frame, FixedTiles(half_and_half), 0.8, outcome)
        assert len(labelled) == 1
        assert labelled["dominant_fraction"].iloc[0] == pytest.approx(1.0)
        assert outcome.rejections == {}


class TestPolygonSizeCap:
    """Continent-scale polygons are refused before any raster is fetched.

    The largest polygon in the source is 10.2 million km2 -- about 10^11 pixels
    spread over ~100 tiles, roughly 10 GB of download for a single row.
    """

    def test_a_polygon_above_the_cap_is_refused(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON], area_m2=[2e10]))
        outcome = RegionOutcome("r")
        tiles = FixedTiles(half_and_half)
        labelled = label_polygons(frame, tiles, 0.8, outcome, max_area_m2=1e10)
        assert len(labelled) == 0
        assert outcome.rejections["too_large"] == 1

    def test_an_oversized_polygon_costs_no_tile_download(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON], area_m2=[2e10]))
        tiles = FixedTiles(half_and_half)
        label_polygons(frame, tiles, 0.8, RegionOutcome("r"), max_area_m2=1e10)
        assert tiles.ensured == []

    def test_a_polygon_exactly_at_the_cap_is_kept(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON], area_m2=[1e10]))
        labelled = label_polygons(
            frame, FixedTiles(half_and_half), 0.8, RegionOutcome("r"), max_area_m2=1e10
        )
        assert len(labelled) == 1

    def test_no_cap_keeps_everything(self, half_and_half) -> None:
        frame, _ = prepare_polygons(polygons_frame(geometry=[LEFT_GEOJSON], area_m2=[1e30]))
        labelled = label_polygons(
            frame, FixedTiles(half_and_half), 0.8, RegionOutcome("r"), max_area_m2=None
        )
        assert len(labelled) == 1

    def test_the_cap_is_applied_by_a_whole_region_run(self, half_and_half) -> None:
        tables = tables_for()
        tables = RegionTables(
            stem="r",
            polygons=polygons_frame(geometry=[LEFT_GEOJSON], area_m2=[2e10]),
            links=tables.links,
            documents=tables.documents,
        )
        examples, outcome = run_region(
            Config(max_polygon_area_m2=1e10), tables, FixedTiles(half_and_half)
        )
        assert len(examples) == 0
        assert outcome.rejections["too_large"] == 1

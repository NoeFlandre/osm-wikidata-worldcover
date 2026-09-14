"""Executable acceptance criteria for the dataset build."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from shapely.geometry import Polygon
from tests.conftest import write_raster

from osm_worldcover.adapters.source import RegionTables
from osm_worldcover.config import Config
from osm_worldcover.domain.nomenclature import is_valid_code
from osm_worldcover.finalize import StreamedBuild, finalize_shards
from osm_worldcover.pipeline import RegionOutcome, run_region

scenarios("features/dataset_build.feature")

WORD = "word"


class World:
    """Everything a scenario builds up before the dataset is built."""

    def __init__(self) -> None:
        self.raster: Path | None = None
        self.polygons: list[dict] = []
        self.links: list[dict] = []
        self.documents: list[dict] = []
        self.extra_regions: list[dict] = []
        self.result: StreamedBuild | None = None
        self.outcome: RegionOutcome | None = None
        self.written: list[list[bytes]] = []
        self.scratch: Path = Path()


@pytest.fixture
def world(tmp_path: Path) -> World:
    state = World()
    state.scratch = tmp_path / "run"
    return state


class FixedTiles:
    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure(self, tile):
        return self.path

    def discard(self, tile) -> None:
        return None


def add_polygon(world: World, geom: Polygon, index: int = 0, region: str = "alpha") -> str:
    polygon_id = f"{region}-latest:way:{index}"
    world.polygons.append(
        {
            "polygon_id": polygon_id,
            "region": region,
            "osm_type": "way",
            "osm_id": index,
            "wikidata": f"Q{index}",
            "name": f"place {index}",
            "lat": geom.centroid.y,
            "lon": geom.centroid.x,
            "geometry": json.dumps(geom.__geo_interface__),
            "area_m2": 1000.0,
            "source_pbf": f"{region}-latest.osm.pbf",
        }
    )
    return polygon_id


def add_document(world: World, polygon_id: str, doc_id: str, words: int) -> None:
    world.links.append(
        {
            "polygon_id": polygon_id,
            "document_id": doc_id,
            "project": "wikipedia",
            "language": "en",
            "link_sources": "[]",
        }
    )
    world.documents.append(
        {
            "document_id": doc_id,
            "language": "en",
            "title": f"Article {doc_id}",
            "url": f"https://example.org/{doc_id}",
            "lead_text": "lead",
            "full_text": " ".join([WORD] * words) + f" {doc_id}",
            "article_length_words": words,
            "fetch_status": "ok",
            "license": "CC BY-SA 4.0",
            "project": "wikipedia",
        }
    )


# --------------------------------------------------------------------------
# Given
# --------------------------------------------------------------------------


@given("a land cover map whose western half is tree cover and eastern half is built-up")
def _west_east(world: World, tmp_path: Path) -> None:
    values = np.zeros((4, 4), dtype="uint8")
    values[:, :2] = 10
    values[:, 2:] = 50
    world.raster = write_raster(tmp_path / "we.tif", values)


@given("a land cover map whose southern half is unobserved")
def _south_unobserved(world: World, tmp_path: Path) -> None:
    values = np.zeros((4, 4), dtype="uint8")
    values[:2, :] = 10
    world.raster = write_raster(tmp_path / "ns.tif", values)


@given("a polygon lying wholly in the tree cover half")
def _left_polygon(world: World) -> None:
    add_polygon(world, Polygon([(0, 0), (0, 4), (2, 4), (2, 0)]))


@given("a polygon spanning both halves equally")
def _even_polygon(world: World) -> None:
    add_polygon(world, Polygon([(0, 0), (0, 4), (4, 4), (4, 0)]))


@given("a polygon covering the whole map")
def _whole_polygon(world: World) -> None:
    add_polygon(world, Polygon([(0, 0), (0, 4), (4, 4), (4, 0)]))


@given(parsers.parse("the polygon is linked to an article of {words:d} words"))
def _one_article(world: World, words: int) -> None:
    add_document(world, world.polygons[-1]["polygon_id"], "d0", words)


@given(parsers.parse("the polygon is linked to {count:d} distinct articles of {words:d} words"))
def _many_articles(world: World, count: int, words: int) -> None:
    for i in range(count):
        add_document(world, world.polygons[-1]["polygon_id"], f"d{i}", words)


@given("the identical OSM object also appears in a neighbouring region")
def _duplicate_region(world: World) -> None:
    original = world.polygons[-1]
    twin = dict(original)
    twin["polygon_id"] = "beta-latest:way:0"
    twin["region"] = "beta"
    world.polygons.append(twin)
    world.links.append(
        {
            "polygon_id": twin["polygon_id"],
            "document_id": "d0",
            "project": "wikipedia",
            "language": "en",
            "link_sources": "[]",
        }
    )


@given(
    parsers.parse("{count:d} polygons scattered within one kilometre, each with its own article")
)
def _scattered(world: World, count: int, tmp_path: Path) -> None:
    if world.raster is None:  # scenarios without the Background raster
        values = np.zeros((4, 4), dtype="uint8")
        values[:, :2] = 10
        values[:, 2:] = 50
        world.raster = write_raster(tmp_path / "we.tif", values)
    for i in range(count):
        offset = i * 0.0001  # about 10 m apart
        geom = Polygon(
            [
                (0.5 + offset, 0.5 + offset),
                (0.5 + offset, 0.6 + offset),
                (0.6 + offset, 0.6 + offset),
                (0.6 + offset, 0.5 + offset),
            ]
        )
        polygon_id = add_polygon(world, geom, index=i)
        add_document(world, polygon_id, f"d{i}", 40)


# --------------------------------------------------------------------------
# When
# --------------------------------------------------------------------------


def build(world: World) -> None:
    tables = RegionTables(
        stem="alpha-latest",
        polygons=pd.DataFrame(world.polygons),
        links=pd.DataFrame(world.links),
        documents=pd.DataFrame(world.documents),
    )
    config = Config()
    assert world.raster is not None, "no land cover map was given"
    examples, outcome = run_region(config, tables, FixedTiles(world.raster))
    world.outcome = outcome
    # Assembly reads shards from disk, as it does in a real run.
    shards = world.scratch / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    examples.to_parquet(shards / "alpha-latest.parquet", index=False)
    world.result = finalize_shards(
        shards,
        config,
        world.scratch / "assembly",
        world.scratch / "out",
        dict(outcome.rejections),
    )


@when("I build the dataset")
def _build(world: World) -> None:
    build(world)


@when("I build the dataset twice")
def _build_twice(world: World, tmp_path: Path) -> None:
    for run in ("a", "b"):
        world.scratch = tmp_path / run
        build(world)
        world.written.append([p.read_bytes() for p in _built(world).paths])


# --------------------------------------------------------------------------
# Then
# --------------------------------------------------------------------------


def _built(world: World) -> StreamedBuild:
    """The finished build, refusing a Then step that ran before the When."""
    assert world.result is not None, "the dataset was never built"
    return world.result


def _rows(world: World) -> pd.DataFrame:
    """Every published row, read back from the files that were written."""
    splits = [p for p in _built(world).paths if p.suffix == ".parquet"]
    return pd.concat([pd.read_parquet(p) for p in splits], ignore_index=True)


@then(parsers.parse("the dataset contains {count:d} example"))
@then(parsers.parse("the dataset contains {count:d} examples"))
def _count(world: World, count: int) -> None:
    assert _built(world).rows == count


@then("the dataset is empty")
def _empty(world: World) -> None:
    assert _built(world).rows == 0


@then(parsers.parse('the example is labelled "{label}"'))
def _label(world: World, label: str) -> None:
    assert _rows(world)["worldcover_label"].tolist() == [label]


@then(parsers.parse("the example's dominant fraction is at least {value:f}"))
def _fraction(world: World, value: float) -> None:
    assert _rows(world)["dominant_fraction"].min() >= value


@then(parsers.parse('the polygon was rejected because "{reason}"'))
def _rejected(world: World, reason: str) -> None:
    assert world.outcome is not None
    assert world.outcome.rejections[reason] >= 1


@then("every example names the same polygon")
def _same_polygon(world: World) -> None:
    assert _rows(world)["polygon_id"].nunique() == 1


@then("every example shares a single split")
def _one_split(world: World) -> None:
    assert _rows(world)["split"].nunique() == 1


@then("no polygon appears in more than one split")
def _no_polygon_leak(world: World) -> None:
    assert (_rows(world).groupby("polygon_id")["split"].nunique() > 1).sum() == 0


@then("no document appears in more than one split")
def _no_document_leak(world: World) -> None:
    assert (_rows(world).groupby("document_id")["split"].nunique() > 1).sum() == 0


@then("the build reports no violations")
def _no_violations(world: World) -> None:
    report = _built(world).report
    assert report.ok, report.violations


@then("every label is a real WorldCover class")
def _valid_labels(world: World) -> None:
    assert all(is_valid_code(int(c)) for c in _rows(world)["worldcover_code"])


@then("both builds produce byte-identical files")
def _identical(world: World) -> None:
    first, second = world.written
    assert first == second

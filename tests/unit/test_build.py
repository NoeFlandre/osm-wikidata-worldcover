"""Shard persistence and resume behaviour of a whole build."""

import pandas as pd

from osm_wikidata_worldcover.build import ShardStore


def frame(n: int = 2) -> pd.DataFrame:
    return pd.DataFrame({"polygon_id": [f"p{i}" for i in range(n)], "text": ["t"] * n})


def test_a_written_shard_is_reported_as_done(tmp_path) -> None:
    store = ShardStore(tmp_path)
    assert not store.has("alpha")
    store.write("alpha", frame())
    assert store.has("alpha")


def test_an_empty_region_is_recorded_so_it_is_not_redone(tmp_path) -> None:
    """A region with no examples is a real result, not an unfinished one."""
    store = ShardStore(tmp_path)
    store.write("alpha", pd.DataFrame())
    assert store.has("alpha")
    assert store.read() == []


def test_shards_are_read_back_in_a_deterministic_order(tmp_path) -> None:
    store = ShardStore(tmp_path)
    store.write("beta", frame(1))
    store.write("alpha", frame(2))
    assert [len(f) for f in store.read()] == [2, 1]


def test_round_trip_preserves_rows(tmp_path) -> None:
    store = ShardStore(tmp_path)
    store.write("alpha", frame(3))
    assert store.read()[0]["polygon_id"].tolist() == ["p0", "p1", "p2"]


def test_a_region_name_with_a_separator_is_still_addressable(tmp_path) -> None:
    store = ShardStore(tmp_path)
    store.write("great-britain-latest", frame())
    assert store.has("great-britain-latest")


def test_partial_writes_are_not_mistaken_for_finished_ones(tmp_path) -> None:
    store = ShardStore(tmp_path)
    (tmp_path / "alpha.parquet.part").write_bytes(b"junk")
    assert not store.has("alpha")


class TestRunBuild:
    """Whole-build orchestration, with the network and rasters stubbed out."""

    def _patch(self, monkeypatch, tmp_path, stems, examples_per_region=1):
        from osm_wikidata_worldcover import build as build_module
        from osm_wikidata_worldcover.adapters.source import RegionTables
        from osm_wikidata_worldcover.pipeline import RegionOutcome

        monkeypatch.setattr(build_module.hub, "resolve_revision", lambda *a, **k: "rev1")
        monkeypatch.setattr(build_module.hub, "list_region_stems", lambda *a, **k: stems)
        monkeypatch.setattr(build_module.hub, "snapshot_region", lambda *a, **k: [])
        monkeypatch.setattr(build_module.hub, "region_files", lambda stem: [])
        monkeypatch.setattr(
            RegionTables, "load", classmethod(lambda cls, root, stem: cls(stem, None, None, None))
        )

        def fake_run_region(config, tables, tiles, keep_tiles=False):
            rows = pd.DataFrame(
                {
                    "polygon_id": [f"{tables.stem}:{i}" for i in range(examples_per_region)],
                    "osm_type": ["way"] * examples_per_region,
                    "osm_id": list(range(examples_per_region)),
                    "region": [tables.stem] * examples_per_region,
                    "document_id": [f"{tables.stem}-d{i}" for i in range(examples_per_region)],
                    "language": ["en"] * examples_per_region,
                    "text": [
                        " ".join(["w"] * 20) + f" {tables.stem}{i}"
                        for i in range(examples_per_region)
                    ],
                    "worldcover_code": [10] * examples_per_region,
                    "worldcover_label": ["Tree cover"] * examples_per_region,
                    "dominant_fraction": [0.95] * examples_per_region,
                    "lat": [49.6] * examples_per_region,
                    "lon": [6.1] * examples_per_region,
                }
            )
            return rows, RegionOutcome(
                tables.stem, polygons_seen=1, polygons_accepted=1, examples=examples_per_region
            )

        monkeypatch.setattr(build_module, "run_region", fake_run_region)
        return build_module

    def test_every_region_contributes(self, tmp_path, monkeypatch) -> None:
        from osm_wikidata_worldcover.config import Config

        module = self._patch(monkeypatch, tmp_path, ["alpha", "beta"])
        report = module.run_build(Config(cache_dir=tmp_path))
        assert report.result.rows == 2
        assert len(report.regions) == 2

    def test_a_finished_region_is_skipped_on_a_rerun(self, tmp_path, monkeypatch) -> None:
        from osm_wikidata_worldcover.config import Config

        module = self._patch(monkeypatch, tmp_path, ["alpha", "beta"])
        config = Config(cache_dir=tmp_path)
        module.run_build(config)
        second = module.run_build(config)
        assert second.regions == []  # nothing re-processed
        assert second.result.rows == 2  # but the data is still there

    def test_rejections_are_summed_across_regions(self, tmp_path, monkeypatch) -> None:
        from osm_wikidata_worldcover.config import Config

        module = self._patch(monkeypatch, tmp_path, ["alpha", "beta"])
        report = module.run_build(Config(cache_dir=tmp_path))
        for region in report.regions:
            region.rejections["below_threshold"] = 2
        assert report.rejections == {"below_threshold": 4}

    def test_an_explicit_region_list_overrides_discovery(self, tmp_path, monkeypatch) -> None:
        from osm_wikidata_worldcover.config import Config

        module = self._patch(monkeypatch, tmp_path, ["alpha", "beta"])
        report = module.run_build(Config(cache_dir=tmp_path), regions=["alpha"])
        assert [r.stem for r in report.regions] == ["alpha"]

    def test_a_pinned_revision_is_not_resolved_again(self, tmp_path, monkeypatch) -> None:
        from osm_wikidata_worldcover import build as build_module
        from osm_wikidata_worldcover.config import Config

        self._patch(monkeypatch, tmp_path, ["alpha"])

        def explode(*_a, **_k):
            raise AssertionError("revision was already pinned")

        monkeypatch.setattr(build_module.hub, "resolve_revision", explode)
        report = build_module.run_build(Config(cache_dir=tmp_path, source_revision="pinned"))
        revisions = pd.concat(report.result.frames.values())["source_revision"].unique()
        assert revisions.tolist() == ["pinned"]


def test_progress_is_reported_as_each_region_starts(tmp_path, monkeypatch) -> None:
    """Regression: announcing every region up front hides where a long run is.

    A list comprehension over a pre-computed "pending" list printed all 386
    region names before any work began.
    """
    from osm_wikidata_worldcover import build as build_module
    from osm_wikidata_worldcover.config import Config

    seen: list[str] = []
    helper = TestRunBuild()
    module = helper._patch(monkeypatch, tmp_path, ["alpha", "beta"])
    original = module._process_region

    def spy(config, revision, stem, raw, tiles, shards, keep_tiles, progress):
        seen.append(f"processing {stem}")
        return original(config, revision, stem, raw, tiles, shards, keep_tiles, progress)

    monkeypatch.setattr(build_module, "_process_region", spy)
    module.run_build(Config(cache_dir=tmp_path), progress=seen.append)

    # beta must not be announced before alpha has been processed.
    assert seen.index("processing alpha") < next(
        i for i, line in enumerate(seen) if line.startswith("[2/2] beta")
    )

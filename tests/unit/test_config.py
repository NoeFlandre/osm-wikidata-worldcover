"""Run configuration loading and overrides."""

from pathlib import Path

import pytest

from osm_worldcover.config import Config


def test_defaults_are_usable_without_arguments() -> None:
    config = Config()
    assert config.threshold == 0.8
    assert config.worldcover_version == "v200"


def test_named_source_selects_its_input_dataset() -> None:
    config = Config(source="website")
    assert config.source_dataset == "NoeFlandre/osm-polygon-website-tag"
    assert config.source_recipe.output_dataset == "NoeFlandre/osm-polygon-website-tag-worldcover"


def test_from_mapping_coerces_paths() -> None:
    config = Config.from_mapping({"out_dir": "a/b", "cache_dir": "c"})
    assert config.out_dir == Path("a/b")
    assert config.cache_dir == Path("c")


def test_from_mapping_coerces_regions_to_a_tuple() -> None:
    assert Config.from_mapping({"regions": ["a", "b"]}).regions == ("a", "b")


def test_from_mapping_keeps_regions_none() -> None:
    assert Config.from_mapping({"regions": None}).regions is None


def test_from_mapping_rejects_unknown_keys() -> None:
    with pytest.raises(ValueError, match="unknown config keys"):
        Config.from_mapping({"nope": 1})


def test_from_yaml_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("threshold: 0.9\nregions: [luxembourg-latest]\n")
    config = Config.from_yaml(path)
    assert config.threshold == 0.9
    assert config.regions == ("luxembourg-latest",)


def test_from_yaml_accepts_an_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("")
    assert Config.from_yaml(path).threshold == 0.8


def test_overrides_ignore_none_so_unset_cli_flags_do_not_clobber() -> None:
    config = Config(threshold=0.9).with_overrides(threshold=None, source_revision="abc")
    assert config.threshold == 0.9
    assert config.source_revision == "abc"


def test_manifest_settings_expose_every_knob_that_changes_the_data() -> None:
    settings = Config(source_revision="r1").as_manifest_settings()
    assert settings["source_revision"] == "r1"
    assert settings["dominance_threshold"] == 0.8
    assert settings["split_ratios"] == {"train": 0.8, "validation": 0.1, "test": 0.1}
    assert settings["worldcover_version"] == "v200"

"""CORINE nomenclature lookup behaviour."""

import pytest

from osm_wikidata_corine.domain import nomenclature as nom


def test_level3_codes_are_the_44_corine_classes() -> None:
    assert len(nom.LEVEL3_LABELS) == 44


@pytest.mark.parametrize(
    ("code", "label"),
    [
        ("111", "Continuous urban fabric"),
        ("311", "Broad-leaved forest"),
        ("523", "Sea and ocean"),
    ],
)
def test_label_for_known_level3_code(code: str, label: str) -> None:
    assert nom.label_for(code) == label


def test_label_for_unknown_code_raises() -> None:
    with pytest.raises(nom.UnknownCorineCode):
        nom.label_for("999")


def test_is_valid_code_discriminates() -> None:
    assert nom.is_valid_code("312")
    assert not nom.is_valid_code("999")
    assert not nom.is_valid_code("")
    assert not nom.is_valid_code("31")


def test_levels_are_derived_prefixes_with_labels() -> None:
    assert nom.level1_code("311") == "3"
    assert nom.level2_code("311") == "31"
    assert nom.level1_label("311") == "Forest and semi natural areas"
    assert nom.level2_label("311") == "Forests"


def test_every_level3_code_has_resolvable_parent_labels() -> None:
    for code in nom.LEVEL3_LABELS:
        assert nom.level1_label(code)
        assert nom.level2_label(code)

"""Text eligibility and exact-duplicate keying."""

import pytest

from osm_wikidata_corine.domain.text import (
    DEFAULT_MIN_WORDS,
    dedup_key,
    is_usable,
    normalise,
    word_count,
)


@pytest.mark.parametrize("raw", ["", "   ", "\n\t ", " "])
def test_blank_text_is_not_usable(raw: str) -> None:
    assert not is_usable(raw)


def test_text_shorter_than_the_minimum_is_not_usable() -> None:
    assert not is_usable("one two three", min_words=4)
    assert is_usable("one two three four", min_words=4)


def test_default_minimum_is_applied_when_not_given() -> None:
    assert not is_usable(" ".join(["w"] * (DEFAULT_MIN_WORDS - 1)))
    assert is_usable(" ".join(["w"] * DEFAULT_MIN_WORDS))


def test_normalise_trims_and_collapses_whitespace_without_touching_content() -> None:
    assert normalise("  Bosc \n de  la\tBartra ") == "Bosc de la Bartra"


def test_normalise_preserves_non_latin_scripts() -> None:
    assert normalise("  Андорра  ла  Веля ") == "Андорра ла Веля"


def test_word_count_ignores_surrounding_whitespace() -> None:
    assert word_count("  a  b   c ") == 3
    assert word_count("") == 0


def test_dedup_key_is_stable_and_label_sensitive() -> None:
    assert dedup_key("a forest article", "311") == dedup_key("a forest article", "311")
    assert dedup_key("a forest article", "311") != dedup_key("a forest article", "312")


def test_dedup_key_ignores_whitespace_only_differences() -> None:
    assert dedup_key("a  forest\narticle", "311") == dedup_key("a forest article", "311")


def test_dedup_key_does_not_collide_across_a_field_boundary() -> None:
    # "ab"+"c" and "a"+"bc" must not hash alike.
    assert dedup_key("ab", "c") != dedup_key("a", "bc")

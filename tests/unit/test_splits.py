"""Geographically disjoint split assignment via H3 cells."""

import pytest

from osm_wikidata_worldcover.domain.splits import (
    DEFAULT_RATIOS,
    DEFAULT_RESOLUTION,
    Split,
    SplitRatios,
    assign_cell,
    cell_for,
)

ANDORRA = (42.4954, 1.5169)


def test_cell_for_is_deterministic() -> None:
    assert cell_for(*ANDORRA) == cell_for(*ANDORRA)


def test_nearby_points_share_a_cell_and_therefore_a_split() -> None:
    a = cell_for(42.4954, 1.5169)
    b = cell_for(42.4960, 1.5175)  # ~80 m away
    assert a == b
    assert assign_cell(a) is assign_cell(b)


def test_distant_points_do_not_share_a_cell() -> None:
    assert cell_for(*ANDORRA) != cell_for(52.52, 13.405)  # Berlin


def test_assignment_is_deterministic_for_a_given_seed() -> None:
    cell = cell_for(*ANDORRA)
    assert assign_cell(cell, seed=7) is assign_cell(cell, seed=7)


def test_seed_changes_the_partition() -> None:
    cells = [cell_for(40 + i * 0.5, 2 + i * 0.5) for i in range(60)]
    assert [assign_cell(c, seed=1) for c in cells] != [assign_cell(c, seed=2) for c in cells]


def test_ratios_are_approximately_honoured_over_many_cells() -> None:
    cells = [cell_for(36 + (i % 180) * 0.15, -9 + (i // 180) * 0.15) for i in range(4000)]
    splits = [assign_cell(c) for c in set(cells)]
    n = len(splits)
    train = splits.count(Split.TRAIN) / n
    assert DEFAULT_RATIOS.train - 0.05 < train < DEFAULT_RATIOS.train + 0.05
    assert set(splits) == set(Split)


def test_default_resolution_and_ratios_are_declared() -> None:
    assert DEFAULT_RESOLUTION == 5
    assert DEFAULT_RATIOS.train + DEFAULT_RATIOS.validation + DEFAULT_RATIOS.test == 1.0


def test_ratios_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        SplitRatios(0.5, 0.2, 0.2)


@pytest.mark.parametrize(("lat", "lon"), [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
def test_out_of_range_coordinates_are_rejected(lat: float, lon: float) -> None:
    with pytest.raises(ValueError):
        cell_for(lat, lon)


def test_nan_coordinates_are_rejected() -> None:
    with pytest.raises(ValueError):
        cell_for(float("nan"), 0.0)

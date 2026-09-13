"""Geographically blocked train/validation/test assignment.

Splitting by example would let an article about a place land in train while a
second article about the *same* place lands in test. Splitting by H3 cell
blocks whole neighbourhoods into one split instead, so a model cannot memorise
a location from one split and be scored on it in another.

Assignment hashes the cell id, so it depends on neither iteration order nor how
many polygons a cell happens to contain, and is reproducible from the seed
alone.
"""

import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from typing import Final

import h3

__all__ = [
    "DEFAULT_RATIOS",
    "DEFAULT_RESOLUTION",
    "DEFAULT_SEED",
    "Split",
    "SplitRatios",
    "assign_cell",
    "cell_for",
]

#: H3 resolution 5 cells average ~252 km2 (~8 km across): large enough that
#: "nearby" polygons share a cell, small enough for thousands of blocks.
DEFAULT_RESOLUTION: Final[int] = 5
DEFAULT_SEED: Final[int] = 20180101

_HASH_SPACE: Final[float] = float(1 << 64)


class Split(Enum):
    """One of the three dataset partitions."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


@dataclass(frozen=True, slots=True)
class SplitRatios:
    """Target share of *cells* per split. Shares must sum to one."""

    train: float
    validation: float
    test: float

    def __post_init__(self) -> None:
        total = self.train + self.validation + self.test
        if not math.isclose(total, 1.0):
            raise ValueError(f"split ratios must sum to 1.0, got {total!r}")
        if min(self.train, self.validation, self.test) < 0.0:
            raise ValueError("split ratios must be non-negative")


DEFAULT_RATIOS: Final[SplitRatios] = SplitRatios(0.8, 0.1, 0.1)


def cell_for(lat: float, lon: float, resolution: int = DEFAULT_RESOLUTION) -> str:
    """Return the H3 cell id containing ``(lat, lon)``."""
    _check_coordinate(lat, lon)
    return h3.latlng_to_cell(lat, lon, resolution)


def _check_coordinate(lat: float, lon: float) -> None:
    """Reject coordinates H3 cannot meaningfully place."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError(f"non-finite coordinate ({lat!r}, {lon!r})")
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude out of range: {lat!r}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"longitude out of range: {lon!r}")


def assign_cell(cell: str, ratios: SplitRatios = DEFAULT_RATIOS, seed: int = DEFAULT_SEED) -> Split:
    """Return the split that ``cell`` -- and everything inside it -- belongs to."""
    position = _unit_hash(cell, seed)
    if position < ratios.train:
        return Split.TRAIN
    if position < ratios.train + ratios.validation:
        return Split.VALIDATION
    return Split.TEST


def _unit_hash(cell: str, seed: int) -> float:
    """Map ``cell`` to a reproducible value in ``[0, 1)``."""
    digest = hashlib.sha256(f"{seed}:{cell}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / _HASH_SPACE

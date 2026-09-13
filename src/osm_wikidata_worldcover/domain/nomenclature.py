"""ESA WorldCover land-cover nomenclature.

WorldCover v200 (2021) classifies every 10 m pixel into one of 11 classes.
The codes are the raster's own pixel values and are deliberately
non-sequential -- 95 and 100 sit outside the otherwise regular step of 10 --
so they are kept exactly as the product defines them rather than re-indexed.

``0`` is the product's no-data value. It is not a class and must never become
a target label.
"""

from types import MappingProxyType
from typing import Final

__all__ = [
    "CLASS_LABELS",
    "NODATA",
    "UnknownLandCoverCodeError",
    "is_valid_code",
    "label_for",
]

#: Pixel value marking "no observation", not a land-cover class.
NODATA: Final[int] = 0


class UnknownLandCoverCodeError(KeyError):
    """Raised when a code is not one of the 11 WorldCover classes."""


CLASS_LABELS: Final[MappingProxyType[int, str]] = MappingProxyType(
    {
        10: "Tree cover",
        20: "Shrubland",
        30: "Grassland",
        40: "Cropland",
        50: "Built-up",
        60: "Bare / sparse vegetation",
        70: "Snow and ice",
        80: "Permanent water bodies",
        90: "Herbaceous wetland",
        95: "Mangroves",
        100: "Moss and lichen",
    }
)


def is_valid_code(code: int) -> bool:
    """Return whether ``code`` is one of the 11 WorldCover classes."""
    return code in CLASS_LABELS


def label_for(code: int) -> str:
    """Return the class label for ``code``."""
    try:
        return CLASS_LABELS[code]
    except KeyError:
        raise UnknownLandCoverCodeError(code) from None

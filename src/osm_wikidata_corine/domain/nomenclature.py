"""CORINE Land Cover nomenclature.

The CLC vector product labels each polygon with a three-digit level-3 code
(``Code_18`` for the 2018 edition). Levels 1 and 2 are the one- and two-digit
prefixes of that code, so only the level-3 table carries information; the
coarser tables exist to give those prefixes human-readable labels.

Codes outside the 44 thematic classes -- CLC's ``990``/``995``/``999``
placeholders for unclassified or no-data surfaces -- are deliberately absent.
They are not land-cover observations and must never become a target label.
"""

from types import MappingProxyType
from typing import Final

__all__ = [
    "LEVEL1_LABELS",
    "LEVEL2_LABELS",
    "LEVEL3_LABELS",
    "UnknownCorineCode",
    "is_valid_code",
    "label_for",
    "level1_code",
    "level1_label",
    "level2_code",
    "level2_label",
]


class UnknownCorineCode(KeyError):
    """Raised when a code is not one of the 44 CLC level-3 classes."""


LEVEL1_LABELS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "1": "Artificial surfaces",
        "2": "Agricultural areas",
        "3": "Forest and semi natural areas",
        "4": "Wetlands",
        "5": "Water bodies",
    }
)

LEVEL2_LABELS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "11": "Urban fabric",
        "12": "Industrial, commercial and transport units",
        "13": "Mine, dump and construction sites",
        "14": "Artificial, non-agricultural vegetated areas",
        "21": "Arable land",
        "22": "Permanent crops",
        "23": "Pastures",
        "24": "Heterogeneous agricultural areas",
        "31": "Forests",
        "32": "Scrub and/or herbaceous vegetation associations",
        "33": "Open spaces with little or no vegetation",
        "41": "Inland wetlands",
        "42": "Maritime wetlands",
        "51": "Inland waters",
        "52": "Marine waters",
    }
)

LEVEL3_LABELS: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "111": "Continuous urban fabric",
        "112": "Discontinuous urban fabric",
        "121": "Industrial or commercial units",
        "122": "Road and rail networks and associated land",
        "123": "Port areas",
        "124": "Airports",
        "131": "Mineral extraction sites",
        "132": "Dump sites",
        "133": "Construction sites",
        "141": "Green urban areas",
        "142": "Sport and leisure facilities",
        "211": "Non-irrigated arable land",
        "212": "Permanently irrigated land",
        "213": "Rice fields",
        "221": "Vineyards",
        "222": "Fruit trees and berry plantations",
        "223": "Olive groves",
        "231": "Pastures",
        "241": "Annual crops associated with permanent crops",
        "242": "Complex cultivation patterns",
        "243": (
            "Land principally occupied by agriculture, with significant areas of natural vegetation"
        ),
        "244": "Agro-forestry areas",
        "311": "Broad-leaved forest",
        "312": "Coniferous forest",
        "313": "Mixed forest",
        "321": "Natural grasslands",
        "322": "Moors and heathland",
        "323": "Sclerophyllous vegetation",
        "324": "Transitional woodland-shrub",
        "331": "Beaches, dunes, sands",
        "332": "Bare rocks",
        "333": "Sparsely vegetated areas",
        "334": "Burnt areas",
        "335": "Glaciers and perpetual snow",
        "411": "Inland marshes",
        "412": "Peat bogs",
        "421": "Salt marshes",
        "422": "Salines",
        "423": "Intertidal flats",
        "511": "Water courses",
        "512": "Water bodies",
        "521": "Coastal lagoons",
        "522": "Estuaries",
        "523": "Sea and ocean",
    }
)


def is_valid_code(code: str) -> bool:
    """Return whether ``code`` is one of the 44 CLC level-3 classes."""
    return code in LEVEL3_LABELS


def label_for(code: str) -> str:
    """Return the level-3 label for ``code``."""
    try:
        return LEVEL3_LABELS[code]
    except KeyError:
        raise UnknownCorineCode(code) from None


def level1_code(code: str) -> str:
    """Return the level-1 code (first digit) of a valid level-3 ``code``."""
    return _checked(code)[:1]


def level2_code(code: str) -> str:
    """Return the level-2 code (first two digits) of a valid level-3 ``code``."""
    return _checked(code)[:2]


def level1_label(code: str) -> str:
    """Return the level-1 label of a valid level-3 ``code``."""
    return LEVEL1_LABELS[level1_code(code)]


def level2_label(code: str) -> str:
    """Return the level-2 label of a valid level-3 ``code``."""
    return LEVEL2_LABELS[level2_code(code)]


def _checked(code: str) -> str:
    if code not in LEVEL3_LABELS:
        raise UnknownCorineCode(code)
    return code

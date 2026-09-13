"""Fetch ESA WorldCover tiles and measure class coverage per polygon.

Coverage is expressed as a share of the **polygon's own area**, never of the
area that happened to be observed. WorldCover marks unobserved pixels as
no-data, and renormalising over the observed ones would label a polygon that
is mostly ocean, or mostly off the edge of a tile, with full confidence. Here
the unobserved part simply goes unattributed, so the shares sum to less than
one and the dominance rule can refuse the polygon.

Because shares are relative to the polygon, contributions from several tiles
add up directly: a polygon straddling a tile boundary needs no mosaic, just
the sum over the tiles it touches.
"""

import math
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from exactextract import exact_extract

from osm_wikidata_worldcover.domain.tiling import Tile

__all__ = ["DEFAULT_BASE_URL", "TileNotPublishedError", "WorldCoverTiles", "class_coverage"]

DEFAULT_BASE_URL: Final[str] = "https://esa-worldcover.s3.eu-central-1.amazonaws.com"

#: exactextract operations: the distinct values, their share of the observed
#: area, and the observed area itself in (fractional) cells.
_OPS: Final[Sequence[str]] = ("unique", "frac", "count")


class TileNotPublishedError(FileNotFoundError):
    """Raised for a tile the product does not publish (open ocean, mostly)."""


class WorldCoverTiles:
    """Addresses, downloads and caches WorldCover tiles.

    Tiles are ~94 MB each and a global run touches thousands of them, so the
    cache is meant to be transient: fetch a tile, use it, then ``discard`` it.
    """

    def __init__(
        self,
        cache_dir: Path,
        version: str = "v200",
        year: int = 2021,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.version = version
        self.year = year
        self.base_url = base_url.rstrip("/")

    def filename_for(self, tile: Tile) -> str:
        """The product's own filename for ``tile``."""
        return f"ESA_WorldCover_10m_{self.year}_{self.version}_{tile.name}_Map.tif"

    def url_for(self, tile: Tile) -> str:
        """The published URL for ``tile``."""
        return f"{self.base_url}/{self.version}/{self.year}/map/{self.filename_for(tile)}"

    def path_for(self, tile: Tile) -> Path:
        """Where ``tile`` is cached locally."""
        return self.cache_dir / self.filename_for(tile)

    def ensure(self, tile: Tile) -> Path:
        """Return a local path to ``tile``, downloading it if absent.

        Raises :class:`TileNotPublishedError` for tiles the product omits.
        """
        path = self.path_for(tile)
        if path.exists() and path.stat().st_size > 0:
            return path
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # Download beside the target and rename, so an interrupted run never
        # leaves a truncated tile that a later run would trust.
        partial = path.with_suffix(path.suffix + ".part")
        try:
            urllib.request.urlretrieve(self.url_for(tile), partial)
        except urllib.error.HTTPError as exc:
            partial.unlink(missing_ok=True)
            if exc.code == 404:
                raise TileNotPublishedError(f"{tile.name} is not published") from exc
            raise
        partial.rename(path)
        return path

    def discard(self, tile: Tile) -> None:
        """Delete the cached copy of ``tile``, if any."""
        self.path_for(tile).unlink(missing_ok=True)


def class_coverage(raster_paths: Iterable[Path], frame: gpd.GeoDataFrame) -> list[dict[int, float]]:
    """Return, per row of ``frame``, each class's share of that row's area.

    Shares are relative to the polygon's own area, so they sum to at most one
    and fall short wherever the polygon was not observed. Contributions from
    multiple non-overlapping rasters are summed.
    """
    if len(frame) == 0:
        return []

    totals: list[defaultdict[int, float]] = [defaultdict(float) for _ in range(len(frame))]
    # Areas are measured in the raster's own planar units, for both the cells
    # and the polygons. Only their ratio is used, so it is exact even though
    # the units are degrees and a degree is not a constant ground distance.
    areas = shapely.area(frame.geometry.to_numpy())

    for path in raster_paths:
        _add_raster(totals, path, frame, areas)

    return [dict(sorted(total.items())) for total in totals]


def _add_raster(
    totals: list[defaultdict[int, float]],
    path: Path,
    frame: gpd.GeoDataFrame,
    areas: np.ndarray,
) -> None:
    """Add one raster's contribution to every polygon's running totals."""
    with rasterio.open(path) as dataset:
        cell_area = abs(dataset.transform.a * dataset.transform.e)
    result = exact_extract(str(path), frame, list(_OPS), output="pandas")
    for index, (values, shares, observed) in enumerate(
        zip(result["unique"], result["frac"], result["count"], strict=True)
    ):
        _accumulate(totals[index], values, shares, observed, cell_area, areas[index])


def _accumulate(
    into: defaultdict[int, float],
    values: Iterable[float],
    shares: Iterable[float],
    observed_cells: float,
    cell_area: float,
    polygon_area: float,
) -> None:
    """Convert shares-of-observed into shares-of-polygon and add them to ``into``."""
    observed_share = _observed_share(observed_cells, cell_area, polygon_area)
    if observed_share is None:
        return
    for value, share in zip(values, shares, strict=True):
        contribution = float(share) * observed_share
        if contribution > 0.0:
            into[int(value)] += contribution


def _observed_share(observed_cells: float, cell_area: float, polygon_area: float) -> float | None:
    """What share of the polygon the raster actually observed, or ``None``.

    exactextract reports NaN for a polygon that never met the raster, so a
    non-finite count means no observation rather than a bad measurement.
    """
    if polygon_area <= 0.0 or not math.isfinite(observed_cells) or observed_cells <= 0.0:
        return None
    return float(observed_cells) * cell_area / polygon_area

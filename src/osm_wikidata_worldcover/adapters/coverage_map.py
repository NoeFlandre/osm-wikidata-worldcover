"""Render a static map of the ESA-labelled polygons in a release."""

from pathlib import Path
from typing import Final

import duckdb
import geopandas as gpd
import pandas as pd

from osm_wikidata_worldcover.domain.manifest import SPLIT_ORDER
from osm_wikidata_worldcover.domain.nomenclature import CLASS_LABELS

__all__ = [
    "CLASS_COLORS",
    "MAP_FILENAME",
    "CoverageMapError",
    "centroids_from_build",
    "write_coverage_map",
]

MAP_FILENAME: Final = "worldcover_centroids.png"
_WORLD_LAND_URL: Final = (
    "https://naturalearth.s3.amazonaws.com/110m_physical/ne_110m_land.zip"
)
CLASS_COLORS: Final[dict[int, str]] = {
    10: "#006400",
    20: "#ffbb22",
    30: "#ffff4c",
    40: "#f096ff",
    50: "#fa0000",
    60: "#b4b4b4",
    70: "#f0f0f0",
    80: "#0064c8",
    90: "#0096a0",
    95: "#00cf75",
    100: "#fae6a0",
}


class CoverageMapError(ValueError):
    """The release cannot be represented by a valid centroid map."""


def centroids_from_build(build_dir: Path) -> pd.DataFrame:
    """Return one validated ESA-labelled centroid row per polygon."""
    build_dir = Path(build_dir)
    paths = [build_dir / f"{split}.parquet" for split in SPLIT_ORDER]
    missing = [path.name for path in paths if not path.exists()]
    if missing:
        raise CoverageMapError(f"build is missing Parquet split(s): {missing}")

    source = _read_parquets_sql(paths)
    connection = duckdb.connect()
    try:
        connection.execute("PRAGMA disable_progress_bar")
        connection.execute(f"CREATE TEMP VIEW coverage_rows AS {source}")
        _validate_rows(connection)
        conflicts = connection.execute(
            """
            SELECT polygon_id
            FROM coverage_rows
            GROUP BY polygon_id
            HAVING count(DISTINCT worldcover_code) > 1
                OR count(DISTINCT worldcover_label) > 1
                OR count(DISTINCT lat) > 1
                OR count(DISTINCT lon) > 1
            ORDER BY polygon_id
            LIMIT 5
            """
        ).fetchall()
        if conflicts:
            examples = [str(row[0]) for row in conflicts]
            raise CoverageMapError(f"conflicting polygon labels or coordinates: {examples}")

        frame = connection.execute(
            """
            SELECT
                polygon_id,
                min(lat) AS lat,
                min(lon) AS lon,
                min(worldcover_code)::INTEGER AS worldcover_code,
                min(worldcover_label) AS worldcover_label
            FROM coverage_rows
            GROUP BY polygon_id
            ORDER BY polygon_id
            """
        ).fetch_df()
    finally:
        connection.close()

    if frame.empty:
        raise CoverageMapError("no ESA-labelled polygons found in the release")
    _validate_labels(frame)
    return frame


def write_coverage_map(
    build_dir: Path,
    output_path: Path,
    *,
    land: gpd.GeoDataFrame | None = None,
) -> int:
    """Render the release centroid map and return its unique-polygon count."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    frame = centroids_from_build(build_dir)
    if land is None:
        land = _load_land()
    if land.crs is None:
        raise CoverageMapError("world land outline has no coordinate reference system")
    land = land.to_crs("EPSG:4326")

    figure, axis = plt.subplots(figsize=(18, 10), dpi=150)
    try:
        land.plot(
            ax=axis,
            color="#edf2f7",
            edgecolor="#a0aec0",
            linewidth=0.25,
        )
        for code in CLASS_LABELS:
            points = frame[frame["worldcover_code"] == code]
            if not points.empty:
                axis.scatter(
                    points["lon"],
                    points["lat"],
                    s=1.8,
                    alpha=0.32,
                    color=CLASS_COLORS[code],
                    linewidths=0,
                    rasterized=True,
                )

        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=CLASS_COLORS[code],
                markeredgecolor="#4a5568",
                markeredgewidth=0.25,
                markersize=6,
                label=f"{code} {label} ({(frame['worldcover_code'] == code).sum():,})",
            )
            for code, label in CLASS_LABELS.items()
        ]
        axis.set_xlim(-180, 180)
        axis.set_ylim(-90, 90)
        axis.set_xlabel("Longitude")
        axis.set_ylabel("Latitude")
        axis.set_title("ESA WorldCover labels of OSM polygons")
        axis.set_axisbelow(True)
        axis.grid(color="#cbd5e0", linewidth=0.35, alpha=0.7)
        figure.legend(
            handles=handles,
            loc="lower center",
            ncol=3,
            bbox_to_anchor=(0.5, 0.035),
            frameon=False,
            fontsize=8,
        )
        figure.text(
            0.5,
            0.008,
            f"{len(frame):,} distinct polygons; each point is a polygon centroid, not a boundary",
            ha="center",
            fontsize=9,
            color="#4a5568",
        )
        figure.tight_layout(rect=(0, 0.14, 1, 1))
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, format="png", bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)
    return len(frame)


def _read_parquets_sql(paths: list[Path]) -> str:
    quoted = ", ".join(f"'{str(path).replace(chr(39), chr(39) * 2)}'" for path in paths)
    return f"""
        SELECT
            CAST(polygon_id AS VARCHAR) AS polygon_id,
            CAST(lat AS DOUBLE) AS lat,
            CAST(lon AS DOUBLE) AS lon,
            CAST(worldcover_code AS INTEGER) AS worldcover_code,
            CAST(worldcover_label AS VARCHAR) AS worldcover_label
        FROM read_parquet([{quoted}], union_by_name = true)
        WHERE worldcover_code IS NOT NULL AND worldcover_label IS NOT NULL
    """


def _validate_rows(connection: duckdb.DuckDBPyConnection) -> None:
    result = connection.execute(
        """
        SELECT
            count(*) FILTER (WHERE polygon_id IS NULL OR polygon_id = ''),
            count(*) FILTER (
                WHERE lat IS NULL OR lon IS NULL
                    OR NOT isfinite(lat) OR NOT isfinite(lon)
                    OR lat < -90 OR lat > 90 OR lon < -180 OR lon > 180
            )
        FROM coverage_rows
        """
    ).fetchone()
    if result is None:
        raise CoverageMapError("could not inspect labelled release rows")
    missing, invalid = result
    if missing:
        raise CoverageMapError(f"{missing} labelled rows have no polygon ID")
    if invalid:
        raise CoverageMapError(f"{invalid} labelled rows have invalid coordinates")


def _validate_labels(frame: pd.DataFrame) -> None:
    unknown = sorted(
        {int(code) for code in frame["worldcover_code"] if int(code) not in CLASS_LABELS}
    )
    if unknown:
        raise CoverageMapError(f"unknown WorldCover code(s): {unknown}")
    mismatches = [
        (int(code), str(label))
        for code, label in zip(
            frame["worldcover_code"], frame["worldcover_label"], strict=True
        )
        if CLASS_LABELS[int(code)] != label
    ]
    if mismatches:
        raise CoverageMapError(f"WorldCover code/label pair does not match: {mismatches[:5]}")


def _load_land() -> gpd.GeoDataFrame:
    try:
        land = gpd.read_file(_WORLD_LAND_URL)
    except Exception as exc:
        raise CoverageMapError("could not load the Natural Earth world land outline") from exc
    if land.empty:
        raise CoverageMapError("Natural Earth world land outline is empty")
    return land

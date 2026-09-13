"""Write a finished build to disk.

Output is versioned: each build lands in its own ``v<version>`` directory
alongside its manifest, so an older dataset is never silently overwritten by a
newer one and both can be compared.

Parquet is written without compression metadata that varies between runs, so
rebuilding the same data yields byte-identical files -- the cheapest possible
check that a pipeline change altered nothing it should not have.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from osm_wikidata_worldcover.domain.manifest import SPLIT_ORDER

__all__ = ["MANIFEST_NAME", "read_manifest", "write_dataset"]

MANIFEST_NAME = "manifest.json"


def write_dataset(
    frame: pd.DataFrame, manifest: Mapping[str, Any], out_dir: Path, version: str
) -> list[Path]:
    """Write every split of ``frame`` and ``manifest`` under ``out_dir/v<version>``.

    Splitting happens on the frame's own ``split`` column, so the writer needs
    to know nothing about how that column was decided.
    """
    target = Path(out_dir) / f"v{version}"
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for split in SPLIT_ORDER:
        path = target / f"{split}.parquet"
        rows = (
            frame[frame["split"] == split].reset_index(drop=True)
            if "split" in frame.columns
            else frame
        )
        # store_schema=False keeps pandas' own metadata -- which embeds index
        # bookkeeping -- out of the file, so equal data means equal bytes.
        pq.write_table(
            pa.Table.from_pandas(rows, preserve_index=False),
            path,
            compression="zstd",
            store_schema=False,
        )
        written.append(path)

    manifest_path = target / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n")
    written.append(manifest_path)
    return written


def read_manifest(build_dir: Path) -> dict:
    """Read the manifest written beside a build."""
    path = Path(build_dir) / MANIFEST_NAME
    if not path.exists():
        raise FileNotFoundError(f"no manifest in {build_dir}")
    return json.loads(path.read_text())

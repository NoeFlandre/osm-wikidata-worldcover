"""Publish a finished build to the Hugging Face Hub.

The dataset card is regenerated from the build's own manifest immediately
before upload, so the published description cannot describe a different build
than the one being uploaded.
"""

import json
from pathlib import Path

from huggingface_hub import HfApi

from osm_wikidata_worldcover.domain.card import render
from osm_wikidata_worldcover.domain.manifest import SPLIT_ORDER

__all__ = ["files_to_publish", "publish_dataset"]

MANIFEST_NAME = "manifest.json"


def files_to_publish(build_dir: Path) -> list[Path]:
    """Return the files that make up a publishable build."""
    build_dir = Path(build_dir)
    splits = [build_dir / f"{name}.parquet" for name in SPLIT_ORDER]
    missing = [p.name for p in splits if not p.exists()]
    if missing:
        raise FileNotFoundError(f"{build_dir} is missing {missing}")
    manifest = build_dir / MANIFEST_NAME
    if not manifest.exists():
        raise FileNotFoundError(f"{build_dir} has no {MANIFEST_NAME}")
    return [*splits, manifest]


def publish_dataset(
    build_dir: Path,
    repo_id: str,
    private: bool = False,
    token: str | None = None,
) -> str:
    """Upload ``build_dir`` to ``repo_id`` and return the dataset URL."""
    build_dir = Path(build_dir)
    files_to_publish(build_dir)

    manifest = json.loads((build_dir / MANIFEST_NAME).read_text())
    (build_dir / "README.md").write_text(render(manifest))

    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)
    api.upload_folder(
        folder_path=str(build_dir),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Publish osm-wikidata-worldcover build",
    )
    return f"https://huggingface.co/datasets/{repo_id}"

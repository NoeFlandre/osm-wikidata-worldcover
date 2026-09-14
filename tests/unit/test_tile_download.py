"""Tile caching and download behaviour, without touching the network."""

import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from osm_worldcover.adapters import worldcover as wc
from osm_worldcover.adapters.worldcover import (
    TileNotPublishedError,
    WorldCoverTiles,
)
from osm_worldcover.domain.tiling import Tile

TILE = Tile(48, 6)


def fake_retrieve(payload: bytes = b"tif"):
    def _retrieve(url: str, target: str) -> None:
        Path(target).write_bytes(payload)

    return _retrieve


def test_an_absent_tile_is_downloaded(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wc.urllib.request, "urlretrieve", fake_retrieve())
    path = WorldCoverTiles(tmp_path).ensure(TILE)
    assert path.exists()
    assert path.read_bytes() == b"tif"


def test_a_cached_tile_is_not_downloaded_again(tmp_path, monkeypatch) -> None:
    tiles = WorldCoverTiles(tmp_path)
    monkeypatch.setattr(wc.urllib.request, "urlretrieve", fake_retrieve())
    tiles.ensure(TILE)

    def explode(*_args, **_kwargs):
        raise AssertionError("should not download a cached tile")

    monkeypatch.setattr(wc.urllib.request, "urlretrieve", explode)
    assert tiles.ensure(TILE).exists()


def test_an_empty_cached_file_is_treated_as_absent(tmp_path, monkeypatch) -> None:
    """A zero-byte file is the fingerprint of an interrupted download."""
    tiles = WorldCoverTiles(tmp_path)
    tiles.path_for(TILE).parent.mkdir(parents=True, exist_ok=True)
    tiles.path_for(TILE).write_bytes(b"")
    monkeypatch.setattr(wc.urllib.request, "urlretrieve", fake_retrieve(b"real"))
    assert tiles.ensure(TILE).read_bytes() == b"real"


def test_an_unpublished_tile_raises(tmp_path, monkeypatch) -> None:
    def not_found(url: str, target: str):
        raise urllib.error.HTTPError(url, 404, "Not Found", Message(), None)

    monkeypatch.setattr(wc.urllib.request, "urlretrieve", not_found)
    with pytest.raises(TileNotPublishedError):
        WorldCoverTiles(tmp_path).ensure(TILE)


def test_other_http_errors_are_not_swallowed(tmp_path, monkeypatch) -> None:
    def server_error(url: str, target: str):
        raise urllib.error.HTTPError(url, 500, "Server Error", Message(), None)

    monkeypatch.setattr(wc.urllib.request, "urlretrieve", server_error)
    with pytest.raises(urllib.error.HTTPError):
        WorldCoverTiles(tmp_path).ensure(TILE)


def test_a_failed_download_leaves_no_partial_file(tmp_path, monkeypatch) -> None:
    def not_found(url: str, target: str):
        Path(target).write_bytes(b"half")
        raise urllib.error.HTTPError(url, 404, "Not Found", Message(), None)

    monkeypatch.setattr(wc.urllib.request, "urlretrieve", not_found)
    tiles = WorldCoverTiles(tmp_path)
    with pytest.raises(TileNotPublishedError):
        tiles.ensure(TILE)
    assert list(tmp_path.iterdir()) == []


def test_discard_releases_a_tile_for_eviction(tmp_path, monkeypatch) -> None:
    """Discard releases rather than deletes; see test_tile_cache for eviction."""
    monkeypatch.setattr(wc.urllib.request, "urlretrieve", fake_retrieve())
    tiles = WorldCoverTiles(tmp_path, max_cached_tiles=0)
    tiles.ensure(TILE)
    tiles.discard(TILE)
    assert not tiles.path_for(TILE).exists()


def test_discarding_an_absent_tile_is_harmless(tmp_path) -> None:
    WorldCoverTiles(tmp_path).discard(TILE)

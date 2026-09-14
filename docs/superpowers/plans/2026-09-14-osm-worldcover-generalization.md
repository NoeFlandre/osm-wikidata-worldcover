# osm-worldcover Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the project to `osm-worldcover` and make one reproducible pipeline produce the existing Wikidata WorldCover dataset plus description-tag and website-tag datasets.

**Architecture:** Source recipes normalize each repository into the existing canonical region tables. Pure domain logic and WorldCover processing remain shared; source-specific I/O, geometry decoding, text extraction, card metadata, and HF publication settings stay in adapters/configuration.

**Tech Stack:** uv, Python 3.12, pandas/GeoPandas/Shapely/PyArrow, Typer, pytest/pytest-bdd/Hypothesis, Ruff, ty, import-linter, CRAP, mutmut, Docker, MkDocs, Hugging Face Hub.

---

### Task 1: Establish source contracts with tests

**Files:**
- Create: `tests/unit/test_sources.py`
- Modify: `tests/unit/test_hub.py`
- Modify: `tests/unit/test_config.py`

- [x] Add failing tests for the three source recipes, source-specific region paths, description WKB normalization, localized descriptions, and website/contact documents.
- [x] Run the focused tests and confirm they fail because the generic source contract is absent.

### Task 2: Implement the generic source registry and adapters

**Files:**
- Create: `src/osm_worldcover/sources.py`
- Modify: `src/osm_worldcover/config.py`
- Modify: `src/osm_worldcover/adapters/source.py`
- Modify: `src/osm_worldcover/adapters/hub.py`
- Modify: `src/osm_worldcover/build.py`
- Modify: `src/osm_worldcover/pipeline.py`

- [x] Add named recipes with source dataset IDs and derived output IDs.
- [x] Normalize each source into canonical polygon/link/document tables.
- [x] Make region discovery, download, cleanup, and build orchestration recipe-aware.
- [x] Run the focused tests and confirm they pass.

### Task 3: Generalize cards and publication metadata

**Files:**
- Modify: `src/osm_worldcover/domain/card.py`
- Modify: `src/osm_worldcover/adapters/publish.py`
- Modify: `src/osm_worldcover/domain/manifest.py`
- Modify: `tests/unit/test_card.py`
- Modify: `tests/unit/test_publish.py`

- [x] Generate source-specific titles, load instructions, provenance links, tags, and licensing caveats while retaining the map and deterministic named examples.
- [x] Test all three card recipes and the generic publication commit message.

### Task 4: Rename the repository/package and user-facing surfaces

**Files:**
- Rename: `src/osm_worldcover/` to `src/osm_worldcover/`
- Modify: `pyproject.toml`, `uv.lock`, `.importlinter`, `README.md`, `docs/`, `Dockerfile`, `.github/workflows/ci.yml`, and all tests/imports.

- [x] Rename package, distribution, CLI, Docker image, docs, badges, and GitHub links to `osm-worldcover`; retain only the historical Wikidata HF dataset ID where required.
- [x] Regenerate the lockfile and run packaging/import smoke tests.

### Task 5: Full verification and publication

- [ ] Run baseline → Ruff → ty → unit/property/acceptance tests → architecture → CRAP → mutation → Docker smoke → diff review.
- [ ] Build representative deterministic releases for all three recipes and inspect cards/maps/Parquet schemas.
- [ ] Rename the GitHub repository and update the remote.
- [ ] Create and publish the two new public HF dataset repositories.
- [ ] Verify each Dataset Viewer config/split/rows/schema and verify the existing Wikidata HF dataset was not modified.

# ADR 0003: Split on H3 cells, not on rows

**Status:** accepted — 2026-09-13

## Context

One place often has many articles — the same monument in twelve languages — and
neighbouring places share their surroundings, hence their land cover. Splitting
examples at random would put the English article about a church in train and the
German article about the same church in test. A model could score by recognising
the place, not by reading the text.

## Decision

Assign every example an **H3 resolution-5 cell** (~252 km², roughly 8 km across)
from its centroid, and assign the *cell* to a split by hashing its id with a
seed. Every row in a cell lands in the same split.

Ratios (80/10/10) are targets for **cells**, not rows, so realised row counts
drift from them — the more so for geographically concentrated builds.

## Consequences

- No polygon and no document can straddle a split. Both are checked as
  published guarantees in `domain/validation.py`, not merely assumed.
- The same OSM object appearing in two overlapping Geofabrik extracts shares a
  centroid, hence a cell, hence a split — so regional overlap cannot leak even
  before de-duplication removes it.
- Assignment depends only on the cell id and the seed, so it is reproducible
  and independent of iteration order or how many rows a cell holds.
- **Residual weakness:** two polygons a metre apart on opposite sides of a cell
  boundary can still land in different splits. Resolution 5 keeps this to a
  small perimeter effect rather than eliminating it; see
  `docs/technical-debt.md`.

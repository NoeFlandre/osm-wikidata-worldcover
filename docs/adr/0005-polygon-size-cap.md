# ADR 0005: Refuse continent-scale polygons

**Status:** accepted — 2026-09-13

## Context

The first global build stalled on Angola. The cause was a single polygon:
Angola itself, 1.25 million km². At 10 m that is ~10¹⁰ pixels spread across
roughly 20 WorldCover tiles — about 2 GB of download and minutes of computation
for **one row**. The largest polygon in the source is 10.2 million km², needing
~100 tiles and ~10¹¹ pixels.

Measured cost is mild up to a point and then dominated by tile count:

| polygon | pixels | zonal-stats time |
| --- | --- | --- |
| 100 km² | 10⁶ | 0.05 s |
| 1,000 km² | 10⁷ | 0.17 s |
| 10,000 km² | 10⁸ | 1.38 s |

Cost is linear in area, and a first attempt at a 100,000 km² cap was still too
generous: the run went CPU-bound on Algeria's provinces at ~14 s per polygon
while the network sat idle at 5% of its capacity.

## Decision

Refuse polygons whose source `area_m2` exceeds **10¹⁰ m² (10,000 km²)**,
screened *before* any tile is fetched. Configurable via `--max-area-km2`;
`None` disables it.

## Consequences

- Excludes **1,099 of 1,259,424** polygons — 0.087%.
- Bounds the worst-case polygon to ~10⁸ pixels, about 1.4 s.
- Bounds per-polygon cost to a handful of tiles, removing the stall.
- Rejections are counted as `too_large` and reported in the manifest, so the
  exclusion is visible rather than silent.
- Defensible on content as well as cost: a polygon this large is a country or
  continent, whose article describes history and governance rather than the
  ground beneath it, and no single land-cover class plausibly covers 80% of it.

## Alternatives considered

- **Read from the rasters' overviews** for large polygons. Correct in principle
  and would preserve those rows, but `exactextract` does not expose overview
  selection, so it would mean hand-rolling decimated reads and a second,
  lower-fidelity code path for 0.019% of the data.
- **No cap.** Rejected: ~450 GB of extra download for 238 rows that would
  almost all fail the dominance test anyway.

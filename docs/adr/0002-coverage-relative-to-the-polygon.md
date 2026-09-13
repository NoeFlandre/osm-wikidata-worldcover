# ADR 0002: Coverage is a share of the polygon, not of the observed area

**Status:** accepted — 2026-09-13

## Context

`exactextract` reports, for each polygon, the distinct raster values under it
and each one's share — normalised over the cells it actually read. Those shares
always sum to 1.0, even when most of the polygon was never observed: cells
outside the raster are not read at all, and WorldCover marks unobserved ground
with a no-data value that is masked out.

Taken at face value, a polygon 95% over open ocean and 5% over a wooded islet
would be reported as 100% `Tree cover` and sail through the 80% filter.

## Decision

Rescale every share by the fraction of the polygon that was actually observed:

```
share_of_polygon = share_of_observed x (observed_cells x cell_area / polygon_area)
```

Shares therefore sum to **at most** one, and the shortfall is exactly the
unobserved part. No-data is never emitted as a class.

## Consequences

- A polygon that was mostly not observed fails dominance and is refused, which
  is the honest outcome — the evidence for a label simply is not there.
- Shares are relative to the polygon, so contributions from different tiles
  **add**. A polygon straddling a tile boundary needs no mosaic or VRT, just a
  sum over the tiles it touches. This removed a whole class of machinery.
- Because the parts can no longer exceed the whole, coverage summing past 1.0
  means the caller double-counted — a real bug. `OverlappingCoverageError`
  fails loudly rather than clamping, which is how the duplicate-raster defect
  in `_fetch` was caught.
- Areas are measured in the raster's own planar units for both the cells and
  the polygon. Only their ratio is used, so the result is exact even though the
  units are degrees.

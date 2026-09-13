# ADR 0004: Stream WorldCover tiles rather than stage them

**Status:** accepted — 2026-09-13

## Context

WorldCover ships as 3°x3° GeoTIFFs of roughly 94 MB. The source polygons touch
**2,499** of them — about 229 GB. Staging that up front would dominate both the
runtime and the disk budget before a single polygon was labelled.

## Decision

Group polygons by the tiles they touch, then for each group: download the
tiles, label every polygon over them, and discard the tiles immediately.
Region shards are written to disk as they complete.

## Consequences

- Peak disk stays near a single tile instead of 229 GB; the 229 GB is
  bandwidth, not storage.
- Grouping means each tile is fetched once for all the polygons over it, rather
  than once per polygon.
- Per-region shards bound memory to one region and make the build resumable: an
  interrupted run skips whatever already finished. A region that produced no
  examples still writes a shard, because that is a finished result and without
  it every restart would retry the empty regions forever.
- Downloaded source tables are deleted once a region's shard is written; the
  full source snapshot is ~21 GB and is never needed twice.
- `--keep-tiles` retains them, which is worth it when repeatedly rebuilding one
  region.

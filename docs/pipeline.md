# How it works

## Shape

```text
cli  ->  build  ->  finalize  ->  pipeline  ->  adapters  ->  domain
```

Dependencies point one way only, and that is checked automatically by
`lint-imports` on every run. `domain/` is pure: no network, no filesystem, no
clock. Everything that touches the outside world lives in `adapters/`.

## A region at a time

A global run touches 2,499 WorldCover tiles, about 229 GB. Nothing is staged up
front (ADR 0004):

1. Download one region's polygons, links and documents.
2. Parse the geometries; drop the invalid ones and count them.
3. Group polygons by the tiles they touch.
4. For each group: fetch the tiles, measure coverage, discard the tiles.
5. Keep polygons one class dominates; join those to their articles.
6. Write the region's shard, then delete its downloaded tables.

Peak disk stays near a single tile. An interrupted run resumes by skipping
regions whose shard already exists.

## Measuring coverage

`exactextract` gives per-class shares of the area it actually read. Those are
rescaled by how much of the polygon was observed at all, so shares sum to *at
most* one and the shortfall is the unobserved part (ADR 0002).

That makes coverage additive across tiles, so a polygon straddling a tile
boundary is just a sum — no mosaic. It also means shares summing past one is a
real bug, and `OverlappingCoverageError` says so rather than clamping.

## Deciding the label

`domain/dominance.py` is the whole rule:

- Shares are taken against the **polygon's** area, never the observed area.
- No-data is not a class and can never win — but it still consumes the polygon,
  so a mostly-unobserved polygon is refused.
- The highest share wins; ties break on the lowest class code, so the result
  never depends on iteration order.
- Accepted only at or above the threshold (default 0.8).

## Assembling the dataset

Two different duplicates are removed. Geofabrik extracts overlap, so one OSM
object can appear under several `polygon_id`s — those collapse to one. Separately,
distinct objects can carry byte-identical text under the same label — those
collapse too.

Splits are assigned last, on H3 cells rather than rows (ADR 0003), then the
whole frame is re-validated before anything is written.

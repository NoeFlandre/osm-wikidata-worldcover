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

1. Download one region's polygons and source-specific text fields.
2. Parse the geometries; drop the invalid ones and count them.
3. Group polygons by the tiles they touch.
4. For each group: fetch the tiles, measure coverage, discard the tiles.
5. Keep polygons one class dominates; join those to their source text.
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

Three different problems are resolved, and conflating them would get at least
one wrong:

1. Geofabrik extracts overlap, so one OSM object appears under several
   `polygon_id`s. One region is chosen per object.
2. Distinct objects can carry byte-identical text under the same label.
3. One article can describe several distant places, which fall in different
   cells and so different splits. The split holding most of that document's
   rows keeps them; the rest are dropped, because moving them would break the
   geographic blocking.

### Nothing is held whole

A global build is several times the memory of the machine that produces it —
measured at 4.9 KB per row. So:

- row-local work (H3 cell, split, duplicate keys) happens **one shard at a
  time**, bounded by a single region;
- the global work — de-duplication and ordering — is left to **DuckDB over
  files**;
- each split is **streamed** from DuckDB to Parquet in Arrow batches;
- validation reads the written files **back** a batch at a time, so what is
  checked is what was actually published.

Rebuilding the same inputs still produces byte-identical files, which is the
cheapest check that none of this changed the data.

# osm-wikidata-worldcover

Build a supervised **text → land-cover** dataset: each example pairs a Wikipedia
or Wikivoyage article with the [ESA WorldCover](https://esa-worldcover.org/)
class that dominates the OpenStreetMap polygon the article describes.

```text
"El Parc Municipal de Ciutat de Luxemburg és un jardí públic urbà..."  ->  10  Tree cover
"Mosconi is an Italian restaurant located at 13 rue Munster..."        ->  50  Built-up
```

Source polygons and articles come from
[`NoeFlandre/osm-polygon-wikidata-and-wikipedia`](https://huggingface.co/datasets/NoeFlandre/osm-polygon-wikidata-and-wikipedia)
(1,259,424 polygons, 386 regions). Scope is **dataset construction only** — no
pretraining or fine-tuning lives here.

## How an example is made

1. Measure what share of each OSM polygon every WorldCover class covers.
2. Keep the polygon only if **one class covers ≥ 80%** of it.
3. Emit one row per `(polygon, document)` pair.
4. Drop empty, very short, and exactly duplicated text.
5. Split on H3 cells so nearby places never straddle train/validation/test.

## Use

```bash
uv sync

# one region, for a quick look
uv run oww build --region luxembourg-latest --out data/out

# everything (≈229 GB of tile traffic, streamed and discarded)
uv run oww build --out data/out --cache data/cache --cached-tiles 1500

# labelling is CPU-bound and single-threaded, so a global run can be split
# across processes by giving each a disjoint region list and its own cache,
# then assembling the shards once
uv run oww build --regions-file regions-a.txt --cache data/w0 --out data/w0/out
uv run oww build --regions-file regions-b.txt --cache data/w1 --out data/w1/out
uv run oww assemble data/w0/shards data/w1/shards --out data/out

uv run oww verify  data/out/v1.0.0     # re-check every guarantee
uv run oww info    data/out/v1.0.0     # class and language distribution
uv run oww publish data/out/v1.0.0 user/name
```

Docker:

```bash
docker build -t osm-wikidata-worldcover .
docker run --rm -v "$PWD/data:/data" osm-wikidata-worldcover \
  build --out /data/out --cache /data/cache
```

## Guarantees

Checked on every build; the build fails if any breaks.

- No polygon appears in more than one split.
- No document appears in more than one split.
- Every label is one of the 11 real WorldCover classes — never no-data.
- Every row's dominant class covers at least the threshold.
- No two rows share both text and label.
- Rebuilding the same inputs produces byte-identical files.

## Design

`domain/` is pure — no network, no filesystem, no clock. Everything that
touches the outside world is an adapter. Dependencies point one way and that is
enforced, not merely intended:

```text
cli  ->  build  ->  finalize  ->  pipeline  ->  adapters  ->  domain
```

Decisions and their trade-offs are in [`docs/adr/`](docs/adr); known weaknesses
are written down in [`docs/technical-debt.md`](docs/technical-debt.md). The most
important one: WorldCover classifies the ground in 10 m pixels, so the label
describes the area **containing** a feature, not the feature itself.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run ty check src/
uv run lint-imports                       # architecture boundaries
uv run pytest                             # unit, property, acceptance
uv run pytest --cov --cov-report=json -q && uv run python scripts/crap.py src
uv run mutmut run                         # mutation testing
uv run mkdocs serve                       # docs
```

CI runs the same gates and blocks merge on any failure.

## Licence

Code MIT. Article text is CC BY-SA 4.0, OpenStreetMap geometry ODbL, ESA
WorldCover CC BY 4.0.

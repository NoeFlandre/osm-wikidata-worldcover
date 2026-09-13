# osm-wikidata-worldcover

A supervised **text → land-cover** dataset. Each example pairs a Wikipedia or
Wikivoyage article with the ESA WorldCover class that dominates the OpenStreetMap
polygon the article describes.

```text
"El Parc Municipal de Ciutat de Luxemburg és un jardí públic urbà..."   ->  10  Tree cover
"Mosconi is an Italian restaurant located at 13 rue Munster..."         ->  50  Built-up
```

## What it is for

Training and evaluating models that infer physical land cover from free text,
across many languages. Scope is **dataset construction only** — no pretraining
or fine-tuning lives here.

## How an example is made

1. Take an OSM polygon and the articles linked to it, from
   [`NoeFlandre/osm-polygon-wikidata-and-wikipedia`](https://huggingface.co/datasets/NoeFlandre/osm-polygon-wikidata-and-wikipedia).
2. Measure what share of the polygon each WorldCover class covers.
3. Keep the polygon only if **one class covers at least 80%** of it.
4. Emit one example per `(polygon, document)` pair.
5. Split on H3 cells so nearby places never straddle train/validation/test.

## Guarantees

Every published build is checked against these, and the build fails if any breaks:

- No polygon appears in more than one split.
- No document appears in more than one split.
- Every label is one of the 11 real WorldCover classes — never no-data.
- Every row's dominant class covers at least the configured threshold.
- No two rows share both text and label.
- Rebuilding the same inputs produces byte-identical files.

## Quick start

```bash
uv sync
uv run oww build --region luxembourg-latest --out data/out
uv run oww verify data/out/v1.0.0
uv run oww info   data/out/v1.0.0
```

## Honesty about what the label means

WorldCover classifies the ground, and its pixels are 10 m. The label says what
covers the area **containing** a feature, not what the feature is made of — a
church is `Built-up` because its surroundings are. See
[Technical debt](technical-debt.md) for the full set of known weaknesses.

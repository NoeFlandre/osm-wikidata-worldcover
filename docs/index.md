# osm-worldcover

`osm-worldcover` turns OSM polygon-associated text into reproducible ESA
WorldCover land-cover datasets. One shared pipeline supports Wikidata-linked
Wikipedia/Wikivoyage text, OSM `description` tags, and OSM website tags.

The Wikidata release remains [`NoeFlandre/osm-wikidata-worldcover`](https://huggingface.co/datasets/NoeFlandre/osm-wikidata-worldcover).
The description and website recipes publish to their own Hugging Face dataset
repositories.

## Quick start

```bash
uv sync
uv run owc build --source wikidata --region luxembourg-latest --out data/out
uv run owc verify data/out/v1.0.0
uv run owc info data/out/v1.0.0
```

Use `--source description` or `--source website` to select another source.

## Global builds

Global runs are CPU-bound and single-threaded. Give each process disjoint region
lists and its own cache, then assemble the shards once:

```bash
uv run owc build --source website --regions-file regions-a.txt --cache data/w0 --out data/w0/out
uv run owc build --source website --regions-file regions-b.txt --cache data/w1 --out data/w1/out
uv run owc assemble data/w0/shards data/w1/shards --source website --out data/out
```

## Label meaning

WorldCover classifies the ground in 10 m pixels. The label says what covers the
area **containing** a feature, not what the feature is made of. See
[Technical debt](technical-debt.md) for known limitations.

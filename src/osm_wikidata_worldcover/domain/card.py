"""Render the Hugging Face dataset card from a build manifest.

Pure: the card is a function of the manifest alone, so the published
description can never drift from the data it describes.
"""

from collections.abc import Mapping
from typing import Any

__all__ = ["render"]

_HEADER = """---
license: cc-by-sa-4.0
language:
  - multilingual
tags:
  - land-cover
  - openstreetmap
  - wikipedia
  - geospatial
  - text-classification
task_categories:
  - text-classification
configs:
  - config_name: default
    data_files:
      - split: train
        path: train.parquet
      - split: validation
        path: validation.parquet
      - split: test
        path: test.parquet
---
"""


def render(manifest: Mapping[str, Any]) -> str:
    """Return the dataset card for ``manifest``."""
    counts = manifest["counts"]
    settings = manifest.get("settings", {})
    threshold_pct = round(float(settings.get("dominance_threshold", 0.8)) * 100)

    return "".join(
        [
            _HEADER,
            _intro(counts, threshold_pct),
            _caveat(),
            _splits(counts),
            _table(
                "Classes",
                ("code", "class", "examples", "share"),
                [
                    (
                        str(row["code"]),
                        row["label"],
                        f"{row['examples']:,}",
                        f"{row['share'] * 100:.1f}%",
                    )
                    for row in manifest.get("class_distribution", [])
                ],
            ),
            _table(
                "Languages (top 15)",
                ("language", "examples", "share"),
                [
                    (row["language"], f"{row['examples']:,}", f"{row['share'] * 100:.1f}%")
                    for row in manifest.get("language_distribution", [])[:15]
                ],
            ),
            _coverage(manifest.get("geographic_coverage", {})),
            _guarantees(threshold_pct),
            _schema(),
            _provenance(settings, manifest.get("rejections", {})),
        ]
    )


def _intro(counts: Mapping[str, Any], threshold_pct: int) -> str:
    total = counts["examples"]["total"]
    return f"""
# osm-wikidata-worldcover

A supervised **text to land-cover** dataset. Each example pairs a Wikipedia or
Wikivoyage article with the [ESA WorldCover](https://esa-worldcover.org/) class
that covers at least {threshold_pct}% of the OpenStreetMap polygon the article
describes.

**{total:,} examples**, {counts["polygons"]["total"]:,} distinct polygons,
{counts["documents"]["total"]:,} distinct documents.

```python
from datasets import load_dataset

ds = load_dataset("NoeFlandre/osm-wikidata-worldcover")
print(ds["train"][0]["text"][:200], ds["train"][0]["worldcover_label"])
```
"""


def _caveat() -> str:
    return """
## What the label means

WorldCover classifies the ground in 10 m pixels. The label therefore describes
the land cover of the area **containing** a feature, not the feature itself: a
church is `Built-up` because its surroundings are, not because the building was
classified. Treat this as place-context classification.

Each row carries `polygon_area_m2` and `observed_fraction` so you can restrict
to polygons large enough for the dominance test to have been a real filter
(`polygon_area_m2 >= 2500` is 25+ pixels).
"""


def _splits(counts: Mapping[str, Any]) -> str:
    rows = [
        (
            name,
            f"{counts['examples'][name]:,}",
            f"{counts['polygons'][name]:,}",
            f"{counts['documents'][name]:,}",
        )
        for name in ("train", "validation", "test")
    ]
    return _table("Splits", ("split", "examples", "polygons", "documents"), rows)


def _coverage(coverage: Mapping[str, Any]) -> str:
    if not coverage:
        return ""
    bbox = coverage.get("bbox", {})
    return (
        "\n## Geographic coverage\n\n"
        f"- H3 cells (resolution 5): {coverage.get('h3_cells', 0):,}\n"
        f"- Source regions: {coverage.get('regions', 0):,}\n"
        f"- Bounding box: {bbox.get('min_lon')}, {bbox.get('min_lat')}"
        f" to {bbox.get('max_lon')}, {bbox.get('max_lat')}\n"
    )


def _guarantees(threshold_pct: int) -> str:
    return f"""
## Guarantees

Every build is checked against these and fails if any breaks:

- **No polygon leakage** — no polygon appears in more than one split.
- **No document leakage** — no document appears in more than one split.
- **Geographic blocking** — splits are assigned per H3 cell, so nearby places
  cannot straddle train, validation and test.
- **Valid labels** — every label is one of the 11 real WorldCover classes;
  no-data is never a label.
- **Dominance** — every row's class covers at least {threshold_pct}% of its polygon.
- **No exact duplicates** — no two rows share both text and label.
- **Deterministic** — rebuilding the same inputs yields byte-identical files.
"""


def _schema() -> str:
    return """
## Columns

| column | meaning |
| --- | --- |
| `text` | Full article text |
| `worldcover_code` / `worldcover_label` | The target class |
| `dominant_fraction` | Share of the polygon covered by that class |
| `observed_fraction` | Share of the polygon observed at all |
| `polygon_id`, `osm_type`, `osm_id` | The OpenStreetMap object |
| `lat`, `lon`, `centroid_wkt` | Polygon centroid |
| `polygon_area_m2` | Polygon area |
| `language`, `project`, `title`, `url` | The article |
| `split`, `h3_cell` | Split and the cell it was decided on |
"""


def _provenance(settings: Mapping[str, Any], rejections: Mapping[str, int]) -> str:
    lines = [
        "\n## Provenance\n",
        f"- Source: [`{settings.get('source_dataset')}`]"
        f"(https://huggingface.co/datasets/{settings.get('source_dataset')})"
        f" at revision `{settings.get('source_revision')}`\n",
        f"- Land cover: ESA WorldCover {settings.get('worldcover_year')}"
        f" {settings.get('worldcover_version')} (10 m)\n",
        f"- Dominance threshold: {settings.get('dominance_threshold')}\n",
        f"- Minimum article length: {settings.get('min_words')} words\n",
        f"- Maximum polygon area: {settings.get('max_polygon_area_m2')} m2\n",
        f"- Split seed: {settings.get('split_seed')},"
        f" H3 resolution {settings.get('h3_resolution')}\n",
        "\nCode: [github.com/NoeFlandre/osm-wikidata-worldcover]"
        "(https://github.com/NoeFlandre/osm-wikidata-worldcover)\n",
    ]
    if rejections:
        lines.append("\n### Polygons refused\n\n")
        lines.append("| reason | polygons |\n| --- | --- |\n")
        lines += [f"| `{k}` | {v:,} |\n" for k, v in sorted(rejections.items())]
    lines.append(
        "\n## Licence\n\n"
        "Article text is CC BY-SA 4.0 (Wikipedia/Wikivoyage). OpenStreetMap "
        "geometry is ODbL. ESA WorldCover is CC BY 4.0.\n"
    )
    return "".join(lines)


def _table(title: str, header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return ""
    out = [f"\n## {title}\n\n", "| " + " | ".join(header) + " |\n"]
    out.append("| " + " | ".join("---" for _ in header) + " |\n")
    out += ["| " + " | ".join(r) + " |\n" for r in rows]
    return "".join(out)

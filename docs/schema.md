# Dataset schema

One row per `(polygon, document)` pair.

## Label

| column | type | meaning |
| --- | --- | --- |
| `worldcover_code` | int | ESA WorldCover class (10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100) |
| `worldcover_label` | str | Human-readable class name |
| `dominant_fraction` | float | Share of the polygon covered by that class (>= threshold) |
| `observed_fraction` | float | Share of the polygon observed at all; < 1 means gaps |

## Text

| column | type | meaning |
| --- | --- | --- |
| `text` | str | Full article text, whitespace-normalised |
| `lead_text` | str | Article lead paragraph |
| `title` | str | Article title |
| `url` | str | Article URL |
| `language` | str | Article language code |
| `project` | str | `wikipedia` or `wikivoyage` |
| `text_words` | int | Whitespace-separated token count |
| `document_id` | str | Stable document identity |

## Place

| column | type | meaning |
| --- | --- | --- |
| `polygon_id` | str | `<region>:<osm_type>:<osm_id>` |
| `osm_type`, `osm_id` | str, int | The OSM object |
| `name` | str | OSM name tag |
| `wikidata` | str | Wikidata QID, where present |
| `lat`, `lon` | float | Polygon centroid |
| `centroid_wkt` | str | Centroid as WKT POINT |
| `polygon_area_m2` | float | Polygon area |
| `region`, `source_pbf` | str | Which extract it came from |

## Split and provenance

| column | type | meaning |
| --- | --- | --- |
| `split` | str | `train`, `validation` or `test` |
| `h3_cell` | str | H3 resolution-5 cell the split was decided on |
| `dataset_version` | str | Version of this build |
| `source_dataset`, `source_revision` | str | Input dataset and pinned commit |
| `worldcover_version`, `worldcover_year` | str, int | Land-cover product used |

## The eleven classes

| code | label |
| --- | --- |
| 10 | Tree cover |
| 20 | Shrubland |
| 30 | Grassland |
| 40 | Cropland |
| 50 | Built-up |
| 60 | Bare / sparse vegetation |
| 70 | Snow and ice |
| 80 | Permanent water bodies |
| 90 | Herbaceous wetland |
| 95 | Mangroves |
| 100 | Moss and lichen |

`0` is WorldCover's no-data value. It is never a label.

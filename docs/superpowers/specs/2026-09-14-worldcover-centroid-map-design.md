# WorldCover centroid coverage map

## Goal

Add a static world map to the Hugging Face dataset card for
`NoeFlandre/osm-wikidata-worldcover`. The map must show the geographic
coverage represented by the published examples: one point per distinct
`polygon_id` that has an ESA WorldCover label in the release.

The dataset's tabular layout and three Dataset Viewer splits remain unchanged.

## Chosen approach

Generate a release asset named `worldcover_centroids.png` from the exact
`train.parquet`, `validation.parquet`, and `test.parquet` files immediately
before publication. The generator will:

1. Read only `polygon_id`, `lat`, `lon`, `worldcover_code`, and
   `worldcover_label` from the three release Parquets.
2. Collapse repeated article rows to one deterministic record per polygon.
3. Fail if a polygon has conflicting ESA codes/labels, missing coordinates, or
   coordinates outside longitude/latitude bounds.
4. Render the points over a world land outline, using a stable color for each
   of the 11 ESA WorldCover classes, with a compact legend and an explicit
   caption that the points are polygon centroids rather than polygon
   boundaries.
5. Write the PNG into the build directory so the existing folder upload sends
   it with the card and Parquet files.

The card renderer will add a coverage-map section after the introduction. It
will link to `worldcover_centroids.png`, state the unique-polygon count, and
explain the centroid representation. The existing `lat`, `lon`, and
`centroid_wkt` columns remain documented as the queryable location fields.

## Dataset Viewer compatibility

The map is a card asset only; it is not added as a split or a column. The
published repository therefore keeps the existing `default` configuration and
`train`, `validation`, and `test` Parquets. After upload, the public Dataset
Viewer API will be checked for:

- a valid dataset response with no processing error;
- exactly the three expected splits;
- non-empty first rows and row pages for every split;
- the expected schema and scalar column types; and
- available Parquet/statistics metadata.

Any Viewer failure is a release failure even if the Hub upload itself succeeds.

## Testing

Unit tests will cover centroid aggregation and validation, deterministic class
colors/legend inputs, map-card rendering, and publisher integration. Tests will
use small local Parquet fixtures and a patched local boundary source so they do
not depend on the network or the full release.

The release verification will additionally inspect the generated PNG and run
the public Dataset Viewer checks against the uploaded repository.

## Non-goals

- Do not add polygon geometries or a new Dataset Viewer split.
- Do not draw true polygon boundaries in the card image.
- Do not change labels, row contents, split assignment, or manifest counts.
- Do not add an interactive JavaScript map whose behavior depends on Hub card
  sanitization.

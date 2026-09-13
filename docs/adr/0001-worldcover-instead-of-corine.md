# ADR 0001: Label with ESA WorldCover, not CORINE

**Status:** accepted — 2026-09-13

## Context

The dataset labels an OSM polygon with the land cover that dominates at least
80% of its area. The obvious source was CORINE Land Cover 2018, which is the
reference product for Europe and carries a rich 44-class level-3 nomenclature.

Measuring the source dataset settled it. Across all 1,259,424 polygons:

| percentile | polygon area |
| --- | --- |
| p25 | 277 m² |
| p50 | 1,301 m² |
| p75 | 24,430 m² |

CORINE's **minimum mapping unit is 25 ha (250,000 m²)**. Only **11.2%** of
polygons reach it. The remaining 89% fall entirely inside a single CORINE
polygon, which means their dominant fraction is 1.0 by construction: the 80%
filter would accept them without testing anything.

## Decision

Label with **ESA WorldCover 2021 v200** at 10 m, 11 classes.

## Consequences

**Gained.** A 10 m pixel is 100 m², so the median polygon spans ~13 pixels and
67% span four or more. Dominance becomes a real discriminator. WorldCover is
global, so all 386 regions contribute rather than Europe alone — Andorra, for
instance, sits outside CORINE's EEA-39 coverage entirely but is labelled here.
It is published on open S3 with no account, removing a credentialed dependency.

**Lost.** WorldCover collapses every settlement into one `Built-up` class,
where CORINE distinguishes eleven artificial classes (urban fabric, industrial,
ports, airports, mines, sport facilities, …). Since many Wikipedia-linked
polygons *are* buildings, this discards the distinction the source data is
richest in. The task is now land **cover**, not land **use**.

## Alternatives considered

- **CLC+ Backbone 2021** — also 10 m and 11 classes, so no taxonomic gain over
  WorldCover, but EEA-38 only and behind a Copernicus login.
- **CORINE at level 1 or 2** — coarser classes raise the pass rate without
  fixing the cause: a 1,301 m² polygon still cannot resolve a 25 ha unit.
- **Both labels side by side** — genuinely attractive, and the disagreement
  between them would be a useful quality signal. Rejected as scope creep for a
  first release; see `docs/technical-debt.md`.

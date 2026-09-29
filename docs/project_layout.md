# Project layout for the next phase

This adapts the existing repository; it is a responsibility map, not a request to move files now. Existing raw and derived data remain date-stamped and Git-ignored. The only new directory needed for this audit is `reports/`.

```text
config/                  # non-secret study/source settings; later a DB config template
data/
  raw/                  # immutable dated provider downloads; no normalisation in place
  interim/              # derived staging/crosswalks; disposable only with provenance
  processed/            # frozen local exports and later DB export snapshots
  metadata/             # manifests, hashes, retrieval and pipeline versions
docs/                    # decisions, dictionary, data audits, reproducibility
reports/                 # phase reports and manuscript-ready narrative
outputs/figures/         # aggregated, privacy-reviewed figures
outputs/tables/          # aggregated, privacy-reviewed tables
notebooks/               # local exploration; no authoritative pipeline state
sql/                     # future migrations/ and queries/ when DB work begins
src/
  ingestion/            # existing downloaders; future database import scripts
  pipeline/             # existing non-GTFS local pipeline until migrated
  cleaning/             # future deterministic source cleaning
  spatial/              # future OSM routing and spatial validation
  gtfs/                 # future, contingent on approval/data availability
  modelling/            # future OLS/XGBoost and diagnostics; not Phase 0
tests/                   # source, join, geometry, and database import checks
```

The requested conceptual `ingest/`, `features/`, `validation/`, and `visualization/` responsibilities can live inside the existing `src/ingestion/`, `src/pipeline/`, `src/spatial/`, and later `src/modelling/` until there is enough code to justify new packages. Do not create empty mirrored packages just for naming symmetry.

## Future PostgreSQL/PostGIS layer (not created)

| Schema | Intended responsibility | Example future entities |
|---|---|---|
| `meta` | Source files, checksums, import runs, schema/pipeline versions | `source_file`, `import_run`, `pipeline_version` |
| `raw` | Faithful, versioned imports with source IDs and timestamps | `airbnb_listing`, `airbnb_calendar`, `airbnb_review`, StatBank source tables |
| `clean` | Typed deduplicated entities and aggregated calendar/review facts | `listing`, `calendar_listing_summary`, `review_listing_summary` |
| `spatial` | Versioned boundaries, OSM POIs/network references, later GTFS stops | `analysis_area`, `osm_poi`, `walking_edge` |
| `features` | Reproducible per-listing distances, accessibility and context joins | `listing_euclidean`, `listing_network`, `listing_context` |
| `analysis` | Frozen sample, outcomes, model-ready tables and fold assignments | `listing_price_sample`, `cv_assignment` |

Use stable source keys and explicit snapshot/import IDs; store geometries with verified SRIDs (source WGS84; projected EPSG:25832), spatial indexes, and source-lineage columns. Keep source files and the checksum manifest outside the database as a reproducible archive. Treat Frederiksberg as a flagged single municipality-sized **analysis area**, not an official Copenhagen district; preserve the 10-district-only sensitivity sample. Avoid host names, free text, and unnecessary personal fields in `clean`, `features`, and `analysis`.

Before any DB creation/import, choose a deployment method, verify PostGIS availability, record versions, add non-secret `.env.example`, document credentials handling, write migrations and idempotent loaders, and test row counts/keys/geometry bounds against the current audited files. No database was created or contacted in Phase 0.

## Phase 1 addendum — 2026-09-29

The existing layout is retained. `compose.yaml`, `.env.example`, `Makefile`, `requirements-db.txt`, `sql/migrations/`, and `src/db/` now provide the database setup and raw-ingestion framework; `src/ingestion/` still owns source downloads. No existing source or pipeline folders were moved. The local Docker daemon is unavailable, so the framework has not yet created or contacted a live PostgreSQL/PostGIS database. See [the Phase 1 report](../reports/phase01_database_setup.md).

## Phase 2–3 operational addendum — 2026-09-29

The Phase 1 daemon limitation above was resolved later that day; the dedicated PostGIS service is operational. Phase 2 added Airbnb clean tables and a runner in `src/pipeline/`. Phase 3 uses the same layout: migration `005_create_context_measures.sql`, source-versioned `raw` tables via `src/db/`, separate `clean` context-measure tables, and `src/pipeline/run_context_phase3.py` for reproducible import/assessment. No source folders were moved, and immutable `data/raw` files remain external provenance archives. See the [Phase 3 report](../reports/phase03_context_data.md).

Phase 4 follows the same pattern: migrations `006_create_spatial_foundation.sql`, `007_official_geography.sql` and `008_map_context_municipalities.sql`, `spatial` provider/official-boundary/study-area/reference/map-context tables, `features.listing_spatial_base`, and runners in `src/pipeline/`. `make phase4-acquire-boundaries` archives official WFS/DAWA study sources immutably in `data/raw/official_boundaries/<date>/`; `make phase4-acquire-map-context` archives Capital Region municipalities separately in `data/raw/official_map_context/<date>/`. `make phase4-run` imports and assigns only the study polygons; neighbouring municipalities are rendered as map context only. Aggregate CV counts and four maps are generated under `outputs/`. The provider polygons remain separate QA layers, not official geography; the City Statbank spatial crosswalk remains unverified. See the [Phase 4 report](../reports/phase04_spatial_foundation.md).

Phase 5 continues in `src/pipeline/` with an immutable OSM PBF archive in `data/raw/osm/phase05/<acquisition-date>/`, migration `009_phase5_euclidean_accessibility.sql`, source-preserving selected objects in `raw`, candidate/canonical OSM destinations in `spatial`, and listing-level Euclidean measures in `features.euclidean_accessibility`. The documented tag/deduplication specification is `docs/osm_poi_taxonomy_phase05.md`. No new top-level package or alternative analytical store is created.

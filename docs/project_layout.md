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

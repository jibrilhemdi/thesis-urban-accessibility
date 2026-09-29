# Reproducing the thesis analysis

The authoritative layer is PostgreSQL/PostGIS. `data/raw/` holds immutable input archives; `outputs/` contains generated, aggregate exports. The older `run_minimum_pipeline.py` and `data/processed/` files are historical local exports, **not** inputs to the Phase 2–10 database analysis. The frozen Phase 9 specification is in [`preanalysis_specification.md`](preanalysis_specification.md); subsequent changes are in [`decision_log.md`](decision_log.md) and [`robustness_registry.md`](robustness_registry.md).

## Environment

- Tested on macOS 26.5.2 (Apple Silicon), Python **3.13.5**, GDAL/OGR **3.8.5**, and Docker Compose with `postgis/postgis:16-3.5` (`linux/amd64` emulation on Apple Silicon). Observed server: PostgreSQL **16.9**, PostGIS **3.5**. `compose.yaml` binds PostgreSQL only to `127.0.0.1` and uses a persistent named volume.
- [`requirements.txt`](../requirements.txt) pins the directly used Python packages to the audited versions. `outputs/tables/phase11/audit.json`, produced by `make audit`, captures installed versions and database/GDAL/OS versions for the actual run. Transitive packages and the mutable Docker image tag are **not** cryptographically locked; use an image digest and an environment-specific resolved lock for stricter bitwise replication. Exact PNG bytes and wall times may vary by font/rendering platform.
- The fixed Phase 8/9 outer random seed is **20260929**; the Phase 9 inner tuning seed is **20260930**. The fixed 1.5-km block allocation seed is **20261034**. Saved assignments live in `analysis.cv_assignments`; do not regenerate them from outcome information. Model candidates and preprocessing live in `src/pipeline/run_analysis_phase9.py` and `outputs/tables/phase09/run_metadata.json`.

## Obtain the immutable inputs

For an **exact** rerun, provision the same `data/raw/` archive and committed `data/metadata/source_manifest.json` into a fresh working copy. `make audit` verifies every archived file's SHA-256 and size against the manifest where listed, and against `meta.source_files` after import. This audit used **58 files**: Inside Airbnb Copenhagen snapshot `2026-06-30` (detailed listings, calendar, reviews, neighbourhood lookup/geometry), historical and selected City/Statistics Denmark extracts, archived official municipality/district/map-context boundaries, older OSM/Overpass provenance files, and the single Phase 5 BBBike Copenhagen PBF/poly/metadata archive. Not all 58 files enter a primary model; some are superseded, provenance or cartographic inputs. The source selection and exact relative paths are in the manifest, [`data_inventory.csv`](data_inventory.csv), and `src/pipeline/run_context_phase3.py`.

If the archive is unavailable, acquisition scripts under `src/ingestion/` and `src/pipeline/acquire_*` document how to obtain new data. Examples: `python -m src.ingestion.download_inside_airbnb --date 2026-06-30`, `python -m src.ingestion.download_copenhagen_statbank --retrieval-date YYYY-MM-DD`, `python -m src.ingestion.download_municipality_statbank --retrieval-date YYYY-MM-DD`, `make phase4-acquire-boundaries`, `make phase4-acquire-map-context`, and `make phase5-acquire`. Review each command's `--help`/source metadata before use. Some services may no longer expose the same vintage; acquiring a newer extract is **not** an exact reproduction and requires a new archive/manifest/version decision. Never overwrite a raw archive or silently replace the archived OSM PBF with live OSM. The PBF is cached under `data/raw/osm/phase05/`, ignored by Git, and reused by Phases 5, 6, 9 and 10. GTFS is not part of this reproduction.

## Fresh rebuild

Use a **fresh checkout and empty database**. This guard matters: phase runners generate reports and outputs at fixed paths. Do not run `make reproduce` in a checkout containing Phase 9/10 outputs or on the existing thesis database. No database volume is dropped or reset by this workflow.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Set a strong, private DB_PASSWORD in .env; choose an unused local DB_PORT.
# Put the documented 2026 raw archive under data/raw/; verify its manifest.
make db-up
make reproduce
make test
make audit
```

`make reproduce` refuses a nonempty `outputs/`, an already migrated database, or existing registered/clean listing rows **before any runner starts**. It checks source hashes and invokes, in order: migrations `001`–`015`; Airbnb raw/clean; context raw/clean; official spatial foundation; Euclidean OSM destinations; walking graph/features; analytical view and diagnostics; fixed folds/EDA; Phase 9 bus proxy and frozen primary models; Phase 10 bus walking and robustness; the Phase 11 audit. It does not call download services. The orchestrator uses the same Python interpreter for each stage; OSM extraction additionally needs `ogr2ogr`/`ogrinfo` on `PATH`. Individual phase targets in the [`Makefile`](../Makefile) remain available for troubleshooting. `make db-down` stops the service without removing the volume.

The Phase 9 primary sample and price outcome are fixed: **12,412** eligible entire-home listings in Copenhagen/Frederiksberg with a positive listed DKK price, official CV area and reachable walking station. The source price is user-confirmed as DKK; the source's `$` symbol does not itself prove currency. Price/log-price are never imputed. The primary opportunity radius/time is 800 m/10 minutes; Phase 10 alternatives are labelled sensitivities. The geographic CV areas are ten official Copenhagen districts plus Frederiksberg municipality as a proxy, not a Copenhagen neighbourhood.

## Verification and outputs

`make test` runs the live database and pure unit tests across Phases 1–10, including key uniqueness, CRS/geometry, source registration, row counts, folds, source-price rules, training-only median/imputation, and Phase 9 freeze integrity. `make audit` is a read-only database/file integrity audit (apart from writing aggregate `outputs/tables/phase11/audit.json`); it checks **21** additional invariants against current source hashes, migration hashes, 23,144-row analytical layers, 12,412-row primary sample, spatial validity, fold coverage, published outputs and CSV header privacy. It does **not** itself rebuild a database. The report [`phase11_reproducibility_audit.md`](../reports/phase11_reproducibility_audit.md) records what was actually rerun and what remains unverified.

Generated results are under `outputs/tables/phaseNN/`, `outputs/figures/phaseNN/` and `reports/`. Raw and point-level tables must not be published. The public output policy prohibits host names, free text, listing identifiers and row-level coordinates; aggregate grid maps suppress small cells. Database-only `analysis`/`features` tables contain listing IDs and must remain access-controlled. The `outputs/tables/phase10/primary_freeze.json` manifest hashes Phase 9 files and every saved CV assignment, so Phase 10 or the audit will fail if the primary results change.

## Public repository and limitations

`.env`, raw Airbnb rows/reviews, OSM PBF/cache files, generated outputs and local virtual environments are ignored by Git. Commit **only** `.env.example`, scripts, migrations, aggregate-safe documentation and approved aggregate outputs. Before publishing, inspect `git status`, `git ls-files data/raw`, and `git ls-files .env`; do not include source snapshots simply because they are locally present. Respect Inside Airbnb's and OSM's licence/attribution terms and any third-party redistribution restrictions.

The data cannot establish transaction prices, bookings, realised demand, causal effects or accurate door-level location. Airbnb coordinates are approximate; OSM is a later snapshot; administrative/context vintages and Frederiksberg's municipality-sized proxy differ. Price is missing for many otherwise eligible listings. Differences from the frozen specification and robustness interpretation are logged rather than overwritten.

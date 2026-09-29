# Phase 1 — PostgreSQL/PostGIS setup and raw-ingestion framework

Date: 2026-09-29. Scope: database infrastructure, migrations, source-file provenance, and faithful CSV import only. No analytical cleaning, Airbnb sample filtering, spatial feature engineering, GTFS, or modelling was performed. Existing raw/interim/processed files were not changed.

## Architecture and commands

`compose.yaml` defines a loopback-only `postgis/postgis:16-3.5` service with a persistent named volume. The [upstream image](https://github.com/postgis/docker-postgis#versions-2026-06-19) publishes amd64, so Compose explicitly requests `linux/amd64` for Apple Silicon emulation. Credentials come from untracked `.env`; `.env.example` is the only template. Phase 1 Python database dependencies are pinned in `requirements-db.txt`. The local PostgreSQL 18.3 Homebrew tools are not used as the server because PostGIS was not installed there.

Run `make db-up`, `make db-connect`, `make db-migrate`, `make db-check`, `make db-version`, `make db-register`, and `make db-ingest-sample` in that order after creating `.env`. `THESIS_DB_TEST=1 make db-test` enables integration tests. `make db-down` stops the container without deleting its volume. The README contains the exact commands and CSV import examples. Migrations are applied transactionally, recorded with SHA-256 in `meta.schema_migrations`, and reject changes to applied migration files.

| Schema | Phase 1 purpose |
|---|---|
| `meta` | Migration history, immutable source-file records, import-run status/errors |
| `raw` | All-text, source-versioned CSV tables with file ID and logical row number |
| `clean` | Reserved for later typed/deduplicated entities |
| `spatial` | Reserved for later validated boundaries/OSM/GTFS layers |
| `features` | Reserved for later accessibility/context features |
| `analysis` | Reserved for later frozen samples and CV assignments |

`meta.source_files` records path, provider, URL where known, SHA-256, size, source/snapshot/acquisition dates where supported, geographic extent, import date, row count, and notes. `meta.import_runs` records source hash, target, CSV decoding options, timestamps, status, loaded rows, and a short error reason without raw cell values. The registration command hashes all 49 files under `data/raw`: 47 are compared with the existing manifest; two metadata sidecars are hashed directly and their retrieval metadata read. It refuses missing manifest files or hash/size drift. The source archive is immutable. Derived interim CSVs in the manifest are intentionally excluded from raw registration.

The CSV importer handles `.csv` and `.csv.gz`, explicit delimiters/encodings, and headerless files. It keeps decoded source values as text, including empty fields, and stores `_source_file_id` plus `_source_row_number`; it neither converts data types nor invents values. A transaction rolls back failed table writes, while a failed import-run record remains. Rerunning a successful source/table import is a no-op. The 11-row Inside Airbnb neighbourhood lookup is the documented sample. JSON/GeoJSON and OSM responses are registered but not imported into spatial tables in this phase.

## Validation and versions

- Python 3.13 environment: SQLAlchemy 2.0.39, psycopg2-binary 2.9.11, python-dotenv 1.1.0. Docker CLI 29.0.1 and Compose v2.40.3 are installed. The running service reports PostgreSQL **16.9** and PostGIS **3.5** (`USE_GEOS=1 USE_PROJ=1 USE_STATS=1`). The pulled image is `postgis/postgis:16-3.5` at digest `sha256:94146ac37bc61e2322f88016056c5920729cb8c64c8542ed590af8fc2abdac07`.
- On 2026-09-29, a locally generated password was stored in Git-ignored `.env`; the dedicated Compose service was started and reached healthy status. All four migrations (001–004) applied transactionally. `make db-check` verified PostGIS and all six schemas. The five Phase 1 tests passed with `THESIS_DB_TEST=1`, including live connection, migration idempotence, source registration, and the 11-row sample neighbourhood CSV import.
- All 49 files under `data/raw` were hash-verified and registered in `meta.source_files`. The subsequent Phase 2 run also imported the detailed Airbnb listings, calendar, reviews, and neighbourhood lookup into source-specific raw tables; see `reports/phase02_airbnb_cleaning.md`. No raw archive file was modified.

## Remaining operational cautions

1. Keep `.env` private and the named Docker volume persistent. `make db-down` stops the service without deleting the volume; do not run `docker compose down -v` against research data.
2. The image tag is versioned but the Compose file is not digest-pinned. Record/recheck the digest if the image is pulled again; Apple Silicon emulation may be slower.
3. Preserve raw data access controls. Detailed Inside Airbnb listings/reviews contain row-level coordinates, names, identifiers, and free text; the raw database is for local controlled research use, not public sharing.

Phase 1 is operational. The existing local processed export remains historical and is not loaded as authoritative database data. Migration 004 and the clean listing table belong to the separately requested Phase 2.

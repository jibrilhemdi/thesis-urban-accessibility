# Urban accessibility and short-term rental outcomes — Copenhagen

Reproducible research workspace for the MSc Social Data Science thesis on whether network-based urban accessibility measures add information beyond conventional location variables when modelling Copenhagen short-term-rental listing prices.

The immediate data stage contains a dated Inside Airbnb Copenhagen snapshot and a reproducible OpenStreetMap/Overpass extraction. Raw source files are intentionally ignored by Git because they contain listing-level coordinates and provider-controlled data. The source manifest, download scripts, schemas, and decisions are kept in the repository so the data can be re-obtained.

## Start here

1. Read [`docs/document_requirements.md`](docs/document_requirements.md) for the separation between the user request and requirements extracted from the two supplied planning documents.
2. Read [`docs/data_governance.md`](docs/data_governance.md) before sharing outputs.
3. Inspect [`data/metadata/source_manifest.json`](data/metadata/source_manifest.json) after downloading.

## Phase 1: local PostgreSQL/PostGIS

The database is the intended persistent analytical store. The existing Parquet/CSV files are legacy local exports, not a second source of truth. Phase 1 only provisions schemas and faithful raw imports; it does not clean listings, build features, or model prices.

Prerequisites: Python 3.13, Docker Desktop with a working daemon, Docker Compose v2, and the local `data/raw/` archive. The Compose image is `postgis/postgis:16-3.5` (PostgreSQL 16, PostGIS 3.5 series); upstream publishes amd64 only, so Apple Silicon uses Docker emulation. The database port is bound to `127.0.0.1` and persists in a named Docker volume. Do not expose or redistribute raw listing/review data.

```bash
python -m pip install -r requirements-db.txt
cp .env.example .env
# Edit .env and set DB_PASSWORD to a new, strong local password.
make db-up
make db-connect
make db-migrate
make db-check
make db-version
make db-register
make db-ingest-sample
THESIS_DB_TEST=1 make db-test
make db-down
```

`.env` is ignored by Git; only `.env.example` belongs in version control. `make db-down` stops the container **without deleting the database volume**. `make db-up` requires Docker Desktop to be running. If port 5433 is occupied, change `DB_PORT` in `.env` before starting. Run `db-migrate` before `db-register` or `db-ingest-sample`. `db-check` prints actual server/PostGIS versions, schema names, and applied migration count without printing credentials.

`make db-register` independently hashes and registers all 49 current files under `data/raw/`, checking the 47 manifest-listed raw files against their recorded SHA-256/size and hashing the two raw metadata sidecars absent from the manifest. It never edits those files. `make db-ingest-sample` loads the 11-row Inside Airbnb neighbourhood lookup into `raw.inside_airbnb_neighbourhoods`; rerunning it skips an already successful import. Raw CSV fields are stored as text with `_source_file_id` and `_source_row_number`, without analytical recoding. Source values are preserved after CSV decoding (not byte-for-byte file quoting). Import runs and errors are logged in `meta.import_runs`.

For another CSV or compressed CSV inside `data/raw/`, run:

```bash
python -m src.db.cli ingest-csv --path data/raw/inside_airbnb/copenhagen/2026-06-30/data/listings.csv.gz --table inside_airbnb_listings
```

For the headerless City Statbank export, specify the encoding and `--no-header`, for example:

```bash
python -m src.db.cli ingest-csv --path data/raw/copenhagen_statbank/2026-09-29/tables/KKBOL3.csv --table city_kkbol3 --no-header --encoding latin-1
```

The CSV importer does not load JSON/GeoJSON/OSM geometry; those files are registered for provenance and await a later spatial-ingestion phase. Use `python -m src.db.cli --help` for command options. Never run destructive Docker volume removal as a normal stop command.

## Phase 2: Airbnb raw tables and clean sample candidate

After the Phase 1 database is running and migrated, run:

```bash
make phase2-run
THESIS_PHASE2_TEST=1 make phase2-test
```

The runner imports the existing detailed listings, calendar, detailed reviews, and neighbourhood lookup into separate `raw` tables, then rebuilds `clean.airbnb_listings` transactionally for snapshot `2026-06-30`. It retains one row per listing with price/coordinate QA and explicit sample flags. The primary candidate view is `analysis.airbnb_primary_sample_candidates`. Source price is treated as DKK per the user's documented assumption, without conversion or imputation. The six pre-specified conventional residential property types, all property-type decisions, and amenity-screening rule are documented in the generated Phase 2 report. Review or availability counts are not eligibility requirements.

On a successful run, aggregate-only tables appear in `outputs/tables/`, including `sample_construction.csv`, and the database-generated report is `reports/phase02_airbnb_cleaning.md`. The raw GeoJSON and compact visualisation listing/review files are not used as primary inputs: they remain registered provenance assets, with boundary validation reserved for later spatial work. The calendar and detailed reviews are not joined to listings in Phase 2, preventing row multiplication. No accessibility features are calculated here.

## Download the current data snapshot

The default configuration uses the Copenhagen snapshot dated `2026-06-30`, which is the latest snapshot listed on the Inside Airbnb download page when this workspace was prepared.

```bash
python src/ingestion/download_inside_airbnb.py
python src/ingestion/download_osm_overpass.py
python -m src.ingestion.download_copenhagen_statbank --retrieval-date YYYY-MM-DD
python -m src.ingestion.download_municipality_statbank --retrieval-date YYYY-MM-DD
python src/ingestion/build_manifest.py
python -m src.pipeline.run_minimum_pipeline
```

The OSM script derives the extraction bounding box from the downloaded listing coordinates and adds a 0.02-degree buffer. It saves the exact Overpass queries beside the raw responses.

The earlier minimum pipeline writes a local analytical export to `data/processed/copenhagen/<snapshot>/`. It cleans listing controls, retains source price without currency conversion, builds OSM walking-time features, and defines 11 analysis areas: 10 Copenhagen districts plus Frederiksberg municipality as one explicitly flagged proxy area. Strict City district fields stay separate from pooled `analysis_area_` fields. All listings have mixed-area context; `eligible_for_district_context_model` remains false for Frederiksberg. GTFS and a load of these derived features into PostGIS remain pending in the historical `data/metadata/pipeline_run.json`.

To use another Inside Airbnb snapshot:

```bash
python src/ingestion/download_inside_airbnb.py --date YYYY-MM-DD
```

## Data layout

```text
data/
├── raw/inside_airbnb/copenhagen/<snapshot>/   # listings, calendar, reviews, neighbourhoods
├── raw/osm/copenhagen/<retrieval-date>/       # Overpass responses and exact queries
├── raw/municipality_statbank/<retrieval-date>/ # national source for Frederiksberg proxy area
├── interim/                                   # cached intermediate tables
├── processed/                                 # frozen analytical data
└── metadata/                                  # manifests and collection metadata
```

The intended feature blocks are property/listing controls (P), basic location (L), OSM network accessibility (A), GTFS transit accessibility (T), and neighbourhood context (N). The pooled context layer has mixed geographic resolution. Copenhagen-only district models remain the cleaner sensitivity check. Copenhagen households now use 2026 Q1, aligned to Frederiksberg's 1 January 2026 reference date; population remains 2026 Q3 for both. Source methods may still differ, and income denominators and dwelling definitions are not fully harmonised, so pooled context measures should be sensitivity covariates, not unqualified equivalents. GTFS remains a modular follow-up source pending approval.

## Sources and attribution

- Inside Airbnb: <https://insideairbnb.com/get-the-data/> and <https://insideairbnb.com/data-assumptions/>. The download page states that the data are licensed under CC BY 4.0.
- OpenStreetMap contributors: <https://www.openstreetmap.org/copyright>. OSM data are available under the Open Database License (ODbL).
- Overpass API: <https://overpass-api.de/>. The raw response includes the OSM data timestamp used by the server.
- City of Copenhagen Statbank: <https://kk.statistikbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1>. The selected tables and periods are recorded in `data/metadata/copenhagen_statbank_run.json`.
- Statistics Denmark StatBank: <https://www.statbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1> and API documentation at <https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api>. The Frederiksberg municipality row supplies its single proxy analysis area; Copenhagen's national row is retained for provenance but not substituted for City district values. Selections are recorded in `data/metadata/municipality_statbank_run.json`.

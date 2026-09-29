# Phase 0 repository audit — 2026-09-29

Scope: read-only inspection of the main worktree and its local data. No modelling, download, database connection, or data mutation was performed. See [data_inventory.csv](data_inventory.csv) for all 61 non-placeholder files under `data/` and [tabular_audit.json](tabular_audit.json) for full-file profiles of all 30 CSV/Parquet datasets. The profiles include columns, sample-inferred dtypes, two redacted first rows, missing counts, duplicate-row and candidate-key counts, delimiter, encoding, and candidate geographic/date fields. Row hashes were used for duplicate tests; these are not a semantic equivalence test.

## Current directory tree

```text
.
├── .git/                         # main Git repository; main at cf31c40
├── .kilo/worktrees/storm-acoustic/ # separate detached older worktree (b21ab19)
├── config/project.yml
├── data/
│   ├── raw/
│   │   ├── inside_airbnb/copenhagen/2026-06-30/{data,visualisations}/
│   │   ├── osm/copenhagen/2026-09-21/{queries,responses}/
│   │   ├── copenhagen_statbank/{2026-09-22,2026-09-29}/{tables,metadata}/
│   │   ├── frederiksberg_statbank/2026-09-22/{tables,metadata}/
│   │   └── municipality_statbank/2026-09-29/{tables,tableinfo}/
│   ├── interim/                  # two City district extracts; old/new municipality extracts
│   ├── processed/copenhagen/2026-06-30/ # same 23,144-row table in Parquet and CSV.gz
│   └── metadata/                 # source manifest, collection and pipeline run metadata
├── docs/                          # methodology and governance; Phase 0 audit files
├── notebooks/test.ipynb           # ignored local exploratory notebook
├── outputs/{figures,tables}/      # empty placeholders
├── sql/                           # empty
├── src/
│   ├── ingestion/                # source downloaders and manifest utilities
│   ├── pipeline/                 # active local non-GTFS listing/OSM/context pipeline
│   ├── cleaning/                 # empty
│   ├── spatial/                  # empty
│   ├── gtfs/                     # empty
│   └── modelling/                # empty
├── tests/test_context_geography.py
├── README.md
├── requirements.txt
└── .gitignore
```

There were 29 tracked files and pre-existing uncommitted edits in the main worktree at audit start. The detached `.kilo` worktree contains an older `src/analysis/run_analysis.py` and `analysis_run.json`; these are **not** part of the current main-worktree pipeline. Existing code/data and the detached worktree were not changed by this audit. No SQL files, migrations, Dockerfile, Compose file, Makefile, project-specific Python environment, or lockfile were found. No `.env` or `.env.example` was found; no credentials were read or printed.

## Active and historical responsibilities

| Location | Observed role | Status |
|---|---|---|
| `src/ingestion/` | Inside Airbnb, OSM/Overpass, City Statbank, and national StatBank downloaders; checksummed source manifest | Active, though the Frederiksberg-only command now delegates to the two-municipality collector |
| `src/pipeline/run_minimum_pipeline.py` | Cleans listings, computes an approximate metric projection and OSM nearest-category walking times, joins context, writes local Parquet/CSV | Active; not a PostgreSQL/PostGIS pipeline |
| `data/raw/` | Date-stamped source responses and source-specific metadata | Raw inputs; ignored by Git |
| `data/interim/` | District/municipality context CSVs | Derived; old 2026-09-22 Frederiksberg row is superseded |
| `data/processed/` | Listing-level analytical table | Derived; two formats of one logical table; ignored by Git |
| `data/metadata/` | Run records, checksum manifest | Active; 51 manifest-listed files were present and passed independent read-only SHA-256 verification |
| `notebooks/test.ipynb` | Local exploratory notebook with an absolute machine path and a saved large output | Legacy/diagnostic, ignored; review or clear outputs before any intentional sharing |
| `.kilo/worktrees/storm-acoustic/` | Detached earlier code and metadata | Legacy worktree; not authoritative for current analysis |
| `sql/`, `src/cleaning/`, `src/spatial/`, `src/gtfs/`, `src/modelling/` | Intended future responsibilities | Empty; do not move current code merely to fill folders |

## Duplicates, inconsistencies, and risks

- The 2026-09-22 and 2026-09-29 City extracts contain byte-identical `KKBEF1`, `KKBOL3`, and `KKIND3` raw CSVs. `KKHUS1` is intentionally different: the newer extract is 2026 Q1 to align households to 1 January 2026; the older is 2026 Q3. Keep both date-stamped collections for provenance.
- The 2026-09-22 Frederiksberg-only interim row is superseded. It copied total population into `resident_count_statbank`, a different concept from the City's housing resident count. The 2026-09-29 national two-municipality extract fixes that mislabelling, but remains municipality-level.
- Parquet and CSV.gz under `processed/` represent the same 23,144 listing IDs, not independent observations. Neither processed file is in the raw-source manifest; a future frozen-analysis manifest should hash derived outputs too.
- The detailed and visualisation listing files are not identical: the latter has 23,146 unique IDs, including two not in the 23,144-row detailed file. Use the detailed file as the current primary source and reconcile before a snapshot freeze.
- The City Statbank raw CSV exports are headerless and wide, with one-row exports for three tables and a 10-row `KKBOL3` export. `KKBOL3` required ISO-8859-1 fallback. A naive `read_csv()` with inferred headers silently loses the first data row; the current collector uses a dedicated parser.
- `docs/document_requirements.md` still describes the initial two-source setup and is stale as a description of current collected context and pipeline. Retain it as historical scope, but cite current metadata and this audit for actual status.
- `requirements.txt` uses lower bounds without a lock/export and omits `pyarrow`, a runtime dependency of the current Parquet output. Current Python is 3.13.5; installed `geopandas`, `shapely`, `pyproj`, `osmnx`, `libpysal`, `esda`, and `xgboost` were not found even though most are requested by `requirements.txt`.
- The current pipeline uses a custom EPSG:25832-compatible calculation, not a verified `pyproj`/PostGIS transform. Coordinate and polygon handling should be validated before database spatial joins. The cached OSM extraction (21 September) postdates the Airbnb snapshot/scrapes (30 June–4 July).
- Raw files are Git-ignored, but the ignored notebook has a saved output of roughly 107 KB and may display row-level data. Do not commit or share it without privacy review.

## Minimal recommendations

Preserve the current `data/raw`, `data/interim`, `data/processed`, `src/ingestion`, and `src/pipeline` conventions. In Phase 1, add only the SQL migration/query files, a documented database configuration template with no secrets, a pinned environment, and idempotent import/validation code needed for the PostgreSQL/PostGIS workflow. Do not create a database or rearrange the active pipeline during Phase 0.

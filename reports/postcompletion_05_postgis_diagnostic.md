# Post-completion 05 — PostgreSQL/PostGIS environment diagnostic

Date: 2026-09-29. Scope: read-only verification of the completed thesis database, explicit comparison with the local Homebrew installation, and connection-command clarification. No analytical table, migration, raw file, model output, or thesis result was changed.

## Disposition

**The Docker thesis database is working and remains authoritative.** `compose.yaml`, `.env`, `src/db/connection.py`, the Phase 1 setup, Phase 11 isolated rebuild, and the populated project schemas all identify the Compose PostGIS service as the thesis data layer. Homebrew is a separate, working PostgreSQL/PostGIS installation; its existence does not imply migration. No repair or migration is warranted.

| Instance | Verified host endpoint | Database/user inspected | Server | PostGIS | Status |
|---|---|---|---|---|---|
| Authoritative Docker Compose | `127.0.0.1:5433` → container `5432` | `thesis_accessibility` / `thesis_researcher` | PostgreSQL 16.9 | 3.5.2, enabled and operational | Compose service healthy |
| Separate Homebrew | `127.0.0.1:5432` | `postgres` / local OS user | PostgreSQL 18.3 | 3.6.4 available; not enabled in `postgres` | `postgresql@18` service started; extension worked in an isolated disposable DB |

The project's Python connection uses `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` from private `.env`; the current non-secret values are the Docker endpoint shown above. Compose binds only loopback and stores data in its named volume. The local `psql` and `pg_config` on `PATH` are Homebrew 18.3 clients at `/opt/homebrew/bin/psql` and `/opt/homebrew/bin/pg_config`; `pg_config --bindir` resolves to `/opt/homebrew/Cellar/postgresql@18/18.3/bin`. Homebrew's PostGIS control file is linked under `/opt/homebrew/share/postgresql@18/extension/` to the 3.6.4 formula. The Docker server and its `psql`/`pg_config` reside inside the image (`/usr/lib/postgresql/16/bin/postgres`, `/usr/bin/psql`, `/usr/bin/pg_config`, respectively); its client/server major version is 16. PostgreSQL 18.3 is the only Homebrew server version found in the installed formula inventory. These client paths do **not** determine which server a connection reaches.

## Explicit endpoint tests

1. `make db-up` found/started the existing Compose service; `docker compose --env-file .env ps` reported healthy and `127.0.0.1:5433->5432/tcp`. `make db-check` reported PostgreSQL 16.9, PostGIS 3.5, all six schemas and 16 applied migrations. Direct queries returned `version()` = PostgreSQL 16.9, `postgis_full_version()` beginning `POSTGIS="3.5.2"`, `current_database()` = `thesis_accessibility`, `current_user` = `thesis_researcher`, and `SHOW port` = `5432` **inside** Docker. `ST_Transform(ST_SetSRID(ST_Point(12.5683,55.6761),4326),25832)` returned `POINT(724351.928637642 6175804.02212861)`.
2. An unqualified `psql` attempted the local Unix socket `/tmp/.s.PGSQL.5432` and failed with `database "jibrilhemdi" does not exist`. It did **not** reach the thesis database. Explicit Homebrew connection to `127.0.0.1:5432`, database `postgres`, local user succeeded and reported PostgreSQL 18.3/port 5432. `pg_available_extensions` reported PostGIS default version 3.6.4 with `installed_version = NULL` in `postgres`. The Homebrew service listens on local port 5432.
3. For a functional Homebrew extension test, a uniquely named, previously absent disposable database (`thesis_postgis_diag_20260929`) was created **only on Homebrew**. `CREATE EXTENSION postgis` succeeded there; `postgis_full_version()` began `POSTGIS="3.6.4"`, and the same EPSG:4326→25832 transform returned the point above. That temporary diagnostic database was dropped after verifying its identity and is now absent. No project/thesis database was touched. Thus Homebrew PostgreSQL **and PostGIS are functional**, but PostGIS is merely *available*, not enabled, in the inspected existing `postgres` database. There is no version/control-file mismatch or installation repair to perform.

PostgreSQL clients can connect to different servers using host, port, user and database arguments. A `psql --version` result describes the client binary only. Bare `psql` applies its own socket/OS-user/default-database rules and ignores this project's `.env`; using it here is ambiguous.

## Authoritative database content and live PostGIS checks

The read-only `make db-diagnose` checks the configured `.env` endpoint against the Compose-published port and actual database/user/server versions; the match was true. It lists the relations and found all required schemas: `meta`, `raw`, `clean`, `spatial`, `features`, `analysis`. Selected current counts:

| Relation | Rows |
|---|---:|
| `meta.source_files` / `meta.schema_migrations` | 58 / 16 |
| `clean.airbnb_listings` | 23,144 |
| `analysis.analysis_dataset_v1` / `analysis.cv_assignments` | 23,144 / 23,144 |
| `features.euclidean_accessibility` / `features.walking_accessibility` | 23,144 / 23,144 |
| `features.analysis_area_context` | 11 |
| `spatial.official_municipalities` / `spatial.official_cv_areas` | 2 / 11 |
| `spatial.osm_pois` / `spatial.transit_stations` | 3,469 / 143 |
| `spatial.walking_nodes` / `spatial.walking_edges` | 545,903 / 617,456 |

The 617,456 persisted walking-edge rows are stored graph segments; the Phase 11 report's 1,234,730 count refers to directed network arcs, not a conflicting table count. Listing keys `(snapshot_date, listing_id)` are unique in the clean, analysis, CV, Euclidean and walking tables (zero duplicates each). All 23,144 listing points are non-null/valid in both EPSG:4326 and EPSG:25832. Inspected official municipality/CV polygons and OSM POI/station points have no invalid geometries or wrong EPSG:25832 SRIDs. Twenty GiST indexes were found in the inspected `clean`, `spatial` and `features` schemas. Euclidean and walking feature joins each cover all 23,144 listings; 22,979 have a reachable-station walking time, leaving 165 with the previously documented disconnected-network status, **not** a new database defect.

Three operations ran against persisted project geometries in EPSG:25832, without writes:

- `ST_Covers` placed the saved City Hall reference point in **Indre By** and covered 23,066 listing points by their saved assigned CV polygon. The remaining listing assignments/edge cases are not silently reassigned by this diagnostic.
- `ST_Distance`/`ST_DWithin` found the nearest saved station to City Hall at **71.13 m** and within 1 km.
- `ST_Transform` converted the saved EPSG:4326 City Hall point to EPSG:25832; the saved projected reference matched to **0.000000 m** at the reported precision.

## Recommended use and answers

Use `make db-up`, then `make db-check` or `make db-diagnose`. To enter the **thesis** database, run **`make db-psql`** from the project root; this invokes `psql` inside the Compose service with its configured user/database. `make db-connect` is a non-interactive, `.env`-driven connection test and now prints the safe endpoint/server identity. At the `psql` prompt, verify with `SELECT version(); SELECT postgis_full_version(); SHOW port; SELECT current_database();` (separate statements). No password is printed or embedded in command arguments.

To answer the requested decisions directly: Docker PostGIS works; Homebrew PostGIS also works when enabled in a specific Homebrew database; versions and ports are in the table above; the completed thesis/reproducibility workflow used Docker, which should remain authoritative. A bare `psql` may select the Homebrew socket/default database instead. **No repair is needed and migration to Homebrew is not recommended** after completion. Do not rerun scientific analyses, apply migrations, or remove the Docker volume for this connection issue.

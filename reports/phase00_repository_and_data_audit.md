# Phase 0 — repository, data, and environment audit

Date: 2026-09-29. Scope: inspection and documentation only. No new data were downloaded, no substantive model was run, no database was created or contacted, and no existing raw/interim/processed file was changed. Existing uncommitted project edits were preserved.

The evidence base is the [repository audit](../docs/repository_audit.md), [61-file data inventory](../docs/data_inventory.csv), [30-file tabular audit](../docs/tabular_audit.json), [availability matrix](../docs/data_availability_matrix.md), [gap register](../docs/data_gap_register.md), and the repository's dated collection/pipeline metadata. The full-file scan checked shapes, missingness, duplicate rows and candidate keys; first-row examples in the structured audit are redacted. Geometry validity, statistical concept equivalence, and source currency are not established by those checks.

## Executive finding

The existing local pipeline and source archive are useful, but the primary analysis is not ready to freeze. The detailed Airbnb file has 23,144 unique listings, of which 21,368 are entire homes/apartments and 12,779 of those have a listed price before the conventional-residential filter. Prices display `$`, with the actual currency unverified. The current context is 10 Copenhagen districts plus Frederiksberg as one municipality-sized proxy; national municipality totals cannot supply within-Frederiksberg neighbourhood variation. PostgreSQL binaries are installed locally, but no project PostgreSQL/PostGIS configuration, migration, or schema exists. These are Phase 1 design and infrastructure tasks, not reasons to fabricate data or begin modelling now.

## 1. What is currently in the repository?

The main worktree has active ingestion scripts for Inside Airbnb, OSM/Overpass, City of Copenhagen Statbank, and Statistics Denmark StatBank; one local minimum pipeline; one context-geography test; source/processing metadata; governance/method notes; and date-stamped local raw/interim/processed data. There are 61 non-placeholder files under `data/`, including 30 CSV/Parquet files. A 51-entry source manifest was independently checked read-only: all files existed and SHA-256 hashes matched. The separate detached `.kilo` worktree contains an older analysis runner and is not the main-worktree pipeline. An ignored exploratory notebook has an absolute local path and a large saved result; it should not be shared without privacy review. See the [tree and status inventory](../docs/repository_audit.md).

## 2. Is the folder structure adequate? 3. What minimal structural changes are recommended?

Yes for source archiving: `data/raw`, `interim`, `processed`, `metadata`, `src/ingestion`, `src/pipeline`, `docs`, `tests`, and `outputs` are sensible. `sql/` and several intended `src/` subfolders are currently empty. This audit added only the requested documentation and `reports/`. Phase 1 should add migration/query files, a non-secret database configuration template, a pinned environment/lock or export, and narrowly scoped import/validation code. It should not rename or move existing folders just to match a generic template. See [project layout](../docs/project_layout.md).

## 4. What Airbnb data are available?

| File/asset | Observed content | Audit result |
|---|---|---|
| `data/listings.csv.gz` | 23,144 rows × 90 columns; unique `id` | Main detailed source; 10 City neighbourhood labels plus Frederiksberg; all 23,144 have plausible regional coordinates; names, URLs, host IDs and free text require controlled handling |
| `visualisations/listings.csv` | 23,146 rows × 19 columns | Compact map layer; two IDs are absent from detailed listings; not the primary analytical source |
| `data/calendar.csv.gz` | 8,448,291 rows × 5 columns; unique `(listing_id,date)` | 2026-06-30 to 2027-07-03; availability/minimum/maximum nights only, **no price field** |
| `data/reviews.csv.gz` | 471,781 rows × 6 columns; unique review `id` | Review dates 2010-06-17 to 2026-07-03; contains reviewer names/IDs and comments |
| `visualisations/reviews.csv` | 471,781 rows × 2 columns | Listing/date only; 7,570 repeated rows are expected when multiple reviews share listing/date; do not treat as duplicate review IDs |
| `visualisations/neighbourhoods.csv` and `.geojson` | 11 labels/polygons | Provider geography; one Frederiksberg polygon; geometry/CRS and boundary membership not independently validated |

The detailed source contains `price`, `room_type`, `property_type`, `accommodates`, `bedrooms`, `bathrooms`, `bathrooms_text`, `amenities`, `minimum_nights`, superhost, calculated host listings, review counts/ratings, and availability. It also has `instant_bookable`, but **all 23,144 values are missing**. Numeric bathrooms are missing for 10,941, whereas a processed number parsed from `bathrooms_text` is available for 22,940; bedrooms are missing for 1,487; ratings for 3,060. Host response time/rates and total host listings are also entirely missing. Minimum nights, calculated host listing count, and amenities are present throughout the raw detailed file. Listing prices are present for 13,860 (9,284 missing); the alternate quoted-nightly-price column provides no value where `price` is missing. The 13,860 priced observations include 683 listings scraped on 3–4 July and 13,177 on 30 June–1 July; no duplicate listing IDs connect these batches, so they are not proven price recoveries. The source displays `$`; do not label the currency without verification. The current processed file is 23,144 × 101 and contains source numeric/log price, a city-centre distance, and nearest-category OSM walking times, but not a frozen primary entire-home/conventional-accommodation sample.

## 5. What context data are available? 6. At what geographic resolution?

| Source | Tables/concept | Time | Geography and use |
|---|---|---|---|
| City of Copenhagen Statbank | `KKBEF1` total population; `KKHUS1` total households; `KKIND3` average disposable income for people with that income type; `KKBOL3` dwellings/occupied dwellings/housing residents | Population 2026 Q3; households 2026 Q1 (1 January); income 2024; dwellings 2026 | Ten Copenhagen districts, joined to 20,644 listings; does not cover Frederiksberg |
| National `FOLK1A` | Total population at first day of quarter | 2026 Q3 | One Copenhagen municipality row and one Frederiksberg municipality row in current extract; no below-municipality values |
| National `FAM55N` | Household cells summed over household type/size/children | 1 January 2026 | Same two municipality rows; City district households now share the reference date, but producer methods may differ |
| National `INDKP106` | Average disposable income for persons aged 14+ in selected group | 2024 | Same two municipality rows; its denominator differs from City `KKIND3` selection |
| National `BOL101` | Dwellings by registered-population status/use/tenure/owner/construction year | 2026 | Same two municipality rows; dwelling definition not independently harmonised with City `KKBOL3` |
| National `BOL106` | Average persons per dwelling with registered population | 2026 | Same two municipality rows; not an area-resident count |

The national files are **municipality-level extracts**, even though their rows can be repeated when joined to individual listings. They cannot support listing-level *neighbourhood* population density or neighbourhood income across both municipalities. They support only a municipality-wide Frederiksberg proxy value. The current pipeline explicitly labels an 11th single Frederiksberg analysis area and retains a strict Copenhagen-only district eligibility flag. No housing resident count is fabricated for Frederiksberg. The old 2026-09-22 Frederiksberg-only interim row is superseded because it incorrectly relabelled total population as housing residents. Matching reference dates do not prove identical geographic coverage or counting: City district population sums to 666,861 versus 670,389 in the national Copenhagen municipality row (difference 3,528), and City district households sum to 332,166 versus 332,181 nationally (difference 15). Area-level density is not yet calculated; the 11 provider polygons have not been spatially validated.

## 7. What spatial/GIS data are missing?

OSM walking-network and POI responses exist in the buffered study area (306,424 and 20,622 elements respectively, timestamped 2026-09-21). The local pipeline built 236,637 graph nodes and nearest-category walking times. It does **not** yet provide validated neighbourhood polygon areas, population density, PostGIS geometries/indexes/spatial joins, station-specific access, Euclidean POI opportunity counts, full walking-time catchment counts, or GTFS timetable access. The current graph is undirected with assumed walking speeds and a custom approximate metric projection. Airbnb coordinates are provider-anonymised. The OSM layer postdates the listing snapshot by roughly three months, so temporally exact accessibility claims need qualification or earlier data.

## 8. Is PostgreSQL/PostGIS configured? 9. What is required before ingestion?

No. Homebrew PostgreSQL 18.3 client/server binaries and Docker command were found, but the project has no DB configuration, credentials template, SQL migrations, database code, or Compose/Dockerfile. No `postgis.control` was found in the inspected Homebrew share directory. This does **not** prove a running service lacks PostGIS; no unknown database was contacted. Before ingestion: select a managed/local/container deployment, verify version and PostGIS extension availability, define credentials/roles and `.env.example`, create reversible migrations for `meta`, `raw`, `clean`, `spatial`, `features`, and `analysis`, establish immutable source IDs/hashes and idempotent imports, validate row counts/keys/geometry/SRID, and document backup/privacy controls. The [layout document](../docs/project_layout.md) assigns schema responsibilities. Do not create the database until those choices and checks are made.

## 10. Which research-plan assumptions are contradicted by actual files?

- The calendar is not a source of nightly prices; it has no price column. Availability is not occupancy or bookings.
- `instant_bookable` exists only as an empty column. Host response fields are also empty; planned controls cannot be assumed available.
- Listed price currency is not verified despite `$` formatting. The data do not provide realised prices.
- The primary entire-home, conventional-residential sample is not yet operationalised or frozen; the existing 13,860 priced rows include room types outside that segment.
- Frederiksberg municipality totals do not become neighbourhood statistics when repeated on listing rows. The pooled 11-area context is mixed-scale, and income/dwelling definitions are not fully harmonised.
- Population density, Euclidean POI counts, station/timetable accessibility, PostgreSQL/PostGIS tables, and substantive model outputs are not present in the active main worktree.
- The installed Python environment does not satisfy all declared GIS/model dependencies, and there is no pinned environment. The ignored notebook and older detached worktree are not reproducible production artefacts.

## 11. What should happen in Phase 1?

1. Freeze the Phase 0 data/provenance baseline without changing source files. Decide and document the primary entire-home, conventional-residential inclusion rule, price currency, scrape-batch treatment, and minimum required controls.
2. Choose/provision a PostgreSQL/PostGIS deployment and pin the Python environment. Add a non-secret config template, migrations, version/role checks, and repeatable source-import tests; do not import before verifying extension availability and privacy requirements.
3. Import exact raw snapshots into `raw`, build typed `clean` entities, and aggregate calendar/reviews by listing **before** joining. Preserve raw and derived hashes and one-to-one listing keys.
4. Validate provider polygons, municipality/district assignment, coordinate transform and spatial indexes. Define a common analysis-area geometry, retain the Frederiksberg proxy flag, and keep the Copenhagen-only sensitivity sample. Resolve whether truly submunicipal Frederiksberg statistics are required or available.
5. Design and verify the planned Euclidean/network feature ladder and CV geography, then begin models in a later phase. GTFS remains contingent on approval.

**Phase 0 stops here.** No Phase 1 ingestion, modelling, or data acquisition has been started.

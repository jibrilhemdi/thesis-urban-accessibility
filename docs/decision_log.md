# Decision log

## 2026-09-21 — project initialization

- **Decision:** use Copenhagen as the study area.
  **Reason:** both supplied thesis documents define Copenhagen as the case study.
- **Decision:** use the Inside Airbnb snapshot dated 2026-06-30 by default.
  **Reason:** it is the latest Copenhagen snapshot listed on the provider’s live download page when the workspace was prepared.
- **Decision:** download detailed listings, calendar, and reviews plus the provider’s summary and neighbourhood files.
  **Reason:** this preserves the minimum source set described in the planning documents while enabling early price-field and activity-proxy inspection.
- **Decision:** derive the OSM extraction bbox from listing coordinates and add a 0.02-degree buffer.
  **Reason:** it keeps the first extraction aligned with the empirical study area while allowing nearby walking connections and amenities.
- **Decision:** query OSM through Overpass and save the exact query text.
  **Reason:** the initial collection should be reproducible without committing to a particular Python GIS package or silently relying on a mutable API query.
- **Decision:** ignore raw data in Git and retain checksums/metadata.
  **Reason:** the raw layers contain listing-level coordinates and are provider-controlled; the thesis needs reproducibility without public redistribution of sensitive row-level data.
- **Data issue recorded:** the downloaded calendar file has no price column.
  **Consequence:** use it only for availability/minimum-night sensitivity unless a different archived file is selected; do not claim that a calendar median price was collected.
- **Data issue recorded:** detailed listings format `price` with `$` in this snapshot.
  **Consequence:** verify the source currency before defining `log_price`; the proposal’s DKK wording is not yet operationally confirmed.
- **Decision:** run the non-GTFS spatial pipeline using local Parquet rather than requiring PostGIS/OSMnx.
  **Reason:** the raw inputs are available and the base environment has pandas, NumPy, SciPy, and PyArrow, while GTFS approval and the heavier GIS database stack are still pending.
- **Decision:** implement nearest-category network travel times and a nearest-category decay index as the first OSM accessibility features.
  **Reason:** these are reproducible minimum-version network measures; full opportunity counts within thresholds and timetable accessibility remain follow-up work.
- **Decision:** collect KKBEF1, KKHUS1, KKIND3, and KKBOL3 from the City of Copenhagen Statbank and join them at district level.
  **Reason:** the official City Statbank provides population, households, income, and dwelling context aligned with 10 City of Copenhagen districts.
- **Decision:** collect Frederiksberg municipality context from Statistics Denmark StatBank rather than assigning it to a City of Copenhagen district.
  **Reason:** Airbnb includes 2,500 Frederiksberg listings, but Frederiksberg is an independent municipality outside the City Statbank district system. National StatBank municipality code 147 provides official population, household, income, and dwelling context while preserving the different geographic level explicitly.

## 2026-09-29 — correct context comparability

- **Correction:** the earlier processed table put Frederiksberg municipality totals in the same columns as Copenhagen district totals. This was not comparable. The earlier Frederiksberg-only tidy file also assigned FOLK1A population to `resident_count_statbank`, although Copenhagen's field came from a housing table.
- **Decision:** preserve the historical raw extraction for provenance, supersede the old tidy row, and keep City of Copenhagen district fields missing for Frederiksberg listings.
- **Decision:** collect Copenhagen (101) and Frederiksberg (147) together from identical national StatBank tables, selections, and periods; join these under separate `municipality_`-prefixed fields. Do not fabricate a national housing resident count.
- **Limitation:** national municipality context has two independent geographic units, so it is suitable for descriptive comparison, not as if it supplied 23,144 independent contextual observations. District and municipality totals should not be compared directly.

## 2026-09-29 — require district or neighbourhood resolution

- **Decision:** remove municipality-level context from the processed analytical table entirely. Keep the historical downloads and provenance files, but do not use them as neighbourhood controls.
- **Decision:** retain all Frederiksberg listings for property/location/OSM analyses, while flagging them ineligible for district-context models. The City of Copenhagen district source applies only to its 10 districts.
- **Open data gap:** Inside Airbnb gives the Frederiksberg listings only a single municipality-wide neighbourhood label. [SOGN1](https://www.statistikbanken.dk/statbank5a/selectvarval/Define.asp?MainTable=SOGN1&PLanguage=0) offers parish-level population and [DAGI/DAWA](https://dawadocs.dataforsyningen.dk/dok/api/sogn) offers parish boundaries, but no verified, compatible small-area population/household/income/dwelling layer and spatial crosswalk has yet been incorporated. Some parish-level income products are [sold separately](https://www.dst.dk/da/TilSalg/produkter/noegletal/noegletal-paa-sogne). Do not infer or fabricate those variables.

## 2026-09-29 — user-approved mixed-resolution analysis area

- **Decision:** use the 10 City of Copenhagen districts and treat Frederiksberg municipality as one additional analysis area, explicitly labelled a municipality proxy rather than an official district. This supersedes the immediately preceding decision to exclude Frederiksberg from all context joins.
- **Implementation:** keep strict City district columns and `eligible_for_district_context_model` unchanged; add separate `analysis_area_` fields for an 11-area pooled analysis. The national Copenhagen row is not substituted for any City district.
- **Comparability rule:** pool only population, households, disposable income, and dwelling totals as exploratory context, with source and period flags. Population shares 2026 Q3; households differ in date (Copenhagen 2026 Q3, Frederiksberg 1 January 2026); income denominators and dwelling definitions differ or remain unverified. Do not pool housing resident or occupied-dwelling measures. Report a Copenhagen-only district sensitivity analysis and avoid calling Frederiksberg an official district.

## 2026-09-29 — align household reference date

- **Correction:** replace the Copenhagen KKHUS1 2026 Q3 household extract with 2026 Q1, corresponding to 1 January 2026 in the [City's quarterly methodology](https://www.kk.dk/sites/default/files/2021-11/KK%20Statistikbank%20dokumentation_04112021.pdf). Frederiksberg's [FAM55N](https://www.statbank.dk/statbank5a/SelectVarVal/Define.asp?MainTable=FAM55N&PLanguage=1) is explicitly 1 January 2026. The earlier 2026 Q3 extract remains in the raw archive for provenance.
- **Decision:** leave population at 2026 Q3 in both sources; only households needed temporal realignment. Store both source period labels and the common `2026-01-01` household reference date in the analytical table.
- **Remaining limitation:** the City district household sum is 332,166 versus the national Copenhagen municipality count of 332,181 (difference 15) at the same date, so identical timing does not prove identical source methods or definitions. Mixed-source context remains flagged; income and dwelling differences are unchanged.

## 2026-09-29 — Phase 0 audit boundary

- **Observed:** the existing `data/raw`/`interim`/`processed` layout and date-stamped metadata are usable; 51 manifest-listed source files passed read-only hash verification. No PostgreSQL/PostGIS project configuration, SQL migration, Docker/Compose setup, or pinned Python environment exists in the main worktree.
- **Decision:** preserve the current structure and all existing source/code files. Add only audit documentation in `docs/` and `reports/` during Phase 0; defer database creation/import and modelling to a separately authorised phase.
- **Observed:** `instant_bookable` and host response fields are entirely missing; detailed price is missing for 9,284 listings; calendar has no price; the visualisation listing file has two IDs absent from detailed listings. These must be resolved or explicitly excluded before a primary sample is frozen.
- **Observed:** national StatBank rows are municipality-level, while City Statbank rows are Copenhagen district-level. The current Frederiksberg single-area proxy is not neighbourhood-level context and does not establish within-Frederiksberg variation or harmonised income/dwelling definitions.

## 2026-09-29 — price-batch and currency policy

- **User confirmation:** treat the numeric Inside Airbnb listing `price` as local DKK, with no conversion. The source strings display `$` and contain no currency code, so retain this as a user-confirmed assumption rather than independent source verification; the earlier currency warning remains historically accurate for the Phase 0 audit.
- **Observed:** the detailed file has 23,144 unique listing IDs and no ID appears in both scrape batches. Valid positive prices number 13,177 on 30 June–1 July and 683 on 3–4 July; 9,284 listings have no source price. The alternative quote-price field does not recover those missing values.
- **Decision:** retain all 13,860 valid source prices for the broad priced-listing analysis, mark the 683 later observations `late_batch_price`, and use the 13,177 early prices as a sensitivity sample. Do not describe a late-only observation as a verified replacement for an earlier missing price. A true early-first, late-if-missing listing-level rule requires linked observations for the same listing ID, which this file lacks.
- **Implementation boundary:** this changes the price-cleaning code and documentation only. Existing processed exports and the historical Phase 0 audit are not overwritten; PostgreSQL/PostGIS remains the intended authoritative analytical store. The thesis's primary entire-home/conventional-residential sample still needs its separate inclusion rule.

## 2026-09-29 — simplify price selection after ID clarification

- **User decision (supersedes the batch-specific policy above):** because every listing ID occurs once, do not replace any price or distinguish early and late scrapes for price selection or modelling. Use each listing's single valid positive source price, regardless of `last_scraped`; leave missing/non-positive prices missing. Keep the DKK assumption recorded above.
- **Data-quality caveat:** retain `last_scraped` as source provenance and report aggregate price completeness by date, not as a model control or early-only analysis sample. The early dates contain 13,177 prices among 14,160 listings; the late dates contain 683 among 8,984. This imbalance should be acknowledged when discussing sample selection.
- **Implementation boundary:** remove the unregenerated batch flags and early-only eligibility from cleaning code. Do not overwrite the existing processed export or begin modelling/database ingestion as part of this correction.

## 2026-09-29 — Phase 1 database infrastructure

- **Decision:** preserve the established repository layout and add only `compose.yaml`, `.env.example`, pinned Phase 1 database dependencies, Make targets, `sql/migrations/`, and `src/db/`. The intended authoritative persistent store is PostgreSQL/PostGIS; existing Parquet/CSV outputs remain legacy exports.
- **Decision:** use `postgis/postgis:16-3.5` on a loopback-bound Docker Compose service with a named persistent volume and an untracked `.env` password. The upstream image is amd64-only, so Apple Silicon requires emulation. The Homebrew PostgreSQL 18.3 install has no recorded PostGIS package.
- **Decision:** checksum-verify and register all 49 files under `data/raw`, including two sidecars absent from the 51-entry source/interim manifest. Preserve CSV source values as text in versioned raw tables; reserve typed cleaning and spatial imports for later phases. Keep import attempts and migration checksums in `meta`.
- **Unresolved runtime dependency:** Docker Desktop is not operational on this machine: the daemon socket is absent and the application bundle lacks its executable. Compose syntax and offline tests passed, but a real PostGIS connection, migrations, registration, and sample import remain unverified and unexecuted. See `reports/phase01_database_setup.md`.

## 2026-09-29 — Phase 2 Airbnb sample specification (implementation, not yet executed)

- **Observed:** the local detailed source has 23,144 unique listing IDs; all 13,860 nonempty `price` strings match the `$`-prefixed numeric format; 9,284 are missing. All listing neighbourhood labels occur in the 11-label provider lookup. The source-only prospective funnel is 21,368 entire-home listings, 21,080 in six clearly conventional types, and 12,521 with source prices and valid coordinates. These are not database-validated counts.
- **Decision:** parse only source-supported price strings, treat numeric values as DKK under the earlier user-confirmed assumption, preserve missing/non-positive outcomes as invalid for log-price, and do not replace prices by scrape date. No review or availability threshold enters eligibility.
- **Decision:** conservatively include `Entire rental unit`, `Entire condo`, `Entire home`, `Entire townhouse`, `Entire villa`, and `Entire loft` as conventional residential forms. Preserve all other property types with explicit exclusion flags and category-level reasons; revisit only through a logged specification change, never model performance.
- **Decision:** use provider neighbourhood lookup membership as the provisional `in_study_area` flag and source WGS84 (EPSG:4326) coordinates transformed in PostGIS to ETRS89 / UTM 32N (EPSG:25832). This is not official polygon containment; provider boundary validation remains open. Amenity candidates are fixed interpretable labels screened at strict 5%–95% prevalence before price selection, not on price association.
- **Unresolved:** the Phase 1 Docker daemon and `.env` are still unavailable. Phase 2 SQL, import/build/report code and tests exist, but no live raw imports, clean table, sample CSV, or database-derived report have run. The current Phase 2 report explicitly labels source-only diagnostics as provisional.

## 2026-09-29 — Phase 1–2 live execution and validation

- **Updated status:** Docker became available after the preceding blocked implementation. A Git-ignored `.env` with a generated local password was created, and the dedicated thesis Compose PostGIS service started healthy. The other existing Docker containers were not changed.
- **Observed:** all four migrations applied; PostgreSQL reports version 16.9 and PostGIS reports version 3.5. All six required schemas exist. The Phase 1 live tests passed, including migration idempotence and the 11-row sample CSV import. All 49 immutable raw files were hash-verified and registered.
- **Observed:** separate raw imports contain 23,144 detailed listing rows, 8,448,291 calendar rows, 471,781 review rows, and 11 provider neighbourhood rows. The clean listing table contains 23,144 unique listing IDs; 12,521 meet the predeclared primary-candidate flags. Phase 2 live geometry, price, room-type, count, and uniqueness tests passed. The database-derived report and aggregate output tables replace the provisional status report.
- **Source limitation retained:** all 23,144 raw `instant_bookable` values are empty, so that proposed predictor remains unavailable; it was not filled or inferred. The source `$` display/assumed DKK currency caveat, provider-neighbourhood rather than official-boundary study-area flag, and provider-anonymised coordinate limitation remain open.

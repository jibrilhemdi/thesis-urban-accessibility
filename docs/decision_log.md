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

## 2026-09-29 — Phase 3 context resolution and model eligibility

- **Decision:** import all 18 archived national and City context CSV versions as separate, faithful `raw` tables; use only the latest two-municipality national and 2026-09-29 City district selections for clean measures. Retain historical versions and import hashes for provenance.
- **Decision:** keep `clean.municipality_context_measures` and `clean.copenhagen_district_context_measures` distinct, with a source ID, period, unit and definition on each row. Do not create a single pooled 11-area income/housing table or copy municipality values to listing rows as neighbourhood data.
- **Observed:** national tables offer two municipality observations; City tables offer ten Copenhagen district observations and none for Frederiksberg. The City district population sum (666,861) and household sum (332,166) differ from national Copenhagen totals (670,389 and 332,181). These discrepancies and unmatched income/housing denominators preclude treating the sources as interchangeable.
- **Model eligibility:** a municipality category derived from Airbnb listing geography is conditionally usable as a primary location control pending official boundary QA. City district context is Copenhagen-only robustness/context, with area-level uncertainty; a pooled Frederiksberg municipality proxy is exploratory mixed-resolution sensitivity only. Municipality income/population are descriptive, not listing/neighbourhood measurements. `log(population_density_i)` remains unavailable without validated area denominators and submunicipal Frederiksberg data; pooled neighbourhood `income_i` remains unavailable without compatible small-area measures.
- **Open acquisition/QA:** obtain/validate official district and municipality/small-area polygons, land-area treatment, a listing-to-area crosswalk, and any needed Frederiksberg small-area population/income/housing data. No small-area value or density is inferred from existing municipality totals.

## 2026-09-29 — Phase 4 provider geography and spatial foundation

- **Observed:** the only archived boundary-like layer is Inside Airbnb's 11-neighbourhood GeoJSON. It has no explicit `crs` member; WGS84 longitude/latitude was inferred under RFC 7946 and recorded, with transformations/distances in EPSG:25832. No official municipal, City district or common Frederiksberg small-area polygon source is present.
- **Decision:** load those polygons into `spatial.provider_neighbourhoods` explicitly as **provider proxies**, not official legal/statistical boundaries. Use `ST_Covers` and require exactly one match for provider area and municipality-proxy assignment. Leave `context_statistical_unit_id` NULL until matching official boundaries are acquired and checked; do not infer a City district merely from similar provider labels.
- **Observed QA:** all 23,144 listings have exactly one covering provider polygon and matching provider label; none is unassigned or multiply assigned. 3,103 are within 100 m of a provider border (1,660 primary candidates). Candidate area Ns range 221–2,209; no number of geographic CV folds is fixed.
- **Decision:** store a provider study proxy and a planned 15-minute OSM extraction footprint based on all listing points plus provider coverage and a 1,500 m EPSG:25832 buffer. This exceeds the 1,260 m path length implied by the existing 1.4 m/s walking assumption. The archived OSM bbox does not fully cover this conservative footprint (96.11% area overlap), but it **does** contain the 1,260 m disk around every primary-candidate listing; only one non-primary listing fails. An expanded extract is needed for all-listing/full-footprint coverage, while feature-level network/POI completeness remains to be verified before full-threshold claims.
- **Decision:** use the published VisitCopenhagen Rådhuspladsen coordinates (12.568809986 E, 55.675902629 N) as the documented square reference point and calculate straight-line centre distance in EPSG:25832. No population density or contextual official-unit key was fabricated.

## 2026-09-29 — Phase 4 official geography and map correction

- **New source:** archive immutable GeoJSON for Copenhagen/Frederiksberg municipalities from the Danish national DAWA/DAGI API and ten Copenhagen `bydel` districts from the City's WFS. Record URLs, acquisition date, SHA-256 hashes and EPSG:4326 source CRS; use EPSG:25832 for metric calculations. The City WFS response does not state district vintage, so do not assume exact contemporaneity with the June Airbnb snapshot.
- **Superseding decision:** official municipality and City district polygons now define study geography and candidate spatial CV units. Frederiksberg remains one municipality-resolution CV unit, not a Copenhagen district. Retain provider polygons as comparison-only. The earlier claim that official polygons are unavailable is historical, not current.
- **Assignment rule:** require a unique `ST_Covers` municipality and unique CV unit with matching municipality codes. This assigns 23,066/23,144 listings and 12,508/12,521 Phase 2 primary candidates; 13 primary candidates remain spatially unassigned, without being removed from the Phase 2 price sample. Do not force points across legal boundaries: 42 points fall inside City district polygons but outside official municipalities, likely due to source edge differences and/or listing coordinate displacement.
- **Context caveat:** an official `bydel` boundary does not itself verify the period-specific City Statbank geography or land-area denominator. Keep `context_statistical_unit_id` NULL and density unavailable until the statistical crosswalk and area treatment are checked.
- **Map correction:** `phase04_study_area.png` now shows only official municipalities. A separate `phase04_osm_coverage.png` shows a 1,500 m buffer of actual official polygons and valid listing points versus the archived OSM request bbox; it replaces the visually misleading convex-hull overlay. The old municipality map filename is retained for compatibility but its content is now official. The revised buffer overlaps the archived bbox by 90.64% of its area; this is not an opportunity/network completeness estimate.

## 2026-09-29 — simplify extraction-area figure

- **User decision:** omit the archived OSM request bbox from `phase04_osm_coverage.png`. The map now shows only the planned 1,500 m extraction buffer and official study municipalities, with a title and legend reflecting those contents. The legacy filename is retained for links.
- **Preserved QA:** the archived bbox remains in `spatial.study_area` and in numeric coverage checks/reporting; no source file, geometry, or overlap statistic is removed. The figure no longer claims to display actual OSM coverage.

## 2026-09-29 — add neighbouring municipality cartographic context

- **User request:** make Phase 4 maps less visually isolated by showing surrounding official municipality boundaries.
- **Decision:** archive the national DAWA/DAGI Capital Region municipality GeoJSON separately with checksum and acquisition metadata. Load it into `spatial.map_context_municipalities`; render municipalities within 3.5 km of the two-municipality study polygon in faint colours behind all four Phase 4 maps. The source contains 29 municipalities; 10 nearby municipalities appear as the local context selection.
- **Analytical boundary unchanged:** context polygons are excluded from `spatial.official_municipalities`, `spatial.official_cv_areas`, study-area union, sample assignment and CV counts. Copenhagen and Frederiksberg remain the only study municipalities. The archived OSM request bbox stays off the maps.

## 2026-09-29 — Phase 5 OSM POI and Euclidean destination definition

- **Source/coverage:** cache the 2026-09-26 BBBike Copenhagen OSM PBF and 2026-09-27 polygon immutably, with 2026-09-29 acquisition metadata/hashes. Its rectangle covers all 23,144 listings' full 1,600 m disks; the archived smaller Overpass request does not. Record the roughly three-month mismatch to the June 30 Airbnb snapshot, rather than claiming contemporaneous destinations.
- **Pre-model taxonomy:** use restaurant/cafe/bar/pub, museum/gallery/attraction/viewpoint/theatre/monument/castle/palace, and named rail/metro station or halt. After inspecting the returned tags, revise the initial `phase05_v1` to `phase05_v2` by excluding memorial-only objects (266 had `historic=memorial`, many plaques/stones/Stolpersteine). This happened before any price modelling, was based on construct relevance, and did not alter the raw PBF. Keep the broader raw selected elements for audit.
- **Deduplication:** merge same-category candidates only on nearby shared normalized names (35/60/250 m by category) or nearby shared Wikidata (100/150/500 m). Prefer node/way/relation in that order. Preserve all source refs and canonical links. Store source point or `ST_PointOnSurface` in EPSG:4326/25832; use the same canonical points in a future walking-network comparison.
- **Feature definitions:** 800 m is the primary Euclidean opportunity count radius; 1,200 and 1,600 m are sensitivity radii. Nearest rail/metro station and counts use EPSG:25832; retain source-edge completeness flags. All 23,144 clean listings receive features, without excluding the 13 Phase 2 primary candidates whose official geographic CV area remains unresolved. No network measures or price models are in scope for this phase.

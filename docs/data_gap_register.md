# Phase 0 data gap register — 2026-09-29

Categories: **A** available but needs cleaning/derivation; **B** wrong geographic resolution; **C** wrong temporal resolution/alignment; **D** absent and must be acquired or provisioned for the stated design; **E** optional extension only. One requirement may appear in more than one category when both data and harmonisation are missing. No acquisition or modelling occurred in Phase 0.

| Category | Requirement/gap | Observed evidence | Consequence and Phase 1 action |
|---|---|---|---|
| A | Primary sample and conventional accommodation | 21,368 `Entire home/apt`; 12,779 have prices; property types include hotels/serviced/nonstandard units | Pre-specify conventional residential property types and exclusion rules; calculate frozen sample counts without silently broadening the segment |
| A | Outcome currency and price missingness | 13,860/23,144 listed prices, all rendered with `$`; 9,284 missing; scrape dates span 30 June–4 July | Verify provider currency and quote semantics, record scrape batch, audit missingness before log transformation or modelling |
| A | Bathrooms/bedrooms | Numeric bathrooms missing for 10,941; `bathrooms_text` parses for 22,940; bedrooms missing for 1,487 | Validate text parser; plan fold-contained missingness handling later |
| A | Amenities and other text fields | Raw amenities present; host/listing/review free text and identifiers also present | Parse only needed amenity features; exclude unnecessary identifying text from analytical tables |
| A | Review and calendar facts | 471,781 detailed reviews and 8,448,291 calendar rows; no exact duplicate review IDs or listing/date calendar keys | Aggregate by listing before joins; define review recency/availability/minimum-night summaries; do not call them demand/bookings |
| A | Euclidean and network opportunity measures | OSM network/POIs and nearest-category walk times exist; only city-centre Euclidean distance is currently engineered | In Phase 1/2 build and validate Euclidean POI counts, walking-network counts, and a reproducible feature table; no models yet |
| A | Population density | Counts and 11 provider polygons exist, but no validated polygon areas/density field | Validate geometry/CRS/topology, compute area denominator, mark Frederiksberg's municipality-sized proxy |
| A | Spatial provenance and coordinate accuracy | Coordinates are provider-anonymised; current metric transform is custom/approximate | In PostGIS, verify SRID and transform, point-in-polygon coverage, boundary-edge cases, and privacy safeguards |
| A | Visualisation file mismatch | 23,146 visualisation listing IDs versus 23,144 detailed IDs; two are summary-only | Reconcile IDs before freezing any joined listing source; prefer detailed listings for primary sample |
| A | Dataset freeze/manifest of derived outputs | 51 source-manifest files have valid hashes; processed Parquet/CSV are not in that manifest | Add output hash and pipeline/code/version lineage to analysis freeze without overwriting raw inputs |
| B | Frederiksberg neighbourhood context | National `FOLK1A`, `FAM55N`, `INDKP106`, `BOL101`, `BOL106` have only municipality codes 101/147 in current extracts | Cannot support within-Frederiksberg neighbourhood values. Current single-area proxy is acceptable only as flagged mixed-resolution sensitivity; acquire validated submunicipal data if neighbourhood inference is required |
| B | Pooled income/context comparability | Copenhagen context is 10 districts; Frederiksberg is one municipality; City `KKIND3` and national `INDKP106` denominators differ | Do not label the national row a district or treat repeated listing joins as independent contextual observations; retain strict City-only analysis |
| B | City district totals versus municipality totals | Copenhagen district population sums to 666,861 versus national municipality 670,389, even in 2026 Q3; household totals differ by 15 on 1 January 2026 | Do not assume the 10 City districts exhaust or exactly reproduce national municipality totals; check unallocated population and source definitions before density/pooled contextual claims |
| C | OSM date versus listing snapshot | OSM timestamp 2026-09-21; listings scraped 2026-06-30–07-04 | Document temporal mismatch; decide whether archived OSM is needed before making snapshot-time claims |
| C | Income vintage | Both sources use 2024 income for 2026 listings | Treat as lagged area context, not concurrent income; document release lag and concepts |
| C | Household versus listing date | Both household sources now reference 2026-01-01, but listings are June–July 2026 | Aligned to each other, not exactly to the listing date; sensitivity/limitation remains |
| D | `instant_bookable` | Column exists but all 23,144 source values are null | Remove as a primary covariate or obtain a verified alternate source/snapshot if essential |
| D | Calendar nightly prices | Calendar has only listing ID, date, availability, minimum/maximum nights | Do not claim calendar-priced outcomes; a separate suitable source would be required |
| D | PostgreSQL/PostGIS project infrastructure | No migrations, SQL files, Compose/Dockerfile, DB config template, or database code; PostGIS extension file not found in inspected local install | Decide deployment, verify extension/version/permissions, add safe config template and migrations before import. Do not connect/create in Phase 0 |
| D | Station-specific/timetable access | No GTFS and no station-specific feature table | Obtain GTFS only after approval; OSM transport-category times are not timetable access |
| D | Full-neighbourhood Frederiksberg population/income | No verified compatible district/neighbourhood statistical source or spatial crosswalk in the project | If the thesis requires within-Frederiksberg variation, source and validate it before pooled neighbourhood models; do not downscale municipality totals |
| E | TabICLv2 benchmark | Not part of current code/data | Consider only after core OLS/XGBoost and validation design are frozen |
| E | TabPFN missing-data sensitivity | Not part of current code/data | Optional methodological extension; no Phase 0 action |
| E | GTFS timetable accessibility | Approval still pending | Modular later extension; keep main analysis viable without it |

The source files support listing-level price/accessibility work, but they do **not** currently support listing-level neighbourhood population density and neighbourhood income across both municipalities at a common submunicipal resolution.

## Phase 3 status update — 2026-09-29

The five national table types (two archived versions each) and four City district table types (two archived versions each) are now loaded as 18 source-specific all-text `raw` tables with checksum/import lineage. Selected current measures are in separate `clean.municipality_context_measures` and `clean.copenhagen_district_context_measures` tables; see [Phase 3 report](../reports/phase03_context_data.md) and the reproducible [assessment CSV](../outputs/tables/phase03/context_source_assessment.csv). This resolves **ingestion**, not the geographic/definition gaps below.

| Category | Remaining context gap | Required action before proposed model use |
|---|---|
| A | `municipality_i` uses Airbnb neighbourhood labels; official boundary assignment has not been validated | Validate listing points against official municipal polygons in a recorded CRS; retain provider-anonymisation caveat |
| A/D | `log(population_density_i)` has population counts but no validated compatible land-area denominator | Acquire/validate official district and municipality/small-area polygons, confirm reference geography and water treatment, then calculate area in EPSG:25832 (or documented equivalent) |
| B/D | Frederiksberg has only one municipality observation in `FOLK1A`, `FAM55N`, `INDKP106`, `BOL101`, `BOL106` | Acquire verified submunicipal population/income/housing data and polygon crosswalk if within-Frederiksberg neighbourhood inference is required; do not downscale totals |
| B | City `KKBEF1`/`KKHUS1` and national municipality totals disagree (population +3,528 nationally; households +15) | Investigate geographic coverage and definitions before treating City sums as the municipality total |
| B | City `KKIND3` and national `INDKP106` income denominators are not established as equivalent | Keep a Copenhagen-only district sensitivity; do not pool them as harmonised 11-area income |
| C | Income is from 2024, housing from 2026, population 2026 Q3 and households 1 January 2026 | Keep separate periods and describe income as lagged context, not contemporaneous listing income |

National municipality values are suitable for two-area descriptive comparison, not as repeated listing-level neighbourhood observations. The only conditionally feasible primary location control from this phase is a municipality indicator derived from listings; City district measures are restricted contextual sensitivity variables. No density or pooled area-income variable has been created.

## Phase 4 spatial audit update — 2026-09-29

The archived Inside Airbnb layer supplied 11 valid provider `MultiPolygon` candidate areas. All 23,144 listings matched exactly one provider polygon with `ST_Covers`, but **official** Copenhagen/Frederiksberg municipal and City statistical-district polygons remain absent. No provider polygon is promoted to an official boundary, and the contextual statistical-unit ID remains NULL. See the [spatial foundation report](../reports/phase04_spatial_foundation.md).

| Category | Outstanding spatial requirement | Evidence and required action |
|---|---|---|
| B/D | Official municipality and City district polygons | Only provider neighbourhood GeoJSON is archived. Acquire matching official boundaries and compare assignment/area definitions before municipal or district spatial keys are declared verified. |
| B/D | Common submunicipal Frederiksberg statistics and geometry | Existing Frederiksberg polygon is one provider area, not neighbourhood-resolution context. Obtain compatible small-area data/boundaries if required; do not subdivide municipality totals. |
| A/D | Population density denominator | Provider polygon geometry areas can be calculated in EPSG:25832, but are not validated official **land** areas matched to statistical population units; density remains unavailable. |
| A | Near-border listing uncertainty | 3,103/23,144 listings are within 100 m of a provider-area edge (1,660 primary candidates). Validate official polygons and perform assignment sensitivity using anonymised listing-location uncertainty. |
| A/D | Complete 15-minute OSM extraction | Archived bbox covers only 96.11% of the conservative 1,500 m-buffer footprint by area, but contains every primary-candidate listing's 1,260 m radius under the 1.4 m/s assumption. One non-primary listing lacks full radius coverage. Re-extract/supplement for all-listing or full-footprint use; independently QA actual network/POI completeness before full-threshold claims. |

The Phase 4 11-area provider counts support CV feasibility inspection but do not fix folds or establish official statistical geography.

## Phase 4 official-boundary correction — 2026-09-29

The previous Phase 4 audit above describes the **initial provider-only state**. Official DAWA/DAGI municipality polygons and the City's ten `bydel` polygons are now archived, registered and loaded; see [updated Phase 4 report](../reports/phase04_spatial_foundation.md). The main study-area map is official. `outputs/tables/phase04/cv_area_counts.csv` now uses ten official Copenhagen districts plus Frederiksberg municipality, not provider polygons.

| Category | Remaining gap after acquisition | Required action |
|---|---|---|
| A | 13/12,521 Phase 2 primary-candidate listings have no consistent official municipality/CV assignment; 42 listings lie inside a City district but outside official municipal polygons | Preserve as unassigned; investigate source-edge differences and Airbnb coordinate anonymisation; predeclare sensitivity for area-based analyses |
| A/D | Official polygons do not by themselves verify City Statbank district unit/period equivalence or land-area denominator | Validate the statistical-area crosswalk and water/land area treatment before density or district-context joins |
| B/D | Frederiksberg remains one municipality-sized context unit, with no comparable within-municipality district values | Acquire compatible small-area measures if within-Frederiksberg neighbourhood inference is needed; do not downscale municipality totals |
| A/D | Archived OSM bbox covers 90.64% of the revised actual-geometry 1,500 m extraction footprint by area | Do not interpret overlap as POI/network completeness; perform edge and network QA before complete accessibility claims |

No final CV folds, population density or contextual area joins were created in this correction.

## Phase 5 Euclidean-accessibility update — 2026-09-29

The earlier OSM bbox coverage concern remains true for the **archived 2026-09-21 Overpass request**, but Phase 5 now uses a separately cached 2026-09-26 BBBike PBF whose polygon covers every listing's 1,600 m count circle and nearest observed station. `features.euclidean_accessibility` contains all 23,144 listings and the frozen canonical POI/station set; see [Phase 5 report](../reports/phase05_euclidean_accessibility.md). This resolves the Euclidean count-radius coverage gap, **not** future walking-network coverage or temporal alignment.

| Category | Remaining Phase 5-related gap | Required action |
|---|---|---|
| C | PBF map state is about three months after the June 30 Airbnb snapshot | Describe as a later OSM proxy; obtain a historical June OSM extract if same-date sensitivity is needed. |
| A/D | Walking-network completeness and routing have not been assessed | Later use the same canonical destination points and a network extract with validated full study/buffer coverage; do not infer network measures from these Euclidean features. |
| A | Polygon/line POIs use `ST_PointOnSurface`, not a mapped public entrance; OSM can omit or duplicate real venues | Preserve canonical destination IDs, audit unusual cases, and document representative-point/OSM completeness uncertainty. |

## Phase 6 walking-network update — 2026-09-29

Phase 6 routes all 23,144 listings to the exact Phase 5 canonical destinations using a persisted OSM pedestrian graph; see [Phase 6 report](../reports/phase06_network_accessibility.md). It resolves the missing walking-feature construction, but not all network coverage/quality issues.

| Category | Remaining network issue | Required action |
|---|---|---|
| A/D | The source PBF omits 8.31 km² of the 203.16 km² official 1,500 m buffered polygon, although every listing's 1,600 m disk is covered and all non-NULL station routes are shorter than the source-edge distance | Acquire a wider matched-vintage PBF if literal whole-buffer coverage or analyses outside the listing-centred catchments are required; do not relabel the current source as full-buffer coverage. |
| A | 165 listings (96 primary candidates) snap to disconnected graph components with no selected station | Preserve NULL station time/status; inspect missing pedestrian links and consider a separately declared connectivity sensitivity, not an unflagged connector. |
| A | Two POIs and five listings snap >100 m; polygon representative points, ferry/elevator omissions, conditional access and constant-speed steps can distort true walking routes | Audit flagged destinations/locations privately, predeclare any alternative routing assumptions and retain the Phase 5 canonical destination set for the main comparison. |
| C | OSM network/destinations date from late September versus June–July listings | Treat as later-map proxy; historical June OSM source is needed for same-date sensitivity. |

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

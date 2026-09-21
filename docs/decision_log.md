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

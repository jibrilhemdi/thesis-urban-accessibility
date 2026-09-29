# Initial data dictionary

This is the source-layer dictionary. The analytical dictionary should be expanded when cleaning and feature engineering begin.

| Source | Object/file | Intended role | Key fields/objects | Main caveat |
|---|---|---|---|---|
| Inside Airbnb | `data/listings.csv.gz` | Listing-level outcomes and controls | `id`, `latitude`, `longitude`, `price`, room/property type, capacity, reviews, host/listing controls | Coordinates are anonymised; price is listed price |
| Inside Airbnb | `data/calendar.csv.gz` | Calendar availability/restriction sensitivity | listing id, date, available, minimum nights, maximum nights | The 2026-06-30 Copenhagen file contains no calendar price field; blocks can reflect host choices as well as bookings |
| Inside Airbnb | `data/reviews.csv.gz` | Review activity/timing | listing id, review date, reviewer/listing identifiers | Reviews are an activity proxy, not bookings |
| Inside Airbnb | `visualisations/listings.csv` | Compact summary layer for maps/EDA | listing id, coordinates, price and summary metrics | Not a substitute for detailed listings; inspect price currency before use |
| Inside Airbnb | `visualisations/reviews.csv` | Compact review summary layer | listing id, date/summary fields | Check exact schema before analysis |
| Inside Airbnb | `visualisations/neighbourhoods.csv` | Neighbourhood lookup | neighbourhood names/identifiers | Provider-defined geography |
| Inside Airbnb | `visualisations/neighbourhoods.geojson` | Neighbourhood polygons | geometry and neighbourhood attributes | Use as a descriptive geography unless boundaries are independently validated |
| OSM/Overpass | `responses/walking_network.json` | Walkable network input | highway ways plus referenced nodes | Query is bounded to the listing extent plus buffer |
| OSM/Overpass | `responses/amenities_and_transport.json` | Amenity/transport opportunities | amenity, tourism, leisure, shop, public transport and selected railway tags | Tag completeness varies spatially |
| City of Copenhagen Statbank | `KKBEF1.csv` | Population context by district | total population, latest available quarter | Geography covers City of Copenhagen districts, not Frederiksberg |
| City of Copenhagen Statbank | `KKHUS1.csv` | Household context by district | total households, latest available quarter | Geography covers City of Copenhagen districts, not Frederiksberg |
| City of Copenhagen Statbank | `KKIND3.csv` | Income context by district | average disposable income for persons aged 14+, sex total, latest annual release | Income is a district-level aggregate in DKK |
| City of Copenhagen Statbank | `KKBOL3.csv` | Dwelling/resident context by district | dwellings, occupied dwellings, residents, average residents per occupied dwelling | Housing variables use the latest available annual release |
| Statistics Denmark StatBank | `FOLK1A.csv`, `FAM55N.csv`, `INDKP106.csv`, `BOL101.csv`, `BOL106.csv` | Municipality context for Frederiksberg | population, households, average disposable income, dwelling totals, registered-population dwellings, average persons per dwelling | Municipality-level context is not a district-level continuation of the City Statbank; source/provider and geography are retained in the analytical output |

Planned derived fields include network travel time to stops/amenities, counts within walking thresholds, distance-decay indices, and spatial validation blocks. These should not be added until the source schema and coordinate handling are inspected.

## Snapshot-specific checks

- Detailed listings contain 23,144 rows and 90 columns. The `price` field is formatted with a dollar sign in the downloaded snapshot; do not label it DKK or convert it until the provider’s currency convention is confirmed and a conversion rule is pre-specified.
- Detailed calendar contains 8,448,291 rows and 5 columns. It is useful for availability/restriction summaries in this snapshot, but not for a calendar-based price outcome.

## Available pipeline outputs

The local processed table at `data/processed/copenhagen/2026-06-30/` contains one row per source listing and includes:

- cleaned numeric source price and `log_price_source_currency` without currency conversion;
- non-identifying property, availability, review, and aggregate host-control fields;
- projected `x_utm32_m`/`y_utm32_m` coordinates and distance to a fixed Copenhagen centre reference;
- nearest OSM network node, off-network snap distance, and network degree;
- walking time to the nearest OSM food/drink, green-space, retail, services, tourism, and transport opportunity;
- `network_nearest_category_accessibility_index`, a minimum-version decay score based on those nearest-category times.

This first index is deliberately not described as a full opportunity count within a 5/10/15-minute catchment. That richer measure can be added after the core analytical table is stable.

The Copenhagen/Frederiksberg context extraction joins 10 City of Copenhagen districts to 20,644 listings and Statistics Denmark municipality context to 2,500 Frederiksberg listings. The source provider and geography fields must be retained in models and tables because the two context layers have different geographic levels.

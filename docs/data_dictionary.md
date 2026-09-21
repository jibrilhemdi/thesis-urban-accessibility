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

Planned derived fields include network travel time to stops/amenities, counts within walking thresholds, distance-decay indices, and spatial validation blocks. These should not be added until the source schema and coordinate handling are inspected.

## Snapshot-specific checks

- Detailed listings contain 23,144 rows and 90 columns. The `price` field is formatted with a dollar sign in the downloaded snapshot; do not label it DKK or convert it until the provider’s currency convention is confirmed and a conversion rule is pre-specified.
- Detailed calendar contains 8,448,291 rows and 5 columns. It is useful for availability/restriction summaries in this snapshot, but not for a calendar-based price outcome.

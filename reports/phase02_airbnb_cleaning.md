# Phase 2 — Airbnb cleaning and primary sample candidate

Snapshot: 2026-06-30. Generated from PostgreSQL `raw` and `clean` tables by `python -m src.pipeline.run_airbnb_phase2`; no local Parquet/CSV was used as input. Source CSV values are kept in versioned raw tables. The primary candidate remains a *listed-price* sample, not bookings or realised prices.

## Raw ingestion and sample funnel

Raw imports: 23,144 detailed listings, 8,448,291 calendar rows, 471,781 detailed reviews, and 11 provider neighbourhood labels. The listings have 23,144 distinct IDs. Calendar and reviews are **not joined** to the listing table in Phase 2.

| Stage | Remaining N | Excluded at stage |
|---|---:|---:|
| raw_listings | 23,144 | 0 |
| in_study_area | 23,144 | 0 |
| entire_home_apt | 21,368 | 1,776 |
| conventional_residential | 21,080 | 288 |
| valid_positive_price | 12,521 | 8,559 |
| valid_coordinates | 12,521 | 0 |

No review-count or availability restriction is used. Source `last_scraped` is provenance, not a replacement-price or model-control rule.

## Price and log-price

The numeric source `price` is treated as DKK per user confirmation; the file displays `$` and has no explicit currency code. No conversion or statistical outcome imputation is performed. Nonmatching or missing price strings remain NULL; non-positive numeric prices have NULL log-price and fail `valid_price`. Values below are listed nightly prices, not transactions.

| Sample | N | Price min | Price Q1 | Price median | Price Q3 | Price max | Log min | Log Q1 | Log median | Log Q3 | Log max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all_valid_prices | 13,860 | 45.16 | 1,272.67 | 1,689.00 | 2,305.00 | 42,931.33 | 3.81 | 7.15 | 7.43 | 7.74 | 10.67 |
| primary_candidate | 12,521 | 71.08 | 1,364.00 | 1,737.50 | 2,342.50 | 42,931.33 | 4.26 | 7.22 | 7.46 | 7.76 | 10.67 |

The same aggregates are exported to `outputs/tables/phase02/price_distribution.csv`.

Price completeness by scrape date (diagnostic only):

| Scrape date | Listings | Valid prices |
|---|---:|---:|
| 2026-06-30 | 10,035 | 9,133 |
| 2026-07-01 | 4,125 | 4,044 |
| 2026-07-03 | 4,329 | 406 |
| 2026-07-04 | 4,655 | 277 |

## Property-type decisions

The inclusion rule is based on clearly residential, self-contained urban dwelling forms, not predictive performance. Excluded rows remain in `clean.airbnb_listings` with flags. The table below covers every source category; `outputs/tables/phase02/property_type_decisions.csv` also gives entire-home and priced counts.

| Property type | All listings | Decision | Reason |
|---|---:|---|---|
| Barn | 1 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Boat | 8 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Camper/RV | 4 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Casa particular | 1 | Exclude | Ambiguous residential type; not verifiably conventional |
| Entire bungalow | 11 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Entire cabin | 8 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Entire condo | 5,599 | Include | Clearly self-contained conventional urban dwelling form |
| Entire cottage | 1 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Entire guesthouse | 27 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Entire guest suite | 5 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Entire home | 1,260 | Include | Clearly self-contained conventional urban dwelling form |
| Entire loft | 104 | Include | Clearly self-contained conventional urban dwelling form |
| Entire place | 5 | Exclude | Ambiguous residential type; not verifiably conventional |
| Entire rental unit | 13,588 | Include | Clearly self-contained conventional urban dwelling form |
| Entire serviced apartment | 162 | Exclude | Hotel, hostel, or serviced/commercial accommodation |
| Entire townhouse | 343 | Include | Clearly self-contained conventional urban dwelling form |
| Entire vacation home | 4 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Entire villa | 186 | Include | Clearly self-contained conventional urban dwelling form |
| Farm stay | 1 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Houseboat | 24 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Hut | 1 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Private room | 1 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in barn | 1 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in bed and breakfast | 17 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in boat | 4 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in casa particular | 5 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in condo | 391 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in guesthouse | 13 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in guest suite | 7 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in home | 134 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in hostel | 13 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in houseboat | 1 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in hut | 3 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in loft | 5 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in rental unit | 1,038 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in serviced apartment | 4 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in shipping container | 5 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in townhouse | 32 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Private room in villa | 36 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Room in aparthotel | 20 | Exclude | Hotel, hostel, or serviced/commercial accommodation |
| Room in boutique hotel | 2 | Exclude | Hotel, hostel, or serviced/commercial accommodation |
| Room in hotel | 30 | Exclude | Hotel, hostel, or serviced/commercial accommodation |
| Shared room in condo | 3 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Shared room in hostel | 9 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Shared room in hotel | 7 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Shared room in rental unit | 1 | Exclude | Room-level accommodation, not a self-contained entire dwelling |
| Shipping container | 3 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Tiny home | 15 | Exclude | Nonstandard, accessory, or holiday accommodation form |
| Tower | 1 | Exclude | Nonstandard, accessory, or holiday accommodation form |

## Candidate controls and amenities

No predictor imputation is applied. Missingness from the clean listing table:

| Field | Missing / all listings |
|---|---:|
| accommodates | 0/23,144 |
| bedrooms | 1,487/23,144 |
| bathrooms | 10,941/23,144 |
| bathrooms_text | 5/23,144 |
| amenities_raw | 0/23,144 |
| minimum_nights | 0/23,144 |
| instant_bookable | 23,144/23,144 |
| host_is_superhost | 1/23,144 |
| host_listings_count | 1/23,144 |
| calculated_host_listings_count | 0/23,144 |
| number_of_reviews | 0/23,144 |
| number_of_reviews_ltm | 0/23,144 |
| review_scores_rating | 3,060/23,144 |

`instant_bookable` is empty for every archived listing and is unavailable as a Phase 2 control; no value is inferred from other fields.

Amenities were parsed as source JSON arrays for the 21,080 entire-home conventional listings, before price selection. 21,080 arrays parsed; 0 are invalid/missing and are not silently treated as amenity absence. 3,869 distinct raw tokens were observed; only controlled, accommodation-relevant labels are published below. Internal candidates require strict 5% < prevalence < 95% among parsed arrays, independent of price.

| Amenity | Present / parsed listings | Prevalence | Internal candidate |
|---|---:|---:|---|
| Wifi | 19,421/21,080 | 92.1% | Yes |
| Kitchen | 20,860/21,080 | 99.0% | No |
| Dishwasher | 12,002/21,080 | 56.9% | Yes |
| Washer | 11,944/21,080 | 56.7% | Yes |
| Dryer | 3,260/21,080 | 15.5% | Yes |
| Dedicated workspace | 8,778/21,080 | 41.6% | Yes |
| Air conditioning | 253/21,080 | 1.2% | No |
| Free parking on premises | 2,837/21,080 | 13.5% | Yes |
| Private patio or balcony | 5,483/21,080 | 26.0% | Yes |
| Self check-in | 7,452/21,080 | 35.4% | Yes |

## Coordinates, reviews, and limitations

Coordinates: 23,144/23,144 valid global longitude/latitude pairs; 23,144 have both 4326 and 25832 point geometries. Longitude range 12.46–12.64; latitude range 55.62–55.73. PostGIS applies `ST_Transform` from source WGS84 (EPSG:4326) to ETRS89 / UTM 32N (EPSG:25832), a projection used for Denmark by [the Danish national mapping authority](https://www.sdfe.dk/media/2919769/001-etrs89-utm.pdf). Both geometry columns have GiST indexes. Airbnb coordinates are provider-anonymised; no address-level precision is claimed.

Review counts: median 8.00; 95th percentile 75.00; max 2,693; zero-review listings 3,060. Reviews are an activity proxy, not bookings.

`in_study_area` uses provider neighbourhood labels in the imported lookup. It is not an independently validated official municipality boundary; polygon containment remains future spatial QA. The conventional-type rule is intentionally conservative and may exclude some residential but atypical/holiday forms. Calendar availability is not occupancy. Detailed reviews contain personal/free text and are kept only in access-controlled `raw`; none is copied to this report or the clean listing table. No accessibility measures are calculated in Phase 2.

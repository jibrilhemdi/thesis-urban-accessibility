# Phase 4 — official study geography and spatial identifiers

Date: 2026-09-29. Reproduce with `make phase4-acquire-boundaries` (once), `make phase4-run`, then `THESIS_PHASE4_TEST=1 make phase4-test`. PostgreSQL/PostGIS is authoritative. This phase does not compute accessibility, density, final CV folds or models.

## Boundary sources and provenance

The initial archived Inside Airbnb `neighbourhoods.geojson` contains 11 provider-labelled areas. Those remain in `spatial.provider_neighbourhoods` for QA only; they are **not** official administrative boundaries. The following official sources were acquired on 2026-09-29 into immutable, date-stamped `data/raw/official_boundaries/2026-09-29/` files with source URLs, byte sizes and SHA-256 hashes in `acquisition_metadata.json` and registrations in `meta.source_files`:

| Layer | Provider | Source date/vintage | Database table |
|---|---|---|---|
| Copenhagen (0101) and Frederiksberg (0147) municipalities | [Danish national DAWA/DAGI municipality API](https://dawadocs.dataforsyningen.dk/dok/api/kommune) | Geometry changed 2026-03-27 and 2024-01-16, respectively, as returned by API | `spatial.official_municipalities` |
| Ten numbered Copenhagen `bydel` districts | [City of Copenhagen WFS `k101:bydel`](https://wfs-kbhkort.kk.dk/k101/ows?service=WFS&request=GetCapabilities) | Service response has no explicit source-vintage field; acquisition date is **not** a claim of 2026 boundary vintage | `spatial.official_copenhagen_districts` |
| Capital Region municipalities for surrounding map context | [Danish national DAWA/DAGI municipality API](https://dawadocs.dataforsyningen.dk/dok/api/kommune), filtered to region 1084 and real municipalities | Individual feature versions; acquired 2026-09-29 | `spatial.map_context_municipalities` |

Source GeoJSON was requested as EPSG:4326 and checked for valid, nonempty `MultiPolygon` geometries; the study-area files additionally passed Copenhagen-area bounds checks. Original coordinate geometry, standard EPSG:4326 geometry and transformed EPSG:25832 geometry/boundaries are retained. EPSG:25832 is used for area, distance and the scale bars. GiST indexes support point-in-polygon assignment. The official municipal union is **100.41 km² of polygon geometry**, not a verified statistical land-area denominator. Official district names and IDs have not yet been crosswalk-verified against the period-specific City Statbank geography; therefore `context_statistical_unit_id` stays NULL. No density has been calculated.

The separate Capital Region archive contains 29 official municipality polygons; 10 within 3.5 km of the study-area geometry appear as low-contrast surrounding map context. Its raw GeoJSON, sidecar checksum and database import are separate from the two study municipalities. It does **not** expand the study area, enter listing assignment, supply contextual covariates or alter CV-area counts.

## Listing assignments

`ST_Covers` assigns a listing only when exactly one official municipality and exactly one official CV unit cover it **and their municipality codes agree**. `spatial.official_cv_areas` is ten official Copenhagen districts plus Frederiksberg municipality as a single, explicitly municipality-resolution unit. The original provider assignment is preserved in separate `municipality_proxy`/`cv_area_id` columns for comparison. Source Airbnb points may be location-anonymised, so exact administrative assignment at a boundary is uncertain.

| Official assignment QA | All 23,144 listings | Phase 2 primary candidates (12,521) |
|---|---:|---:|
| Consistent municipality + CV area | 23,066 | 12,508 |
| No covering municipality | 76 | 13 |
| No covering CV area | 36 | 5 |
| District polygon covers point, municipality polygon does not | 42 | 8 |
| Municipality covers point, no district/CV polygon does | 2 | 0 |
| Multiple municipality or CV polygons | 0 | 0 |
| Within 100 m of an official CV-area boundary | 3,357 | Not used as an exclusion |

The two official layer products are not geometrically identical at every edge: 42 points are inside a district polygon but outside both municipal polygons. Among the 76 outside-municipality points, distance to the nearest municipality polygon ranges from 0.1 to 56.7 m (median 17.5 m for points outside both layers; 4.1 m for district-only points). These could reflect source-boundary differences or Airbnb coordinate displacement; there is no evidence to force an area assignment. The 13 Phase 2 candidates remain in the Phase 2 sample and are flagged as unassigned for any later area-based analysis. Counts in [official CV-area table](../outputs/tables/cv_area_counts.csv) consequently sum to 12,508, **not** 12,521. This is a spatial assignment gap, not an Airbnb price exclusion.

The city-centre reference remains City Hall Square (12.568809986° E, 55.675902629° N), sourced from [VisitCopenhagen](https://www.visitcopenhagen.nl/kobenhavn/planlaeg-din-tur/city-hall-square-gdk414247). `distance_centre_euclidean_km` is a straight-line EPSG:25832 distance, not network travel time.

## What the maps mean

- [Study area](../outputs/figures/phase04_study_area.png): Copenhagen and Frederiksberg are highlighted as the **only study municipalities**, with light neighbouring municipality polygons behind them and the City Hall Square reference. Small detached pieces and waterfront detail are in the source administrative polygons, not invented plotting units.
- [Municipalities](../outputs/figures/phase04_municipality_proxy.png): the two official municipalities in different colours. The filename is retained for compatibility with earlier links; its contents are **no longer proxy geography**.
- [Candidate geographic CV areas](../outputs/figures/phase04_candidate_cv_areas.png): ten numbered official Copenhagen districts and Frederiksberg as one municipality-sized unit. Numbers are district identifiers, not final folds.
- [Planned OSM extraction area](../outputs/figures/phase04_osm_coverage.png): pale blue is a planned 1,500 m buffer around official municipal polygons **and all valid listing points**, created in EPSG:25832, with faint neighbouring municipalities for orientation. It is a proposed extraction footprint, **not** a municipal boundary or a depiction of already downloaded OSM features. The buffer also surrounds small detached legal municipal pieces, producing isolated circles. The archived OSM request box is deliberately **not plotted**; its overlap remains a numerical QA check below. The filename is retained for compatibility with earlier links.

The older `phase04_study_area.png` looked strange because it superimposed a provider-proxy union, a convex-hull buffer and a projected OSM request box in one image, with raw UTM axes. The new main map separates study geography from the planned extraction area and adds a metric scale bar, north arrow, readable legend and source attribution. The planned footprint now buffers the actual official geometry and valid listings, rather than connecting detached pieces with a large convex hull. Its area is **203.16 km²**. Separately, the archived 2026-09-21 OSM request bbox is **244.10 km²** and covers **90.64%** of the planned buffered footprint by area; it does not contain the whole footprint. The area percentage is not a measure of POI/network completeness. The archived bbox covers a 1,260 m Euclidean disk around every Phase 2 primary-candidate listing under the provisional 1.4 m/s walking assumption, but detailed network/POI completeness remains to be checked. Archived OSM also postdates the June–July Airbnb listing snapshot.

## Outstanding work

Verify an exact district-to-City-Statbank unit crosswalk and statistical area denominator before using district context/density. Resolve or sensitivity-test 13 primary-candidate points lacking consistent official spatial assignment. Frederiksberg still has only municipality-level context; no within-municipality small-area statistics have been fabricated. Verify network/POI coverage before claiming complete 15-minute access. No final CV fold structure has been selected.

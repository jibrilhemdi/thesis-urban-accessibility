# Phase 5 — OSM destinations and Euclidean accessibility

Completed 2026-09-29. Scope ends at straight-line accessibility; no walking-network measure, price regression, or feature selection by model performance was run.

## Source, extent and timing

The immutable [BBBike Copenhagen OpenStreetMap city extract](https://download3.bbbike.org/osm/bbbike/Copenhagen/) is archived as `data/raw/osm/phase05/2026-09-29/Copenhagen.osm.pbf` (52,339,239 bytes, SHA-256 `0f1bdc8e56ff00fbe4deac6ebeb2c96497b3b5331989d07a156ae5645d462e13`) with `Copenhagen.poly` (SHA-256 `30f9e005301145cbe617a4897d31d26defd28b13268a6cefe755180ca12d4b94`) and acquisition metadata. The source's published file modification date is 2026-09-26 (polygon: 2026-09-27); acquisition was 2026-09-29 UTC. The polygon is a rectangle at 12.25–12.70° E and 55.55–55.85° N. OSM data are © OpenStreetMap contributors, ODbL. The Inside Airbnb listing snapshot is 2026-06-30: **the OSM source is about three months later**, so these features do not represent an exact contemporaneous June built environment. A dated June OSM historical extract would be needed for a temporally matched sensitivity.

The PBF and polygon are registered in `meta.source_files` with hashes, source URLs, dates and extent. The selected-source import is logged in `meta.import_runs`. The preceding 2026-09-21 Overpass request box did not cover every listing's 1,600 m disk (67 all-listing cases, including 35 primary candidates), so it was not used for these features. The new PBF polygon covers the full 1,600 m disk for all 23,144 listing coordinates. No repeated live OSM calls are needed on rerun.

Extraction used Python 3.13.5, SQLAlchemy 2.0.39 and GDAL 3.8.5's OSM PBF driver with the pinned `config/osmconf_phase5.ini` and the five `points`, `lines`, `multipolygons`, `multilinestrings`, `other_relations` layers. The exact prefilter (also logged in `meta.import_runs.import_options`) was `amenity IN (restaurant,cafe,bar,pub,theatre) OR tourism IN (museum,gallery,attraction,viewpoint) OR historic IN (monument,memorial,castle,palace) OR railway IN (station,halt) OR public_transport=station`. The broader historical `memorial` prefilter deliberately retains those objects in `raw` for audit even though final taxonomy v2 excludes memorial-only destinations. GDAL-selected GeoJSON features and full returned tags are retained in `raw.osm_phase5_elements`; the original PBF remains the authoritative immutable source. PostgreSQL 16.9/PostGIS 3.5 spatial tables store representative points in WGS84 EPSG:4326 and ETRS89 / UTM zone 32N EPSG:25832. All metric distance/count calculations use EPSG:25832.

## Frozen, pre-model taxonomy

The specification is [`docs/osm_poi_taxonomy_phase05.md`](../docs/osm_poi_taxonomy_phase05.md), version `phase05_v2`. `food_social` uses restaurants, cafes, bars and pubs. `cultural_tourist` uses museums, galleries, attractions, viewpoints, theatres, monuments, castles and palaces. `station` uses named railway stations/halts and named public-transport stations with a rail/subway mode, excluding entrances and bus/tram-only stops. The destination entity, not an entrance, is the unit. OSM features with more than one qualifying category can appear in more than one category; no outcome association was used to decide this.

Initial v1 included all `historic=memorial`. Inspection of the returned tags showed 266 such objects, including many plaques, stones and Stolpersteine. Before any price modelling, v2 excluded memorial-only objects as weak proxies for substantial cultural/tourist opportunities. The source PBF was **not** replaced or edited; only Phase 5 derived rows were rebuilt. This taxonomy revision is documented in the decision log. Returned station mode tags gave 37 metro, 101 urban-rail/light-rail and 5 other-rail canonical objects; the mode is descriptive, not a different nearest-station destination set. OSM does not certify every facility's operational status; no selected station had `disused`, `construction`, `proposed`, `abandoned`, or `passenger=no` tags in the returned data.

| Stage / category | Objects |
| --- | ---: |
| Raw, tagged OSM objects retained | 3,981 |
| Category candidates: food/social | 3,010 |
| Category candidates: cultural/tourist | 468 |
| Category candidates: station | 165 |
| Canonical food/social destinations | 3,006 |
| Canonical cultural/tourist destinations | 463 |
| Canonical stations | 143 |
| Candidate duplicates merged across categories | 31 |

The raw tagged set includes 340 selected-by-query objects that do not pass the final category rules, chiefly memorial-only and other unqualified public-transport objects. Two other OSM objects qualify for more than one category, so the candidate total is not simply raw minus excluded. It is an audit extract, not the complete city OSM database. Geometry representatives were 3,380 candidate nodes and 263 polygon/line points-on-surface, with counts by category retained in `spatial.osm_destination_candidates`. A polygon/line `ST_PointOnSurface` lies on the mapped feature, but need not be its public entrance; the same canonical point set must be used for the eventual network comparison.

## Deduplication and query design

Each candidate retains OSM type/ID, source file, tags, name, WGS84 and projected point, canonical reference and merge reason. The predeclared rules merge only same-category, nearby candidates with a shared normalized name (35 m food, 60 m culture, 250 m station) or shared Wikidata ID (100/150/500 m respectively). Spatial proximity alone does not merge unrelated venues. Canonical preference is node, then way, then relation, then lower OSM ID. Of the 31 merged duplicates, 27 used same-name proximity and 4 shared Wikidata. Breakdown: 4 food, 5 cultural and 22 station duplicate objects. `spatial.osm_pois` and `spatial.transit_stations` retain all merged source references and duplicate counts. Different entrances and platforms with different names may remain separate; this conservative rule is visible in the candidate audit and is a residual OSM mapping limitation.

`features.euclidean_accessibility` contains one row per 2026-06-30 listing. Nearest station is found by KNN GiST ordering on `geom_25832 <-> listing geom_25832`, then exact `ST_Distance`. Food/social and cultural/tourist counts use a GiST-supported `ST_DWithin(...,1600)` search and filtered exact `ST_DWithin` tests for 800 and 1,200 m; the 1,600 m count is the outer filtered set. Primary planned radius is 800 m; 1,200/1,600 m are sensitivity radii. The table records source/taxonomy, CRS EPSG 25832, coordinate validity, complete-count coverage, source-edge distance and nearest-station coverage. No missing coordinate/count is silently filled; in this snapshot all 23,144 clean listings have valid geometries.

## Feature distributions and coverage QA

| Measure, all 23,144 listings | Mean | P5 | P25 | Median | P75 | P95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Food/social count, 800 m | 112.8 | 9 | 32 | 78 | 147 | 350 |
| Cultural/tourist count, 800 m | 10.9 | 0 | 2 | 5 | 14 | 48 |
| Nearest station, metres | 453.2 | 128.1 | 275.1 | 406.2 | 561.0 | 901.8 |

Mean counts at 1,200/1,600 m are 226.3/375.5 food/social and 23.8/41.5 cultural/tourist. Seven listings have zero food/social destinations within 800 m; 1,994 have zero cultural/tourist destinations within 800 m. The nearest-station range is 5.7–2,372.8 m. For the 12,521 Phase 2 primary candidates, mean 800 m counts are 116.3 food/social and 11.6 cultural/tourist; mean nearest-station distance is 453.1 m. These are descriptive, not model effects.

All 23,144 rows have a full 1,600 m source-circle coverage flag and a complete nearest-station search: the smallest distance from a listing to the PBF polygon edge is 3,794.9 m, greater than both 1,600 m and the largest observed nearest-station distance (2,372.8 m). Counts are nonnegative and monotone across radii; no row multiplication occurred. All 12,521 primary candidates have a Phase 5 feature row, including the 13 still lacking a reliable official CV-area assignment from Phase 4. That geography gap remains unresolved; Phase 5 does not force those assignments.

The reproducible spot-check command is `python -m src.pipeline.qa_euclidean_phase5 --private-map /private/tmp/phase05_private_qa.png`. It picks distinct primary-candidate listings nearest the City Hall centre, farthest periphery, nearest the named OSM `Inderhavnen` water polygon, and nearest an official municipal border. The private four-panel map was inspected: the centre has a dense POI field, the periphery is sparse, the harbour-side case intersects the waterfront, and the border case crosses an official edge. The map stays **outside** public outputs because it contains individual listing points. An independent `ST_DWithin` recount and station `min(ST_Distance)` query matched all four stored cases:

| Private QA case (no listing identifier/coordinates) | Food 800 m | Culture 800 m | Station m | Independent recount |
| --- | ---: | ---: | ---: | --- |
| Centre | 439 | 60 | 63.8 | Pass |
| Periphery | 4 | 0 | 724.7 | Pass |
| Harbour-side | 183 | 29 | 720.6 | Pass |
| Municipal border | 24 | 5 | 318.1 | Pass |

The full import took about 8.0 seconds and the feature SQL about 9.3 seconds in the local Docker/PostGIS environment (hardware-specific, excluding download and manual QA). The Phase 5 live/static tests pass via `THESIS_PHASE5_TEST=1 make phase5-test`. Re-running `make phase5-run` reuses the registered immutable source and canonical destinations, then transactionally refreshes the feature rows without duplication.

## Reproduction and limitations

Run `make phase5-acquire`, `make phase5-run`, `THESIS_PHASE5_TEST=1 make phase5-test`, then the private QA command above; see the README. The runner regenerates aggregate-only `outputs/tables/phase05_destination_counts.csv` and `outputs/tables/phase05_feature_summary.csv` from PostGIS for the category/distribution tables; the spot-check table is regenerated by the QA command. No row-level listing coordinates or host fields are exported. The OSM extract is a September map state, can omit unmapped businesses, and uses points-on-surface rather than entrances for polygons. Straight-line proximity ignores barriers, bridges, water crossings and routing. The resulting canonical destination set is frozen for the later network comparison, but **no network accessibility was calculated in Phase 5**.

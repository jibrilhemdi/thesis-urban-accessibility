# Phase 6 — walking-network accessibility

Completed 2026-09-29. This phase constructs a pedestrian graph, snaps the Phase 2 listings and the **exact Phase 5 canonical POI/station keys**, computes walking routes, and stores all persistent network and feature state in PostgreSQL/PostGIS. No price modelling was performed.

## Source, construction and coverage

The network reuses the immutable [BBBike Copenhagen OSM PBF](https://download3.bbbike.org/osm/bbbike/Copenhagen/) acquired in Phase 5: file date 2026-09-26, download date 2026-09-29, SHA-256 `0f1bdc8e56ff00fbe4deac6ebeb2c96497b3b5331989d07a156ae5645d462e13`. No second request or changed destination extract was introduced. This map state remains roughly three months after the 2026-06-30 Airbnb snapshot. The raw PBF stays immutable and its provenance is already in `meta.source_files`.

Python 3.13.5, [Pyosmium 4.3.1](https://docs.osmcode.org/pyosmium/latest/reference/Handler-Processing/), NetworkX 3.4.2, PyProj 3.8.0, NumPy 2.1.3 and SciPy 1.15.3 were used. The `walk_phase06_v1` filter admits pedestrian-permitted OSM highway ways, excluding motorways/trunks, construction/proposed ways, area polygons, explicitly denied/private foot access, and ferries. Cycleways, bridleways and busways require affirmative foot access. Pedestrian-specific one-way/conveying tags are directional; motor-vehicle `oneway` alone does not make walking one-way. Exact rules and dependency versions are stored in `spatial.walking_networks.filter_spec` and `src/spatial/walking_network.py`. This is a documented research walking graph, not a claim of complete legal/physical accessibility; conditional access, gates, elevators, surface quality and stairs speed are not fully modelled.

Original OSM node IDs define topology, avoiding false connections where a bridge/underpass merely crosses in projected coordinates. Every admitted consecutive way-node pair becomes a segment with its actual foot direction(s). Way/node source coordinates are WGS84 EPSG:4326; lengths and snapping use ETRS89 / UTM 32N EPSG:25832. `spatial.walking_networks`, `spatial.walking_nodes` and `spatial.walking_edges` persist the source/version, projected node points and directed-segment permissions in PostGIS. A directed NetworkX graph is reconstructed from the source PBF for computation. The graph is recoverable from both the immutable PBF/code and the persisted node/edge tables.

| Graph measure | Count |
| --- | ---: |
| Admitted OSM ways | 149,131 |
| Walking nodes | 545,903 |
| Source way segments | 617,456 |
| Directed routable arcs | 1,234,730 |
| Weakly connected components | 816 |
| Nodes in largest component | 539,676 |

**Coverage boundary:** the PBF fully contains every listing's 1,600 m straight-line disk, and all computed station routes with non-NULL results are shorter than the listing-to-source-edge distance. Thus the *listing-centred 10/15/20-minute measures* and reported reachable station minima pass the available source-edge check. It does **not** fully cover the entire official 1,500 m buffered study polygon: 8.31 km² of its 203.16 km² lies outside the rectangular source, mostly on the eastern fringe; 0.03 km² of the unbuffered official study polygon lies outside. The overlap audit is reproduced by `outputs/tables/phase06/source_coverage.csv`. Do not claim full official-buffer coverage. A wider matched-vintage PBF is required for that literal coverage requirement or for non-listing-centred uses of the whole buffer. The earlier September 21 Overpass network was not substituted because its request box is smaller still.

## Walking assumptions and same-destination comparison

Constant speed is **4.8 km/h = 80 m/min**. Thus 10, 15 and 20 minutes correspond to **800, 1,200 and 1,600 m of walking-route length**. These are *not* Euclidean circles: the Phase 5 features count canonical destinations within 800/1,200/1,600 m straight-line distance, whereas Phase 6 counts those whose shortest eligible network route plus both endpoint snap connectors fits the same metre budget. The primary walking opportunity measure is 10 minutes; 15/20 minutes are sensitivities. The preferred nearest-station variable is continuous walking minutes, with network metres also retained. This is a walk to an OSM station point, **not** GTFS transit travel time, service frequency or station entrance availability. No occupancy or price variable enters any route decision.

Listings, all 3,469 canonical food/cultural POIs and all 143 canonical stations are snapped to their nearest routable walking **node** via a projected EPSG:25832 KD-tree. The source point, network-node key, connector distance, component and >100 m / >250 m warning flags are persisted in `features.walking_listing_snaps` and `spatial.walking_destination_snaps`. Every Phase 5 canonical destination has exactly one Phase 6 snap; no deduplicated POI was replaced, selected by price, or omitted. A connector is a straight line between the entity point and graph node, not a verified entrance/crossing, so large or barrier-crossing connectors remain a limitation.

| Entity | N | Median snap m | P95 m | Maximum m | >100 m | >250 m |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Listings | 23,144 | 17.73 | 47.23 | 118.01 | 5 | 0 |
| Canonical POIs | 3,469 | 15.16 | 37.25 | 218.38 | 2 | 0 |
| Canonical stations | 143 | 11.84 | 25.72 | 42.35 | 0 | 0 |

## Routing algorithm and runtime

One reverse, multi-source Dijkstra search propagates the shortest directional network distance and canonical station key from all station nodes, seeded with each station's connector cost. A listing adds its own connector to that result. For opportunities, listings are grouped by snapped node (13,311 distinct origins). One NetworkX cutoff Dijkstra to at most `1600 m - minimum listing connector` is run per origin. The reached-node distances are joined to the Phase 5 POI snaps; sorted category-specific arrival costs are counted with binary search for each listing's 800/1,200/1,600 m budget after adding that listing's connector. This avoids a 23,144 × 3,612 full origin-destination matrix and still counts distinct canonical POIs that share a network node. The opportunity searches visited 101,984,961 nodes in total (with repetition across origins).

On the local Docker/PostGIS machine, PBF graph construction took 10.01 s, graph persistence 30.56 s, routing 98.29 s, and the full run 154.02 s (hardware-specific; excludes the earlier PBF download and private visual QA). The graph import is versioned and logged in `meta.import_runs`; rerunning reuses its verified persisted rows. `features.walking_accessibility` is transactionally refreshed without replacing Phase 5 Euclidean features.

## Distributions and Euclidean comparison

| Measure, all listings unless noted | Mean | P5 | Median | P95 |
| --- | ---: | ---: | ---: | ---: |
| Walking food/social, 10 min | 65.83 | 3 | 43 | 223 |
| Walking food/social, 15 min | 141.95 | 9 | 98 | 466 |
| Walking food/social, 20 min | 243.75 | 20 | 161 | 769 |
| Walking cultural/tourist, 10 min | 5.69 | 0 | 2 | 26 |
| Walking cultural/tourist, 15 min | 13.42 | 0 | 6 | 59 |
| Walking cultural/tourist, 20 min | 24.45 | 1 | 12 | 96 |
| Nearest station, walking minutes (reachable N=22,979) | 8.87 | 3.01 | 8.11 | 16.63 |

At the primary 800 m/10-minute comparison, food/social means are **112.77 Euclidean versus 65.83 walking** (medians 78 versus 43); cultural/tourist means are **10.94 versus 5.69** (medians 5 versus 2). Walking counts never exceed corresponding same-radius Euclidean counts for any listing, as required by the projected straight-line lower bound. Nearest-station Euclidean distance has a 406.18 m median; walking network distance among reachable listings has a 648.93 m median. These minimums need not select the same station. Full radius comparisons and quantiles are reproducibly exported to `outputs/tables/phase06/euclidean_network_comparison.csv` and `feature_summary.csv`; area summaries are in `area_comparison.csv` and snap diagnostics in `snap_diagnostics.csv`. These files contain aggregates only, not host fields, free text, listing IDs or row-level coordinates.

All 23,144 listings have a Phase 6 feature row, including all 12,521 Phase 2 primary candidates. **22,979** have a reachable selected station and complete source-edge check. **165** (including 96 primary candidates) snap to small graph components with no reachable canonical station; their nearest-station distance/time and coverage flag are NULL with `routing_status='no_reachable_station'`. All 165 lie outside the largest weak component. They were not silently bridged to another component or statistically imputed. Opportunity counts remain defined for their own connected components. The station-time maximum among reachable listings is 48.54 minutes; it is a long-tail listed-location proxy, not evidence of a practical transit trip.

## Four geographic spot checks

The reproducible command `.venv/bin/python -m src.pipeline.qa_walking_phase6 --private-map /private/tmp/phase06_private_qa.png` selects distinct primary-candidate listings in the dense centre, beside the named OSM `Inderhavnen` harbour water polygon with a large straight-line/network food gap, at the periphery, and at an official municipal border. It independently reruns the 800 m NetworkX POI count and checks the nearest-station shortest path, including snap connectors. All four pass. The private map was visually inspected: many harbour-side points fall inside the 800 m circle across water but are not walk-reachable in 10 minutes; central/border areas have mixed reachable and circle-only POIs; the periphery remains sparse. The point-level QA map is in `/private/tmp`, **not** public project outputs.

| QA case | Food: Euclid 800 m | Food: walk 10 min | Culture: Euclid 800 m | Culture: walk 10 min | Euclid station m | Walk station min |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dense centre | 439 | 342 | 60 | 43 | 63.8 | 6.7 |
| Harbour barrier | 364 | 81 | 53 | 10 | 331.6 | 9.5 |
| Periphery | 4 | 1 | 0 | 0 | 724.7 | 12.3 |
| Municipal border | 388 | 298 | 40 | 26 | 172.1 | 3.0 |

## QA, unresolved issues and reproduction

Live tests verify migration idempotence, graph row counts/CRS, one snap per canonical Phase 5 destination, one feature row per listing, constant-speed conversions, and the network ≥ Euclidean distance / network counts ≤ same-radius Euclidean counts. `THESIS_PHASE6_TEST=1 make phase6-test` passes. The main unresolved issues are the official-buffer edge gap, the 165 disconnected listings, possible connector crossings/entrance mismatch, omitted ferries/elevator links and conditional access, constant-speed treatment of stairs/grade, and the September-versus-June temporal mismatch. No path was fabricated for disconnected components, and no outcome modelling occurred.

Reproduce with a local environment from the unified `requirements.txt`, the Phase 5 PBF/destination tables and a running PostGIS database: `make phase6-run`, `make phase6-export`, `THESIS_PHASE6_TEST=1 make phase6-test`, then the private QA command above. The export is derived from PostGIS; it is not an alternative analytical source of truth. Stop before modelling.

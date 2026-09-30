# Frozen Phase 5 OSM destination inventory for thesis appendix

This is a read-only documentation export from the canonical PostGIS tables, not a new extraction or feature construction. No price/model data were accessed.

Reproduce on the existing thesis database with `make destination-inventory` (or run `.venv/bin/python -m src.pipeline.export_destination_inventory_appendix` and then `.venv/bin/python -m src.pipeline.export_final_latex_tables`). The exporter fails if the archived PBF hash, saved Phase 5 counts, or Phase 6 snapped canonical keys differ.

- Taxonomy: `phase05_v2`; OSM source: `Copenhagen.osm.pbf`, dated 2026-09-26 and acquired 2026-09-29; SHA-256 `0f1bdc8e56ff00fbe4deac6ebeb2c96497b3b5331989d07a156ae5645d462e13`.
- Archived source URL: https://download3.bbbike.org/osm/bbbike/Copenhagen/Copenhagen.osm.pbf; recorded source extent: BBBike Copenhagen extract polygon; see Copenhagen.poly.
- The OSM map state is roughly three months later than the 2026-06-30 Airbnb listing snapshot. OSM does not exhaustively represent real-world destinations.
- Source geometry is EPSG:4326; spatial inside/outside classification uses ST_Covers with the official two-municipality union in EPSG:25832. The buffered primary accessibility universe is **not** clipped to that union.

## Exact post-deduplication counts

| Group | Inside study union | Outside study union | Total |
| --- | ---: | ---: | ---: |
| food_social | 2,315 | 691 | 3,006 |
| cultural_tourist | 272 | 191 | 463 |
| station | 65 | 78 | 143 |

Station modes: metro 37, urban_rail 101, rail 5. The 143 stations are named railway stations/halts or named qualifying public-transport stations. Bus/tram-only stops and subway entrances are not primary stations.

## Taxonomy and deduplication

Food/social = amenity restaurant/cafe/bar/pub. Cultural/tourist = tourism museum/gallery/attraction/viewpoint, amenity theatre, or historic monument/castle/palace. Memorial-only historical objects were excluded in phase05_v2 before price modelling. Other nonqualifying fast-food/takeaway-only, accommodation, generic historic and unnamed station tags remain excluded. A multi-tag object can qualify in more than one destination group; within a group it appears once. The subtype summary assigns one mutually exclusive display subtype, prioritising tourism, then amenity, then historic for multi-tag cultural POIs; this changes no inclusion rule. The full inventories retain an `all_qualifying_osm_tags` JSON field, so a palace-tagged attraction is still identifiable even when its exclusive display subtype is attraction.
Candidate-link audit: 3,643 Phase 5 candidates map to 3,612 canonical rows; dedup reasons are canonical 3612, same-name-nearby 27, same-Wikidata-nearby 4. Every canonical row has exactly the stored merged OSM refs and duplicate count. Nodes were preferred to ways, then relations, then lower OSM ID under the frozen within-category distance rules. Wikidata IDs in the CSV are drawn from all merged candidates where available; multiple distinct IDs, if any, are semicolon-separated.

## Appendix and supplementary files

- Appendix CSV/Markdown: `outputs/tables/final/appendix_destination_taxonomy.*`, `appendix_destination_counts.*`, `appendix_destination_examples.*`, and `appendix_destination_rail_metro.*`.
- Appendix LaTeX: `outputs/latex/appendix/destination_taxonomy.tex`, `destination_counts.tex`, `destination_examples.tex`, and `destination_rail_metro_full.tex`.
- Full supplementary CSVs: `outputs/tables/supplementary/destination_inventory_food_social.csv`, `destination_inventory_cultural_tourist.csv`, and `destination_inventory_rail_metro.csv`. They contain only public OSM destination coordinates/IDs, never Airbnb listing coordinates or IDs.

## Reconciliation and manuscript note

The exported group totals match the saved `outputs/tables/phase05/destination_counts.csv`: 3,006 food/social, 463 cultural/tourist and 143 stations. All 3,612 canonical keys appear exactly once in Phase 6 `spatial.walking_destination_snaps` on network `walk_phase06_v1_0f1bdc8e56ff00fb`. The Euclidean feature table has 23,144 rows with this Phase 5 source/version; the walking feature table has 23,144 rows on the same source/network. Station modes agree with the Phase 5 report and Phase 8 map legend. No raw OSM duplicate was separately exported after canonical merging.

**Manuscript-ready appendix note.** Accessibility measures use a fixed canonical OSM destination universe. Euclidean and walking measures use the same destinations: raw OSM elements were deduplicated before feature construction, and the taxonomy was fixed before price modelling. Memorial-only objects were excluded from the cultural/tourist set; bus stops are not part of the primary rail/metro/S-train station set. Full canonical inventories are supplied as supplementary machine-readable files. The OSM snapshot is dated 26 September 2026, roughly three months after the 30 June 2026 Airbnb snapshot. OSM mapping is not exhaustive of real-world destinations.

**Freeze:** no destination definition changed; no accessibility feature changed; no model was refitted. This export documents the existing frozen destination universe.

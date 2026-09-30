# Output placement plan

Copenhagen–Frederiksberg urban core means Copenhagen Municipality plus Frederiksberg Municipality. Keep eight numbered main tables plus a compact core RQ2 comparison panel. Phase 9 is the frozen base specification; the area-context-adjusted core specification was conceptually planned but implemented after Phase 9 because context comparability was unresolved at the Phase 7 freeze. Place the saved context-comparison figure and panel together in the main RQ2 results, not only in the generic robustness table. Use the validation-design schematic in Methods and retain the residual Moran diagnostic, actual 1.5 km block map and validation-designs table in the appendix. Original phase figures remain in place; no model result is replaced. Caption text is in `docs/final_figure_captions.md`.

| Item | Main text file |
|---|---|
| Table 1 — Sample construction | `outputs/tables/final/table1_sample_construction.csv` / `outputs/tables/final/table1_sample_construction.md` |
| Table 2 — Variable specification | `outputs/tables/final/table2_variable_specification.csv` / `outputs/tables/final/table2_variable_specification.md` |
| Table 3 — Descriptive statistics | `outputs/tables/final/table3_descriptive_statistics.csv` / `outputs/tables/final/table3_descriptive_statistics.md` |
| Table 4 — Accessibility definitions | `outputs/tables/final/table4_accessibility_definitions.csv` / `outputs/tables/final/table4_accessibility_definitions.md` |
| Table 5 — Compact hedonic ladder | `outputs/tables/final/table5_hedonic_ladder.csv` / `outputs/tables/final/table5_hedonic_ladder.md` |
| Table 6 — Predictive performance | `outputs/tables/final/table6_predictive_performance.csv` / `outputs/tables/final/table6_predictive_performance.md` |
| Table 7 — Incremental accessibility value | `outputs/tables/final/table7_incremental_accessibility.csv` / `outputs/tables/final/table7_incremental_accessibility.md` |
| Core RQ2 panel — Base versus area-context-adjusted prediction | `outputs/tables/final/table_rq2_area_context.csv` / `outputs/tables/final/table_rq2_area_context.md` |
| Table 8 — Robustness summary | `outputs/tables/final/table8_robustness_summary.csv` / `outputs/tables/final/table8_robustness_summary.md` |
| Figure 1 — Research workflow | `outputs/figures/final/figure1_workflow.png` |
| Figure 2 — Study area overview | `outputs/figures/final/figure2_study_area.png` |
| Figure 3 — Price distribution and spatial pattern | `outputs/figures/final/figure3_price_pattern.png` |
| Figure 4 — Euclidean versus network catchment | `outputs/figures/final/figure4_catchment_example.png` |
| Figure 5 — Matched accessibility measures | `outputs/figures/final/figure5_matched_accessibility.png` |
| Figure 6 — Accessibility–price association | `outputs/figures/final/figure6_accessibility_coefficients.png` |
| Figure 7 — Random versus geographic performance | `outputs/figures/final/figure7_validation_performance.png` |
| Figure 8 — Outer CV geography | `outputs/figures/final/figure8_cv_geography.png` |
| Methods figure — Validation designs | `outputs/figures/final/figure_validation_designs.png` |
| Core RQ2 context figure — Accessibility before/after area socioeconomic context | `outputs/figures/context_incremental_accessibility.png` |

## Frozen OSM destination appendix

These are documentation of the unchanged `phase05_v2` canonical destination universe, not new analytical results. No OSM inventory belongs in the main text. The appendix uses compact taxonomy, count and deterministic-example tables plus the complete 143-station list; thousands of POIs remain supplementary CSVs. The source is the 26 September 2026 OSM snapshot, about three months after the Airbnb snapshot. [Provenance and QA](../reports/appendix_destination_inventory.md).

| Item | Appendix / supplementary file |
|---|---|
| Taxonomy appendix | `outputs/tables/final/appendix_destination_taxonomy.csv` / `outputs/tables/final/appendix_destination_taxonomy.md` |
| Counts appendix | `outputs/tables/final/appendix_destination_counts.csv` / `outputs/tables/final/appendix_destination_counts.md` |
| Examples appendix | `outputs/tables/final/appendix_destination_examples.csv` / `outputs/tables/final/appendix_destination_examples.md` |
| Rail Metro appendix | `outputs/tables/final/appendix_destination_rail_metro.csv` / `outputs/tables/final/appendix_destination_rail_metro.md` |
| Full food social inventory | `outputs/tables/supplementary/destination_inventory_food_social.csv` (SUPPLEMENTARY / REPOSITORY) |
| Full cultural tourist inventory | `outputs/tables/supplementary/destination_inventory_cultural_tourist.csv` (SUPPLEMENTARY / REPOSITORY) |
| Full rail metro inventory | `outputs/tables/supplementary/destination_inventory_rail_metro.csv` (SUPPLEMENTARY / REPOSITORY) |

Thesis-ready LaTeX: `outputs/latex/appendix/destination_taxonomy.tex`, `destination_counts.tex`, `destination_examples.tex`, and `destination_rail_metro_full.tex`.

## Boundary-endpoint illustration

Keep the original main-text Figure 4 unchanged. Place the separate [public-OSM boundary catchment](../outputs/figures/final/appendix_boundary_catchment_example.png) in the appendix, cited alongside the boundary-sensitivity table. It illustrates which canonical endpoints are excluded when the official municipal union is applied; it is not a rerouted network catchment or a model-performance graphic. [Reproducible figure report](../reports/appendix_boundary_catchment_figure.md).

## Spatial-validation methods placement

The [validation-design schematic](../outputs/figures/final/figure_validation_designs.png) belongs in the Methods spatial-validation section (MAIN TEXT). Reference the actual [1.5 km geometric-block map](../outputs/figures/final/appendix_geometric_block_cv.png) there; the map is APPENDIX. The saved [validation-designs table](../outputs/tables/final/table_validation_designs.md) is APPENDIX supporting Methods. Random CV is interspersed, the block design is a non-administrative robustness split, and leave-one-area-out across 11 analysis areas is the primary unseen-area test.

## Appendix and repository-only outputs

The table below covers every exported file. `APPENDIX` means substantively useful but too detailed/redundant for the main narrative; `REPOSITORY ONLY` means QA, source coverage, tuning or machine-readable lineage rather than a manuscript figure/table.

| File | Placement | Reason |
|---|---|---|
| `outputs/figures/final/_revision_sources/appendix_geometric_block_cv.png` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/figures/final/_revision_sources/figure2_study_area.png` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/figures/final/_revision_sources/figure4_catchment_example.png` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/figures/final/appendix_boundary_catchment_example.png` | APPENDIX | Boundary endpoint inclusion illustration (public OSM only) |
| `outputs/figures/final/appendix_geometric_block_cv.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/final/figure9_residual_diagnostics.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase04/candidate_cv_areas.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase04/municipality_proxy.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase04/osm_coverage.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase04/study_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase07/missing_price_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase07/missing_price_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/cultural_euclidean_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/cultural_euclidean_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/cultural_walking_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/cultural_walking_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/euclidean_network_hexbin.png` | APPENDIX | Source presentation retained; final main-text composite preferred |
| `outputs/figures/phase08/food_euclidean_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/food_euclidean_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/food_walking_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/food_walking_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/listing_density.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/median_price_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/median_price_grid.png` | APPENDIX | Source presentation retained; final main-text composite preferred |
| `outputs/figures/phase08/price_distributions.png` | APPENDIX | Source presentation retained; final main-text composite preferred |
| `outputs/figures/phase08/station_walking_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase08/station_walking_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase09/accessibility_increment.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase09/geographic_oof_residual_ols_mw_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase09/geographic_oof_residual_ols_mw_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase09/geographic_oof_residual_xgboost_mw_area.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase09/geographic_oof_residual_xgboost_mw_grid.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase09/model_performance.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase09/ols_mw_coefficients.png` | APPENDIX | Source presentation retained; final main-text composite preferred |
| `outputs/figures/phase09/oof_residual_moran.png` | APPENDIX | Source presentation retained; final main-text composite preferred |
| `outputs/figures/phase09/xgb_mw_shap.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase10/bus_increment.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase10/geographic_fold_stability.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/figures/phase10/primary_validation_context.png` | APPENDIX | Source presentation retained; final main-text composite preferred |
| `outputs/figures/phase10/threshold_sensitivity.png` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/analysis_area_context.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/boundary_sensitivity_comparison.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/boundary_sensitivity_destination_counts.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/boundary_sensitivity_edge_concentration.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/boundary_sensitivity_feature_changes.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/boundary_sensitivity_fold_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/boundary_sensitivity_geographic_pairs.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/boundary_sensitivity_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/boundary_sensitivity_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/boundary_sensitivity_tuning.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/conclusion_stability.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/context_augmented_fold_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/context_augmented_geographic_pairs.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/context_augmented_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/context_augmented_ols.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/context_augmented_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/context_augmented_tuning.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/context_comparison.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/context_district_source_audit.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/copenhagen_only_context_sensitivity.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/final/appendix_boundary_catchment_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/final/appendix_destination_counts.csv` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/appendix_destination_counts.md` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/appendix_destination_examples.csv` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/appendix_destination_examples.md` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/appendix_destination_rail_metro.csv` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/appendix_destination_rail_metro.md` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/appendix_destination_taxonomy.csv` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/appendix_destination_taxonomy.md` | APPENDIX | Frozen canonical OSM destination appendix documentation |
| `outputs/tables/final/catchment_example_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/final/table5_full_coefficients_appendix.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/final/table5_full_coefficients_appendix.md` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/final/table7_incremental_accessibility_appendix.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/final/table7_incremental_accessibility_appendix.md` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/final/table_validation_designs.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/final/table_validation_designs.md` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/final/table_validation_performance.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/final/table_validation_performance.md` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase02/amenities_prevalence.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase02/control_missingness.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase02/price_distribution.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase02/property_type_decisions.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase02/sample_construction.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase03/context_source_assessment.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase04/cv_area_counts.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase05/destination_counts.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase05/feature_summary.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase06/area_comparison.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase06/euclidean_network_comparison.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase06/feature_summary.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase06/snap_diagnostics.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase06/source_coverage.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase07/context_area_redundancy.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase07/missingness_report.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase07/price_missingness_comparison.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase07/redundancy_pairs.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase07/sample_summary.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase07/spatial_cv_folds.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase07/vif_diagnostics.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/accessibility_correlations.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/buffer_feasibility.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/cv_fold_summary.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/descriptive_statistics.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/distance_bin_covariance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/geographic_support.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/map_coverage.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase08/sample_composition.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase08/spatial_moran.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/bus_fold_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/bus_ols_coefficient.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/bus_robustness.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/destination_boundary_audit.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/fold_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/geographic_fold_summary.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/geographic_residual_by_area.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/geographic_residual_grid_coverage.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/incremental_accessibility.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/model_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/ols_coefficients.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/ols_complete_case_sensitivity.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/ols_ladder.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/random_vs_geographic_cv.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/residual_moran.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/run_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase09/xgb_mw_shap.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase09/xgboost_tuning.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase10/accessibility_representation.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/buffer_separation.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/buffer_train_loss.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/bus_diagnostics.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/bus_feature_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase10/bus_shap.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/bus_spotcheck_groups.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/bus_vif.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/conclusion_stability.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/fold_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/geographic_fold_pairs.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/geographic_fold_summary.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/model_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/ols_associations.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/price_trim_by_area.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/primary_freeze.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase10/robustness_summary.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/robustness_summary.md` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/run_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase10/sample_change_by_area.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/spatial_error_coefficients.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/phase10/spatial_error_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase10/xgboost_tuning.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase11/audit.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/phase11/layout_migration.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/price_observability_by_scrape.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/price_observability_comparison.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/price_observability_fold_counts.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/price_observability_fold_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/price_observability_geographic_pairs.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/price_observability_metadata.json` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/price_observability_performance.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/price_observability_sample_profile.csv` | APPENDIX | Supporting robustness, detail or alternative map |
| `outputs/tables/price_observability_tuning.csv` | REPOSITORY ONLY | Diagnostic/provenance detail |
| `outputs/tables/supplementary/destination_inventory_cultural_tourist.csv` | REPOSITORY ONLY | Full public-OSM canonical inventory (supplementary CSV) |
| `outputs/tables/supplementary/destination_inventory_food_social.csv` | REPOSITORY ONLY | Full public-OSM canonical inventory (supplementary CSV) |
| `outputs/tables/supplementary/destination_inventory_rail_metro.csv` | REPOSITORY ONLY | Full public-OSM canonical inventory (supplementary CSV) |

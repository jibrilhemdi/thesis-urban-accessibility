# Final output manifest

Generated from the v2 proposal and v2 end-to-end plan, matched against all current `outputs/tables/` and `outputs/figures/` files. Status refers to **presentation completeness**, not statistical endorsement. Phase 9 M0/ME/MW/MEW remain the frozen **base specification**. The conceptually planned area socioeconomic-context adjustment was implemented after Phase 9, once sources were audited, and is presented as an **area-context-adjusted core specification**, not the original frozen Phase 7 model or a fully harmonised neighbourhood measure. `READY` means the file exists and passed this assembly audit; manuscript placement still needs final typesetting. `SUPERSEDED` means a final composite/copy is preferred for the main text; the source file remains intact. Placement is one of MAIN TEXT, APPENDIX, or REPOSITORY ONLY. Thesis-ready captions are in `docs/final_figure_captions.md`.

## Planned main-text items

| Item | Planned content | Status | Publication file | Placement |
|---|---|---|---|---|
| Table 1 | Sample construction | READY | `outputs/tables/final/table1_sample_construction.csv` | MAIN TEXT |
| Table 2 | Variable specification | READY BUT NEEDS FORMATTING | `outputs/tables/final/table2_variable_specification.csv` | MAIN TEXT |
| Table 3 | Descriptive statistics | READY BUT NEEDS FORMATTING | `outputs/tables/final/table3_descriptive_statistics.csv` | MAIN TEXT |
| Table 4 | Accessibility definitions | READY | `outputs/tables/final/table4_accessibility_definitions.csv` | MAIN TEXT |
| Table 5 | Compact hedonic ladder | READY BUT NEEDS FORMATTING | `outputs/tables/final/table5_hedonic_ladder.csv` | MAIN TEXT |
| Table 6 | Predictive performance | READY | `outputs/tables/final/table6_predictive_performance.csv` | MAIN TEXT |
| Table 7 | Incremental accessibility value | READY | `outputs/tables/final/table7_incremental_accessibility.csv` | MAIN TEXT |
| Core RQ2 panel | Base versus area-context-adjusted prediction | READY | `outputs/tables/final/table_rq2_area_context.csv` | MAIN TEXT |
| Table 8 | Robustness summary | READY BUT NEEDS FORMATTING | `outputs/tables/final/table8_robustness_summary.csv` | MAIN TEXT |
| Figure 1 | Research workflow | READY | `outputs/figures/final/figure1_workflow.png` | MAIN TEXT |
| Figure 2 | Study area overview | READY | `outputs/figures/final/figure2_study_area.png` | MAIN TEXT |
| Figure 3 | Price distribution and spatial pattern | READY | `outputs/figures/final/figure3_price_pattern.png` | MAIN TEXT |
| Figure 4 | Euclidean versus network catchment | READY | `outputs/figures/final/figure4_catchment_example.png` | MAIN TEXT |
| Figure 5 | Matched accessibility measures | READY | `outputs/figures/final/figure5_matched_accessibility.png` | MAIN TEXT |
| Figure 6 | Accessibility–price association | READY | `outputs/figures/final/figure6_accessibility_coefficients.png` | MAIN TEXT |
| Figure 7 | Random versus geographic performance | READY | `outputs/figures/final/figure7_validation_performance.png` | MAIN TEXT |
| Figure 8 | Outer CV geography | READY | `outputs/figures/final/figure8_cv_geography.png` | MAIN TEXT |
| Methods figure | Validation designs | READY | `outputs/figures/final/figure_validation_designs.png` | MAIN TEXT |
| Core RQ2 context figure | Accessibility before/after area socioeconomic context | READY | `outputs/figures/context_incremental_accessibility.png` | MAIN TEXT |

## Frozen OSM destination appendix and supplementary inventories

Documentation-only export from the unchanged Phase 5 `phase05_v2` canonical tables. No destination set, accessibility feature, or model was changed. The four compact tables belong in the appendix; full canonical POI and rail inventories remain supplementary CSVs.

| Item | File | Placement |
|---|---|---|
| Destination taxonomy | `outputs/tables/final/appendix_destination_taxonomy.csv` / `outputs/tables/final/appendix_destination_taxonomy.md` | APPENDIX |
| Destination counts | `outputs/tables/final/appendix_destination_counts.csv` / `outputs/tables/final/appendix_destination_counts.md` | APPENDIX |
| Destination examples | `outputs/tables/final/appendix_destination_examples.csv` / `outputs/tables/final/appendix_destination_examples.md` | APPENDIX |
| Destination rail metro | `outputs/tables/final/appendix_destination_rail_metro.csv` / `outputs/tables/final/appendix_destination_rail_metro.md` | APPENDIX |
| Full canonical food social inventory | `outputs/tables/supplementary/destination_inventory_food_social.csv` | SUPPLEMENTARY / REPOSITORY |
| Full canonical cultural tourist inventory | `outputs/tables/supplementary/destination_inventory_cultural_tourist.csv` | SUPPLEMENTARY / REPOSITORY |
| Full canonical rail metro inventory | `outputs/tables/supplementary/destination_inventory_rail_metro.csv` | SUPPLEMENTARY / REPOSITORY |

LaTeX appendix files: `outputs/latex/appendix/destination_taxonomy.tex`, `destination_counts.tex`, `destination_examples.tex`, and `destination_rail_metro_full.tex`. [Inventory QA and manuscript note](../reports/appendix_destination_inventory.md).

## Boundary-endpoint illustration

Separate appendix-only public-OSM catchment example; the main-text Figure 4 remains unchanged. The paired panels show eligible canonical destination endpoints under the buffered primary and study-union-restricted sensitivity definitions. This is not a walking-route or model-result figure.

| Boundary catchment example | `outputs/figures/final/appendix_boundary_catchment_example.png` | APPENDIX |

[Illustration provenance and QA](../reports/appendix_boundary_catchment_figure.md).

## Complete exported-file inventory

All non-placeholder files present at audit time are classified below, including source phase outputs and post-completion amendments.

| Path | Status | Placement |
|---|---|---|
| `outputs/figures/context_incremental_accessibility.png` | READY | MAIN TEXT |
| `outputs/figures/final/_revision_sources/appendix_geometric_block_cv.png` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/figures/final/_revision_sources/figure2_study_area.png` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/figures/final/_revision_sources/figure4_catchment_example.png` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/figures/final/appendix_boundary_catchment_example.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/final/appendix_geometric_block_cv.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/final/figure1_workflow.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure2_study_area.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure3_price_pattern.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure4_catchment_example.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure5_matched_accessibility.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure6_accessibility_coefficients.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure7_validation_performance.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure8_cv_geography.png` | READY | MAIN TEXT |
| `outputs/figures/final/figure9_residual_diagnostics.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/final/figure_validation_designs.png` | READY | MAIN TEXT |
| `outputs/figures/phase04/candidate_cv_areas.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase04/municipality_proxy.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase04/osm_coverage.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase04/study_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase07/missing_price_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase07/missing_price_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/cultural_euclidean_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/cultural_euclidean_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/cultural_walking_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/cultural_walking_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/euclidean_network_hexbin.png` | SUPERSEDED | APPENDIX |
| `outputs/figures/phase08/food_euclidean_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/food_euclidean_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/food_walking_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/food_walking_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/listing_density.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/median_price_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/median_price_grid.png` | SUPERSEDED | APPENDIX |
| `outputs/figures/phase08/price_distributions.png` | SUPERSEDED | APPENDIX |
| `outputs/figures/phase08/station_walking_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase08/station_walking_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase09/accessibility_increment.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase09/geographic_oof_residual_ols_mw_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase09/geographic_oof_residual_ols_mw_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase09/geographic_oof_residual_xgboost_mw_area.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase09/geographic_oof_residual_xgboost_mw_grid.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase09/model_performance.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase09/ols_mw_coefficients.png` | SUPERSEDED | APPENDIX |
| `outputs/figures/phase09/oof_residual_moran.png` | SUPERSEDED | APPENDIX |
| `outputs/figures/phase09/xgb_mw_shap.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase10/bus_increment.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase10/geographic_fold_stability.png` | APPENDIX ONLY | APPENDIX |
| `outputs/figures/phase10/primary_validation_context.png` | SUPERSEDED | APPENDIX |
| `outputs/figures/phase10/threshold_sensitivity.png` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/analysis_area_context.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/boundary_sensitivity_comparison.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/boundary_sensitivity_destination_counts.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/boundary_sensitivity_edge_concentration.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/boundary_sensitivity_feature_changes.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/boundary_sensitivity_fold_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/boundary_sensitivity_geographic_pairs.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/boundary_sensitivity_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/boundary_sensitivity_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/boundary_sensitivity_tuning.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/conclusion_stability.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/context_augmented_fold_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/context_augmented_geographic_pairs.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/context_augmented_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/context_augmented_ols.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/context_augmented_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/context_augmented_tuning.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/context_comparison.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/context_district_source_audit.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/copenhagen_only_context_sensitivity.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_boundary_catchment_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/final/appendix_destination_counts.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_destination_counts.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_destination_examples.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_destination_examples.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_destination_rail_metro.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_destination_rail_metro.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_destination_taxonomy.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/appendix_destination_taxonomy.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/catchment_example_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/final/table1_sample_construction.csv` | READY | MAIN TEXT |
| `outputs/tables/final/table1_sample_construction.md` | READY | MAIN TEXT |
| `outputs/tables/final/table2_variable_specification.csv` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table2_variable_specification.md` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table3_descriptive_statistics.csv` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table3_descriptive_statistics.md` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table4_accessibility_definitions.csv` | READY | MAIN TEXT |
| `outputs/tables/final/table4_accessibility_definitions.md` | READY | MAIN TEXT |
| `outputs/tables/final/table5_full_coefficients_appendix.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/table5_full_coefficients_appendix.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/table5_hedonic_ladder.csv` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table5_hedonic_ladder.md` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table6_predictive_performance.csv` | READY | MAIN TEXT |
| `outputs/tables/final/table6_predictive_performance.md` | READY | MAIN TEXT |
| `outputs/tables/final/table7_incremental_accessibility.csv` | READY | MAIN TEXT |
| `outputs/tables/final/table7_incremental_accessibility.md` | READY | MAIN TEXT |
| `outputs/tables/final/table7_incremental_accessibility_appendix.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/table7_incremental_accessibility_appendix.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/table8_robustness_summary.csv` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table8_robustness_summary.md` | READY BUT NEEDS FORMATTING | MAIN TEXT |
| `outputs/tables/final/table_rq2_area_context.csv` | READY | MAIN TEXT |
| `outputs/tables/final/table_rq2_area_context.md` | READY | MAIN TEXT |
| `outputs/tables/final/table_validation_designs.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/table_validation_designs.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/final/table_validation_performance.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/final/table_validation_performance.md` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase02/amenities_prevalence.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase02/control_missingness.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase02/price_distribution.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase02/property_type_decisions.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase02/sample_construction.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase03/context_source_assessment.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase04/cv_area_counts.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase05/destination_counts.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase05/feature_summary.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase06/area_comparison.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase06/euclidean_network_comparison.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase06/feature_summary.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase06/snap_diagnostics.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase06/source_coverage.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase07/context_area_redundancy.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase07/missingness_report.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase07/price_missingness_comparison.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase07/redundancy_pairs.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase07/sample_summary.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase07/spatial_cv_folds.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase07/vif_diagnostics.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/accessibility_correlations.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/buffer_feasibility.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/cv_fold_summary.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/descriptive_statistics.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/distance_bin_covariance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/geographic_support.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/map_coverage.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase08/sample_composition.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase08/spatial_moran.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/bus_fold_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/bus_ols_coefficient.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/bus_robustness.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/destination_boundary_audit.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/fold_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/geographic_fold_summary.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/geographic_residual_by_area.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/geographic_residual_grid_coverage.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/incremental_accessibility.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/model_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/ols_coefficients.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/ols_complete_case_sensitivity.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/ols_ladder.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/random_vs_geographic_cv.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/residual_moran.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/run_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase09/xgb_mw_shap.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase09/xgboost_tuning.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase10/accessibility_representation.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/buffer_separation.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/buffer_train_loss.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/bus_diagnostics.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/bus_feature_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase10/bus_shap.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/bus_spotcheck_groups.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/bus_vif.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/conclusion_stability.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/fold_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/geographic_fold_pairs.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/geographic_fold_summary.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/model_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/ols_associations.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/price_trim_by_area.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/primary_freeze.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase10/robustness_summary.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/robustness_summary.md` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/run_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase10/sample_change_by_area.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/spatial_error_coefficients.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/phase10/spatial_error_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase10/xgboost_tuning.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase11/audit.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/phase11/layout_migration.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/price_observability_by_scrape.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/price_observability_comparison.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/price_observability_fold_counts.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/price_observability_fold_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/price_observability_geographic_pairs.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/price_observability_metadata.json` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/price_observability_performance.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/price_observability_sample_profile.csv` | APPENDIX ONLY | APPENDIX |
| `outputs/tables/price_observability_tuning.csv` | APPENDIX ONLY | REPOSITORY ONLY |
| `outputs/tables/supplementary/destination_inventory_cultural_tourist.csv` | SUPPLEMENTARY | REPOSITORY ONLY |
| `outputs/tables/supplementary/destination_inventory_food_social.csv` | SUPPLEMENTARY | REPOSITORY ONLY |
| `outputs/tables/supplementary/destination_inventory_rail_metro.csv` | SUPPLEMENTARY | REPOSITORY ONLY |

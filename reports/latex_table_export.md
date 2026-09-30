# Final LaTeX table export

Date: 2026-09-30. This is a presentation-only export of frozen, machine-readable results. No model was fitted or tuned, no analytical table was changed, and no metric was manually retyped. Run `python -m src.pipeline.export_final_latex_tables` from the repository root (or invoke the module from another directory). The exporter reads CSVs and writes only under `outputs/latex/`.

## Generated files and authoritative inputs

| LaTeX file under `outputs/latex/` | Machine-readable input |
| --- | --- |
| `tables/table1_sample_construction.tex` | `outputs/tables/final/table1_sample_construction.csv` |
| `tables/table2_variable_specification.tex` | `outputs/tables/final/table2_variable_specification.csv` |
| `tables/table3_descriptive_statistics.tex` | `outputs/tables/final/table3_descriptive_statistics.csv` |
| `tables/table4_accessibility_definitions.tex` | `outputs/tables/final/table4_accessibility_definitions.csv` |
| `tables/table5_hedonic_ladder.tex` | `outputs/tables/final/table5_hedonic_ladder.csv` |
| `tables/table6_predictive_performance.tex` | `outputs/tables/final/table6_predictive_performance.csv` |
| `tables/table7_incremental_accessibility.tex` | `outputs/tables/final/table7_incremental_accessibility.csv` |
| `tables/table_rq2_area_context.tex` | `outputs/tables/final/table_rq2_area_context.csv` (presentation-only selection of saved `outputs/tables/context_comparison.csv`) |
| `tables/table8_robustness_summary.tex` | `outputs/tables/final/table8_robustness_summary.csv` |
| `tables/table_validation_designs.tex` | `outputs/tables/final/table_validation_designs.csv` |
| `appendix/table5_full_coefficients.tex` | `outputs/tables/final/table5_full_coefficients_appendix.csv` |
| `appendix/table7_incremental_accessibility_full.tex` | `outputs/tables/final/table7_incremental_accessibility.csv`; `outputs/tables/final/table7_incremental_accessibility_appendix.csv` |
| `appendix/context_comparison.tex` | `outputs/tables/context_comparison.csv` |
| `appendix/copenhagen_only_context.tex` | `outputs/tables/copenhagen_only_context_sensitivity.csv` |
| `appendix/price_observability_comparison.tex` | `outputs/tables/price_observability_comparison.csv` |
| `appendix/boundary_definition_sensitivity.tex` | `outputs/tables/boundary_sensitivity_comparison.csv` (RMSE rows only) |
| `appendix/geographic_fold_performance.tex` | `outputs/tables/phase09/fold_performance.csv` (geographic XGBoost M0/MW rows); names from `outputs/tables/phase04/cv_area_counts.csv` |
| `appendix/block_buffer_validation_summary.tex` | `outputs/tables/final/table_validation_performance.csv` |
| `appendix/destination_taxonomy.tex` | `outputs/tables/final/appendix_destination_taxonomy.csv` (frozen Phase 5 canonical export) |
| `appendix/destination_counts.tex` | `outputs/tables/final/appendix_destination_counts.csv` (frozen Phase 5 canonical export) |
| `appendix/destination_examples.tex` | `outputs/tables/final/appendix_destination_examples.csv` (outcome-independent examples) |
| `appendix/destination_rail_metro_full.tex` | `outputs/tables/final/appendix_destination_rail_metro.csv` (all canonical stations) |

The exporter also creates `table_preamble.tex`, `main_tables.tex`, `appendix_tables.tex`, and `table_test_document.tex`. The four destination `.tex` files are created by the read-only `make destination-inventory` export from the canonical PostGIS tables; the final LaTeX exporter includes them in `appendix_tables.tex` when present. The compact RQ2 panel is placed directly after Main Table 7. It compares the frozen Phase 9 **base specification** with the **area-context-adjusted core specification**, which was conceptually planned but implemented after Phase 9; its four rows copy existing matched model metrics without refitting. Main Table 7 deliberately excludes MW-versus-ME rows; the full appendix table includes them. Full coefficient values/HC3 SE/confidence limits are preserved, while substantively unhelpful intercept percentage transformations are omitted. The geographic-fold appendix translates saved IDs using the official area-name lookup; fold assignments are not modified.

## Typesetting and integration

The preamble lists only packages used by the generated tables: `fontenc`, `inputenc`, `booktabs`, `threeparttable`, `array`, `tabularx`, `longtable`, and `pdflscape`. Wide specification, robustness, and validation tables use landscape pages and/or multipage longtables. Table 3 uses continuous and categorical panels. The exporter escapes LaTeX-special characters and renders numerical values at manuscript precision without changing the underlying CSV precision. Tables have stable `tab:` labels, captions, and explanatory notes.

From the repository root, include `\input{outputs/latex/table_preamble.tex}` in the thesis preamble, then `\input{outputs/latex/main_tables.tex}` and, after `\appendix`, `\input{outputs/latex/appendix_tables.tex}`. If the thesis document is compiled from another directory, adapt the `\input` path prefix; the generated include files assume the repository root is the LaTeX working directory.

## Checks and layout status

`python -m unittest tests.test_final_latex_table_export -v` checks the export. After `make destination-inventory`, the test document includes ten main/methods and twelve appendix tables. It compiled with `pdflatex -interaction=nonstopmode -halt-on-error` in two passes to a 36-page PDF, with no LaTeX errors, warnings or overfull boxes on the second pass. The four new appendix tables are drawn only from the frozen Phase 5 canonical export; full multi-thousand-row POI inventories remain CSV and are not inserted into the PDF. Final placement should still be checked in the thesis's own document class and margins. No model or analytical source CSV was regenerated.

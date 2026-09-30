"""Read-only integrity checks for the final presentation revision."""

from __future__ import annotations

import json
import unittest

import pandas as pd

from src.ingestion.common import PROJECT_ROOT, sha256_file


T = PROJECT_ROOT / "outputs/tables/final"
F = PROJECT_ROOT / "outputs/figures/final"


class FinalOutputRevisionTests(unittest.TestCase):
    def test_frozen_phase9_exports_unchanged(self):
        freeze = json.loads((PROJECT_ROOT / "outputs/tables/phase10/primary_freeze.json").read_text())
        for relative, digest in freeze["phase9_file_sha256"].items():
            self.assertEqual(sha256_file(PROJECT_ROOT / relative), digest, relative)

    def test_sample_and_units(self):
        table = pd.read_csv(T / "table1_sample_construction.csv")
        raw = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase02/sample_construction.csv")
        self.assertIn("Inside Airbnb Copenhagen–Frederiksberg extract", set(table["Filter step"]))
        self.assertIn("Assigned official validation area", set(table["Filter step"]))
        self.assertEqual(list(table["N remaining"][:len(raw)]), list(raw.remaining_n))
        specs = pd.read_csv(T / "table2_variable_specification.csv")
        metres = specs.loc[specs.Variable == "nearest_station_euclidean_m"].iloc[0]
        km = specs.loc[specs.Variable == "nearest_station_euclidean_km"].iloc[0]
        self.assertIn("m;", metres["Transformation/unit"])
        self.assertIn("km;", km["Transformation/unit"])
        self.assertEqual(km["Model block"], "ME/MEW")

    def test_notes_and_comparison_split(self):
        note3 = (T / "table3_descriptive_statistics.md").read_text()
        for required in ("11 area units", "Frederiksberg municipality-level", "Income definitions differ", "area-context-adjusted core specification"):
            self.assertIn(required, note3)
        self.assertIn("buffered", (T / "table4_accessibility_definitions.md").read_text())
        self.assertIn("HC3 addresses heteroskedasticity, not residual spatial dependence",
                      (T / "table5_hedonic_ladder.md").read_text())
        main = pd.read_csv(T / "table7_incremental_accessibility.csv")
        extra = pd.read_csv(T / "table7_incremental_accessibility_appendix.csv")
        self.assertEqual(len(main), 12)
        self.assertEqual(len(extra), 8)
        self.assertEqual(list(main.columns), ["Validation", "Estimator", "Comparison", "Delta RMSE reduction",
                                              "Delta MAE reduction", "Reference RMSE", "New RMSE"])
        self.assertTrue(main.Comparison.str.endswith("versus M0").all())
        self.assertTrue(extra.Comparison.str.endswith("versus ME").all())
        source = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase09/model_performance.csv")
        idx = source.set_index(["cv_scheme", "model", "feature_set"])
        incremental = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase09/incremental_accessibility.csv")
        for r in pd.concat([main, extra]).itertuples(index=False):
            scheme = "random_5" if r.Validation == "Random 5-fold" else "geographic_11"
            candidate, baseline = r.Comparison.split(" versus ")
            ref = idx.loc[(scheme, r.Estimator, baseline)]
            new = idx.loc[(scheme, r.Estimator, candidate)]
            self.assertAlmostEqual(r[3], round(ref.rmse_log-new.rmse_log, 5))
            self.assertAlmostEqual(r[4], round(ref.mae_log-new.mae_log, 5))
            saved = incremental[(incremental.cv_scheme == scheme) & (incremental.model == r.Estimator) &
                                (incremental.comparison == r.Comparison)]
            if not saved.empty:
                self.assertAlmostEqual(r[3], round(float(saved.rmse_reduction_log.iloc[0]), 5))

    def test_frozen_ols_and_performance_numbers(self):
        summary = pd.read_csv(T / "table3_descriptive_statistics.csv")
        self.assertEqual(int(summary.loc[summary.Variable == "Listed nightly price", "N"].iloc[0]), 12412)
        descriptive = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase08/descriptive_statistics.csv")
        for label, source_name in (("Listed nightly price", "price_nightly"),
                                   ("Log listed price", "log_price"),
                                   ("Accommodates", "accommodates"), ("Bedrooms", "bedrooms")):
            original = descriptive[(descriptive.cohort == "common_model_comparison") &
                                   (descriptive.variable == source_name)].iloc[0]
            displayed = summary.loc[summary.Variable == label].iloc[0]
            self.assertEqual(int(displayed.N), int(original.n_observed))
            self.assertAlmostEqual(displayed.Mean, original["mean"], places=3)
            self.assertAlmostEqual(displayed.SD, original.sd, places=3)
        ladder = pd.read_csv(T / "table5_hedonic_ladder.csv")
        source_coeff = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase09/ols_coefficients.csv")
        for model in ("ME", "MW", "MEW"):
            for term in ladder["Focal term (unit)"].iloc[:6]:
                entry = source_coeff[(source_coeff.feature_set == model) & (source_coeff.term == term)]
                displayed = ladder.loc[ladder["Focal term (unit)"] == term, model].iloc[0]
                if entry.empty:
                    self.assertEqual(displayed, "—")
                else:
                    value = entry.iloc[0]
                    expected = (f"{value.beta_log_price:+.4f} ({value.robust_se_hc3:.4f}); "
                                f"[{value.ci95_low:+.4f}, {value.ci95_high:+.4f}]")
                    self.assertEqual(displayed, expected)
        final_perf = pd.read_csv(T / "table6_predictive_performance.csv")
        source_perf = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase09/model_performance.csv")
        self.assertEqual(len(final_perf), len(source_perf))
        for row in source_perf.itertuples():
            label = "Random 5-fold" if row.cv_scheme == "random_5" else "Leave-one-area-out (11 analysis areas)"
            estimator = "Training mean" if row.model == "train_mean" else row.model
            block = "—" if row.feature_set == "none" else row.feature_set
            actual = final_perf[(final_perf.Validation == label) & (final_perf.Estimator == estimator) &
                                (final_perf.Block == block)].iloc[0]
            self.assertEqual(int(actual.N), int(row.n))
            self.assertAlmostEqual(actual["RMSE (ln price)"], round(row.rmse_log, 4))
            self.assertAlmostEqual(actual["MAE (ln price)"], round(row.mae_log, 4))
            self.assertAlmostEqual(actual["R² (OOF)"], round(row.r2_log, 3))

    def test_validation_designs_and_context_sources(self):
        designs = pd.read_csv(T / "table_validation_designs.csv")
        self.assertEqual(len(designs), 5)
        self.assertEqual(list(designs["Validation scheme"]), [
            "Random 5-fold", "1.5 km geometric block 5-fold",
            "Leave-one-area-out (11 analysis areas)",
            "Buffered leave-one-area-out 500 m", "Buffered leave-one-area-out 1000 m"])
        self.assertIn("whole", designs.loc[1, "Spatial separation principle"].lower())
        comparison = pd.read_csv(PROJECT_ROOT / "outputs/tables/context_comparison.csv")
        primary = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase09/model_performance.csv")
        context = pd.read_csv(PROJECT_ROOT / "outputs/tables/context_augmented_performance.csv")
        for row in comparison.itertuples():
            initial = primary[(primary.cv_scheme == row.cv_scheme) & (primary.model == row.model)]
            new = context[(context.cv_scheme == row.cv_scheme) & (context.model == row.model)]
            old_base = initial.loc[initial.feature_set == "M0", "rmse_log"].iloc[0]
            old_access = initial.loc[initial.feature_set == row.accessibility, "rmse_log"].iloc[0]
            new_base = new.loc[new.feature_set == "M0_CTX", "rmse_log"].iloc[0]
            new_access = new.loc[new.feature_set == row.accessibility+"_CTX", "rmse_log"].iloc[0]
            self.assertAlmostEqual(row.delta_rmse_phase9, old_base-old_access)
            self.assertAlmostEqual(row.delta_rmse_ctx, new_base-new_access)

    def test_context_and_boundary_values(self):
        publication = pd.read_csv(T / "table8_robustness_summary.csv")
        phase10 = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase10/robustness_summary.csv")
        for analysis in ("apartment_condo", "reviewed_only", "review_count", "threshold_15", "threshold_20",
                         "price_trim_1_99", "buffer_500m", "buffer_1000m", "block_1500m", "bus_walking"):
            original = phase10[(phase10.analysis == analysis) & (phase10.model == "XGBoost") &
                               (phase10.validation_method.str.contains("geographic|block_1500")) &
                               (phase10.accessibility_specification.str.contains("MW"))].iloc[0]
            displayed = publication.loc[publication.Analysis == analysis.replace("_", " ")].iloc[0]
            self.assertEqual(int(displayed.N), int(original.sample_N))
            self.assertAlmostEqual(float(displayed.RMSE), round(float(original.RMSE), 4))
            self.assertAlmostEqual(float(displayed["ΔRMSE vs reference"]),
                                   round(float(original.Delta_RMSE_vs_relevant_baseline), 5))
        cph = pd.read_csv(PROJECT_ROOT / "outputs/tables/copenhagen_only_context_sensitivity.csv")
        m0, mw = (cph.loc[cph.feature_set == name].iloc[0] for name in ("M0_CTX", "MW_CTX"))
        row = publication.loc[publication.Analysis == "Area context (Copenhagen only)"].iloc[0]
        self.assertEqual(int(row.N), int(mw.n))
        self.assertEqual(row.Validation, "geographic_10")
        self.assertAlmostEqual(float(row.RMSE), round(float(mw.geographic_xgb_rmse_log), 4))
        self.assertAlmostEqual(float(row["ΔRMSE vs reference"]),
                               round(float(m0.geographic_xgb_rmse_log-mw.geographic_xgb_rmse_log), 5))
        folds = pd.read_csv(PROJECT_ROOT / "outputs/tables/context_augmented_fold_performance.csv")
        folds = folds[(folds["sample"] == "copenhagen_10_districts") & (folds.cv_scheme == "geographic_11") &
                      (folds.model == "XGBoost") & (folds.feature_set.isin(["M0_CTX", "MW_CTX"]))]
        pairs = folds.pivot(index="fold", columns="feature_set", values="rmse_log")
        self.assertIn(f"{(pairs.MW_CTX < pairs.M0_CTX).sum()}/{len(pairs)}", row.Interpretation)
        source = pd.read_csv(PROJECT_ROOT / "outputs/tables/boundary_sensitivity_performance.csv")
        source = source[(source.cv_scheme == "geographic_11") & (source.model == "XGBoost")]
        baseline = source.loc[source.feature_set == "M0"].iloc[0]
        walk = source.loc[source.feature_set == "MW"].iloc[0]
        bound = publication.loc[publication.Analysis == "Study-boundary destinations"].iloc[0]
        self.assertEqual(int(bound.N), int(walk.n))
        self.assertAlmostEqual(float(bound.RMSE), round(float(walk.rmse_log), 4))
        self.assertAlmostEqual(float(bound["ΔRMSE vs reference"]), round(float(baseline.rmse_log-walk.rmse_log), 5))
        note = (T / "table8_robustness_summary.md").read_text()
        self.assertIn("matching no-access baseline, NOT Euclidean access", note)

    def test_figure_metadata_and_placement(self):
        metadata = json.loads((T / "catchment_example_metadata.json").read_text())
        self.assertEqual((metadata["walk_reachable_pois"], metadata["candidate_pois_in_circle"]), (42, 82))
        self.assertEqual(sha256_file(F / "figure6_accessibility_coefficients.png"),
                         sha256_file(PROJECT_ROOT / "outputs/figures/phase09/ols_mw_coefficients.png"))
        self.assertEqual(sha256_file(F / "figure9_residual_diagnostics.png"),
                         sha256_file(PROJECT_ROOT / "outputs/figures/phase09/oof_residual_moran.png"))
        self.assertTrue((F / "figure_validation_designs.png").is_file())
        self.assertTrue((F / "appendix_geometric_block_cv.png").is_file())
        manifest = (PROJECT_ROOT / "docs/final_output_manifest.md").read_text()
        placement = (PROJECT_ROOT / "docs/output_placement_plan.md").read_text()
        self.assertIn("`outputs/figures/context_incremental_accessibility.png` | MAIN TEXT", manifest)
        self.assertIn("`outputs/figures/final/figure9_residual_diagnostics.png` | APPENDIX ONLY | APPENDIX", manifest)
        self.assertIn("appendix_geometric_block_cv.png", placement)
        self.assertIn("table7_incremental_accessibility_appendix.csv", placement)
        captions = (PROJECT_ROOT / "docs/final_figure_captions.md").read_text()
        self.assertIn("Multiple blocks belong to each fold; blocks themselves are not folds", captions)
        self.assertIn("Core RQ2 comparison", captions)
        inventory = manifest.split("## Complete exported-file inventory", 1)[1]
        self.assertNotIn(" | METHODS |", inventory)
        for line in inventory.splitlines():
            if line.startswith("| `outputs/"):
                self.assertTrue(any(line.endswith(f"| {value} |") for value in
                                    ("MAIN TEXT", "APPENDIX", "REPOSITORY ONLY")), line)


if __name__ == "__main__":
    unittest.main()

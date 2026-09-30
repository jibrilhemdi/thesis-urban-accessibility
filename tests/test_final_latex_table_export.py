"""Read-only provenance and formatting checks for the frozen LaTeX export."""

from __future__ import annotations

import csv
import unittest

from src.pipeline.export_final_latex_tables import FINAL, OUT, ROOT, num, tex


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


class FinalLatexExportTests(unittest.TestCase):
    def test_all_requested_files_exist(self):
        expected_main = (
            "table1_sample_construction", "table2_variable_specification",
            "table3_descriptive_statistics", "table4_accessibility_definitions",
            "table5_hedonic_ladder", "table6_predictive_performance",
            "table7_incremental_accessibility", "table_rq2_area_context",
            "table8_robustness_summary",
            "table_validation_designs",
        )
        expected_app = (
            "table5_full_coefficients", "table7_incremental_accessibility_full",
            "context_comparison", "copenhagen_only_context",
            "price_observability_comparison", "boundary_definition_sensitivity",
            "geographic_fold_performance", "block_buffer_validation_summary",
            "destination_taxonomy", "destination_counts", "destination_examples",
            "destination_rail_metro_full",
        )
        for stem in expected_main:
            self.assertTrue((OUT / "tables" / f"{stem}.tex").is_file(), stem)
        for stem in expected_app:
            self.assertTrue((OUT / "appendix" / f"{stem}.tex").is_file(), stem)
        for name in ("table_preamble", "main_tables", "appendix_tables", "table_test_document"):
            self.assertTrue((OUT / f"{name}.tex").is_file(), name)

    def test_source_values_are_rendered_from_csv(self):
        source = read_csv(FINAL / "table1_sample_construction.csv")
        rendered = (OUT / "tables/table1_sample_construction.tex").read_text()
        for row in source:
            self.assertIn(num(row["N remaining"], count=True), rendered)
            self.assertIn(tex(row["Filter step"]), rendered)
        perf = read_csv(FINAL / "table6_predictive_performance.csv")
        rendered = (OUT / "tables/table6_predictive_performance.tex").read_text()
        for row in perf:
            self.assertIn(num(row["RMSE (ln price)"], 4), rendered)
            self.assertIn(num(row["MAE (ln price)"], 4), rendered)

    def test_main_and_appendix_split(self):
        self.assertIn("table_rq2_area_context.tex", (OUT / "main_tables.tex").read_text())
        self.assertNotIn("table_rq2_area_context.tex", (OUT / "appendix_tables.tex").read_text())
        self.assertIn("destination_rail_metro_full.tex", (OUT / "appendix_tables.tex").read_text())
        main = (OUT / "tables/table7_incremental_accessibility.tex").read_text()
        extra = (OUT / "appendix/table7_incremental_accessibility_full.tex").read_text()
        self.assertNotIn("MW versus ME", main)
        self.assertIn("MW versus ME", extra)
        coeff = (OUT / "appendix/table5_full_coefficients.tex").read_text()
        self.assertIn("HC3 SE", coeff)
        for row in read_csv(FINAL / "table5_full_coefficients_appendix.csv"):
            self.assertIn(num(row["beta_log_price"], 4), coeff)
        # Intercept percent transformations are deliberately absent.
        self.assertNotIn("139,665", coeff)

    def test_escaping_labels_and_area_names(self):
        self.assertEqual(tex("x_y%&#$"), r"x\_\allowbreak{}y\%\&\#\$")
        area_lookup = {r["area"]: r["area_name"] for r in read_csv(ROOT / "outputs/tables/phase04/cv_area_counts.csv")}
        geographic = (OUT / "appendix/geographic_fold_performance.tex").read_text()
        for area, name in area_lookup.items():
            self.assertNotIn(area + " &", geographic)
            if area in {r["fold"] for r in read_csv(ROOT / "outputs/tables/phase09/fold_performance.csv") if r["cv_scheme"] == "geographic_11"}:
                self.assertIn(tex(name), geographic)
        self.assertIn("Frederiksberg", geographic)


if __name__ == "__main__":
    unittest.main()

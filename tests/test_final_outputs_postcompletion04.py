"""QA for the post-completion, presentation-only publication assembly."""

from __future__ import annotations

import json
import os
import unittest

import pandas as pd

from src.ingestion.common import PROJECT_ROOT
from src.pipeline.run_final_outputs_postcompletion04 import freeze
from src.db.connection import get_engine


TABLES = PROJECT_ROOT / "outputs/tables/final"
FIGURES = PROJECT_ROOT / "outputs/figures/final"


class PublicationOutputTests(unittest.TestCase):
    def test_all_planned_items_exist_and_are_private_safe(self):
        for number in range(1, 9):
            files = list(TABLES.glob(f"table{number}_*.csv"))
            self.assertTrue(files, f"Missing final Table {number}")
        for number in range(1, 10):
            files = list(FIGURES.glob(f"figure{number}_*.png"))
            self.assertEqual(len(files), 1, f"Missing or duplicated final Figure {number}")
            self.assertGreater(files[0].stat().st_size, 10_000)
        for path in TABLES.glob("*.csv"):
            columns = set(pd.read_csv(path, nrows=0).columns)
            private = {"listing_id", "host_name", "host_id", "metric_x", "metric_y", "geom_25832"}
            if path.name != "appendix_destination_rail_metro.csv":
                private.update({"latitude", "longitude"})
            self.assertFalse(columns.intersection(private), path.name)

    def test_sample_and_frozen_model_values(self):
        construction = pd.read_csv(TABLES / "table1_sample_construction.csv")
        self.assertEqual(int(construction.iloc[-1]["N remaining"]), 12412)
        self.assertEqual(int(construction.loc[construction["Filter step"].str.contains("Observed positive"),
                                               "N removed"].iloc[0]), 8559)
        stats = pd.read_csv(TABLES / "table3_descriptive_statistics.csv")
        self.assertEqual(int(stats.loc[stats.Variable == "Listed nightly price", "N"].iloc[0]), 12412)
        performance = pd.read_csv(TABLES / "table6_predictive_performance.csv")
        frozen = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase09/model_performance.csv")
        self.assertEqual(len(performance), len(frozen))
        self.assertTrue((performance.N == 12412).all())
        expected = frozen[(frozen.cv_scheme == "geographic_11") &
                          (frozen.model == "XGBoost") & (frozen.feature_set == "MW")].iloc[0]
        actual = performance[(performance.Validation == "Leave-one-area-out (11 analysis areas)") &
                             (performance.Estimator == "XGBoost") &
                             (performance.Block == "MW")].iloc[0]
        self.assertAlmostEqual(float(actual["RMSE (ln price)"]), round(float(expected.rmse_log), 4))
        robustness = pd.read_csv(TABLES / "table8_robustness_summary.csv")
        self.assertTrue(robustness.Analysis.str.contains("Area context").any())
        self.assertTrue(robustness.Analysis.str.contains("High-price-completeness").any())
        self.assertEqual(int(robustness.loc[robustness.Analysis.str.contains("High-price-completeness"), "N"].iloc[0]), 11808)

    def test_manifest_covers_every_export_and_neutral_origin(self):
        manifest = (PROJECT_ROOT / "docs/final_output_manifest.md").read_text(encoding="utf-8")
        placement = (PROJECT_ROOT / "docs/output_placement_plan.md").read_text(encoding="utf-8")
        for base in (PROJECT_ROOT / "outputs/tables", PROJECT_ROOT / "outputs/figures"):
            for path in base.rglob("*"):
                if not path.is_file() or path.name in (".gitkeep", ".DS_Store"):
                    continue
                relative = path.relative_to(PROJECT_ROOT).as_posix()
                self.assertIn(f"`{relative}`", manifest, relative)
                self.assertIn(f"`{relative}`", placement, relative)
        meta = json.loads((TABLES / "catchment_example_metadata.json").read_text())
        self.assertEqual(meta["crs_epsg"], 25832)
        self.assertEqual(meta["walking_budget_m"], 800)
        self.assertIn("public walking-network component", meta["origin_definition"])
        self.assertGreater(meta["walk_reachable_pois"], 0)
        self.assertLess(meta["walk_reachable_pois"], meta["candidate_pois_in_circle"])


@unittest.skipUnless(os.environ.get("THESIS_FINAL_OUTPUTS_TEST") == "1", "live DB opt-in")
class LiveFreezeTests(unittest.TestCase):
    def test_primary_artifacts_and_cv_hash(self):
        engine = get_engine()
        try:
            with engine.connect() as conn:
                freeze(conn)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()

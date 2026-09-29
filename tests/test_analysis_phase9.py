"""Phase 9 leakage guards and optional live model-output QA."""

import csv
import os
import unittest
import warnings

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.run_analysis_phase9 import (
    FEATURES, _inner_splits, _load, build_preprocessor, prepare_features,
)
from src.pipeline.run_bus_proximity_phase9 import selection_rule


class Phase9PureTest(unittest.TestCase):
    def test_training_only_median_and_unknown_category(self):
        train = pd.DataFrame({name: [0.0, 0.0, 0.0] for name in FEATURES["M0"]
                              if name not in ("property_type", "official_municipality_code")})
        train["bedrooms"] = [1.0, np.nan, 3.0]
        train["property_type"] = ["Entire home"] * 3
        train["official_municipality_code"] = ["0101"] * 3
        test = train.iloc[[0]].copy()
        test["bedrooms"] = np.nan
        test["property_type"] = "Entire villa"
        prep = build_preprocessor("M0")
        prep.fit(train[list(FEATURES["M0"])])
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Found unknown categories")
            transformed = prep.transform(test[list(FEATURES["M0"])])
        names = list(prep.get_feature_names_out())
        self.assertEqual(float(transformed[0, names.index("bedrooms")]), 2.0)
        self.assertEqual(float(transformed[0, names.index("missingindicator_bedrooms")]), 1.0)

    def test_bus_taxonomy_is_separate_and_specific(self):
        self.assertEqual(selection_rule({"highway": "bus_stop"}), "highway=bus_stop")
        self.assertEqual(selection_rule({"public_transport": "platform", "bus": "yes"}),
                         "public_transport=platform;bus=yes")
        self.assertIsNone(selection_rule({"public_transport": "station", "train": "yes"}))
        self.assertIsNone(selection_rule({"public_transport": "platform", "tram": "yes"}))

    def test_deterministic_log_transforms_and_grouped_inner_folds(self):
        frame = pd.DataFrame({name: [1.0] * 800 for name in FEATURES["M0"]
                              if name not in ("property_type", "official_municipality_code")})
        frame["property_type"] = "Entire home"
        frame["official_municipality_code"] = ["0101", "0147"] * 400
        frame["nearest_station_euclidean_m"] = 800.0
        frame["nearest_bus_stop_euclidean_m"] = 120.0
        frame["food_social_800m"] = 9
        frame["cultural_tourist_800m"] = 4
        frame["food_social_w_10"] = 5
        frame["cultural_tourist_w_10"] = 2
        frame["nearest_station_walking_minutes"] = 12.0
        frame["block_1km_id"] = np.repeat(np.arange(20), 40).astype(str)
        prepared = prepare_features(frame)
        self.assertAlmostEqual(prepared["nearest_bus_stop_euclidean_km"].iloc[0], .12)
        self.assertAlmostEqual(prepared["log1p_food_e800"].iloc[0], np.log(10))
        splits = _inner_splits(prepared)
        self.assertEqual(len(splits), 4)
        for learning, validation in splits:
            self.assertFalse(set(prepared.iloc[learning]["block_1km_id"]) &
                             set(prepared.iloc[validation]["block_1km_id"]))


@unittest.skipUnless(os.environ.get("THESIS_PHASE9_TEST") == "1", "Set THESIS_PHASE9_TEST=1 after phase9-run")
class Phase9LiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_bus_migration_and_spatial_coverage(self):
        self.assertEqual(migrate(self.engine), [])
        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT count(*) n,count(*) FILTER (WHERE nearest_bus_stop_euclidean_m IS NULL) missing "
                "FROM features.bus_stop_proximity"
            )).one()
            stop_n = conn.scalar(text("SELECT count(*) FROM spatial.bus_stops"))
        self.assertEqual(tuple(row), (23144, 0))
        self.assertEqual(stop_n, 4351)

    def test_common_sample_and_saved_outer_assignments(self):
        with self.engine.connect() as conn:
            frame = _load(conn)
        self.assertEqual(len(frame), 12412)
        self.assertFalse(frame[["snapshot_date", "listing_id"]].duplicated().any())
        self.assertEqual(frame["random_fold"].nunique(), 5)
        self.assertEqual(frame["heldout_area"].nunique(), 11)
        self.assertEqual(frame["block_1km_id"].isna().sum(), 0)
        self.assertEqual(frame["log_price"].isna().sum(), 0)
        self.assertTrue((frame["price_nightly"] > 0).all())

    def test_aggregate_outputs(self):
        expected = {
            "phase09_ols_ladder.csv": 4,
            "phase09_ols_complete_case_sensitivity.csv": 12,
            "phase09_model_performance.csv": 18,
            "phase09_random_vs_geographic_cv.csv": 9,
            "phase09_fold_performance.csv": 144,
            "phase09_geographic_fold_summary.csv": 9,
            "phase09_residual_moran.csv": 8,
            "phase09_geographic_residual_by_area.csv": 22,
            "phase09_geographic_residual_grid_coverage.csv": 2,
            "phase09_destination_boundary_audit.csv": 8,
            "phase09_xgboost_tuning.csv": 80,
            "phase09_bus_robustness.csv": 4,
            "phase09_bus_fold_performance.csv": 32,
            "phase09_bus_ols_coefficient.csv": 1,
        }
        for filename, n_expected in expected.items():
            with (PROJECT_ROOT / "outputs/tables" / filename).open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertFalse({"listing_id", "host_name", "metric_x", "metric_y", "latitude", "longitude"}
                                 & set(reader.fieldnames), filename)
                self.assertEqual(sum(1 for _ in reader), n_expected, filename)
        for filename in ("phase09_model_performance.png", "phase09_accessibility_increment.png",
                         "phase09_ols_mw_coefficients.png", "phase09_oof_residual_moran.png",
                         "phase09_xgb_mw_shap.png",
                         "phase09_geographic_oof_residual_ols_mw_area.png",
                         "phase09_geographic_oof_residual_xgboost_mw_area.png",
                         "phase09_geographic_oof_residual_ols_mw_grid.png",
                         "phase09_geographic_oof_residual_xgboost_mw_grid.png"):
            self.assertTrue((PROJECT_ROOT / "outputs/figures" / filename).is_file(), filename)

        with (PROJECT_ROOT / "outputs/tables/phase09_geographic_residual_grid_coverage.csv").open(
                newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                self.assertEqual(row["crs_epsg"], "25832")
                self.assertGreaterEqual(int(row["smallest_displayed_cell_n"]), 10)
                self.assertEqual(int(row["n_available_listings"]), 12412)
                self.assertEqual(int(row["n_displayed_listings"]) +
                                 int(row["n_not_displayed"]), 12412)

        with (PROJECT_ROOT / "outputs/tables/phase09_destination_boundary_audit.csv").open(
                newline="", encoding="utf-8") as handle:
            boundary = {row["measure"]: row for row in csv.DictReader(handle)}
        self.assertEqual(int(boundary["canonical_station_outside_study"]["count"]), 78)
        self.assertEqual(int(boundary["primary_nearest_walking_station_outside_study"]["count"]), 80)
        self.assertTrue(all(row["crs_epsg"] == "25832" for row in boundary.values()))


if __name__ == "__main__":
    unittest.main()

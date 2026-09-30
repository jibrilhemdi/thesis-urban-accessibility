"""Guardrails for the separate context-augmented modelling outputs."""

from __future__ import annotations

import csv
import os
import unittest

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline import run_analysis_phase9 as p9
from src.pipeline.run_context_models_postcompletion02 import (
    CONTEXT, SETS, freeze_check, load_sample, preprocessor,
)


class ContextArchitectureTests(unittest.TestCase):
    def test_feature_ladder_adds_exactly_two_fields(self):
        self.assertEqual(tuple(CONTEXT),
                         ("log_analysis_area_population_density", "analysis_area_income_100k_dkk"))
        for base, original in p9.FEATURES.items():
            self.assertEqual(SETS[f"{base}_CTX"], original + CONTEXT)
            self.assertNotIn("analysis_area_is_municipality_proxy", SETS[f"{base}_CTX"])
            self.assertNotIn("analysis_area_income_definition_differs", SETS[f"{base}_CTX"])

    def test_median_is_learned_only_on_fit_data(self):
        columns = SETS["M0_CTX"]
        train = pd.DataFrame({column: [1.0, 3.0, 5.0] for column in columns})
        train["property_type"] = "Entire rental unit"
        train["official_municipality_code"] = "0101"
        train.loc[2, "bedrooms"] = np.nan
        test = train.iloc[[2]].copy()
        test["analysis_area_income_100k_dkk"] = 10_000.0
        prep = preprocessor("M0_CTX")
        prep.fit(train)
        names = list(prep.get_feature_names_out())
        transformed = prep.transform(test)
        self.assertEqual(float(transformed[0, names.index("bedrooms")]), 2.0)
        self.assertEqual(float(transformed[0, names.index("analysis_area_income_100k_dkk")]), 10_000.0)


@unittest.skipUnless(os.environ.get("THESIS_CONTEXT_MODELS_TEST") == "1", "live model-output opt-in")
class ContextModelOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_frozen_primary_files_and_cv(self):
        with self.engine.connect() as conn:
            freeze_check(conn)
            frame = load_sample(conn)
        self.assertEqual(len(frame), 12412)
        self.assertEqual(frame["heldout_area"].nunique(), 11)
        self.assertEqual(frame["random_fold"].nunique(), 5)
        self.assertFalse(frame[list(CONTEXT)].isna().any().any())
        self.assertEqual((frame["official_municipality_code"] == "0101").sum(), 11108)

    def test_outputs_are_matched_and_aggregate(self):
        tables = PROJECT_ROOT / "outputs/tables"
        performance = pd.read_csv(tables / "context_augmented_performance.csv")
        folds = pd.read_csv(tables / "context_augmented_fold_performance.csv")
        pairs = pd.read_csv(tables / "context_augmented_geographic_pairs.csv")
        comparison = pd.read_csv(tables / "context_comparison.csv")
        city = pd.read_csv(tables / "copenhagen_only_context_sensitivity.csv")
        self.assertEqual(len(performance), 16)
        self.assertTrue((performance.n == 12412).all())
        self.assertEqual(len(folds), 188)
        self.assertEqual(len(pairs), 22)
        self.assertTrue((pairs.n_test >= 221).all())
        self.assertEqual(len(comparison), 12)
        self.assertTrue((comparison.n == 12412).all())
        self.assertEqual(len(city), 3)
        self.assertTrue((city.n == 11108).all())
        for (sample, scheme, fold), part in folds.groupby(["sample", "cv_scheme", "fold"]):
            self.assertEqual(part.n.nunique(), 1)
            self.assertEqual(part.train_n.nunique(), 1)
            self.assertEqual(len(part), 8 if sample == "mixed_11_areas" else 6)
        for filename in ("context_augmented_ols.csv", "context_augmented_performance.csv",
                         "context_augmented_fold_performance.csv", "context_augmented_geographic_pairs.csv",
                         "context_comparison.csv", "copenhagen_only_context_sensitivity.csv",
                         "context_augmented_tuning.csv"):
            with (tables / filename).open(encoding="utf-8", newline="") as handle:
                columns = next(csv.reader(handle))
            prohibited = {"listing_id", "host_id", "host_name", "latitude", "longitude", "metric_x", "metric_y"}
            self.assertFalse(prohibited.intersection(columns), filename)
        self.assertTrue((PROJECT_ROOT / "outputs/figures/context_incremental_accessibility.png").is_file())


if __name__ == "__main__":
    unittest.main()

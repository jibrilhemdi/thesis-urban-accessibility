"""Audit and model-output safeguards for high-completeness scrape batches."""

from __future__ import annotations

import csv
import os
import unittest

import pandas as pd

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.run_price_observability_postcompletion03 import (
    FEATURE_SETS, THRESHOLD, audit_batches, check_freeze,
    load_robustness_sample,
)


class FixedRuleTests(unittest.TestCase):
    def test_predeclared_rule_and_phase9_ladder(self):
        self.assertEqual(THRESHOLD, .90)
        self.assertEqual(FEATURE_SETS, ("M0", "ME", "MW"))


@unittest.skipUnless(os.environ.get("THESIS_OBSERVABILITY_TEST") == "1", "live DB opt-in")
class LiveObservabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_audit_and_fixed_sample(self):
        with self.engine.connect() as conn:
            check_freeze(conn)
            audit, high = audit_batches(conn)
            original, selected = load_robustness_sample(conn, high)
        self.assertEqual(sum(r["n_total"] for r in audit), 21080)
        self.assertEqual(sum(r["n_valid_price"] for r in audit), 12521)
        self.assertEqual({r["scrape_date"] for r in audit if r["high_completeness_batch"]},
                         {"2026-06-30", "2026-07-01"})
        self.assertTrue(all(r["high_completeness_batch"] ==
                            (r["valid_price_rate"] >= THRESHOLD) for r in audit))
        self.assertEqual(len(original), 12412)
        self.assertEqual(len(selected), 11808)
        self.assertFalse(selected.log_price.isna().any())
        self.assertTrue((selected.price_nightly > 0).all())
        self.assertEqual(selected.random_fold.nunique(), 5)
        self.assertEqual(selected.heldout_area.nunique(), 11)
        self.assertGreaterEqual(selected.groupby("heldout_area").size().min(), 200)
        self.assertFalse(selected[["snapshot_date", "listing_id"]].duplicated().any())

    def test_aggregate_outputs_and_matched_folds(self):
        out = PROJECT_ROOT / "outputs/tables"
        audit = pd.read_csv(out / "price_observability_by_scrape.csv")
        folds = pd.read_csv(out / "price_observability_fold_counts.csv")
        performance = pd.read_csv(out / "price_observability_performance.csv")
        fold_metrics = pd.read_csv(out / "price_observability_fold_performance.csv")
        comparison = pd.read_csv(out / "price_observability_comparison.csv")
        pairs = pd.read_csv(out / "price_observability_geographic_pairs.csv")
        self.assertEqual(len(audit), 4)
        self.assertEqual(len(folds), 16)
        self.assertEqual(len(performance), 12)
        self.assertTrue((performance.n == 11808).all())
        self.assertEqual(len(fold_metrics), 96)
        self.assertEqual(len(comparison), 12)
        self.assertEqual(len(pairs), 22)
        self.assertTrue((pairs.n_high_completeness >= 211).all())
        for (validation, fold), part in fold_metrics.groupby(["validation", "saved_fold"]):
            self.assertEqual(len(part), 6)
            self.assertEqual(part.n.nunique(), 1)
            self.assertEqual(part.train_n.nunique(), 1)
        for name in ("price_observability_by_scrape.csv", "price_observability_sample_profile.csv",
                     "price_observability_fold_counts.csv", "price_observability_performance.csv",
                     "price_observability_fold_performance.csv", "price_observability_comparison.csv",
                     "price_observability_geographic_pairs.csv", "price_observability_tuning.csv"):
            with (out / name).open(encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))
            self.assertFalse({"listing_id", "host_id", "host_name", "latitude", "longitude",
                              "metric_x", "metric_y"}.intersection(header), name)


if __name__ == "__main__":
    unittest.main()

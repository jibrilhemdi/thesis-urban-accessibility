"""Use one valid source price per listing, independent of scrape date."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.pipeline.run_minimum_pipeline import PROJECT_ROOT, clean_listings


class PricePolicyTest(unittest.TestCase):
    def test_scrape_date_does_not_select_or_replace_price(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "listings.csv.gz"
            pd.DataFrame(
                {
                    "id": [1, 2, 3, 4],
                    "last_scraped": ["2026-06-30", "2026-07-04", "2026-07-03", "2026-07-02"],
                    "price": ["$1,200.00", "$900.00", None, "$800.00"],
                    "latitude": [55.7] * 4,
                    "longitude": [12.5] * 4,
                }
            ).to_csv(source, index=False, compression="gzip")
            with patch("src.pipeline.run_minimum_pipeline.PROJECT_ROOT", root):
                frame, summary = clean_listings(source)

        by_id = frame.set_index("listing_id")
        self.assertEqual(by_id.loc[1, "price_nightly"], 1200)
        self.assertEqual(by_id.loc[2, "price_nightly"], 900)
        self.assertTrue(by_id.loc[2, "eligible_for_price_model"])
        self.assertTrue(pd.isna(by_id.loc[3, "price_nightly"]))
        self.assertTrue(pd.isna(by_id.loc[3, "log_price"]))
        self.assertEqual(by_id.loc[4, "price_nightly"], 800)
        self.assertTrue(by_id.loc[4, "eligible_for_price_model"])
        self.assertEqual(summary["eligible_for_price_model_rows"], 3)
        self.assertEqual(summary["price_completeness_by_scrape_date"]["2026-07-03"]["missing_or_invalid_price_rows"], 1)
        self.assertNotIn("price_scrape_batch", frame)
        self.assertNotIn("price_fallback_used", frame)
        self.assertEqual(summary["price_currency"], "DKK")

    def test_duplicate_listing_id_requires_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "listings.csv.gz"
            pd.DataFrame(
                {
                    "id": [1, 1],
                    "last_scraped": ["2026-06-30", "2026-07-04"],
                    "price": [None, "$900.00"],
                    "latitude": [55.7, 55.7],
                    "longitude": [12.5, 12.5],
                }
            ).to_csv(source, index=False, compression="gzip")
            with patch("src.pipeline.run_minimum_pipeline.PROJECT_ROOT", root):
                with self.assertRaisesRegex(ValueError, "reconciliation step"):
                    clean_listings(source)

    def test_current_snapshot_counts(self) -> None:
        source = PROJECT_ROOT / "data/raw/inside_airbnb/copenhagen/2026-06-30/data/listings.csv.gz"
        if not source.exists():
            self.skipTest("Local raw snapshot is unavailable")
        frame, summary = clean_listings(source)
        self.assertEqual(summary["rows"], 23144)
        by_date = summary["price_completeness_by_scrape_date"]
        self.assertEqual(by_date["2026-06-30"]["valid_price_rows"] + by_date["2026-07-01"]["valid_price_rows"], 13177)
        self.assertEqual(by_date["2026-07-03"]["valid_price_rows"] + by_date["2026-07-04"]["valid_price_rows"], 683)
        self.assertEqual(by_date["2026-07-03"]["missing_or_invalid_price_rows"] + by_date["2026-07-04"]["missing_or_invalid_price_rows"], 8301)
        self.assertEqual(summary["missing_source_price_rows"], 9284)
        self.assertEqual(summary["eligible_for_price_model_rows"], 13860)
        self.assertEqual(frame["listing_id"].nunique(), len(frame))


if __name__ == "__main__":
    unittest.main()

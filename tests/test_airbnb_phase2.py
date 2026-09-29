"""Airbnb Phase 2 classification and opt-in PostgreSQL QA."""

import csv
import gzip
import os
import unittest
from datetime import date

from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.run_airbnb_phase2 import CONVENTIONAL_PROPERTY_TYPES, property_type_reason


SNAPSHOT = date(2026, 6, 30)


class PropertyRuleTest(unittest.TestCase):
    def test_conventional_rule_is_fixed_and_interpretable(self) -> None:
        self.assertEqual(len(CONVENTIONAL_PROPERTY_TYPES), 6)
        self.assertTrue(property_type_reason("Entire rental unit")[0])
        self.assertFalse(property_type_reason("Entire serviced apartment")[0])
        self.assertFalse(property_type_reason("Room in hotel")[0])
        self.assertFalse(property_type_reason("Entire place")[0])

    def test_current_source_has_unique_ids_and_expected_room_types(self) -> None:
        source = PROJECT_ROOT / "data/raw/inside_airbnb/copenhagen/2026-06-30/data/listings.csv.gz"
        if not source.exists():
            self.skipTest("Local Inside Airbnb source unavailable")
        with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 23144)
        self.assertEqual(len({row["id"] for row in rows}), len(rows))
        self.assertEqual({row["room_type"] for row in rows},
                         {"Entire home/apt", "Private room", "Shared room"})
        self.assertEqual(sum(row["room_type"] == "Entire home/apt" and
                             row["property_type"] in CONVENTIONAL_PROPERTY_TYPES and
                             bool(row["price"]) for row in rows), 12521)


@unittest.skipUnless(os.environ.get("THESIS_PHASE2_TEST") == "1", "Set THESIS_PHASE2_TEST=1 after phase2-run")
class LivePhase2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def test_raw_imports_and_clean_listing_uniqueness(self) -> None:
        with self.engine.connect() as conn:
            for table, expected in (
                ("inside_airbnb_listings", 23144),
                ("inside_airbnb_calendar", 8448291),
                ("inside_airbnb_reviews", 471781),
                ("inside_airbnb_neighbourhood_lookup", 11),
            ):
                self.assertEqual(conn.scalar(text(f"SELECT count(*) FROM raw.{table}")), expected)
            total, distinct = conn.execute(text(
                "SELECT count(*), count(DISTINCT listing_id) FROM clean.airbnb_listings "
                "WHERE snapshot_date = :snapshot"
            ), {"snapshot": SNAPSHOT}).one()
            self.assertEqual((total, distinct), (23144, 23144))

    def test_geometry_price_coordinates_and_room_type(self) -> None:
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT count(*) FILTER (WHERE valid_coordinates AND (geom IS NULL OR geom_25832 IS NULL)), "
                "count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) <> 4326), "
                "count(*) FILTER (WHERE geom_25832 IS NOT NULL AND ST_SRID(geom_25832) <> 25832), "
                "count(*) FILTER (WHERE primary_sample_candidate AND (price_nightly <= 0 OR log_price IS NULL)), "
                "count(*) FILTER (WHERE primary_sample_candidate AND room_type <> 'Entire home/apt'), "
                "count(*) FILTER (WHERE primary_sample_candidate), "
                "count(*) FILTER (WHERE NOT (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180) "
                "AND valid_coordinates) "
                "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot"
            ), {"snapshot": SNAPSHOT}).one()
            self.assertEqual(tuple(result), (0, 0, 0, 0, 0, 12521, 0))


if __name__ == "__main__":
    unittest.main()

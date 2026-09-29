"""Phase 3 source-resolution rules and opt-in live database validation."""

import os
import unittest
from decimal import Decimal

from sqlalchemy import text

from src.db.connection import get_engine
from src.pipeline.run_context_phase3 import _number, raw_table


class ContextUnitTest(unittest.TestCase):
    def test_numeric_source_cells_are_not_silently_filled(self) -> None:
        self.assertEqual(_number("1,9"), Decimal("1.9"))
        for value in ("", "..", "-1", "NaN"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _number(value)
        with self.assertRaises(ValueError):
            _number("1.9", integer=True)

    def test_raw_version_names_do_not_collide(self) -> None:
        self.assertNotEqual(raw_table("dst_frb", "2026-09-22", "BOL101"),
                            raw_table("dst_municipal", "2026-09-29", "BOL101"))


@unittest.skipUnless(os.environ.get("THESIS_PHASE3_TEST") == "1", "Set THESIS_PHASE3_TEST=1 after phase3-run")
class LiveContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def test_raw_versions_and_clean_geographic_keys(self) -> None:
        with self.engine.connect() as conn:
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM meta.import_runs WHERE status='success' "
                "AND (target_table LIKE 'raw.dst_%' OR target_table LIKE 'raw.kk_district_%')"
            )), 18)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM clean.municipality_context_measures")), 12)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM clean.copenhagen_district_context_measures")), 70)
            self.assertEqual(conn.scalar(text(
                "SELECT count(DISTINCT municipality_code) FROM clean.municipality_context_measures"
            )), 2)
            self.assertEqual(conn.scalar(text(
                "SELECT count(DISTINCT district_code) FROM clean.copenhagen_district_context_measures"
            )), 10)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM clean.copenhagen_district_context_measures "
                "WHERE district_name ILIKE '%Frederiksberg%'"
            )), 0)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM raw.dst_frb_20260922_bol101")), 16632)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM raw.dst_municipal_20260929_bol101")), 33264)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM raw.kk_district_20260929_kkbol3")), 10)

    def test_periods_and_source_lineage_are_explicit(self) -> None:
        with self.engine.connect() as conn:
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM clean.municipality_context_measures WHERE source_file_id IS NULL"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM clean.copenhagen_district_context_measures WHERE source_file_id IS NULL"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM clean.municipality_context_measures "
                "WHERE measure_code='average_personal_disposable_income' AND reference_period='2024'"
            )), 2)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM clean.copenhagen_district_context_measures "
                "WHERE measure_code='district_households' AND reference_period='2026Q1'"
            )), 10)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM clean.airbnb_listings"
            )), 23144)
            self.assertEqual(conn.scalar(text(
                "SELECT sum(value) FROM clean.copenhagen_district_context_measures "
                "WHERE measure_code='district_population'"
            )), Decimal(666861))
            self.assertEqual(conn.scalar(text(
                "SELECT value FROM clean.municipality_context_measures "
                "WHERE municipality_code='101' AND measure_code='total_population'"
            )), Decimal(670389))


if __name__ == "__main__":
    unittest.main()

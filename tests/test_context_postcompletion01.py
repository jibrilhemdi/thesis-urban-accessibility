"""Source-map and live-database integrity checks for the post-completion audit."""

from __future__ import annotations

import math
import os
import unittest

from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.pipeline.run_context_postcompletion01 import verify_city_metadata, verify_national_metadata


class SourceMetadataTests(unittest.TestCase):
    def test_city_district_codes_names_and_periods(self):
        city = verify_city_metadata()
        self.assertEqual(set(city), {f"10{i:02}" for i in range(1, 11)})
        self.assertEqual(sum(row[1] for row in city.values()), 666861)
        self.assertEqual(city["1004"][0], "Vesterbro/Kongens Enghave")

    def test_national_selection_metadata(self):
        values = verify_national_metadata()
        self.assertEqual(values[("FOLK1A", "101")], 670389)
        self.assertEqual(values[("FOLK1A", "147")], 105947)
        self.assertEqual(values[("INDKP106", "101")], 295836)
        self.assertEqual(values[("INDKP106", "147")], 344810)


@unittest.skipUnless(os.environ.get("THESIS_CONTEXT_AUDIT_TEST") == "1", "live DB opt-in")
class DatabaseContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_migration_idempotent(self):
        self.assertEqual(migrate(self.engine), [])

    def test_one_valid_row_per_official_area(self):
        with self.engine.connect() as conn:
            records = conn.execute(text("""
                SELECT analysis_area_code, population_count, area_km2,
                       population_density_per_km2, log_population_density,
                       average_disposable_income_dkk, income_100k_dkk,
                       analysis_area_is_municipality_proxy,
                       analysis_area_income_definition_differs
                FROM features.analysis_area_context
            """)).mappings().all()
        self.assertEqual(len(records), 11)
        self.assertEqual(len({r["analysis_area_code"] for r in records}), 11)
        for row in records:
            self.assertGreater(row["population_count"], 0)
            self.assertGreater(row["area_km2"], 0)
            self.assertTrue(math.isfinite(row["log_population_density"]))
            self.assertAlmostEqual(row["population_density_per_km2"],
                                   row["population_count"] / row["area_km2"], places=7)
            self.assertAlmostEqual(row["log_population_density"],
                                   math.log(row["population_density_per_km2"]), places=12)
            self.assertEqual(row["income_100k_dkk"], row["average_disposable_income_dkk"] / 100000)
            self.assertEqual(row["analysis_area_is_municipality_proxy"],
                             row["analysis_area_code"] == "frederiksberg_0147")
            self.assertEqual(row["analysis_area_income_definition_differs"],
                             row["analysis_area_code"] == "frederiksberg_0147")

    def test_join_preserves_rows_and_primary_sample(self):
        with self.engine.connect() as conn:
            base = conn.execute(text("""
                SELECT count(*), count(DISTINCT (snapshot_date, listing_id)),
                       count(*) FILTER (WHERE primary_sample_candidate AND official_cv_area_id IS NOT NULL
                                         AND nearest_station_walking_minutes IS NOT NULL)
                FROM analysis.analysis_dataset_v1
            """)).one()
            joined = conn.execute(text("""
                SELECT count(*), count(DISTINCT (snapshot_date, listing_id)),
                       count(*) FILTER (WHERE primary_sample_candidate AND official_cv_area_id IS NOT NULL
                                         AND nearest_station_walking_minutes IS NOT NULL),
                       count(*) FILTER (WHERE official_cv_area_id IS NOT NULL AND analysis_area_code IS NULL),
                       count(*) FILTER (WHERE official_cv_area_id IS NULL AND analysis_area_code IS NULL)
                FROM analysis.analysis_dataset_context_v1
            """)).one()
        self.assertEqual(base, (23144, 23144, 12412))
        self.assertEqual(joined, (23144, 23144, 12412, 0, 78))


if __name__ == "__main__":
    unittest.main()

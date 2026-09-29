"""Phase 7 view, provenance, spatial fold and privacy checks."""

import csv
import os
import unittest

from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.output_paths import output_file
from src.pipeline.run_analysis_phase7 import DICTIONARY


class SpecificationTest(unittest.TestCase):
    def test_dictionary_and_public_outputs_are_declared(self):
        self.assertIn("log_price", DICTIONARY)
        self.assertIn("bathrooms_effective", DICTIONARY)
        self.assertEqual(DICTIONARY["instant_bookable"][3], "unusable")
        self.assertEqual(DICTIONARY["frb_municipality_income_2024_dkk_person"][3], "descriptive_only")


@unittest.skipUnless(os.environ.get("THESIS_PHASE7_TEST") == "1", "Set THESIS_PHASE7_TEST=1 after phase7-run")
class LivePhase7Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_migrations_are_idempotent(self):
        self.assertEqual(migrate(self.engine), [])

    def test_listing_cardinality_and_price(self):
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT count(*) n,count(DISTINCT (snapshot_date,listing_id)) unique_n,"
                "count(*) FILTER (WHERE primary_sample_candidate) primary_n,"
                "count(*) FILTER (WHERE missing_or_invalid_price) missing_n,"
                "count(*) FILTER (WHERE primary_sample_candidate AND "
                "(price_nightly <= 0 OR log_price IS NULL)) bad_primary_n,"
                "count(*) FILTER (WHERE missing_or_invalid_price AND log_price IS NOT NULL) imputed_n "
                "FROM analysis.analysis_dataset_v1"
            )).one()
            self.assertEqual(tuple(result), (23144, 23144, 12521, 9284, 0, 0))

    def test_source_text_bathrooms_and_context_separation(self):
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT count(*) FILTER (WHERE primary_sample_candidate AND "
                "bathrooms_source='source_text') text_n,"
                "count(*) FILTER (WHERE primary_sample_candidate AND "
                "bathrooms_effective IS NULL) missing_bath_n,"
                "count(*) FILTER (WHERE official_municipality_code='0147' AND "
                "district_income_2024_dkk_person IS NOT NULL) leaked_city_n,"
                "count(*) FILTER (WHERE official_municipality_code='0101' AND "
                "frb_municipality_income_2024_dkk_person IS NOT NULL) leaked_frb_n "
                "FROM analysis.analysis_dataset_v1"
            )).one()
            self.assertEqual(tuple(result), (1674, 0, 0, 0))

    def test_frozen_blocks_and_common_sample(self):
        with self.engine.connect() as conn:
            split_blocks = conn.scalar(text(
                "SELECT count(*) FROM (SELECT block_id FROM analysis.spatial_cv_folds_v1 "
                "GROUP BY 1 HAVING count(DISTINCT fold_id)>1) q"
            ))
            self.assertEqual(split_blocks, 0)
            result = conn.execute(text(
                "SELECT count(*) all_n,count(*) FILTER (WHERE a.primary_sample_candidate) primary_n,"
                "count(*) FILTER (WHERE a.primary_sample_candidate AND "
                "a.nearest_station_walking_minutes IS NOT NULL) common_n,"
                "count(DISTINCT f.block_id) block_n,count(DISTINCT f.fold_id) fold_n "
                "FROM analysis.spatial_cv_folds_v1 f JOIN analysis.analysis_dataset_v1 a "
                "USING(snapshot_date,listing_id)"
            )).one()
            self.assertEqual(tuple(result), (23066, 12508, 12412, 111, 5))
            municipality_folds = conn.scalar(text(
                "SELECT count(*) FROM (SELECT fold_id FROM analysis.spatial_cv_folds_v1 "
                "GROUP BY 1 HAVING count(DISTINCT municipality_code)=2) q"
            ))
            self.assertEqual(municipality_folds, 5)

    def test_public_diagnostics_are_aggregate_only(self):
        for filename in ("missingness_report.csv", "price_missingness_comparison.csv",
                         "redundancy_pairs.csv", "vif_diagnostics.csv", "phase07_sample_summary.csv",
                         "phase07_spatial_cv_folds.csv"):
            with output_file("tables", "phase07", filename).open(newline="", encoding="utf-8") as handle:
                columns = csv.DictReader(handle).fieldnames
            self.assertFalse({"listing_id", "host_name", "latitude", "longitude", "reviews"} & set(columns))
        with (PROJECT_ROOT / "docs/data_dictionary_analysis.csv").open(newline="", encoding="utf-8") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), len(DICTIONARY))

    def test_missing_price_grid_uses_aggregate_suppressed_cells(self):
        with self.engine.connect() as conn:
            grid = conn.execute(text(
                "WITH cells AS (SELECT floor(ST_X(l.geom_25832)/500)::integer gx,"
                "floor(ST_Y(l.geom_25832)/500)::integer gy,"
                "count(*) FILTER (WHERE a.missing_or_invalid_price) missing_n "
                "FROM analysis.analysis_dataset_v1 a JOIN clean.airbnb_listings l "
                "USING(snapshot_date,listing_id) WHERE a.in_study_area "
                "AND a.entire_home_apt AND a.conventional_residential "
                "AND a.valid_coordinates GROUP BY 1,2) "
                "SELECT count(*) FILTER (WHERE missing_n>=5) shown_cells,"
                "sum(missing_n) FILTER (WHERE missing_n>=5) shown_missing,"
                "sum(missing_n) all_missing FROM cells"
            )).one()
        self.assertEqual(tuple(grid), (236, 8346, 8559))
        self.assertTrue(output_file("figures", "phase07", "missing_price_grid.png").is_file())

    def test_missing_price_area_percentage_uses_assigned_denominators(self):
        with self.engine.connect() as conn:
            areas = conn.execute(text(
                "SELECT count(*) area_n,sum(n) assigned_n,sum(missing_n) missing_n,"
                "min(100.0*missing_n/n) min_pct,max(100.0*missing_n/n) max_pct "
                "FROM (SELECT official_cv_area_id,count(*) n,"
                "count(*) FILTER (WHERE missing_or_invalid_price) missing_n "
                "FROM analysis.analysis_dataset_v1 "
                "WHERE in_study_area AND entire_home_apt AND conventional_residential "
                "AND valid_coordinates AND official_cv_area_id IS NOT NULL "
                "GROUP BY official_cv_area_id) q"
            )).one()
        self.assertEqual(tuple(areas[:3]), (11, 21019, 8511))
        self.assertGreater(float(areas.min_pct), 30)
        self.assertLess(float(areas.max_pct), 45)
        self.assertTrue(output_file("figures", "phase07", "missing_price_area.png").is_file())


if __name__ == "__main__":
    unittest.main()

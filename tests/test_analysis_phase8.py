"""Phase 8 spatial diagnostics and immutable outer-fold QA."""

import csv
import os
import unittest

import numpy as np
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.osm_taxonomy_phase5 import categories
from src.spatial.spatial_diagnostics import knn_indices, moran_knn


class SpatialDiagnosticTest(unittest.TestCase):
    def test_bus_only_stop_is_not_a_frozen_station_destination(self):
        self.assertNotIn("station", categories({"name": "Example stop", "highway": "bus_stop", "bus": "yes"}))
        self.assertNotIn("station", categories({"name": "Example terminal", "public_transport": "station",
                                                 "bus": "yes"}))

    def test_knn_excludes_self_and_moran_is_reproducible(self):
        x, y = np.meshgrid(np.arange(6), np.arange(6))
        points = np.column_stack((x.ravel(), y.ravel())).astype(float)
        neighbours = knn_indices(points, k=4)
        self.assertEqual(neighbours.shape, (36, 4))
        self.assertTrue(all(row not in indices for row, indices in enumerate(neighbours)))
        values = x.ravel().astype(float)
        first = moran_knn(values, points, k=4, permutations=99, seed=123)
        self.assertEqual(first, moran_knn(values, points, k=4, permutations=99, seed=123))
        self.assertGreater(first["moran_i"], 0)


@unittest.skipUnless(os.environ.get("THESIS_PHASE8_TEST") == "1", "Set THESIS_PHASE8_TEST=1 after phase8-run")
class LivePhase8Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_migrations_and_assignment_cardinality(self):
        self.assertEqual(migrate(self.engine), [])
        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT count(*) n,count(DISTINCT (snapshot_date,listing_id)) unique_n,"
                "count(*) FILTER (WHERE heldout_area IS NOT NULL) assigned_n,"
                "count(DISTINCT random_fold) random_folds,"
                "count(DISTINCT geographic_fold) geographic_folds,"
                "count(DISTINCT block_1500m_fold) robustness_folds "
                "FROM analysis.cv_assignments"
            )).one()
            self.assertEqual(tuple(row), (23144, 23144, 23066, 5, 11, 5))

    def test_geographic_areas_and_frozen_grid_integrity(self):
        with self.engine.connect() as conn:
            mismatch = conn.scalar(text(
                "SELECT count(*) FROM analysis.cv_assignments a "
                "JOIN features.listing_spatial_base s USING(snapshot_date,listing_id) "
                "LEFT JOIN analysis.spatial_cv_folds_v1 f USING(snapshot_date,listing_id) "
                "WHERE a.heldout_area IS DISTINCT FROM s.official_cv_area_id "
                "OR a.block_1km_id IS DISTINCT FROM f.block_id "
                "OR a.block_1km_fold IS DISTINCT FROM f.fold_id"
            ))
            split_blocks = conn.scalar(text(
                "SELECT count(*) FROM (SELECT block_1500m_id FROM analysis.cv_assignments "
                "WHERE block_1500m_id IS NOT NULL GROUP BY 1 "
                "HAVING count(DISTINCT block_1500m_fold)>1) q"
            ))
            min_test_n = conn.scalar(text(
                "SELECT min(n) FROM (SELECT count(*) n FROM analysis.cv_assignments f "
                "JOIN analysis.analysis_dataset_v1 a USING(snapshot_date,listing_id) "
                "WHERE a.primary_sample_candidate AND a.nearest_station_walking_minutes IS NOT NULL "
                "AND f.heldout_area IS NOT NULL "
                "GROUP BY f.heldout_area) q"
            ))
        self.assertEqual((mismatch, split_blocks, min_test_n), (0, 0, 221))

    def test_buffer_exclusions_are_nested_and_not_test_rows(self):
        with self.engine.connect() as conn:
            invalid = conn.scalar(text(
                "SELECT count(*) FROM analysis.cv_buffer_exclusions b "
                "JOIN analysis.cv_assignments a USING(snapshot_date,listing_id) "
                "WHERE b.heldout_area=a.heldout_area OR b.buffer_m NOT IN (500,1000)"
            ))
            nonnested = conn.scalar(text(
                "SELECT count(*) FROM analysis.cv_buffer_exclusions b "
                "WHERE b.buffer_m=500 AND NOT EXISTS ("
                "SELECT 1 FROM analysis.cv_buffer_exclusions bigger "
                "WHERE bigger.buffer_m=1000 AND bigger.heldout_area=b.heldout_area "
                "AND bigger.snapshot_date=b.snapshot_date AND bigger.listing_id=b.listing_id)"
            ))
            self.assertEqual((invalid, nonnested), (0, 0))

    def test_outputs_are_aggregate_and_complete(self):
        table_names = ("phase08_descriptive_statistics.csv", "phase08_sample_composition.csv",
                       "phase08_accessibility_correlations.csv", "phase08_spatial_moran.csv",
                       "phase08_distance_bin_covariance.csv", "phase08_cv_fold_summary.csv",
                       "phase08_geographic_support.csv", "phase08_buffer_feasibility.csv",
                       "phase08_map_coverage.csv")
        for filename in table_names:
            with (PROJECT_ROOT / "outputs/tables" / filename).open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertTrue(next(reader, None), filename)
                self.assertFalse({"listing_id", "host_name", "latitude", "longitude", "metric_x", "metric_y"} &
                                 set(reader.fieldnames), filename)
        with (PROJECT_ROOT / "outputs/tables/phase08_map_coverage.csv").open(newline="", encoding="utf-8") as handle:
            coverage = list(csv.DictReader(handle))
        self.assertEqual(len(coverage), 12)  # Six variables, two map resolutions each.
        for row in coverage:
            self.assertGreaterEqual(int(row["smallest_displayed_unit_n"]), 5)
            self.assertEqual(int(row["n_available_listings"]),
                             int(row["n_displayed_listings"]) + int(row["n_not_displayed"]))
            self.assertEqual(row["destination_taxonomy_version"], "phase05_v2")
            if row["variable"] == "price_nightly":
                self.assertEqual(int(row["destination_marker_count"]), 0)
            else:
                self.assertGreater(int(row["destination_marker_count"]), 0)
        self.assertEqual({int(row["destination_marker_count"]) for row in coverage
                          if row["variable"] == "nearest_station_walking_minutes"}, {93})
        for filename in ("phase08_price_distributions.png", "phase08_listing_density.png",
                         "phase08_median_price_area.png", "phase08_median_price_grid.png",
                         "phase08_food_euclidean_area.png", "phase08_food_euclidean_grid.png",
                         "phase08_food_walking_area.png", "phase08_food_walking_grid.png",
                         "phase08_cultural_euclidean_area.png", "phase08_cultural_euclidean_grid.png",
                         "phase08_cultural_walking_area.png", "phase08_cultural_walking_grid.png",
                         "phase08_station_walking_area.png", "phase08_station_walking_grid.png",
                         "phase08_euclidean_network_hexbin.png"):
            self.assertTrue((PROJECT_ROOT / "outputs/figures" / filename).is_file(), filename)


if __name__ == "__main__":
    unittest.main()

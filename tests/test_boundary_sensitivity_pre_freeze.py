"""Read-only integrity tests for the post-freeze destination-endpoint sensitivity."""

from __future__ import annotations

import os
import unittest

import pandas as pd
from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.run_context_models_postcompletion02 import freeze_check


@unittest.skipUnless(os.environ.get("THESIS_BOUNDARY_TEST") == "1",
                     "Set THESIS_BOUNDARY_TEST=1 for live sensitivity tests")
class BoundarySensitivityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_primary_freeze_and_destination_subsets(self):
        with self.engine.connect() as conn:
            freeze_check(conn)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.official_municipalities "
                "WHERE municipality_code IN ('0101','0147')")), 2)
            for table, key in (("osm_pois", "destination_key"),
                               ("transit_stations", "station_key")):
                subset = ("osm_pois_study_union_sensitivity" if table == "osm_pois" else
                          "transit_stations_study_union_sensitivity")
                n, outside, orphan = conn.execute(text(
                    f"SELECT count(*),count(*) FILTER (WHERE NOT ST_Covers(u.geom_25832,v.geom_25832)),"
                    f"count(*) FILTER (WHERE p.{key} IS NULL) FROM spatial.{subset} v "
                    f"CROSS JOIN spatial.study_union_boundary_sensitivity u "
                    f"LEFT JOIN spatial.{table} p ON p.{key}=v.{key}"
                )).one()
                self.assertGreater(n, 0)
                self.assertEqual(outside, 0)
                self.assertEqual(orphan, 0)

    def test_feature_rows_are_unique_and_monotone(self):
        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT count(*) n,count(DISTINCT (f.snapshot_date,f.listing_id)) unique_n,"
                "count(*) FILTER (WHERE f.food_social_800m_clip>a.food_social_800m "
                "OR f.cultural_tourist_800m_clip>a.cultural_tourist_800m "
                "OR f.food_social_w_10_clip>a.food_social_w_10 "
                "OR f.cultural_tourist_w_10_clip>a.cultural_tourist_w_10 "
                "OR f.nearest_station_euclidean_m_clip+1e-6<a.nearest_station_euclidean_m "
                "OR f.nearest_station_walking_minutes_clip+1e-6<a.nearest_station_walking_minutes) bad,"
                "count(*) FILTER (WHERE f.nearest_station_euclidean_m_clip IS NULL "
                "OR f.nearest_station_walking_minutes_clip IS NULL) missing_station "
                "FROM features.destination_boundary_sensitivity f "
                "JOIN analysis.analysis_dataset_v1 a USING(snapshot_date,listing_id)"
            )).one()
            self.assertEqual(row.n, 12412)
            self.assertEqual(row.unique_n, row.n)
            self.assertEqual(row.bad, 0)
            self.assertEqual(row.missing_station, 0)

    def test_euclidean_values_against_postgis_spot_checks(self):
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "WITH sample AS MATERIALIZED (SELECT f.snapshot_date,f.listing_id,"
                "f.food_social_800m_clip,f.cultural_tourist_800m_clip,"
                "f.nearest_station_euclidean_m_clip,l.geom_25832 "
                "FROM features.destination_boundary_sensitivity f "
                "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
                "ORDER BY f.listing_id LIMIT 8),"
                "pois AS MATERIALIZED (SELECT category,geom_25832 "
                "FROM spatial.osm_pois_study_union_sensitivity),"
                "stations AS MATERIALIZED (SELECT geom_25832 "
                "FROM spatial.transit_stations_study_union_sensitivity) "
                "SELECT f.food_social_800m_clip,f.cultural_tourist_800m_clip,"
                "f.nearest_station_euclidean_m_clip,"
                "(SELECT count(*) FROM pois p "
                "WHERE p.category='food_social' AND ST_DWithin(p.geom_25832,f.geom_25832,800)),"
                "(SELECT count(*) FROM pois p "
                "WHERE p.category='cultural_tourist' AND ST_DWithin(p.geom_25832,f.geom_25832,800)),"
                "(SELECT min(ST_Distance(s.geom_25832,f.geom_25832)) "
                "FROM stations s) "
                "FROM sample f"
            )).all()
        self.assertEqual(len(rows), 8)
        for food, culture, station, food_sql, culture_sql, station_sql in rows:
            self.assertEqual(food, food_sql)
            self.assertEqual(culture, culture_sql)
            self.assertAlmostEqual(station, station_sql, places=6)

    def test_saved_fold_coverage_and_unchanged_baseline(self):
        root = PROJECT_ROOT / "outputs/tables"
        pooled = pd.read_csv(root / "boundary_sensitivity_performance.csv")
        folds = pd.read_csv(root / "boundary_sensitivity_fold_performance.csv")
        primary = pd.read_csv(root / "phase09/model_performance.csv")
        self.assertEqual(len(pooled), 12)
        self.assertEqual(len(folds), 96)
        self.assertTrue((pooled.n == 12412).all())
        for scheme, expected in (("random_5", 5), ("geographic_11", 11)):
            self.assertEqual(folds.loc[folds.cv_scheme == scheme, "fold"].nunique(), expected)
            for model in ("OLS", "XGBoost"):
                original = primary.loc[(primary.cv_scheme == scheme) &
                                       (primary.model == model) & (primary.feature_set == "M0")].iloc[0]
                clipped = pooled.loc[(pooled.cv_scheme == scheme) &
                                     (pooled.model == model) & (pooled.feature_set == "M0")].iloc[0]
                for metric in ("rmse_log", "mae_log", "r2_log"):
                    self.assertAlmostEqual(original[metric], clipped[metric], places=12)


if __name__ == "__main__":
    unittest.main()

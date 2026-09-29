"""Phase 10 deduplication, fold-wise preprocessing and optional live integrity QA."""

import json
import os
import unittest

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.output_paths import output_file
from src.pipeline.run_analysis_phase10 import FEATURES, _freeze, _preprocessor
from src.pipeline.run_bus_walking_phase10 import deduplicate


class Phase10PureTest(unittest.TestCase):
    def test_bus_dedup_preserves_opposite_direction_stops(self):
        stops = pd.DataFrame([
            {"bus_stop_key": "node/2", "x": 0., "y": 0., "tags": {"name": "Central"}},
            {"bus_stop_key": "way/4", "x": 2., "y": 0., "tags": {"name": "Central"}},
            {"bus_stop_key": "node/3", "x": 12., "y": 0., "tags": {"name": "Central"}},
            {"bus_stop_key": "node/5", "x": 0., "y": 1., "tags": {"name": "Another"}},
        ])
        self.assertEqual(deduplicate(stops), [("node/2", 2), ("node/3", 1), ("node/5", 1)])

    def test_training_only_median_for_phase10(self):
        columns = tuple(FEATURES["M0"])
        train = pd.DataFrame({key: [0., 0., 0.] for key in columns if key not in
                              ("property_type", "official_municipality_code")})
        train["bedrooms"] = [1., np.nan, 3.]
        train["property_type"] = "Entire condo"
        train["official_municipality_code"] = "0101"
        test = train.iloc[[0]].copy()
        test["bedrooms"] = np.nan
        prep = _preprocessor(columns).fit(train[list(columns)])
        transformed = prep.transform(test[list(columns)])
        names = list(prep.get_feature_names_out())
        self.assertEqual(float(transformed[0, names.index("bedrooms")]), 2.)
        self.assertEqual(float(transformed[0, names.index("missingindicator_bedrooms")]), 1.)


@unittest.skipUnless(os.getenv("THESIS_PHASE10_TEST") == "1", "Set THESIS_PHASE10_TEST=1")
class Phase10LiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_phase9_artifacts_and_cv_frozen(self):
        expected = json.loads(output_file("tables", "phase10", "primary_freeze.json").read_text())
        with self.engine.connect() as conn:
            self.assertEqual(_freeze(conn), expected)

    def test_bus_table_cardinality_units_and_geometry(self):
        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT count(*) n,count(DISTINCT (snapshot_date,listing_id)) unique_n,"
                "count(*) FILTER(WHERE bus_walk_time_min IS NULL) unreachable,"
                "count(*) FILTER(WHERE bus_walk_time_min IS NOT NULL AND "
                "abs(bus_walk_time_min*80-bus_walk_distance_m)>0.00001) bad_speed,"
                "count(*) FILTER(WHERE distance_crs_epsg<>25832 OR walking_speed_kmh<>4.80) bad_units "
                "FROM features.bus_accessibility"
            )).one()
            bad_geom = conn.scalar(text(
                "SELECT count(*) FROM spatial.bus_stops_canonical "
                "WHERE NOT ST_IsValid(geom_25832) OR ST_SRID(geom_25832)<>25832"
            ))
            primary_missing = conn.scalar(text(
                "SELECT count(*) FROM analysis.analysis_dataset_v1 a "
                "JOIN features.bus_accessibility b USING(snapshot_date,listing_id) "
                "WHERE a.primary_sample_candidate AND a.official_cv_area_id IS NOT NULL "
                "AND a.nearest_station_walking_minutes IS NOT NULL "
                "AND b.bus_walk_time_min IS NULL"
            ))
        self.assertEqual(tuple(row), (23144, 23144, 140, 0, 0))
        self.assertEqual(bad_geom, 0)
        self.assertEqual(primary_missing, 0)

    def test_phase10_public_tables_have_no_row_level_fields(self):
        forbidden = {"listing_id", "host_name", "latitude", "longitude",
                     "metric_x", "metric_y", "price_nightly", "log_price"}
        paths = list((PROJECT_ROOT / "outputs/tables/phase10").glob("*.csv"))
        for path in paths:
            names = set(pd.read_csv(path, nrows=0).columns)
            self.assertFalse(names & forbidden, path.name)
        self.assertEqual(len(pd.read_csv(output_file("tables", "phase10", "model_performance.csv"))), 64)
        self.assertEqual(len(pd.read_csv(output_file("tables", "phase10", "conclusion_stability.csv"))), 48)

    def test_outcome_units_and_buffer_separation(self):
        with self.engine.connect() as conn:
            invalid = conn.scalar(text(
                "SELECT count(*) FROM analysis.analysis_dataset_v1 a "
                "WHERE a.primary_sample_candidate AND a.official_cv_area_id IS NOT NULL "
                "AND a.nearest_station_walking_minutes IS NOT NULL "
                "AND (a.price_nightly<=0 OR a.log_price IS NULL "
                "OR abs(a.log_price-ln(a.price_nightly::double precision))>1e-10)"
            ))
        separation = pd.read_csv(output_file("tables", "phase10", "buffer_separation.csv"))
        self.assertEqual(invalid, 0)
        self.assertEqual(len(separation), 22)
        self.assertTrue((separation.actual_min_separation_m >= separation.buffer_m).all())
        self.assertEqual(set(separation.crs_epsg), {25832})


if __name__ == "__main__":
    unittest.main()

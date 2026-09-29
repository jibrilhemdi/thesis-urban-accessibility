"""Phase 4 provider-boundary, assignment, CRS and aggregate-output QA."""

import csv
import os
import unittest
from decimal import Decimal

from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.run_spatial_phase4 import EXTRACTION_BUFFER_METRES, MAX_WALK_MINUTES, WALK_SPEED_MPS


class SpatialRuleTest(unittest.TestCase):
    def test_buffer_exceeds_predeclared_15_minute_path_length(self) -> None:
        self.assertGreater(EXTRACTION_BUFFER_METRES, MAX_WALK_MINUTES * 60 * WALK_SPEED_MPS)


@unittest.skipUnless(os.environ.get("THESIS_PHASE4_TEST") == "1", "Set THESIS_PHASE4_TEST=1 after phase4-run")
class LiveSpatialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def test_polygons_are_valid_and_source_identified(self) -> None:
        with self.engine.connect() as conn:
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.provider_neighbourhoods")), 11)
            invalid = conn.scalar(text(
                "SELECT count(*) FROM spatial.provider_neighbourhoods WHERE NOT ST_IsValid(geom_4326) "
                "OR NOT ST_IsValid(geom_25832) OR ST_SRID(geom_4326)<>4326 "
                "OR ST_SRID(geom_25832)<>25832 OR source_file_id IS NULL"
            ))
            self.assertEqual(invalid, 0)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.provider_neighbourhoods WHERE municipality_proxy='Frederiksberg'"
            )), 1)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.study_area")), 4)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.official_municipalities")), 2)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.official_copenhagen_districts")), 10)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.official_cv_areas")), 11)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.map_context_municipalities")), 29)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.map_context_municipalities WHERE NOT ST_IsValid(geom_4326) "
                "OR ST_SRID(geom_25832)<>25832 OR source_file_id IS NULL"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM meta.import_runs WHERE status='success' "
                "AND target_table='spatial.map_context_municipalities'"
            )), 1)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM meta.source_files WHERE relative_path LIKE "
                "'data/raw/official_boundaries/%'"
            )), 4)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM meta.import_runs WHERE status='success' AND "
                "target_table IN ('spatial.official_municipalities','spatial.official_copenhagen_districts')"
            )), 3)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.official_municipalities WHERE NOT ST_IsValid(geom_4326) "
                "OR ST_SRID(geom_25832)<>25832 OR source_file_id IS NULL"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.official_copenhagen_districts WHERE NOT ST_IsValid(geom_4326) "
                "OR ST_SRID(geom_25832)<>25832 OR source_file_id IS NULL"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT buffer_metres FROM spatial.study_area WHERE area_kind='planned_15min_extraction'"
            )), Decimal(EXTRACTION_BUFFER_METRES))

    def test_assignments_and_distance(self) -> None:
        with self.engine.connect() as conn:
            qa = conn.execute(text(
                "SELECT count(*),count(*) FILTER (WHERE polygon_match_count=0),"
                "count(*) FILTER (WHERE polygon_match_count>1),"
                "count(*) FILTER (WHERE near_provider_border_100m),"
                "count(*) FILTER (WHERE provider_label_matches_polygon IS FALSE),"
                "count(*) FILTER (WHERE context_statistical_unit_id IS NOT NULL) "
                "FROM features.listing_spatial_base"
            )).one()
            self.assertEqual(tuple(qa), (23144, 0, 0, 3103, 0, 0))
            official = conn.execute(text(
                "SELECT count(*) FILTER (WHERE official_municipality_match_count=0),"
                "count(*) FILTER (WHERE official_cv_match_count=0),"
                "count(*) FILTER (WHERE official_cv_area_id IS NOT NULL),"
                "count(*) FILTER (WHERE l.primary_sample_candidate AND official_cv_area_id IS NULL) "
                "FROM features.listing_spatial_base s JOIN clean.airbnb_listings l USING(snapshot_date,listing_id)"
            )).one()
            self.assertEqual(tuple(official), (76, 36, 23066, 13))
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM features.listing_spatial_base WHERE "
                "context_statistical_unit_id IS NOT NULL"
            )), 0)
            max_error = conn.scalar(text(
                "SELECT max(abs(s.distance_centre_euclidean_km - "
                "ST_Distance(l.geom_25832,c.geom_25832)/1000.0)) "
                "FROM features.listing_spatial_base s JOIN clean.airbnb_listings l "
                "USING (snapshot_date,listing_id) CROSS JOIN spatial.reference_points c "
                "WHERE c.reference_id='city_hall_square'"
            ))
            self.assertLess(max_error, 1e-9)
            self.assertFalse(conn.scalar(text(
                "SELECT ST_Covers(o.geom_4326,p.geom_4326) FROM spatial.study_area o "
                "CROSS JOIN spatial.study_area p WHERE o.area_kind='archived_osm_bbox' "
                "AND p.area_kind='planned_15min_extraction'"
            )))
            incomplete = conn.execute(text(
                "SELECT count(*) FILTER (WHERE NOT ST_Covers(o.geom_25832,ST_Buffer(l.geom_25832,:radius))),"
                "count(*) FILTER (WHERE l.primary_sample_candidate AND NOT "
                "ST_Covers(o.geom_25832,ST_Buffer(l.geom_25832,:radius))) "
                "FROM clean.airbnb_listings l CROSS JOIN spatial.study_area o "
                "WHERE o.area_kind='archived_osm_bbox'"
            ), {"radius": MAX_WALK_MINUTES * 60 * WALK_SPEED_MPS}).one()
            self.assertEqual(tuple(incomplete), (1, 0))

    def test_cv_counts_and_maps_are_aggregate_only(self) -> None:
        with (PROJECT_ROOT / "outputs/tables/cv_area_counts.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 11)
        self.assertEqual(sum(int(row["eligible_n"]) for row in rows), 12508)
        self.assertGreater(min(int(row["eligible_n"]) for row in rows), 0)
        self.assertFalse({"listing_id", "host_name", "latitude", "longitude"}.intersection(rows[0]))
        for filename in ("phase04_study_area.png", "phase04_municipality_proxy.png",
                         "phase04_candidate_cv_areas.png", "phase04_osm_coverage.png"):
            self.assertTrue((PROJECT_ROOT / "outputs/figures" / filename).is_file())


if __name__ == "__main__":
    unittest.main()

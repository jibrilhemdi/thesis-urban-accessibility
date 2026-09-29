"""Phase 5 taxonomy, OSM provenance, destination and Euclidean-feature QA."""

import json
import csv
import os
import unittest

from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline.acquire_osm_phase5 import existing_archive
from src.pipeline.osm_taxonomy_phase5 import categories, normalize_name


class TaxonomyTest(unittest.TestCase):
    def test_inclusion_and_exclusion(self) -> None:
        self.assertEqual(categories({"amenity": "restaurant"}), ("food_social",))
        self.assertEqual(categories({"tourism": "museum"}), ("cultural_tourist",))
        self.assertEqual(categories({"historic": "memorial"}), ())
        self.assertEqual(categories({"railway": "subway_entrance", "name": "X"}), ())
        self.assertEqual(categories({"railway": "station"}), ())
        self.assertEqual(categories({"railway": "station", "name": "X"}), ("station",))
        self.assertEqual(normalize_name("Nørreport Station"), "nørreport st")


@unittest.skipUnless(os.environ.get("THESIS_PHASE5_TEST") == "1", "Set THESIS_PHASE5_TEST=1 after phase5-run")
class LiveEuclideanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = get_engine()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def test_source_registration_and_import_log(self) -> None:
        archive = existing_archive()
        self.assertIsNotNone(archive)
        metadata = json.loads((archive / "acquisition_metadata.json").read_text(encoding="utf-8"))
        with self.engine.connect() as conn:
            for name in ("Copenhagen.osm.pbf", "Copenhagen.poly"):
                self.assertEqual(sha256_file(archive / name), metadata["files"][name]["sha256"])
                row = conn.execute(text(
                    "SELECT source_file_id,trim(file_hash_sha256),file_size,source_url "
                    "FROM meta.source_files WHERE relative_path=:path"
                ), {"path": f"data/raw/osm/phase05/{archive.name}/{name}"}).one()
                self.assertEqual(row[1], metadata["files"][name]["sha256"])
                self.assertEqual(row[2], metadata["files"][name]["size_bytes"])
                self.assertTrue(row[3].startswith("https://download3.bbbike.org/"))
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM meta.import_runs WHERE target_table='raw.osm_phase5_elements' "
                "AND status='success'"
            )), 1)

    def test_phase5_migration_is_idempotent(self) -> None:
        self.assertEqual(migrate(self.engine), [])

    def test_destination_integrity(self) -> None:
        with self.engine.connect() as conn:
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM raw.osm_phase5_elements")), 3981)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.osm_destination_candidates")), 3643)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.osm_pois")), 3469)
            self.assertEqual(conn.scalar(text("SELECT count(*) FROM spatial.transit_stations")), 143)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.osm_destination_candidates c "
                "LEFT JOIN spatial.osm_destination_candidates a "
                "ON c.canonical_candidate_key=a.candidate_key "
                "WHERE a.candidate_key IS NULL"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.osm_pois WHERE ST_SRID(geom)<>4326 OR ST_SRID(geom_25832)<>25832 "
                "OR NOT ST_IsValid(geom)"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM spatial.transit_stations WHERE ST_SRID(geom)<>4326 "
                "OR ST_SRID(geom_25832)<>25832 OR name IS NULL"
            )), 0)
            self.assertEqual(conn.scalar(text(
                "SELECT sum(duplicate_count) FROM (SELECT duplicate_count FROM spatial.osm_pois "
                "UNION ALL SELECT duplicate_count FROM spatial.transit_stations) x"
            )), 31)

    def test_feature_completeness_and_monotonicity(self) -> None:
        with self.engine.connect() as conn:
            qa = conn.execute(text(
                "SELECT count(*) AS n,count(DISTINCT (snapshot_date,listing_id)) AS unique_n,"
                "count(*) FILTER (WHERE valid_coordinates AND (NOT count_coverage_complete "
                "OR NOT nearest_station_coverage_complete OR nearest_station_distance_m IS NULL)) AS edge_or_missing,"
                "count(*) FILTER (WHERE food_social_800m>food_social_1200m "
                "OR food_social_1200m>food_social_1600m OR cultural_tourist_800m>cultural_tourist_1200m "
                "OR cultural_tourist_1200m>cultural_tourist_1600m) AS nonmonotone,"
                "count(*) FILTER (WHERE NOT valid_coordinates AND (food_social_800m IS NOT NULL "
                "OR nearest_station_distance_m IS NOT NULL)) AS invalid_filled "
                "FROM features.euclidean_accessibility"
            )).one()
            self.assertEqual(tuple(qa), (23144, 23144, 0, 0, 0))
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM features.euclidean_accessibility f JOIN clean.airbnb_listings l "
                "USING(snapshot_date,listing_id) WHERE l.primary_sample_candidate"
            )), 12521)
            # Independent exact spatial recount for a reproducible sample of listings.
            mismatch = conn.scalar(text(
                "WITH sample AS (SELECT * FROM clean.airbnb_listings WHERE valid_coordinates "
                "ORDER BY listing_id LIMIT 50) SELECT count(*) FROM sample l "
                "JOIN features.euclidean_accessibility f USING(snapshot_date,listing_id) "
                "WHERE f.food_social_800m<>(SELECT count(*) FROM spatial.osm_pois p "
                "WHERE p.category='food_social' AND ST_DWithin(p.geom_25832,l.geom_25832,800)) "
                "OR abs(f.nearest_station_distance_m-(SELECT min(ST_Distance(s.geom_25832,l.geom_25832)) "
                "FROM spatial.transit_stations s))>0.000001"
            ))
            self.assertEqual(mismatch, 0)

    def test_public_aggregate_exports_have_no_listing_identifiers(self) -> None:
        for filename, expected_rows in (("phase05_destination_counts.csv", 3),
                                        ("phase05_feature_summary.csv", 7)):
            with (PROJECT_ROOT / "outputs/tables" / filename).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), expected_rows)
            self.assertFalse({"listing_id", "host_name", "latitude", "longitude", "name"}
                             .intersection(rows[0].keys()))


if __name__ == "__main__":
    unittest.main()

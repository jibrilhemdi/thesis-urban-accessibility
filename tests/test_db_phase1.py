"""Offline provenance checks and opt-in live PostGIS smoke tests."""

import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text

from src.db.connection import database_settings, get_engine
from src.db.migrations import REQUIRED_SCHEMAS, database_check, migrate
from src.db.raw_csv import _csv_rows, ingest_csv
from src.db.sources import prepare_all_sources, prepare_source, register_records
from src.ingestion.common import PROJECT_ROOT, sha256_file


SAMPLE = Path("data/raw/inside_airbnb/copenhagen/2026-06-30/visualisations/neighbourhoods.csv")


class SourcePreparationTest(unittest.TestCase):
    def test_all_local_raw_files_verify_without_mutation(self) -> None:
        if not (PROJECT_ROOT / "data/raw/inside_airbnb").exists():
            self.skipTest("Local raw archive is unavailable")
        records = prepare_all_sources()
        original_archive = [record for record in records if not record["relative_path"].startswith((
            "data/raw/official_boundaries/", "data/raw/official_map_context/", "data/raw/osm/phase05/"))]
        self.assertEqual(len(original_archive), 49)
        phase5_archive = [record for record in records if record["relative_path"].startswith(
            "data/raw/osm/phase05/")]
        if phase5_archive:
            self.assertEqual(len(phase5_archive), 3)
            self.assertTrue(all(record["source_url"] for record in phase5_archive))
        official_archive = [record for record in records if record["relative_path"].startswith(
            "data/raw/official_boundaries/")]
        self.assertGreaterEqual(len(official_archive), 4)
        self.assertTrue(all(record["source_url"] for record in official_archive
                            if record["filename"].endswith(".geojson")))
        map_context_archive = [record for record in records if record["relative_path"].startswith(
            "data/raw/official_map_context/")]
        self.assertGreaterEqual(len(map_context_archive), 2)
        self.assertTrue(all(record["source_url"] for record in map_context_archive
                            if record["filename"].endswith(".geojson")))
        self.assertEqual(len({record["relative_path"] for record in records}), len(records))
        self.assertTrue(all(len(record["file_hash_sha256"]) == 64 for record in records))
        self.assertTrue(any(record["relative_path"].endswith("snapshot_metadata.json") for record in records))

    def test_manifest_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / SAMPLE
            path.parent.mkdir(parents=True)
            path.write_text("neighbourhood\nExample\n", encoding="utf-8")
            record = {"local_path": SAMPLE.as_posix(), "sha256": "0" * 64,
                      "size_bytes": path.stat().st_size}
            with self.assertRaisesRegex(ValueError, "differs from manifest"):
                prepare_source(path, project_root=root, manifest={SAMPLE.as_posix(): record})
            record["sha256"] = sha256_file(path)
            prepared = prepare_source(path, project_root=root, manifest={SAMPLE.as_posix(): record})
            self.assertEqual(prepared["snapshot_date"].isoformat(), "2026-06-30")

    def test_headerless_csv_retains_first_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_text("first,1\nsecond,2\n", encoding="utf-8")
            columns, rows, handle = _csv_rows(path, encoding="utf-8", delimiter=",", header=False)
            try:
                self.assertEqual(columns, ["field_1", "field_2"])
                self.assertEqual(list(rows), [["first", "1"], ["second", "2"]])
            finally:
                handle.close()


@unittest.skipUnless(os.environ.get("THESIS_DB_TEST") == "1", "Set THESIS_DB_TEST=1 for live DB tests")
class LiveDatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = database_settings()
        cls.engine = get_engine()
        with cls.engine.connect() as conn:
            if conn.scalar(text("SELECT current_database()")) != cls.settings["DB_NAME"]:
                raise RuntimeError("Test DB_NAME mismatch")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def test_connection_postgis_schemas_and_idempotent_migrations(self) -> None:
        migrate(self.engine)
        self.assertEqual(migrate(self.engine), [])
        checked = database_check(self.engine, self.settings["DB_NAME"])
        self.assertEqual(set(checked["schemas"]), set(REQUIRED_SCHEMAS))
        self.assertTrue(checked["postgis_version"])
        self.assertGreaterEqual(checked["applied_migrations"], 3)

    def test_registration_and_sample_import_are_idempotent(self) -> None:
        migrate(self.engine)
        prepared = prepare_source(PROJECT_ROOT / SAMPLE, manifest={})
        first_id = register_records(self.engine, [prepared])[0]
        second_id = register_records(self.engine, [prepared])[0]
        self.assertEqual(first_id, second_id)
        first = ingest_csv(self.engine, SAMPLE, "inside_airbnb_neighbourhoods")
        self.assertIn(first["status"], ("success", "already_imported"))
        second = ingest_csv(self.engine, SAMPLE, "inside_airbnb_neighbourhoods")
        self.assertEqual(second["status"], "already_imported")
        with self.engine.connect() as conn:
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM raw.inside_airbnb_neighbourhoods WHERE _source_file_id = :id"
            ), {"id": first_id}), 11)
            self.assertEqual(conn.scalar(text(
                "SELECT row_count FROM meta.source_files WHERE source_file_id = :id"
            ), {"id": first_id}), 11)
            self.assertEqual(conn.scalar(text(
                "SELECT count(*) FROM raw.inside_airbnb_neighbourhoods "
                "WHERE _source_file_id = :id AND neighbourhood_group = ''"
            ), {"id": first_id}), 11)


if __name__ == "__main__":
    unittest.main()

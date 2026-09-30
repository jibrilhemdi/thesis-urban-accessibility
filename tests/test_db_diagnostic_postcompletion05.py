"""Read-only checks for the explicit thesis-database diagnostic."""

from __future__ import annotations

import json
import os
import unittest

from src.db.connection import database_settings
from src.db.diagnose import authoritative


@unittest.skipUnless(os.environ.get("THESIS_DB_TEST") == "1", "Set THESIS_DB_TEST=1 for live DB tests")
class LiveDiagnosticTest(unittest.TestCase):
    def test_thesis_endpoint_integrity_and_secret_redaction(self) -> None:
        result = authoritative()
        settings = database_settings()
        self.assertTrue(result["compose_connection_matches"])
        self.assertEqual(result["connection"]["name"], settings["DB_NAME"])
        self.assertEqual(result["connection"]["user"], settings["DB_USER"])
        self.assertEqual(result["server"]["database"], settings["DB_NAME"])
        self.assertEqual(set(result["expected_schemas"]), set(result["present_schemas"]))
        self.assertGreater(result["row_counts"]["analysis.analysis_dataset_v1"], 0)
        self.assertEqual(result["feature_coverage"]["listings"],
                         result["feature_coverage"]["euclidean_rows"])
        self.assertEqual(result["feature_coverage"]["listings"],
                         result["feature_coverage"]["walking_rows"])
        self.assertTrue(all(item["duplicate_keys"] == 0
                            for item in result["key_uniqueness"].values()))
        self.assertTrue(all(item["invalid"] == 0 and item["wrong_srid"] == 0
                            for item in result["geometry_qa"].values()))
        self.assertEqual(result["spatial_operations"]["reference_transform_srid"], 25832)
        self.assertNotIn(settings["DB_PASSWORD"], json.dumps(result))


if __name__ == "__main__":
    unittest.main()

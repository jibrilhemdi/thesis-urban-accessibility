"""Scientific-v1 provenance and presentation-separation integrity checks."""

from __future__ import annotations

import json
import os
import unittest

from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline.create_scientific_freeze import _database_state, _science_path
from src.pipeline.run_final_presentation import RELEASE, verify_science


class ScientificFreezeFilesTests(unittest.TestCase):
    def test_release_manifest_and_immutable_scientific_files(self):
        manifest = json.loads((RELEASE / "scientific_manifest.json").read_text())
        self.assertEqual(manifest["primary_sample_n"], 12412)
        self.assertEqual(manifest["analysis_area_count"], 11)
        self.assertEqual(manifest["schema_migration_count"], 17)
        self.assertEqual(manifest["cv_assignment_rows"], 23144)
        self.assertEqual(manifest["canonical_destination_counts"],
                         {"food_social": 3006, "cultural_tourist": 463, "station": 143})
        self.assertFalse(manifest["scientific_results_mutable"])
        self.assertTrue(manifest["presentation_outputs_mutable"])
        self.assertEqual(verify_science(), manifest["scientific_file_count"])
        for relative, digest in manifest["scientific_file_sha256"].items():
            self.assertEqual(sha256_file(RELEASE / relative), digest)
            self.assertTrue(_science_path(PROJECT_ROOT / relative), relative)
        self.assertFalse(any(path.startswith("outputs/figures/") for path in
                             manifest["scientific_file_sha256"]))

    def test_public_release_has_no_private_source_rows_or_packaging_debris(self):
        names = [path.relative_to(RELEASE).as_posix() for path in RELEASE.rglob("*") if path.is_file()]
        self.assertFalse(any(name.startswith(("data/raw/", "data/interim/", "data/processed/"))
                             or name == ".env" or "__MACOSX/" in name or "/._" in name
                             or name.endswith((".aux", ".log", ".out", ".toc"))
                             for name in names))
        self.assertIn("SCIENTIFIC_FREEZE.md", names)
        self.assertIn("outputs/latex/main_tables.tex", names)
        self.assertIn("outputs/figures/final/figure4_catchment_example.png", names)


@unittest.skipUnless(os.environ.get("THESIS_SCIENTIFIC_FREEZE_TEST") == "1", "live DB opt-in")
class LiveScientificFreezeTests(unittest.TestCase):
    def test_database_identity_sample_sources_and_cv_match_manifest(self):
        saved = json.loads((RELEASE / "scientific_manifest.json").read_text())
        live = _database_state()
        for key in ("authoritative_database", "database_host", "database_port",
                    "schema_migration_count", "primary_sample_n", "analysis_area_count",
                    "cv_assignment_rows", "cv_assignments_sha256", "phase9_freeze_sha256",
                    "official_cv_area_geometry_sha256", "canonical_destination_counts"):
            self.assertEqual(live[key], saved[key], key)
        self.assertEqual(live["source_file_registry"], saved["source_file_registry"])


if __name__ == "__main__":
    unittest.main()

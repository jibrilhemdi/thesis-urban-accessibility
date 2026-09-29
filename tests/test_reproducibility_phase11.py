"""Safety and dependency-order checks for the guarded Phase 11 rebuild."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pipeline import rebuild_phase11
from src.pipeline.migrate_output_layout import destination
from src.pipeline.output_paths import output_file


class RebuildSafetyTest(unittest.TestCase):
    def test_phase_output_paths_have_short_basenames_and_no_collision(self):
        self.assertEqual(output_file("tables", "phase09", "phase09_model_performance.csv"),
                         output_file("tables", "phase09", "model_performance.csv"))
        self.assertNotEqual(output_file("tables", "phase09", "model_performance.csv"),
                            output_file("tables", "phase10", "model_performance.csv"))
        self.assertEqual(destination("tables", "sample_construction.csv"),
                         output_file("tables", "phase02", "sample_construction.csv"))
        with self.assertRaises(ValueError):
            output_file("tables", "phase09", "../secret.csv")

    def test_existing_output_refuses_rebuild_before_database_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outputs/tables").mkdir(parents=True)
            (root / "outputs/figures").mkdir()
            (root / "outputs/tables/phase09").mkdir()
            (root / "outputs/tables/phase09/model_performance.csv").touch()
            with patch.object(rebuild_phase11, "PROJECT_ROOT", root), \
                 patch.object(rebuild_phase11, "get_engine") as engine:
                with self.assertRaisesRegex(RuntimeError, "fresh checkout"):
                    rebuild_phase11.require_fresh_destination()
                engine.assert_not_called()

    def test_phase_order_preserves_frozen_model_dependency(self):
        modules = [step[0] for step in rebuild_phase11.STEPS]
        self.assertLess(modules.index("src.pipeline.run_airbnb_phase2"),
                        modules.index("src.pipeline.run_euclidean_phase5"))
        self.assertLess(modules.index("src.pipeline.run_walking_phase6"),
                        modules.index("src.pipeline.run_analysis_phase8"))
        self.assertLess(modules.index("src.pipeline.run_analysis_phase8"),
                        modules.index("src.pipeline.run_analysis_phase9"))
        self.assertLess(modules.index("src.pipeline.run_analysis_phase9"),
                        modules.index("src.pipeline.run_analysis_phase10"))
        self.assertEqual(modules[-1], "src.pipeline.audit_reproducibility_phase11")


if __name__ == "__main__":
    unittest.main()

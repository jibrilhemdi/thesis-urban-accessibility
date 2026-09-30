"""Presentation-only checks against saved RQ2 context comparison values."""

from __future__ import annotations

import csv
import unittest

from src.pipeline.export_rq2_context_panel import DEST, MARKDOWN, ROOT, build_rows


class RQ2ContextPresentationTests(unittest.TestCase):
    def test_panel_copies_existing_saved_values(self):
        with DEST.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows, build_rows())
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["N"] for row in rows}, {"12412"})

    def test_core_role_and_chronology_are_explicit(self):
        claims = (ROOT / "docs/final_claims_for_thesis.md").read_text()
        placement = (ROOT / "docs/output_placement_plan.md").read_text()
        manifest = (ROOT / "docs/final_output_manifest.md").read_text()
        resolution = (ROOT / "reports/pre_freeze_resolution.md").read_text()
        panel = MARKDOWN.read_text()
        for document in (claims, placement, manifest, resolution, panel):
            self.assertIn("area-context-adjusted core", document.lower())
            self.assertIn("Phase 9", document)
        self.assertIn("post-phase-9 implementation", claims.lower())
        self.assertIn("Core RQ2 panel", placement)
        self.assertIn("Core RQ2 context figure", manifest)


if __name__ == "__main__":
    unittest.main()

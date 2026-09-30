"""Read-only checks for final claim synthesis and output completeness."""

from __future__ import annotations

import csv
import re
import unittest

from src.pipeline.export_pre_freeze_claims import DEST, ROOT, build, read, verify_outputs


class PreFreezeScientificAuditTests(unittest.TestCase):
    def test_saved_outputs_complete(self):
        verify_outputs()

    def test_claims_match_saved_aggregates(self):
        expected = build()
        with DEST.open(newline="", encoding="utf-8") as stream:
            actual = list(csv.DictReader(stream))
        self.assertEqual(actual, expected)
        self.assertEqual([row["claim_id"] for row in actual], [f"C{i}" for i in range(1, 8)])
        self.assertEqual({row["status"] for row in actual}, {"SUPPORTED", "NOT SUPPORTED"})

    def test_no_new_model_output_is_created(self):
        # The producer consumes aggregate metrics and has no database/model imports.
        from src.pipeline import export_pre_freeze_claims as producer

        self.assertEqual(len(read(producer.TABLES / "final/table_validation_performance.csv")), 5)
        self.assertEqual(len(build()), 7)

    def test_internal_report_links_exist(self):
        for relative in (
            "docs/final_claims_for_thesis.md",
            "docs/deviations_from_preanalysis.md",
            "reports/pre_freeze_resolution.md",
        ):
            path = ROOT / relative
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if target.startswith(("http:", "https:")):
                    continue
                linked = (path.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(linked.exists(), f"{relative}: {target}")


if __name__ == "__main__":
    unittest.main()

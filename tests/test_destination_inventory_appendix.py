"""QA of the documentation-only frozen canonical OSM destination export."""

from __future__ import annotations

import csv
import os
import unittest
from collections import Counter

from src.pipeline.export_destination_inventory_appendix import (
    FINAL, GROUPS, LATEX, ROOT, SUPPLEMENT, read_database, validate,
)


def read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


class DestinationInventoryTests(unittest.TestCase):
    def test_saved_counts_reconcile(self):
        phase5 = {r["category"]: int(r["canonical_n"])
                  for r in read(ROOT / "outputs/tables/phase05/destination_counts.csv")}
        files = {
            "food_social": SUPPLEMENT / "destination_inventory_food_social.csv",
            "cultural_tourist": SUPPLEMENT / "destination_inventory_cultural_tourist.csv",
            "station": SUPPLEMENT / "destination_inventory_rail_metro.csv",
        }
        summary = read(FINAL / "appendix_destination_counts.csv")
        total = {r["destination_group"]: int(r["total"]) for r in summary
                 if r["OSM subtype"] == "ALL SUBTYPES"}
        self.assertEqual(total, phase5)
        all_keys = []
        for group in GROUPS:
            rows = read(files[group])
            self.assertEqual(len(rows), phase5[group])
            key = "canonical_station_id" if group == "station" else "canonical_destination_id"
            ids = [r[key] for r in rows]
            self.assertEqual(len(ids), len(set(ids)))
            all_keys.extend(ids)
            self.assertEqual({r["taxonomy_version"] for r in rows}, {"phase05_v2"})
            self.assertEqual({r["destination_group"] for r in rows}, {group})
            for row in rows:
                self.assertIn(row["inside_study_union"], {"True", "False"})
                if group == "station":
                    self.assertEqual(row["inside_study_union"] == "True",
                                     row["municipality_or_external_status"] in {"København", "Frederiksberg"})
        self.assertEqual(len(all_keys), len(set(all_keys)))
        self.assertEqual(len(all_keys), 3612)
        for group in GROUPS:
            subtype_rows = [r for r in summary if r["destination_group"] == group
                            and r["OSM subtype"] != "ALL SUBTYPES"]
            self.assertEqual(sum(int(r["total"]) for r in subtype_rows), phase5[group])
            self.assertTrue(all(int(r["total"]) == int(r["inside Copenhagen–Frederiksberg study union"])
                                + int(r["outside Copenhagen–Frederiksberg study union"])
                                for r in subtype_rows))

    def test_public_data_only_and_station_copy(self):
        files = list(SUPPLEMENT.glob("destination_inventory_*.csv"))
        self.assertEqual(len(files), 3)
        for path in files:
            columns = set(read(path)[0])
            self.assertFalse(columns & {"listing_id", "host_id", "host_name", "price_nightly", "log_price"})
            self.assertTrue({"longitude", "latitude", "all_source_osm_refs"} <= columns)
        self.assertEqual(read(FINAL / "appendix_destination_rail_metro.csv"),
                         read(SUPPLEMENT / "destination_inventory_rail_metro.csv"))
        modes = Counter(r["mode"] for r in read(FINAL / "appendix_destination_rail_metro.csv"))
        self.assertEqual(modes, {"metro": 37, "urban_rail": 101, "rail": 5})

    def test_examples_and_latex_placement(self):
        examples = read(FINAL / "appendix_destination_examples.csv")
        self.assertLessEqual(len(examples), 36)
        grouped = Counter((r["Destination group"], r["OSM subtype"]) for r in examples)
        self.assertTrue(all(n <= 3 for n in grouped.values()))
        for group in ("food_social", "cultural_tourist"):
            inventory = read(SUPPLEMENT / f"destination_inventory_{group}.csv")
            for subtype in {r["osm_subtype"] for r in inventory}:
                eligible = [r for r in inventory if r["osm_subtype"] == subtype and r["canonical_name"]]
                chosen = sorted(eligible, key=lambda r: (r["canonical_name"].casefold(),
                                                         r["canonical_destination_id"]))[:3]
                actual = [r["Canonical destination ID"] for r in examples
                          if r["Destination group"] == group and r["OSM subtype"] == subtype]
                self.assertEqual(actual, [r["canonical_destination_id"] for r in chosen])
        for stem in ("destination_taxonomy", "destination_counts", "destination_examples",
                     "destination_rail_metro_full"):
            self.assertTrue((LATEX / f"{stem}.tex").is_file())
            self.assertIn(f"{stem}.tex", (ROOT / "outputs/latex/appendix_tables.tex").read_text())
        self.assertNotIn("destination_inventory_food_social.csv", (ROOT / "outputs/latex/appendix_tables.tex").read_text())


@unittest.skipUnless(os.environ.get("THESIS_DESTINATION_INVENTORY_TEST") == "1", "live DB opt-in")
class LiveDestinationInventoryTests(unittest.TestCase):
    def test_exact_postgis_canonical_and_snaps(self):
        canonical, meta = read_database()
        self.assertEqual(validate(canonical, meta),
                         {"food_social": 3006, "cultural_tourist": 463, "station": 143})


if __name__ == "__main__":
    unittest.main()

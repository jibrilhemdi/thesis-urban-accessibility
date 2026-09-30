"""Presentation-only checks for the public-OSM boundary illustration."""

from __future__ import annotations

import hashlib
import json
import os
import unittest

from src.pipeline.export_boundary_catchment_figure import (
    ANCHOR_STATION, EXPECTED_NODE, FIGURE, METADATA, ROOT, load_public_geography,
)


class BoundaryCatchmentFigureTests(unittest.TestCase):
    def test_metadata_and_original_figure_are_unchanged(self):
        data = json.loads(METADATA.read_text(encoding="utf-8"))
        self.assertEqual(data["origin_public_osm_node_id"], EXPECTED_NODE)
        self.assertEqual(data["anchor_canonical_station_key"], ANCHOR_STATION)
        self.assertEqual(data["taxonomy_version"], "phase05_v2")
        self.assertEqual(data["crs_epsg"], 25832)
        self.assertEqual(data["radius_m"], 800)
        self.assertEqual((data["poi_within_circle"], data["poi_retained_inside_union"],
                          data["poi_excluded_outside_union"]), (22, 4, 18))
        self.assertEqual(sum(v["inside"] for v in data["poi_by_category"].values()), 4)
        self.assertEqual(sum(v["outside"] for v in data["poi_by_category"].values()), 18)
        self.assertEqual(data["stations_within_circle"], {"inside": 1, "outside": 0})
        self.assertTrue(FIGURE.is_file())
        self.assertGreater(FIGURE.stat().st_size, 50_000)
        original = ROOT / "outputs/figures/final/figure4_catchment_example.png"
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),
                         "a974303b55f1bcfe6ed806ab4b1d214429b3b9a80d617e5b2b7e80ff657e473a")
        self.assertFalse(any("airbnb" in table.lower() or "listing" in table.lower()
                             for table in data["source_tables"]))

    def test_appendix_caption_and_placement(self):
        figure_path = FIGURE.relative_to(ROOT).as_posix()
        captions = (ROOT / "docs/final_figure_captions.md").read_text()
        manifest = (ROOT / "docs/final_output_manifest.md").read_text()
        placement = (ROOT / "docs/output_placement_plan.md").read_text()
        self.assertIn("Destination-boundary catchment (Appendix)", captions)
        self.assertIn("no route is shown or clipped", captions)
        self.assertIn(f"`{figure_path}` | APPENDIX ONLY | APPENDIX", manifest)
        self.assertIn(f"`{figure_path}` | APPENDIX", placement)
        self.assertIn("Keep the original main-text Figure 4 unchanged", placement)


@unittest.skipUnless(os.environ.get("THESIS_BOUNDARY_CATCHMENT_TEST") == "1", "live DB opt-in")
class LiveBoundaryCatchmentFigureTests(unittest.TestCase):
    def test_live_public_endpoint_reconciliation(self):
        node, polygon, pois, stations = load_public_geography()
        self.assertEqual(node["osm_node_id"], EXPECTED_NODE)
        self.assertIn(polygon["type"], {"Polygon", "MultiPolygon"})
        self.assertEqual((len(pois), sum(p["inside"] for p in pois)), (22, 4))
        self.assertEqual((len(stations), sum(s["inside"] for s in stations)), (1, 1))


if __name__ == "__main__":
    unittest.main()

"""Illustrate the frozen destination-endpoint boundary sensitivity, without routing.

Only public OSM destination/node coordinates and the saved official municipal
union are read from PostGIS. No listing, feature, price, or model table is used.
Run: .venv/bin/python -m src.pipeline.export_boundary_catchment_figure
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from sqlalchemy import text

from src.db.connection import get_engine
from src.pipeline.osm_taxonomy_phase5 import TAXONOMY_VERSION
from src.pipeline.run_official_geography_phase4 import _rings


ROOT = Path(__file__).resolve().parents[2]
FIGURE = ROOT / "outputs/figures/final/appendix_boundary_catchment_example.png"
METADATA = ROOT / "outputs/tables/final/appendix_boundary_catchment_metadata.json"
REPORT = ROOT / "reports/appendix_boundary_catchment_figure.md"
ANCHOR_STATION = "phase05_v2:station:node:598201521"  # Hellerup, public OSM station
EXPECTED_NODE = 11247216821  # nearest saved Phase 6 node to the public station
RADIUS_M = 800.0
INK = "#29485B"
TEAL = "#5D9D8C"
CORAL = "#D7957E"
BLUE = "#779DB9"
PURPLE = "#A08BB7"
GREY = "#ACB9B9"


def load_public_geography() -> tuple[dict, dict, list[dict], list[dict]]:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            anchor = conn.execute(text(
                "SELECT station_key,name,source_file_id,taxonomy_version,"
                "ST_X(geom_25832) AS x,ST_Y(geom_25832) AS y "
                "FROM spatial.transit_stations WHERE station_key=:key"
            ), {"key": ANCHOR_STATION}).mappings().one()
            if anchor["taxonomy_version"] != TAXONOMY_VERSION or anchor["name"] != "Hellerup":
                raise ValueError("Hellerup canonical station changed from frozen Phase 5")
            network = conn.execute(text(
                "SELECT network_id,source_file_id FROM spatial.walking_networks "
                "ORDER BY built_at DESC LIMIT 1"
            )).mappings().one()
            if network["source_file_id"] != anchor["source_file_id"]:
                raise ValueError("Station and saved walking network use different OSM archives")
            node = dict(conn.execute(text(
                "SELECT osm_node_id,ST_X(geom_25832) AS x,ST_Y(geom_25832) AS y,"
                "ST_SRID(geom_25832) AS crs," 
                "ST_Distance(geom_25832,ST_SetSRID(ST_MakePoint(:sx,:sy),25832)) AS station_offset_m "
                "FROM spatial.walking_nodes WHERE network_id=:network "
                "ORDER BY geom_25832 <-> ST_SetSRID(ST_MakePoint(:sx,:sy),25832) LIMIT 1"
            ), {"network": network["network_id"], "sx": anchor["x"], "sy": anchor["y"]}).mappings().one())
            if node["osm_node_id"] != EXPECTED_NODE or node["crs"] != 25832 or node["station_offset_m"] > 100:
                raise ValueError("Illustrative public origin no longer matches saved Phase 6 graph")
            ox, oy = float(node["x"]), float(node["y"])
            params = {"x": ox, "y": oy, "radius": RADIUS_M}
            union = conn.execute(text(
                "SELECT ST_IsValid(u.geom_25832) AS valid,ST_SRID(u.geom_25832) AS crs,"
                "ST_AsGeoJSON(ST_Intersection(u.geom_25832,"
                "ST_MakeEnvelope(:x-900,:y-900,:x+900,:y+900,25832)),3) AS clipped_geojson "
                "FROM spatial.study_union_boundary_sensitivity u"
            ), params).mappings().one()
            if not union["valid"] or union["crs"] != 25832 or not union["clipped_geojson"]:
                raise ValueError("Official study union invalid or does not intersect illustration")
            polygon = json.loads(union["clipped_geojson"])
            if polygon["type"] not in {"Polygon", "MultiPolygon"}:
                raise ValueError("Expected polygonal official-study-union intersection")
            poi_sql = (
                "SELECT p.destination_key,p.category,p.taxonomy_version,"
                "ST_X(p.geom_25832) AS x,ST_Y(p.geom_25832) AS y,"
                "ST_Covers(u.geom_25832,p.geom_25832) AS inside "
                "FROM spatial.osm_pois p CROSS JOIN spatial.study_union_boundary_sensitivity u "
                "WHERE ST_DWithin(p.geom_25832,ST_SetSRID(ST_MakePoint(:x,:y),25832),:radius) "
                "ORDER BY p.category,p.destination_key"
            )
            pois = [dict(r) for r in conn.execute(text(poi_sql), params).mappings()]
            station_sql = (
                "SELECT s.station_key,s.name,s.station_mode,s.taxonomy_version,"
                "ST_X(s.geom_25832) AS x,ST_Y(s.geom_25832) AS y,"
                "ST_Covers(u.geom_25832,s.geom_25832) AS inside "
                "FROM spatial.transit_stations s CROSS JOIN spatial.study_union_boundary_sensitivity u "
                "WHERE ST_DWithin(s.geom_25832,ST_SetSRID(ST_MakePoint(:x,:y),25832),:radius) "
                "ORDER BY s.station_key"
            )
            stations = [dict(r) for r in conn.execute(text(station_sql), params).mappings()]
            conn.rollback()
    finally:
        engine.dispose()
    if not pois or not any(p["inside"] for p in pois) or not any(not p["inside"] for p in pois):
        raise ValueError("The frozen Hellerup illustration no longer spans retained and excluded POIs")
    if any(p["taxonomy_version"] != TAXONOMY_VERSION for p in pois + stations):
        raise ValueError("Illustrative destinations do not match frozen Phase 5 taxonomy")
    if len({p["destination_key"] for p in pois}) != len(pois) or \
            len({s["station_key"] for s in stations}) != len(stations):
        raise ValueError("Repeated canonical destination in illustration")
    return node, polygon, pois, stations


def draw(node: dict, polygon: dict, pois: list[dict], stations: list[dict]) -> None:
    ox, oy = float(node["x"]), float(node["y"])
    inside = sum(bool(p["inside"]) for p in pois)
    outside = len(pois)-inside
    fig, axes = plt.subplots(1, 2, figsize=(13.3, 7.4), dpi=200, sharex=True, sharey=True)
    fig.patch.set_facecolor("white")
    for i, ax in enumerate(axes):
        ax.set_facecolor("#F5F6F4")
        _rings(ax, polygon, fill="#E6F0E8", edge="#547C74", linewidth=1.7)
        ax.add_patch(Circle((ox, oy), RADIUS_M, fill=False, edgecolor="#849BA0",
                            linestyle=(0, (5, 3)), linewidth=1.4, zorder=4))
        for category, marker, color in (("food_social", "o", CORAL),
                                        ("cultural_tourist", "^", BLUE)):
            retained = [p for p in pois if p["category"] == category and p["inside"]]
            external = [p for p in pois if p["category"] == category and not p["inside"]]
            if retained:
                ax.scatter([p["x"] for p in retained], [p["y"] for p in retained],
                           s=55, marker=marker, color=color, edgecolor=INK, linewidth=.45, zorder=6)
            if external:
                if i == 0:
                    ax.scatter([p["x"] for p in external], [p["y"] for p in external],
                               s=55, marker=marker, facecolor=color, edgecolor="white",
                               linewidth=.6, zorder=6)
                else:
                    ax.scatter([p["x"] for p in external], [p["y"] for p in external],
                               s=42, marker="x", color=GREY, linewidth=1.3, zorder=6)
        for station in stations:
            if i == 0 or station["inside"]:
                ax.scatter([station["x"]], [station["y"]], marker="D", s=88,
                           color=PURPLE if station["inside"] else GREY,
                           edgecolor=INK, linewidth=.55, zorder=7)
            else:
                ax.scatter([station["x"]], [station["y"]], marker="x", s=60,
                           color=GREY, linewidth=1.3, zorder=7)
        ax.scatter([ox], [oy], marker="*", s=245, color="#E2BB72", edgecolor=INK,
                   linewidth=.8, zorder=8)
        ax.set_xlim(ox-900, ox+900)
        ax.set_ylim(oy-900, oy+900)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color("#B9CBC7")
        ax.text(.82, .08, "STUDY UNION", transform=ax.transAxes, ha="center", va="center",
                fontsize=8.5, color="#366A60", fontweight="bold",
                bbox=dict(facecolor="white", alpha=.86, edgecolor="none", pad=3))
        ax.text(.97, .97, "OUTSIDE UNION", transform=ax.transAxes, ha="right", va="top",
                fontsize=8.5, color="#7D8B8C", fontweight="bold",
                bbox=dict(facecolor="white", alpha=.86, edgecolor="none", pad=3))
        ax.plot([ox-780, ox-280], [oy-780, oy-780], color=INK, lw=2.1, zorder=10)
        ax.text(ox-530, oy-740, "500 m", ha="center", va="bottom", fontsize=8, color=INK)
    axes[0].set_title(f"A · Buffered primary: {len(pois)} POIs", loc="left", fontsize=12, color=INK)
    axes[1].set_title(f"B · Union endpoints only: {inside} POIs", loc="left", fontsize=12, color=INK)
    handles = [
        Line2D([], [], marker="*", linestyle="", markerfacecolor="#E2BB72", markeredgecolor=INK,
               markersize=12, label="Public OSM-node origin"),
        Line2D([], [], marker="o", linestyle="", color=CORAL, markersize=7, label="Food/social POI"),
        Line2D([], [], marker="^", linestyle="", color=BLUE, markersize=7, label="Cultural/tourist POI"),
        Line2D([], [], marker="D", linestyle="", color=PURPLE, markersize=7, label="Rail station"),
        Line2D([], [], marker="x", linestyle="", color=GREY, markersize=7,
               label="Outside endpoint excluded in B"),
        Line2D([], [], color="#547C74", linewidth=2, label="Study-union boundary"),
    ]
    fig.legend(handles=handles, ncol=3, loc="lower center", bbox_to_anchor=(.5, .045),
               frameon=False, fontsize=8.5)
    fig.suptitle("Destination boundary: same place, different eligible endpoints",
                 fontsize=15, color=INK, y=.985)
    fig.text(.5, .135,
             f"Illustrative public node beside Hellerup station; {inside} POIs lie in/on Copenhagen–Frederiksberg, {outside} lie outside. "
             "Grey crosses in B are shown for comparison but not counted.\n"
             "Both panels use the same 800 m straight-line circle; walking routes are not clipped or depicted. "
             "No Airbnb point is shown. EPSG:25832.",
             ha="center", va="center", fontsize=8.1, color=INK)
    fig.subplots_adjust(top=.84, bottom=.24, left=.025, right=.975, wspace=.045)
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    node, polygon, pois, stations = load_public_geography()
    draw(node, polygon, pois, stations)
    by_category = {category: {"inside": sum(p["category"] == category and p["inside"] for p in pois),
                              "outside": sum(p["category"] == category and not p["inside"] for p in pois)}
                   for category in ("food_social", "cultural_tourist")}
    by_station = {"inside": sum(s["inside"] for s in stations),
                  "outside": sum(not s["inside"] for s in stations)}
    metadata = {
        "figure": FIGURE.relative_to(ROOT).as_posix(),
        "origin_public_osm_node_id": node["osm_node_id"],
        "anchor_canonical_station_key": ANCHOR_STATION,
        "origin_rule": "nearest node in saved Phase 6 walking network to canonical Hellerup station",
        "node_to_station_m": round(float(node["station_offset_m"]), 3),
        "radius_m": int(RADIUS_M), "crs_epsg": 25832,
        "poi_within_circle": len(pois),
        "poi_retained_inside_union": sum(p["inside"] for p in pois),
        "poi_excluded_outside_union": sum(not p["inside"] for p in pois),
        "poi_by_category": by_category, "stations_within_circle": by_station,
        "source_tables": ["spatial.osm_pois", "spatial.transit_stations",
                          "spatial.study_union_boundary_sensitivity", "spatial.walking_nodes"],
        "endpoint_rule": "ST_Covers(official Copenhagen-Frederiksberg union, canonical endpoint)",
        "taxonomy_version": TAXONOMY_VERSION,
        "scope": "illustrative straight-line endpoint comparison only; no listing, route or model computation",
    }
    METADATA.parent.mkdir(parents=True, exist_ok=True)
    METADATA.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "# Appendix boundary-catchment illustration\n\n"
        "The separate [appendix figure](../outputs/figures/final/appendix_boundary_catchment_example.png) "
        "uses the same canonical Phase 5 `phase05_v2` POIs/stations and official EPSG:25832 two-municipality union "
        "as the [frozen endpoint sensitivity](pre_freeze_boundary_sensitivity.md). It does **not** replace "
        "main-text Figure 4, which illustrates straight-line versus walking-network reach.\n\n"
        f"The public anchor is saved Phase 6 OSM walking node `{node['osm_node_id']}`, selected as the nearest "
        f"node to canonical Hellerup station `{ANCHOR_STATION}` ({node['station_offset_m']:.1f} m away). "
        "This geography-only choice uses no Airbnb listing, price or fitted-model information. "
        f"Its fixed 800 m Euclidean circle contains **{len(pois)}** canonical POIs: "
        f"**{metadata['poi_retained_inside_union']}** in/on the official study union and "
        f"**{metadata['poi_excluded_outside_union']}** outside. "
        f"Food/social in/out = {by_category['food_social']['inside']}/{by_category['food_social']['outside']}; "
        f"cultural/tourist in/out = {by_category['cultural_tourist']['inside']}/{by_category['cultural_tourist']['outside']}. "
        f"Stations inside/outside this example circle = {by_station['inside']}/{by_station['outside']}; "
        "the nearby Hellerup station remains eligible in both panels. Grey crosses in panel B mark visible-but-excluded "
        "public OSM endpoints; they are not counted there.\n\n"
        "This is an **illustration of endpoint eligibility**, not the listing-level change distribution, a walking service-area calculation, "
        "or evidence of model improvement. The saved pedestrian network and its cross-border routes are not clipped. "
        "The matched model results and changed-listing counts remain in the boundary-sensitivity report. "
        "Only public OSM nodes, canonical POIs/stations and official boundary geometry are drawn. "
        f"Reproduce with `.venv/bin/python -m src.pipeline.export_boundary_catchment_figure`; metadata are in "
        f"`{METADATA.relative_to(ROOT)}`. No Phase 9 file or original Figure 4 was modified.\n",
        encoding="utf-8",
    )
    print(f"Saved {FIGURE.relative_to(ROOT)}: {len(pois)} POIs, "
          f"{metadata['poi_retained_inside_union']} retained, {metadata['poi_excluded_outside_union']} excluded")


if __name__ == "__main__":
    main()

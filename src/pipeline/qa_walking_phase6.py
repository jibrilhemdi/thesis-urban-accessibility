"""Private centre/barrier/periphery/border walking-vs-Euclidean spot checks."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import networkx as nx
from sqlalchemy import bindparam, text

from src.db.connection import get_engine
from src.pipeline.acquire_osm_phase5 import PBF_NAME, existing_archive
from src.pipeline.qa_euclidean_phase5 import _plot_geometry, inner_harbour_geometry
from src.spatial.walking_network import build_graph


def select_cases(conn, water: str) -> list[dict]:
    selected = []
    cases = (
        ("dense centre", "s.distance_centre_euclidean_km ASC", ""),
        ("harbour barrier", "(e.food_social_800m-w.food_social_w_10) DESC", 
         "AND ST_DWithin(l.geom_25832,ST_Boundary(ST_Transform("
         "ST_SetSRID(ST_GeomFromGeoJSON(:water),4326),25832)),350) "),
        ("periphery", "s.distance_centre_euclidean_km DESC", ""),
        ("municipal border", "s.distance_centre_euclidean_km ASC", "AND s.near_official_border_100m "),
    )
    for label, order_by, condition in cases:
        query = text(
            "SELECT l.listing_id,ST_X(l.geom_25832) AS x,ST_Y(l.geom_25832) AS y,"
            "e.food_social_800m,e.cultural_tourist_800m,e.nearest_station_distance_m,"
            "w.food_social_w_10,w.cultural_tourist_w_10,w.nearest_station_walking_minutes,"
            "a.snapped_node_id,a.snap_distance_m "
            "FROM clean.airbnb_listings l JOIN features.listing_spatial_base s "
            "USING(snapshot_date,listing_id) JOIN features.euclidean_accessibility e "
            "USING(snapshot_date,listing_id) JOIN features.walking_accessibility w "
            "USING(snapshot_date,listing_id) JOIN features.walking_listing_snaps a "
            "USING(snapshot_date,listing_id) WHERE l.primary_sample_candidate AND w.routing_status='ok' "
            + condition + "AND l.listing_id NOT IN :excluded ORDER BY " + order_by + " LIMIT 1"
        ).bindparams(bindparam("excluded", expanding=True))
        row = conn.execute(query, {"water": water, "excluded": [r["listing_id"] for r in selected] or [-1]}).mappings().one()
        selected.append({**row, "label": label})
    return selected


def validate_paths(graph, cases: list[dict], destinations: list[dict]) -> tuple[list[dict], dict]:
    by_node = {}
    for dest in destinations:
        by_node.setdefault(dest["snapped_node_id"], []).append(dest)
    summaries = []
    reached_by_case = {}
    for case in cases:
        origin = case["snapped_node_id"]
        source_snap = case["snap_distance_m"]
        reached = nx.single_source_dijkstra_path_length(
            graph, origin, cutoff=max(0, 1600-source_snap), weight="length_m")
        counts = {"food_social": 0, "cultural_tourist": 0}
        for node, route_m in reached.items():
            for dest in by_node.get(node, ()):
                if dest["category"] != "station" and source_snap + route_m + dest["snap_distance_m"] <= 800:
                    counts[dest["category"]] += 1
        if counts != {"food_social": case["food_social_w_10"],
                      "cultural_tourist": case["cultural_tourist_w_10"]}:
            raise AssertionError(f"NetworkX independent 800m recount differs in {case['label']}")
        # Verify no station beats the stored nearest time, including both connectors.
        recorded_m = case["nearest_station_walking_minutes"] * 80
        station_reach = nx.single_source_dijkstra_path_length(
            graph, origin, cutoff=recorded_m-source_snap+0.01, weight="length_m")
        candidate_station_m = min(
            (source_snap + route_m + dest["snap_distance_m"]
             for node, route_m in station_reach.items()
             for dest in by_node.get(node, ()) if dest["category"] == "station"),
            default=math.inf,
        )
        if abs(candidate_station_m-recorded_m) > 0.01:
            raise AssertionError(f"Nearest-station path differs in {case['label']}")
        reached_by_case[case["label"]] = reached
        summaries.append({
            "case": case["label"], "euclidean_food_800m": case["food_social_800m"],
            "walking_food_10min": counts["food_social"],
            "euclidean_culture_800m": case["cultural_tourist_800m"],
            "walking_culture_10min": counts["cultural_tourist"],
            "euclidean_station_m": round(case["nearest_station_distance_m"], 1),
            "walking_station_min": round(case["nearest_station_walking_minutes"], 1),
            "independent_route_check": "pass",
        })
    return summaries, reached_by_case


def private_map(conn, cases, destinations, reached_by_case, water, target: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    water_metric = json.loads(conn.scalar(text(
        "SELECT ST_AsGeoJSON(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:water),4326),25832))"
    ), {"water": water}))
    boundaries = [json.loads(g) for g in conn.execute(text(
        "SELECT ST_AsGeoJSON(geom_25832) FROM spatial.official_municipalities"
    )).scalars()]
    fig, axes = plt.subplots(2, 2, figsize=(11, 10), constrained_layout=True)
    for ax, case in zip(axes.flat, cases):
        x, y = case["x"], case["y"]
        for geometry in boundaries:
            _plot_geometry(ax, geometry, "#445266", fill=False)
        _plot_geometry(ax, water_metric, "#75b7d4", fill=True)
        reached = reached_by_case[case["label"]]
        for dest in destinations:
            if dest["category"] == "station" or math.hypot(dest["x"]-x, dest["y"]-y) > 800:
                continue
            walk_m = (case["snap_distance_m"] + reached[dest["snapped_node_id"]] + dest["snap_distance_m"]
                      if dest["snapped_node_id"] in reached else math.inf)
            color = "#2a8278" if walk_m <= 800 else "#d9754b"
            ax.scatter(dest["x"], dest["y"], s=7, color=color, alpha=0.62, zorder=2)
        ax.add_patch(plt.Circle((x, y), 800, fill=False, color="#252e38", linewidth=1, zorder=3))
        ax.scatter(x, y, s=100, marker="*", color="#f3c647", edgecolors="#252e38", zorder=5)
        ax.set_xlim(x-1600, x+1600)
        ax.set_ylim(y-1600, y+1600)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(case["label"])
    fig.suptitle("Private Phase 6 QA — green walk-reachable, orange straight-line-only; do not publish")
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-map", type=Path)
    args = parser.parse_args()
    water = inner_harbour_geometry()
    graph, *_ = build_graph(existing_archive() / PBF_NAME)
    engine = get_engine()
    try:
        with engine.connect() as conn:
            cases = select_cases(conn, water)
            destinations = [dict(row) for row in conn.execute(text(
                "SELECT s.destination_kind,s.destination_key,s.category,s.snapped_node_id,s.snap_distance_m,"
                "ST_X(COALESCE(p.geom_25832,t.geom_25832)) AS x,"
                "ST_Y(COALESCE(p.geom_25832,t.geom_25832)) AS y "
                "FROM spatial.walking_destination_snaps s "
                "LEFT JOIN spatial.osm_pois p ON s.destination_kind='poi' AND p.destination_key=s.destination_key "
                "LEFT JOIN spatial.transit_stations t ON s.destination_kind='station' AND t.station_key=s.destination_key"
            )).mappings()]
            summaries, reached = validate_paths(graph, cases, destinations)
            if args.private_map:
                private_map(conn, cases, destinations, reached, water, args.private_map)
        print(json.dumps(summaries, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

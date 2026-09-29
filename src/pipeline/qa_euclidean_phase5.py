"""Private, reproducible spot-check map; never publish listing-level coordinates."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from sqlalchemy import bindparam, text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.acquire_osm_phase5 import existing_archive


PBF = (existing_archive() or PROJECT_ROOT / "data/raw/osm/phase05/nonexistent") / "Copenhagen.osm.pbf"


def inner_harbour_geometry() -> str:
    command = ["ogr2ogr", "-f", "GeoJSONSeq", "/vsistdout/", str(PBF), "multipolygons",
               "-where", "natural='water' AND name='Inderhavnen'"]
    output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    features = [json.loads(line.lstrip("\x1e")) for line in output.splitlines() if line.strip()]
    if len(features) != 1:
        raise RuntimeError(f"Expected one OSM Inderhavnen water polygon, got {len(features)}")
    return json.dumps(features[0]["geometry"])


def select_cases(conn, water: str) -> list[dict]:
    chosen = []
    selectors = {
        "centre": "s.distance_centre_euclidean_km ASC",
        "periphery": "s.distance_centre_euclidean_km DESC",
        "harbour-side": "ST_Distance(l.geom_25832, ST_Boundary(ST_Transform("
                        "ST_SetSRID(ST_GeomFromGeoJSON(:water),4326),25832))) ASC",
        "municipal border": "ST_Distance(l.geom_25832,ST_Boundary(m.geom_25832)) ASC",
    }
    for label, ordering in selectors.items():
        join = "CROSS JOIN spatial.official_municipalities m" if label == "municipal border" else ""
        condition = "AND s.near_official_border_100m" if label == "municipal border" else ""
        row = conn.execute(text(
            "SELECT l.listing_id,ST_X(l.geom_25832) AS x,ST_Y(l.geom_25832) AS y,"
            "f.food_social_800m,f.food_social_1200m,f.food_social_1600m,"
            "f.cultural_tourist_800m,f.cultural_tourist_1200m,f.cultural_tourist_1600m,"
            "f.nearest_station_distance_m,f.source_edge_distance_m "
            "FROM clean.airbnb_listings l JOIN features.listing_spatial_base s "
            "USING(snapshot_date,listing_id) JOIN features.euclidean_accessibility f "
            "USING(snapshot_date,listing_id) " + join + " WHERE l.primary_sample_candidate " + condition +
            " AND l.listing_id NOT IN :excluded ORDER BY " + ordering + " LIMIT 1"
        ).bindparams(bindparam("excluded", expanding=True)),
            {"water": water, "excluded": [r["listing_id"] for r in chosen] or [-1]}).mappings().one()
        chosen.append({**row, "label": label})
    return chosen


def independently_validate(conn, cases: list[dict]) -> list[dict]:
    results = []
    for case in cases:
        result = dict(conn.execute(text(
            "WITH p AS (SELECT geom_25832 FROM clean.airbnb_listings "
            "WHERE snapshot_date='2026-06-30' AND listing_id=:id) "
            "SELECT (SELECT count(*) FROM spatial.osm_pois d,p WHERE d.category='food_social' "
            "AND ST_DWithin(d.geom_25832,p.geom_25832,800)) AS food800,"
            "(SELECT count(*) FROM spatial.osm_pois d,p WHERE d.category='food_social' "
            "AND ST_DWithin(d.geom_25832,p.geom_25832,1200)) AS food1200,"
            "(SELECT count(*) FROM spatial.osm_pois d,p WHERE d.category='food_social' "
            "AND ST_DWithin(d.geom_25832,p.geom_25832,1600)) AS food1600,"
            "(SELECT count(*) FROM spatial.osm_pois d,p WHERE d.category='cultural_tourist' "
            "AND ST_DWithin(d.geom_25832,p.geom_25832,800)) AS culture800,"
            "(SELECT count(*) FROM spatial.osm_pois d,p WHERE d.category='cultural_tourist' "
            "AND ST_DWithin(d.geom_25832,p.geom_25832,1200)) AS culture1200,"
            "(SELECT count(*) FROM spatial.osm_pois d,p WHERE d.category='cultural_tourist' "
            "AND ST_DWithin(d.geom_25832,p.geom_25832,1600)) AS culture1600,"
            "(SELECT min(ST_Distance(d.geom_25832,p.geom_25832)) "
            "FROM spatial.transit_stations d,p) AS station_m"
        ), {"id": case["listing_id"]}).mappings().one())
        expected = (case["food_social_800m"], case["food_social_1200m"],
                    case["food_social_1600m"], case["cultural_tourist_800m"],
                    case["cultural_tourist_1200m"], case["cultural_tourist_1600m"])
        actual = tuple(result[k] for k in ("food800", "food1200", "food1600",
                                            "culture800", "culture1200", "culture1600"))
        if actual != expected or abs(result["station_m"] - case["nearest_station_distance_m"]) > 1e-6:
            raise AssertionError(f"Independent spatial recount mismatch in {case['label']}")
        results.append({"case": case["label"], "food_800m": actual[0], "culture_800m": actual[3],
                        "station_distance_m": round(result["station_m"], 1),
                        "source_edge_distance_m": round(case["source_edge_distance_m"], 1),
                        "independent_recount": "pass"})
    return results


def _plot_geometry(ax, geometry: dict, color: str, *, fill: bool) -> None:
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        xs, ys = zip(*polygon[0])
        if fill:
            ax.fill(xs, ys, color=color, alpha=0.27, zorder=0)
        else:
            ax.plot(xs, ys, color=color, linewidth=0.7, alpha=0.8, zorder=1)


def private_map(conn, cases: list[dict], water: str, target: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    water_metric = json.loads(conn.scalar(text(
        "SELECT ST_AsGeoJSON(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:water),4326),25832))"
    ), {"water": water}))
    boundaries = [json.loads(value) for value in conn.execute(text(
        "SELECT ST_AsGeoJSON(geom_25832) FROM spatial.official_municipalities"
    )).scalars()]
    fig, axes = plt.subplots(2, 2, figsize=(11, 10), constrained_layout=True)
    for ax, case in zip(axes.flat, cases):
        x, y = case["x"], case["y"]
        for geometry in boundaries:
            _plot_geometry(ax, geometry, "#445266", fill=False)
        _plot_geometry(ax, water_metric, "#75b7d4", fill=True)
        dots = conn.execute(text(
            "SELECT category,ST_X(geom_25832),ST_Y(geom_25832) FROM spatial.osm_pois "
            "WHERE ST_DWithin(geom_25832,ST_SetSRID(ST_MakePoint(:x,:y),25832),1600)"
        ), {"x": x, "y": y}).all()
        for category, px, py in dots:
            ax.scatter(px, py, s=6, alpha=0.6,
                       color="#dc7848" if category == "food_social" else "#7b5ca7", zorder=2)
        station = conn.execute(text(
            "SELECT ST_X(geom_25832),ST_Y(geom_25832) FROM spatial.transit_stations "
            "ORDER BY geom_25832 <-> ST_SetSRID(ST_MakePoint(:x,:y),25832) LIMIT 1"
        ), {"x": x, "y": y}).one()
        ax.scatter(station[0], station[1], s=58, marker="s", color="#252e38", zorder=4)
        ax.scatter(x, y, s=90, marker="*", color="#e7bd34", edgecolors="#252e38", zorder=5)
        ax.add_patch(plt.Circle((x, y), 800, fill=False, color="#252e38", linewidth=1, zorder=3))
        ax.set_xlim(x-1700, x+1700)
        ax.set_ylim(y-1700, y+1700)
        ax.set_aspect("equal")
        ax.set_title(case["label"])
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Private Phase 5 QA — listing points must not be published")
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-map", type=Path, help="Write point-level QA image outside public outputs")
    args = parser.parse_args()
    water = inner_harbour_geometry()
    engine = get_engine()
    try:
        with engine.connect() as conn:
            cases = select_cases(conn, water)
            results = independently_validate(conn, cases)
            if args.private_map:
                private_map(conn, cases, water, args.private_map)
        print(json.dumps(results, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

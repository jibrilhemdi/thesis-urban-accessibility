"""Export aggregate-only Phase 6 diagnostics from authoritative PostGIS tables."""

from __future__ import annotations

import csv

from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.output_paths import PhaseDirectory
from src.pipeline.acquire_osm_phase5 import POLY_NAME, existing_archive, polygon_wkt


SUMMARY_COLUMNS = (
    ("nearest_station_network_distance_m", "metres"),
    ("nearest_station_walking_minutes", "minutes"),
    ("food_social_w_10", "count"), ("food_social_w_15", "count"),
    ("food_social_w_20", "count"), ("cultural_tourist_w_10", "count"),
    ("cultural_tourist_w_15", "count"), ("cultural_tourist_w_20", "count"),
)
COMPARISONS = (
    ("food_social", "food_social_800m", "food_social_w_10", 800),
    ("food_social", "food_social_1200m", "food_social_w_15", 1200),
    ("food_social", "food_social_1600m", "food_social_w_20", 1600),
    ("cultural_tourist", "cultural_tourist_800m", "cultural_tourist_w_10", 800),
    ("cultural_tourist", "cultural_tourist_1200m", "cultural_tourist_w_15", 1200),
    ("cultural_tourist", "cultural_tourist_1600m", "cultural_tourist_w_20", 1600),
)


def _float(value, places=2):
    return None if value is None else round(float(value), places)


def export() -> dict:
    target = PhaseDirectory("tables", "phase06")
    target.mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    try:
        source_wkt = polygon_wkt((existing_archive() / POLY_NAME).read_text(encoding="utf-8"))
        with engine.connect() as conn:
            network = dict(conn.execute(text(
                "SELECT network_id,node_count,source_segment_count,directed_arc_count,"
                "weak_component_count,largest_component_nodes,source_date "
                "FROM spatial.walking_networks"
            )).mappings().one())
            summary = []
            for column, unit in SUMMARY_COLUMNS:
                row = conn.execute(text(
                    f"SELECT count({column}) AS n,avg({column}) AS mean,"
                    f"count(*) FILTER (WHERE {column}=0) AS zero_n,max({column}) AS max_value,"
                    f"percentile_cont(ARRAY[0.05,0.25,0.5,0.75,0.95]) "
                    f"WITHIN GROUP (ORDER BY {column}) AS quantiles "
                    "FROM features.walking_accessibility"
                )).mappings().one()
                summary.append({"measure": column, "unit": unit, "n": row["n"],
                                "mean": _float(row["mean"]), "zero_n": row["zero_n"],
                                "max": _float(row["max_value"]),
                                **{key: _float(value) for key, value in zip(
                                    ("p05", "p25", "median", "p75", "p95"), row["quantiles"])} })
            comparison = []
            for category, euclidean, walking, radius in COMPARISONS:
                row = conn.execute(text(
                    f"SELECT count(w.{walking}) AS n,avg(e.{euclidean}) AS euclid_mean,"
                    f"avg(w.{walking}) AS walk_mean,"
                    f"percentile_cont(0.5) WITHIN GROUP (ORDER BY e.{euclidean}) AS euclid_median,"
                    f"percentile_cont(0.5) WITHIN GROUP (ORDER BY w.{walking}) AS walk_median,"
                    f"count(*) FILTER (WHERE w.{walking}<e.{euclidean}) AS walk_lower_n,"
                    f"count(*) FILTER (WHERE w.{walking}=e.{euclidean}) AS equal_n "
                    "FROM features.walking_accessibility w JOIN features.euclidean_accessibility e "
                    "USING(snapshot_date,listing_id)"
                )).mappings().one()
                comparison.append({"category": category, "radius_m": radius, "n": row["n"],
                                   "euclidean_mean": _float(row["euclid_mean"]),
                                   "walking_mean": _float(row["walk_mean"]),
                                   "euclidean_median": _float(row["euclid_median"]),
                                   "walking_median": _float(row["walk_median"]),
                                   "walking_lower_n": row["walk_lower_n"], "equal_n": row["equal_n"]})
            snaps = []
            for kind, table in (("listing", "features.walking_listing_snaps"),
                                ("poi", "spatial.walking_destination_snaps"),
                                ("station", "spatial.walking_destination_snaps")):
                where = ("WHERE destination_kind=:kind" if kind != "listing" else "")
                row = conn.execute(text(
                    "SELECT count(snap_distance_m) AS n,avg(snap_distance_m) AS mean,"
                    "count(*) FILTER (WHERE large_snap) AS large_n,"
                    "count(*) FILTER (WHERE severe_snap) AS severe_n,max(snap_distance_m) AS max_value,"
                    "percentile_cont(ARRAY[0.5,0.95,0.99]) WITHIN GROUP (ORDER BY snap_distance_m) "
                    f"AS quantiles FROM {table} {where}"
                ), {"kind": kind}).mappings().one()
                snaps.append({"entity": kind, "n": row["n"], "mean_m": _float(row["mean"]),
                              "p50_m": _float(row["quantiles"][0]),
                              "p95_m": _float(row["quantiles"][1]),
                              "p99_m": _float(row["quantiles"][2]),
                              "max_m": _float(row["max_value"]),
                              "over_100m_n": row["large_n"], "over_250m_n": row["severe_n"]})
            area = [dict(row) for row in conn.execute(text(
                "SELECT coalesce(s.official_cv_area_id,'unassigned') AS cv_area_id,"
                "count(*) AS primary_n,"
                "round(avg(e.food_social_800m),2) AS euclidean_food_800m_mean,"
                "round(avg(w.food_social_w_10),2) AS walking_food_10min_mean,"
                "round(avg(e.cultural_tourist_800m),2) AS euclidean_culture_800m_mean,"
                "round(avg(w.cultural_tourist_w_10),2) AS walking_culture_10min_mean,"
                "round(avg(w.nearest_station_walking_minutes)::numeric,2) AS station_walk_min_mean,"
                "count(*) FILTER (WHERE w.routing_status='no_reachable_station') AS station_unreachable_n "
                "FROM clean.airbnb_listings l JOIN features.listing_spatial_base s "
                "USING(snapshot_date,listing_id) JOIN features.euclidean_accessibility e "
                "USING(snapshot_date,listing_id) JOIN features.walking_accessibility w "
                "USING(snapshot_date,listing_id) WHERE l.primary_sample_candidate "
                "GROUP BY 1 ORDER BY 1"
            )).mappings()]
            for row in area:
                for key, value in row.items():
                    if hasattr(value, "as_tuple"):
                        row[key] = float(value)
            coverage = [dict(row) for row in conn.execute(text(
                "WITH source AS (SELECT ST_Transform(ST_GeomFromText(:poly,4326),25832) AS geom) "
                "SELECT a.area_kind,round((ST_Area(a.geom_25832)/1e6)::numeric,3) AS area_km2,"
                "round((ST_Area(ST_Difference(a.geom_25832,source.geom))/1e6)::numeric,3) "
                "AS outside_source_km2,ST_Covers(source.geom,a.geom_25832) AS fully_covered "
                "FROM spatial.study_area a CROSS JOIN source "
                "WHERE a.area_kind IN ('official_study_area','planned_15min_extraction') "
                "ORDER BY a.area_kind"
            ), {"poly": source_wkt}).mappings()]
            for row in coverage:
                row["area_km2"] = float(row["area_km2"])
                row["outside_source_km2"] = float(row["outside_source_km2"])

        tables = {
            "phase06_feature_summary.csv": summary,
            "phase06_euclidean_network_comparison.csv": comparison,
            "phase06_snap_diagnostics.csv": snaps,
            "phase06_area_comparison.csv": area,
            "phase06_source_coverage.csv": coverage,
        }
        for filename, rows in tables.items():
            with (target / filename).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        return {"network": network, "files": {name: len(rows) for name, rows in tables.items()}}
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(export())

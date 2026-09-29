"""Read-only aggregate audit of canonical destinations across study borders.

This does not change the frozen Phase 5/6 features or Phase 9 models.
Coordinates are evaluated in EPSG:25832; no point or listing ID is exported.
"""

from __future__ import annotations

import csv
import json

from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT


OUTPUT = PROJECT_ROOT / "outputs/tables/phase09_destination_boundary_audit.csv"
STUDY = "s.area_kind='official_study_area'"


def run() -> list[dict]:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            candidate_n = int(conn.scalar(text(
                "SELECT count(*) FROM analysis.analysis_dataset_v1 WHERE primary_sample_candidate"
            )))
            if candidate_n != 12521:
                raise RuntimeError("Phase 9 destination audit requires the frozen candidate sample")
            rows = []
            for source, category, table, geom in (
                ("food_social", "food_social", "spatial.osm_pois", "p.geom_25832"),
                ("cultural_tourist", "cultural_tourist", "spatial.osm_pois", "p.geom_25832"),
                ("station", None, "spatial.transit_stations", "p.geom_25832"),
            ):
                category_filter = "AND p.category=:category" if category else ""
                result = conn.execute(text(
                    f"SELECT count(*) AS total,count(*) FILTER (WHERE NOT ST_Covers(s.geom_25832,{geom})) "
                    f"AS outside_n FROM {table} p CROSS JOIN spatial.study_area s "
                    f"WHERE {STUDY} {category_filter}"
                ), {"category": category}).mappings().one()
                rows.append({"measure": f"canonical_{source}_outside_study", "count": int(result["outside_n"]),
                             "denominator": int(result["total"]), "crs_epsg": 25832,
                             "definition": "canonical destination point outside Copenhagen/Frederiksberg union"})
            impacted = conn.execute(text(
                "SELECT p.category,count(DISTINCT (a.snapshot_date,a.listing_id)) AS affected_n "
                "FROM analysis.analysis_dataset_v1 a "
                "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
                "JOIN spatial.osm_pois p ON ST_DWithin(p.geom_25832,l.geom_25832,800) "
                "CROSS JOIN spatial.study_area s "
                "WHERE a.primary_sample_candidate AND s.area_kind='official_study_area' "
                "AND NOT ST_Covers(s.geom_25832,p.geom_25832) GROUP BY p.category"
            )).mappings().all()
            for row in impacted:
                rows.append({"measure": f"primary_with_outside_{row['category']}_within_800m",
                             "count": int(row["affected_n"]), "denominator": candidate_n,
                             "crs_epsg": 25832,
                             "definition": "primary-candidate listing with at least one external POI in 800 m Euclidean radius"})
            for mode, feature_table in (("euclidean", "features.euclidean_accessibility"),
                                        ("walking", "features.walking_accessibility")):
                result = conn.execute(text(
                    "SELECT count(*) FILTER (WHERE NOT ST_Covers(s.geom_25832,p.geom_25832)) AS n "
                    "FROM analysis.analysis_dataset_v1 a "
                    f"JOIN {feature_table} f USING(snapshot_date,listing_id) "
                    "JOIN spatial.transit_stations p ON p.station_key=f.nearest_station_key "
                    "CROSS JOIN spatial.study_area s "
                    "WHERE a.primary_sample_candidate AND s.area_kind='official_study_area'"
                )).one()
                rows.append({"measure": f"primary_nearest_{mode}_station_outside_study",
                             "count": int(result.n), "denominator": candidate_n, "crs_epsg": 25832,
                             "definition": f"primary-candidate {mode} nearest canonical station outside study union"})
            cross_area = conn.scalar(text(
                "SELECT count(*) FROM analysis.analysis_dataset_v1 a "
                "JOIN features.walking_accessibility w USING(snapshot_date,listing_id) "
                "JOIN spatial.transit_stations p ON p.station_key=w.nearest_station_key "
                "JOIN spatial.official_cv_areas cv ON cv.area_id=a.official_cv_area_id "
                "CROSS JOIN spatial.study_area s "
                "WHERE a.primary_sample_candidate AND s.area_kind='official_study_area' "
                "AND ST_Covers(s.geom_25832,p.geom_25832) "
                "AND NOT ST_Covers(cv.geom_25832,p.geom_25832)"
            ))
            rows.append({"measure": "primary_nearest_walking_station_other_official_area_inside_study",
                         "count": int(cross_area), "denominator": candidate_n, "crs_epsg": 25832,
                         "definition": "primary-candidate nearest walking station in study union but not listing official CV area"})
    finally:
        engine.dispose()
    if len(rows) != 8 or any(row["count"] > row["denominator"] for row in rows):
        raise RuntimeError("Destination boundary audit cardinality failed")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

"""Build the Phase 4 spatial base, then attach archived official geography."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.db.sources import prepare_source, register_records
from src.ingestion.common import PROJECT_ROOT


SNAPSHOT = date(2026, 6, 30)
BOUNDARY_PATH = Path("data/raw/inside_airbnb/copenhagen/2026-06-30/visualisations/neighbourhoods.geojson")
OSM_METADATA_PATH = Path("data/raw/osm/copenhagen/2026-09-21/extraction_metadata.json")
CENTRE_LON = 12.568809986
CENTRE_LAT = 55.675902629
CENTRE_URL = "https://www.visitcopenhagen.nl/kobenhavn/planlaeg-din-tur/city-hall-square-gdk414247"
CENTRE_ACCESSED = date(2026, 9, 29)
WALK_SPEED_MPS = 1.4  # Existing non-GTFS pipeline assumption; not a measured pedestrian speed.
MAX_WALK_MINUTES = 15
EXTRACTION_BUFFER_METRES = 1500  # 15 min * 1.4 m/s = 1260 m; 240 m margin.


def _file_id(conn, path: Path) -> int:
    return conn.execute(text("SELECT source_file_id FROM meta.source_files WHERE relative_path=:path"),
                        {"path": path.as_posix()}).scalar_one()


def import_provider_boundaries(engine) -> int:
    record = prepare_source(PROJECT_ROOT / BOUNDARY_PATH)
    source_id = register_records(engine, [record])[0]
    source = json.loads((PROJECT_ROOT / BOUNDARY_PATH).read_text(encoding="utf-8"))
    if source.get("type") != "FeatureCollection" or source.get("crs") is not None:
        raise ValueError("Unexpected GeoJSON envelope/CRS; review before loading")
    features = source.get("features")
    if not isinstance(features, list) or len(features) != 11:
        raise ValueError("Expected 11 archived provider neighbourhood polygons")
    labels = [feature.get("properties", {}).get("neighbourhood") for feature in features]
    if len(set(labels)) != 11 or any(not isinstance(value, str) for value in labels):
        raise ValueError("Missing/duplicate provider neighbourhood labels")
    with engine.connect() as conn:
        prior = conn.scalar(text(
            "SELECT count(*) FROM meta.import_runs WHERE source_file_id=:id "
            "AND target_table='spatial.provider_neighbourhoods' AND status='success'"
        ), {"id": source_id})
        if prior:
            existing = conn.execute(text(
                "SELECT count(*) AS n, count(DISTINCT provider_label) AS labels, "
                "count(*) FILTER (WHERE source_file_id<>:id) AS wrong_source "
                "FROM spatial.provider_neighbourhoods"
            ), {"id": source_id}).one()
            if tuple(existing) != (11, 11, 0):
                raise RuntimeError("Previously imported provider polygons do not match logged source")
            return source_id
    with engine.begin() as conn:
        run_id = conn.scalar(text(
            "INSERT INTO meta.import_runs (source_file_id,source_hash_sha256,target_table,import_options,status) "
            "VALUES (:id,:hash,'spatial.provider_neighbourhoods',CAST(:options AS jsonb),'running') RETURNING import_run_id"
        ), {"id": source_id, "hash": record["file_hash_sha256"],
            "options": json.dumps({"source_crs": "GeoJSON RFC 7946 WGS84 lon/lat; source has no crs member",
                                   "target_crs": [4326, 25832]})})
    try:
        with engine.begin() as conn:
            existing_count = conn.scalar(text("SELECT count(*) FROM spatial.provider_neighbourhoods"))
            if existing_count:
                raise RuntimeError("Boundary table already contains a different source; manual review required")
            for index, feature in enumerate(features, 1):
                geometry = feature.get("geometry")
                if not isinstance(geometry, dict) or geometry.get("type") != "MultiPolygon":
                    raise ValueError("Expected archived MultiPolygon GeoJSON geometries")
                payload = json.dumps(geometry, separators=(",", ":"))
                qa = conn.execute(text(
                    "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geojson),4326) AS geom) "
                    "SELECT ST_IsValid(geom), ST_IsValidReason(geom), ST_IsEmpty(geom), "
                    "ST_XMin(geom),ST_XMax(geom),ST_YMin(geom),ST_YMax(geom) FROM g"
                ), {"geojson": payload}).one()
                if not qa[0] or qa[2] or not (12.3 < qa[3] < qa[4] < 12.8 and 55.5 < qa[5] < qa[6] < 55.9):
                    raise ValueError(f"Provider polygon {index} invalid or out of regional bounds: {qa[1]}")
                label = feature["properties"]["neighbourhood"]
                conn.execute(text(
                    "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geojson),4326) AS geom), "
                    "p AS (SELECT geom, ST_Transform(geom,25832) AS metric FROM g) "
                    "INSERT INTO spatial.provider_neighbourhoods "
                    "(area_id,provider_label,municipality_proxy,source_file_id,source_crs_text,source_crs_basis,"
                    "geom_source,geom_4326,geom_25832,boundary_25832) "
                    "SELECT :area_id,:label,:municipality,:source_id,:crs,:basis,geom,geom,metric,ST_Boundary(metric) FROM p"
                ), {"geojson": payload, "area_id": f"provider_{index:02d}", "label": label,
                    "municipality": "Frederiksberg" if label == "Frederiksberg" else "Copenhagen",
                    "source_id": source_id, "crs": "WGS84 longitude/latitude (EPSG:4326 storage)",
                    "basis": "No explicit crs member; interpreted under GeoJSON RFC 7946"})
            conn.execute(text("UPDATE meta.source_files SET imported_at=now(),row_count=11 WHERE source_file_id=:id"),
                         {"id": source_id})
            conn.execute(text(
                "UPDATE meta.import_runs SET status='success',finished_at=now(),rows_loaded=11 "
                "WHERE import_run_id=:run_id"
            ), {"run_id": run_id})
    except Exception as error:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE meta.import_runs SET status='failed',finished_at=now(),error_message=:message "
                "WHERE import_run_id=:run_id"
            ), {"run_id": run_id, "message": type(error).__name__})
        raise
    return source_id


def build_spatial_base(engine, boundary_source_id: int) -> dict:
    osm_id = register_records(engine, [prepare_source(PROJECT_ROOT / OSM_METADATA_PATH)])[0]
    osm = json.loads((PROJECT_ROOT / OSM_METADATA_PATH).read_text(encoding="utf-8"))
    south, west, north, east = osm["bbox_south_west_north_east"]
    if not (55.5 < south < north < 55.9 and 12.3 < west < east < 12.8):
        raise ValueError("Archived OSM bounding box is not in the expected Copenhagen extent")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM features.listing_spatial_base WHERE snapshot_date=:snapshot"), {"snapshot": SNAPSHOT})
        conn.execute(text("DELETE FROM spatial.study_area"))
        conn.execute(text("DELETE FROM spatial.reference_points WHERE reference_id='city_hall_square'"))
        conn.execute(text(
            "WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon,:lat),4326) AS geom) "
            "INSERT INTO spatial.reference_points "
            "(reference_id,description,source_url,source_accessed_on,source_crs_text,geom_4326,geom_25832) "
            "SELECT 'city_hall_square','Rådhuspladsen / Copenhagen City Hall Square reference point',"
            ":url,:accessed,'WGS84 longitude/latitude (EPSG:4326)',geom,ST_Transform(geom,25832) FROM p"
        ), {"lon": CENTRE_LON, "lat": CENTRE_LAT, "url": CENTRE_URL, "accessed": CENTRE_ACCESSED})
        conn.execute(text(
            "WITH g AS (SELECT ST_Multi(ST_CollectionExtract(ST_UnaryUnion(ST_Collect(geom_25832)),3)) AS geom "
            "FROM spatial.provider_neighbourhoods) "
            "INSERT INTO spatial.study_area (area_kind,description,source_file_id,buffer_metres,geom_4326,geom_25832) "
            "SELECT 'provider_study_proxy','Union of 11 provider neighbourhood polygons; not official municipality boundary',"
            ":source_id,0,ST_Transform(geom,4326),geom FROM g"
        ), {"source_id": boundary_source_id})
        conn.execute(text(
            "WITH p AS (SELECT geom_25832 AS geom FROM spatial.study_area WHERE area_kind='provider_study_proxy'), "
            "l AS (SELECT ST_ConvexHull(ST_Collect(geom_25832)) AS geom FROM clean.airbnb_listings "
            "WHERE snapshot_date=:snapshot AND valid_coordinates), "
            "g AS (SELECT ST_Multi(ST_Buffer(ST_ConvexHull(ST_Collect(p.geom,l.geom)),:buffer)) AS geom FROM p,l) "
            "INSERT INTO spatial.study_area (area_kind,description,source_file_id,buffer_metres,geom_4326,geom_25832) "
            "SELECT 'planned_15min_extraction','Convex hull of provider coverage and all listing points, buffered 1500 m in EPSG:25832',"
            ":source_id,:buffer,ST_Transform(geom,4326),geom FROM g"
        ), {"snapshot": SNAPSHOT, "buffer": EXTRACTION_BUFFER_METRES, "source_id": boundary_source_id})
        conn.execute(text(
            "WITH g AS (SELECT ST_Multi(ST_MakeEnvelope(:west,:south,:east,:north,4326)) AS geom) "
            "INSERT INTO spatial.study_area (area_kind,description,source_file_id,buffer_metres,geom_4326,geom_25832) "
            "SELECT 'archived_osm_bbox','2026-09-21 archived Overpass query bbox; not a municipality boundary',"
            ":source_id,0,geom,ST_Transform(geom,25832) FROM g"
        ), {"west": west, "south": south, "east": east, "north": north, "source_id": osm_id})
        conn.execute(text(
            "WITH matched AS ("
            " SELECT l.snapshot_date,l.listing_id,count(p.area_id)::integer AS matches,"
            " min(p.area_id) AS area_id,min(p.provider_label) AS label,"
            " min(p.municipality_proxy) AS municipality,"
            " bool_or(l.neighbourhood_cleansed=p.provider_label) AS label_matches"
            " FROM clean.airbnb_listings l LEFT JOIN spatial.provider_neighbourhoods p"
            " ON ST_Covers(p.geom_4326,l.geom)"
            " WHERE l.snapshot_date=:snapshot GROUP BY l.snapshot_date,l.listing_id"
            ") INSERT INTO features.listing_spatial_base "
            "(snapshot_date,listing_id,municipality_proxy,cv_area_id,provider_neighbourhood,"
            "polygon_match_count,provider_label_matches_polygon,assignment_status,"
            "context_statistical_unit_id,context_assignment_status,near_provider_border_100m,"
            "distance_centre_euclidean_km,distance_crs_epsg) "
            "SELECT l.snapshot_date,l.listing_id,CASE WHEN m.matches=1 THEN m.municipality END,"
            "CASE WHEN m.matches=1 THEN m.area_id END,CASE WHEN m.matches=1 THEN m.label END,"
            "m.matches,CASE WHEN m.matches=1 THEN m.label_matches END,"
            "CASE WHEN m.matches=0 THEN 'no_provider_polygon' WHEN m.matches=1 THEN 'unique_provider_polygon' "
            "ELSE 'multiple_provider_polygons' END,NULL,'official_statistical_boundary_unverified',"
            "EXISTS (SELECT 1 FROM spatial.provider_neighbourhoods p WHERE "
            "ST_DWithin(l.geom_25832,p.boundary_25832,100)),"
            "ST_Distance(l.geom_25832,c.geom_25832)/1000.0,25832 "
            "FROM clean.airbnb_listings l JOIN matched m USING (snapshot_date,listing_id) "
            "CROSS JOIN spatial.reference_points c "
            "WHERE l.snapshot_date=:snapshot AND c.reference_id='city_hall_square'"
        ), {"snapshot": SNAPSHOT})
        qa = dict(conn.execute(text(
            "SELECT count(*) AS n,count(*) FILTER (WHERE polygon_match_count=0) AS no_polygon,"
            "count(*) FILTER (WHERE polygon_match_count>1) AS multiple_polygons,"
            "count(*) FILTER (WHERE near_provider_border_100m) AS near_border_100m,"
            "count(*) FILTER (WHERE provider_label_matches_polygon IS FALSE) AS label_mismatch "
            "FROM features.listing_spatial_base WHERE snapshot_date=:snapshot"
        ), {"snapshot": SNAPSHOT}).mappings().one())
        if qa["n"] != conn.scalar(text(
            "SELECT count(*) FROM clean.airbnb_listings WHERE snapshot_date=:snapshot"
        ), {"snapshot": SNAPSHOT}):
            raise RuntimeError("Spatial base row count differs from clean listings")
        coverage = dict(conn.execute(text(
            "SELECT ST_Covers(o.geom_4326,p.geom_4326) AS archived_osm_covers_planned,"
            "ST_Area(ST_Intersection(o.geom_25832,p.geom_25832)) / NULLIF(ST_Area(p.geom_25832),0) "
            "AS planned_area_overlap_fraction "
            "FROM spatial.study_area o CROSS JOIN spatial.study_area p "
            "WHERE o.area_kind='archived_osm_bbox' AND p.area_kind='planned_15min_extraction'"
        )).mappings().one())
        radius_qa = dict(conn.execute(text(
            "SELECT count(*) FILTER (WHERE NOT ST_Covers(o.geom_25832,"
            "ST_Buffer(l.geom_25832,:radius))) AS listings_without_full_archived_radius,"
            "count(*) FILTER (WHERE l.primary_sample_candidate AND NOT ST_Covers(o.geom_25832,"
            "ST_Buffer(l.geom_25832,:radius))) AS primary_without_full_archived_radius,"
            "min(ST_Distance(l.geom_25832,ST_Boundary(p.geom_25832))) "
            "AS min_distance_to_planned_extraction_border_m "
            "FROM clean.airbnb_listings l CROSS JOIN spatial.study_area o "
            "CROSS JOIN spatial.study_area p WHERE l.snapshot_date=:snapshot "
            "AND o.area_kind='archived_osm_bbox' AND p.area_kind='planned_15min_extraction'"
        ), {"snapshot": SNAPSHOT, "radius": MAX_WALK_MINUTES * 60 * WALK_SPEED_MPS}).mappings().one())
    return {**qa, **coverage, **radius_qa}


def export_cv_counts(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(text(
            "SELECT p.area_id AS area,p.provider_label AS provider_area_label,"
            "p.municipality_proxy AS municipality,count(l.listing_id) AS eligible_n,"
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY l.price_nightly::double precision) AS median_price_dkk,"
            "stddev_samp(l.log_price) AS sd_log_price,"
            "ST_XMin(p.geom_4326) AS bbox_west_lon,ST_YMin(p.geom_4326) AS bbox_south_lat,"
            "ST_XMax(p.geom_4326) AS bbox_east_lon,ST_YMax(p.geom_4326) AS bbox_north_lat,"
            "ST_Area(p.geom_25832)/1000000.0 AS provider_polygon_area_km2 "
            "FROM spatial.provider_neighbourhoods p "
            "LEFT JOIN features.listing_spatial_base s ON s.cv_area_id=p.area_id AND s.snapshot_date=:snapshot "
            "LEFT JOIN clean.airbnb_listings l ON l.snapshot_date=s.snapshot_date AND l.listing_id=s.listing_id "
            "AND l.primary_sample_candidate "
            "GROUP BY p.area_id,p.provider_label,p.municipality_proxy,p.geom_4326,p.geom_25832 "
            "ORDER BY p.municipality_proxy,p.provider_label"
        ), {"snapshot": SNAPSHOT}).mappings()]
    path = PROJECT_ROOT / "outputs/tables/cv_area_counts.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*rows[0].keys(), "boundary_status", "distance_crs_epsg"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "boundary_status": "Inside Airbnb provider proxy; not official district/municipality",
                             "distance_crs_epsg": 25832})
    return rows


def _plot_rings(ax, geometry: dict, *, color: str, fill: bool = True, linewidth: float = 0.7) -> None:
    for polygon in geometry["coordinates"]:
        outer = polygon[0]
        xs, ys = zip(*outer)
        if fill:
            ax.fill(xs, ys, facecolor=color, edgecolor="#273746", linewidth=linewidth, alpha=0.74)
        else:
            ax.plot(xs, ys, color=color, linewidth=linewidth)
        # Interior holes are drawn as white to avoid implying land coverage.
        for ring in polygon[1:]:
            if fill:
                hx, hy = zip(*ring)
                ax.fill(hx, hy, facecolor="white", edgecolor="#273746", linewidth=0.35)


def export_maps(engine) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with engine.connect() as conn:
        polygons = [dict(row) for row in conn.execute(text(
            "SELECT area_id,provider_label,municipality_proxy,ST_AsGeoJSON(geom_25832) AS geojson,"
            "ST_X(ST_PointOnSurface(geom_25832)) AS x,ST_Y(ST_PointOnSurface(geom_25832)) AS y "
            "FROM spatial.provider_neighbourhoods ORDER BY area_id"
        )).mappings()]
        study = [dict(row) for row in conn.execute(text(
            "SELECT area_kind,ST_AsGeoJSON(geom_25832) AS geojson FROM spatial.study_area ORDER BY area_kind"
        )).mappings()]
    for row in [*polygons, *study]:
        row["geometry"] = json.loads(row["geojson"])
    output = PROJECT_ROOT / "outputs/figures"
    output.mkdir(parents=True, exist_ok=True)
    colors = {"Copenhagen": "#3d7ea6", "Frederiksberg": "#df8f44"}

    fig, ax = plt.subplots(figsize=(8, 8))
    for row in study:
        if row["area_kind"] == "planned_15min_extraction":
            _plot_rings(ax, row["geometry"], color="#cf7380", fill=False, linewidth=1.4)
        elif row["area_kind"] == "archived_osm_bbox":
            _plot_rings(ax, row["geometry"], color="#777777", fill=False, linewidth=0.9)
    for row in polygons:
        _plot_rings(ax, row["geometry"], color="#8eaaa1")
    ax.set_title("Study proxy, planned 15-min extraction (red), archived OSM bbox (grey)")
    _finish_map(fig, ax, output / "phase04_study_area.png")

    fig, ax = plt.subplots(figsize=(8, 8))
    for row in polygons:
        _plot_rings(ax, row["geometry"], color=colors[row["municipality_proxy"]])
    ax.set_title("Municipality proxies from provider polygons — not official boundaries")
    _finish_map(fig, ax, output / "phase04_municipality_proxy.png")

    fig, ax = plt.subplots(figsize=(8, 8))
    for row in polygons:
        _plot_rings(ax, row["geometry"], color=colors[row["municipality_proxy"]])
        ax.text(row["x"], row["y"], row["area_id"].removeprefix("provider_"),
                fontsize=8, ha="center", va="center", color="#17252e")
    ax.set_title("11 candidate CV areas (provider polygons; no folds fixed)")
    _finish_map(fig, ax, output / "phase04_candidate_cv_areas.png")


def _finish_map(fig, ax, path: Path) -> None:
    ax.set_aspect("equal")
    ax.set_xlabel("Easting (m), EPSG:25832")
    ax.set_ylabel("Northing (m), EPSG:25832")
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.grid(alpha=0.18)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.11)
    fig.text(0.02, 0.015, "Boundary source: Inside Airbnb, 2026-06-30 (CC BY 4.0); provider proxy, not official geography",
             fontsize=7, color="#37474f")
    fig.savefig(path, dpi=180)
    import matplotlib.pyplot as plt
    plt.close(fig)


def main() -> None:
    from src.pipeline.run_official_geography_phase4 import (
        assign_official_geography, export_official_cv_counts, export_official_maps,
        import_map_context_boundaries, import_official_boundaries,
    )

    engine = get_engine()
    try:
        print("Applied migrations:", migrate(engine), flush=True)
        source_id = import_provider_boundaries(engine)
        qa = build_spatial_base(engine, source_id)
        official_ids = import_official_boundaries(engine)
        map_context_source_id = import_map_context_boundaries(engine)
        official_qa = assign_official_geography(engine, official_ids)
        areas = export_official_cv_counts(engine)
        export_official_maps(engine)
        print(json.dumps({"boundary_source_id": source_id, "official_source_ids": official_ids,
                          "map_context_source_id": map_context_source_id,
                          "official_areas": len(areas), "official_assignment_qa": official_qa,
                          "eligible_assigned_n": sum(row["eligible_n"] for row in areas),
                          "provider_assignment_qa": {key: qa[key] for key in (
                              "n", "no_polygon", "multiple_polygons", "near_border_100m", "label_mismatch")}},
                         default=str, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

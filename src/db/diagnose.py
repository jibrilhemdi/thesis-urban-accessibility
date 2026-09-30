"""Read-only diagnostic of the authoritative Compose DB and a separate local PostgreSQL.

Never prints passwords, changes extensions, or creates/drops databases. The
Homebrew endpoint is an explicit candidate, verified by the server response.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import shutil
import subprocess

import psycopg2
from sqlalchemy import text

from src.db.connection import database_settings, get_engine
from src.db.migrations import REQUIRED_SCHEMAS


TABLES = (
    "meta.source_files", "meta.schema_migrations", "clean.airbnb_listings",
    "analysis.analysis_dataset_v1", "analysis.cv_assignments",
    "features.euclidean_accessibility", "features.walking_accessibility",
    "features.analysis_area_context", "spatial.official_municipalities",
    "spatial.official_cv_areas", "spatial.osm_pois", "spatial.transit_stations",
    "spatial.walking_nodes", "spatial.walking_edges",
)


def _compose_port() -> dict:
    try:
        run = subprocess.run(
            ["docker", "compose", "--env-file", ".env", "port", "db", "5432"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "not_available"}
    if run.returncode != 0:
        return {"status": "not_running_or_unavailable"}
    value = run.stdout.strip()
    match = re.fullmatch(r"(.+):(\d+)", value)
    if not match:
        return {"status": "unrecognized_port_output"}
    return {"status": "published", "host": match.group(1), "port": int(match.group(2))}


def authoritative() -> dict:
    settings = database_settings()
    safe = {key.removeprefix("DB_").lower(): settings[key]
            for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER")}
    safe["port"] = int(safe["port"])
    result = {"label": "AUTHORITATIVE THESIS DATABASE — Docker Compose", "connection": safe,
              "compose_published_port": _compose_port()}
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            identity = conn.execute(text(
                "SELECT current_database(),current_user,current_setting('port'),"
                "current_setting('server_version'),postgis_lib_version()"
            )).one()
            result["server"] = {"database": identity[0], "user": identity[1],
                                "internal_port": int(identity[2]),
                                "postgresql_version": identity[3], "postgis_version": identity[4]}
            result["expected_schemas"] = list(REQUIRED_SCHEMAS)
            result["present_schemas"] = conn.execute(text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name IN ('meta','raw','clean','spatial','features','analysis') "
                "ORDER BY schema_name")).scalars().all()
            counts = {}
            for relation in TABLES:
                if conn.scalar(text("SELECT to_regclass(:relation)"), {"relation": relation}) is None:
                    counts[relation] = None
                else:
                    # Fixed, code-owned identifiers only; no user-provided SQL here.
                    counts[relation] = int(conn.scalar(text(f"SELECT count(*) FROM {relation}")))
            result["row_counts"] = counts
            result["relations"] = [f"{s}.{n} ({kind})" for s, n, kind in conn.execute(text(
                "SELECT n.nspname,c.relname,CASE c.relkind WHEN 'v' THEN 'view' "
                "WHEN 'm' THEN 'materialized view' ELSE 'table' END "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname IN ('meta','raw','clean','spatial','features','analysis') "
                "AND c.relkind IN ('r','p','v','m') ORDER BY n.nspname,c.relname"))]
            unique = {}
            for relation in ("clean.airbnb_listings", "analysis.analysis_dataset_v1",
                             "features.euclidean_accessibility", "features.walking_accessibility",
                             "analysis.cv_assignments"):
                total, distinct = conn.execute(text(
                    f"SELECT count(*),count(DISTINCT (snapshot_date,listing_id)) FROM {relation}"
                )).one()
                unique[relation] = {"rows": int(total), "unique_snapshot_listing_keys": int(distinct),
                                    "duplicate_keys": int(total-distinct)}
            result["key_uniqueness"] = unique
            validity = {}
            for relation, column, expected_srid in (
                ("clean.airbnb_listings", "geom", 4326),
                ("clean.airbnb_listings", "geom_25832", 25832),
                ("spatial.official_municipalities", "geom_25832", 25832),
                ("spatial.official_cv_areas", "geom_25832", 25832),
                ("spatial.osm_pois", "geom_25832", 25832),
                ("spatial.transit_stations", "geom_25832", 25832),
            ):
                nonnull, invalid, wrong_srid = conn.execute(text(
                    f"SELECT count(*) FILTER (WHERE {column} IS NOT NULL),"
                    f"count(*) FILTER (WHERE {column} IS NOT NULL AND NOT ST_IsValid({column})),"
                    f"count(*) FILTER (WHERE {column} IS NOT NULL AND ST_SRID({column})<>{expected_srid}) "
                    f"FROM {relation}"
                )).one()
                validity[f"{relation}.{column}"] = {"non_null": int(nonnull),
                    "invalid": int(invalid), "wrong_srid": int(wrong_srid),
                    "expected_srid": expected_srid}
            result["geometry_qa"] = validity
            result["gist_indexes"] = [f"{r[0]}.{r[1]}.{r[2]}" for r in conn.execute(text(
                "SELECT schemaname,tablename,indexname FROM pg_indexes "
                "WHERE schemaname IN ('spatial','clean','features') "
                "AND indexdef ILIKE '%USING gist%' ORDER BY schemaname,tablename,indexname"))]
            result["feature_coverage"] = dict(conn.execute(text(
                "SELECT count(*) AS listings,"
                "count(e.listing_id) AS euclidean_rows,"
                "count(w.listing_id) AS walking_rows,"
                "count(*) FILTER (WHERE w.nearest_station_walking_minutes IS NOT NULL) AS reachable_station_rows "
                "FROM clean.airbnb_listings l "
                "LEFT JOIN features.euclidean_accessibility e USING(snapshot_date,listing_id) "
                "LEFT JOIN features.walking_accessibility w USING(snapshot_date,listing_id)"
            )).one()._mapping)
            for key, value in result["feature_coverage"].items():
                result["feature_coverage"][key] = int(value)
            # Three independent PostGIS operations on saved project geometries.
            city_hall_areas = conn.execute(text(
                "SELECT a.area_name FROM spatial.official_cv_areas a "
                "JOIN spatial.reference_points p ON p.reference_id='city_hall_square' "
                "WHERE ST_Covers(a.geom_25832,p.geom_25832) ORDER BY a.area_id"
            )).scalars().all()
            matched_listings = conn.scalar(text(
                "SELECT count(*) FROM clean.airbnb_listings l "
                "JOIN features.listing_spatial_base b USING(snapshot_date,listing_id) "
                "JOIN spatial.official_cv_areas a ON a.area_id=b.official_cv_area_id "
                "WHERE ST_Covers(a.geom_25832,l.geom_25832)"
            ))
            nearest_station = conn.execute(text(
                "SELECT round(ST_Distance(p.geom_25832,s.geom_25832)::numeric,2),"
                "ST_DWithin(p.geom_25832,s.geom_25832,1000) "
                "FROM spatial.reference_points p CROSS JOIN spatial.transit_stations s "
                "WHERE p.reference_id='city_hall_square' "
                "ORDER BY p.geom_25832 <-> s.geom_25832 LIMIT 1"
            )).one()
            transformed = conn.execute(text(
                "SELECT ST_SRID(ST_Transform(geom_4326,25832)),"
                "round(ST_Distance(ST_Transform(geom_4326,25832),geom_25832)::numeric,6) "
                "FROM spatial.reference_points WHERE reference_id='city_hall_square'"
            )).one()
            result["spatial_operations"] = {
                "point_in_polygon_city_hall_area": city_hall_areas,
                "assigned_listing_points_covered_by_assigned_polygon": int(matched_listings),
                "nearest_station_to_city_hall_distance_m": float(nearest_station[0]),
                "nearest_station_within_1000m": bool(nearest_station[1]),
                "reference_transform_srid": int(transformed[0]),
                "reference_transform_roundtrip_difference_m": float(transformed[1]),
                "metric_crs_epsg": 25832,
            }
    finally:
        engine.dispose()
    published = result["compose_published_port"]
    result["compose_connection_matches"] = bool(
        published.get("status") == "published" and published.get("port") == safe["port"]
        and published.get("host") == safe["host"] and result["server"]["database"] == safe["name"]
        and result["server"]["user"] == safe["user"]
        and result["server"]["postgresql_version"].startswith("16.")
        and result["server"]["postgis_version"].startswith("3.5"))
    if not result["compose_connection_matches"]:
        raise RuntimeError("Project connection does not match the published Compose server; refusing ambiguity")
    return result


def homebrew(host: str, port: int, user: str, database: str, diagnostic_database: str) -> dict:
    result = {"label": "LOCAL HOMEBREW CANDIDATE — separate from thesis",
              "target": {"host": host, "port": port, "database": database, "user": user},
              "psql_executable": shutil.which("psql"),
              "pg_config_executable": shutil.which("pg_config")}
    try:
        raw = psycopg2.connect(host=host, port=port, user=user, dbname=database,
                               connect_timeout=3)
    except psycopg2.OperationalError:
        result["status"] = "not_running_or_connection_unavailable"
        result["postgis_available"] = None
        result["postgis_enabled_in_inspected_database"] = None
        result["diagnostic_database"] = {"name": diagnostic_database, "present": None}
        return result
    try:
        raw.set_session(readonly=True)
        with raw.cursor() as cur:
            cur.execute("SELECT current_database(),current_user,current_setting('port'),current_setting('server_version')")
            db, actual_user, actual_port, pg = cur.fetchone()
            result.update({"status": "running", "database": db, "user": actual_user,
                           "verified_server_port": int(actual_port), "postgresql_version": pg,
                           "server_build_identified_as_homebrew": "Homebrew" in pg})
            cur.execute("SELECT default_version,installed_version FROM pg_available_extensions WHERE name='postgis'")
            extension = cur.fetchone()
            result["postgis_available"] = bool(extension)
            result["postgis_available_version"] = extension[0] if extension else None
            result["postgis_enabled_in_inspected_database"] = bool(extension and extension[1])
            result["postgis_enabled_version"] = extension[1] if extension else None
            cur.execute("SELECT count(*) FROM pg_database WHERE datname=%s", (diagnostic_database,))
            result["diagnostic_database"] = {"name": diagnostic_database,
                                              "present": bool(cur.fetchone()[0])}
            if result["postgis_enabled_in_inspected_database"]:
                cur.execute("SELECT postgis_lib_version()")
                result["postgis_function_version"] = cur.fetchone()[0]
    finally:
        raw.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--homebrew-host", default="127.0.0.1")
    parser.add_argument("--homebrew-port", type=int, default=5432,
                        help="Explicit candidate port; verified against SHOW port")
    parser.add_argument("--homebrew-user", default=getpass.getuser())
    parser.add_argument("--homebrew-database", default="postgres")
    parser.add_argument("--diagnostic-database", default="thesis_postgis_diag_20260929")
    args = parser.parse_args()
    data = {"authoritative_thesis_database": authoritative(),
            "local_homebrew_database": homebrew(args.homebrew_host, args.homebrew_port,
                                                args.homebrew_user, args.homebrew_database,
                                                args.diagnostic_database)}
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Read-only provenance, database, output and environment audit for Phase 11.

Writes only an aggregate JSON audit outside the database. Exit nonzero on a
failed integrity check. This does not claim that a clean-room rebuild ran.
"""

from __future__ import annotations

import csv
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from src.db.connection import database_settings, get_engine
from src.db.migrations import MIGRATION_DIR, REQUIRED_SCHEMAS
from src.db.sources import prepare_all_sources
from src.ingestion.common import PROJECT_ROOT, sha256_file, write_json
from src.pipeline.run_analysis_phase10 import _freeze
from src.pipeline.output_paths import PhaseDirectory, output_file


OUT = PhaseDirectory("tables", "phase11")
PACKAGES = (
    "SQLAlchemy", "psycopg2-binary", "python-dotenv", "pandas", "numpy",
    "PyYAML", "requests", "beautifulsoup4", "geopandas", "shapely",
    "pyproj", "osmium", "networkx", "scipy", "scikit-learn",
    "statsmodels", "libpysal", "spreg", "xgboost", "matplotlib",
    "seaborn", "pyogrio", "pyarrow",
)
FORBIDDEN_PUBLIC_FIELDS = {
    "listing_id", "host_name", "host_id", "latitude", "longitude",
    "metric_x", "metric_y", "price_nightly", "log_price", "review_text",
}


def audit() -> dict:
    checks: list[dict] = []

    def check(name: str, observed: object, expected: object) -> None:
        checks.append({"name": name, "observed": observed, "expected": expected,
                       "passed": observed == expected})

    sources = prepare_all_sources()  # hashes manifest-listed and all unlisted sidecars
    check("immutable raw archive files", len(sources), 58)
    expected_source = {r["relative_path"]: (r["file_hash_sha256"], r["file_size"]) for r in sources}
    settings = database_settings()
    engine = get_engine()
    try:
        with engine.connect() as conn:
            check("database name", conn.scalar(text("SELECT current_database()")), settings["DB_NAME"])
            schemas = set(conn.execute(text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name IN ('meta','raw','clean','spatial','features','analysis')"
            )).scalars())
            check("required schemas", sorted(schemas), sorted(REQUIRED_SCHEMAS))
            recorded = dict(conn.execute(text(
                "SELECT migration_name,trim(file_hash_sha256) FROM meta.schema_migrations"
            )).all())
            expected_migrations = {p.name: sha256_file(p) for p in
                                   sorted(MIGRATION_DIR.glob("[0-9][0-9][0-9]_*.sql"))}
            check("migration checksum history", recorded, expected_migrations)
            db_sources = {r.relative_path: (r.file_hash_sha256.strip(), r.file_size)
                          for r in conn.execute(text(
                              "SELECT relative_path,file_hash_sha256,file_size FROM meta.source_files"
                          ))}
            check("registered source path/hash/size", db_sources, expected_source)
            table_counts = {}
            for table in (
                "clean.airbnb_listings", "features.listing_spatial_base",
                "features.euclidean_accessibility", "features.walking_accessibility",
                "features.bus_stop_proximity", "features.bus_accessibility",
                "analysis.analysis_dataset_v1", "analysis.cv_assignments",
            ):
                table_counts[table] = conn.scalar(text(f"SELECT count(*) FROM {table}"))
            check("one listing row in each analytical layer",
                  table_counts, {name: 23144 for name in table_counts})
            for table in ("clean.airbnb_listings", "features.listing_spatial_base",
                          "features.euclidean_accessibility", "features.walking_accessibility",
                          "features.bus_accessibility", "analysis.cv_assignments"):
                result = conn.scalar(text(
                    f"SELECT count(*)-count(DISTINCT (snapshot_date,listing_id)) FROM {table}"
                ))
                check(f"duplicate keys: {table}", result, 0)
            qa = conn.execute(text(
                "SELECT count(*) FILTER(WHERE geom IS NOT NULL AND "
                "(NOT ST_IsValid(geom) OR ST_SRID(geom)<>4326)) AS invalid_wgs84,"
                "count(*) FILTER(WHERE geom_25832 IS NOT NULL AND "
                "(NOT ST_IsValid(geom_25832) OR ST_SRID(geom_25832)<>25832)) AS invalid_metric,"
                "count(*) FILTER(WHERE valid_coordinates AND (geom IS NULL OR geom_25832 IS NULL)) AS missing_geom "
                "FROM clean.airbnb_listings"
            )).one()
            check("listing geometry valid / EPSG:4326 + 25832", list(qa), [0, 0, 0])
            polygon_qa = conn.execute(text(
                "SELECT count(*) FILTER(WHERE NOT ST_IsValid(geom_25832) OR "
                "ST_SRID(geom_25832)<>25832) FROM spatial.official_cv_areas"
            )).scalar_one()
            check("official CV geometry valid / EPSG:25832", polygon_qa, 0)
            sample = conn.execute(text(
                "SELECT count(*) AS n,count(*) FILTER(WHERE price_nightly<=0 OR log_price IS NULL "
                "OR abs(log_price-ln(price_nightly::double precision))>1e-10) AS bad_price,"
                "count(*) FILTER(WHERE c.random_fold NOT BETWEEN 1 AND 5 OR "
                "c.heldout_area IS NULL OR c.geographic_fold IS NULL) AS bad_folds "
                "FROM analysis.analysis_dataset_v1 a JOIN analysis.cv_assignments c "
                "USING(snapshot_date,listing_id) WHERE a.primary_sample_candidate "
                "AND a.official_cv_area_id IS NOT NULL "
                "AND a.nearest_station_walking_minutes IS NOT NULL"
            )).one()
            check("frozen primary N / invalid DKK outcome / incomplete folds", list(sample), [12412, 0, 0])
            fold_counts = conn.execute(text(
                "SELECT count(DISTINCT random_fold),count(DISTINCT heldout_area),"
                "count(*) FILTER(WHERE heldout_area IS NOT NULL) FROM analysis.cv_assignments"
            )).one()
            check("fold coverage random/geographic/assigned", list(fold_counts), [5, 11, 23066])
            bus_qa = conn.execute(text(
                "SELECT count(*) FILTER(WHERE distance_crs_epsg<>25832 OR walking_speed_kmh<>4.8),"
                "count(*) FILTER(WHERE bus_walk_time_min IS NOT NULL AND "
                "abs(bus_walk_time_min*80-bus_walk_distance_m)>0.00001) "
                "FROM features.bus_accessibility"
            )).one()
            check("bus feature units / 4.8 km/h routing", list(bus_qa), [0, 0])
            freeze_path = output_file("tables", "phase10", "primary_freeze.json")
            check("Phase 9 output and CV hash freeze",
                  _freeze(conn), json.loads(freeze_path.read_text(encoding="utf-8")))
            server = conn.scalar(text("SHOW server_version"))
            postgis = conn.scalar(text("SELECT postgis_version()"))
    finally:
        engine.dispose()

    expected_outputs = (
        OUT / "phase09_model_performance.csv",
        OUT / "phase09_fold_performance.csv",
        OUT / "phase09_run_metadata.json",
        output_file("tables", "phase10", "robustness_summary.csv"),
        output_file("figures", "phase09", "model_performance.png"),
        output_file("figures", "phase10", "primary_validation_context.png"),
    )
    check("core aggregate tables and figures", [p.is_file() for p in expected_outputs],
          [True] * len(expected_outputs))
    metadata = json.loads((OUT / "phase09_run_metadata.json").read_text(encoding="utf-8"))
    check("documented primary random/inner seeds",
          [metadata.get("seed"), metadata.get("inner_seed")], [20260929, 20260930])
    privacy_violations = []
    for path in sorted((PROJECT_ROOT / "outputs/tables").glob("phase*/*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            columns = set(next(csv.reader(stream), []))
        prohibited = sorted(columns & FORBIDDEN_PUBLIC_FIELDS)
        if prohibited:
            privacy_violations.append({"file": path.name, "fields": prohibited})
    check("public CSV header privacy", privacy_violations, [])
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    gdal = subprocess.check_output(["ogrinfo", "--version"], text=True).strip()
    result = {
        "audit_version": "phase11_v1", "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "existing database/archive integrity; NOT a clean-room rebuild",
        "all_checks_passed": all(row["passed"] for row in checks), "checks": checks,
        "environment": {"python": sys.version.split()[0], "os": platform.platform(),
                        "postgresql": server, "postgis": postgis, "gdal": gdal,
                        "packages": versions, "container_image": "postgis/postgis:16-3.5"},
    }
    write_json(OUT / "phase11_audit.json", result)
    return result


if __name__ == "__main__":
    report = audit()
    print(json.dumps({"all_checks_passed": report["all_checks_passed"],
                      "checks": len(report["checks"]),
                      "failed": [r["name"] for r in report["checks"] if not r["passed"]]}, indent=2))
    if not report["all_checks_passed"]:
        raise SystemExit(1)

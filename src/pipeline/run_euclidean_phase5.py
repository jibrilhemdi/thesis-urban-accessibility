"""Import archived OSM destinations and build listing-level Euclidean features.

The immutable PBF is the source of truth. GDAL's OSM driver emits a selected,
losslessly retained GeoJSON feature in raw; all category decisions are versioned.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
import csv
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.db.sources import prepare_source, register_records
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline.output_paths import PhaseDirectory
from src.pipeline.acquire_osm_phase5 import PBF_NAME, POLY_NAME, existing_archive, polygon_wkt
from src.pipeline.osm_taxonomy_phase5 import (
    NAME_DEDUP_METRES, TAXONOMY_VERSION, WIKIDATA_DEDUP_METRES,
    categories, normalize_name, station_mode,
)


SNAPSHOT = date(2026, 6, 30)
ARCHIVE = existing_archive() or PROJECT_ROOT / "data/raw/osm/phase05/nonexistent"
CONFIG = PROJECT_ROOT / "config/osmconf_phase5.ini"
LAYERS = ("points", "lines", "multipolygons", "multilinestrings", "other_relations")
WHERE = ("amenity IN ('restaurant','cafe','bar','pub','theatre') "
         "OR tourism IN ('museum','gallery','attraction','viewpoint') "
         "OR historic IN ('monument','memorial','castle','palace') "
         "OR railway IN ('station','halt') OR public_transport='station'")


def _source_ref(layer: str, properties: dict) -> tuple[str, int]:
    if layer == "points":
        kind, value = "node", properties.get("osm_id")
    elif layer == "lines":
        kind, value = "way", properties.get("osm_id")
    elif properties.get("osm_way_id"):
        kind, value = "way", properties["osm_way_id"]
    else:
        kind, value = "relation", properties.get("osm_id")
    if value is None or not str(value).lstrip("-").isdigit():
        raise ValueError(f"Missing/invalid OSM ID in {layer}: {value!r}")
    return kind, abs(int(value))


def _tags(properties: dict) -> dict:
    extra = properties.get("all_tags") or {}
    if isinstance(extra, str):
        extra = json.loads(extra)
    if not isinstance(extra, dict):
        raise ValueError("GDAL all_tags is not a JSON object")
    tags = dict(extra)
    for key, value in properties.items():
        if key not in {"osm_id", "osm_way_id", "all_tags"} and value is not None:
            tags[key] = value
    return tags


def _features(layer: str):
    command = ["ogr2ogr", "--config", "OSM_CONFIG_FILE", str(CONFIG), "-f", "GeoJSONSeq",
               "/vsistdout/", str(ARCHIVE / PBF_NAME), layer, "-where", WHERE]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdout is not None
    try:
        for line in process.stdout:
            line = line.lstrip("\x1e").strip()
            if line:
                feature = json.loads(line)
                if feature.get("type") != "Feature" or not feature.get("geometry"):
                    raise ValueError(f"Invalid GDAL GeoJSON feature in {layer}")
                yield feature
    finally:
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr else ""
        returncode = process.wait()
        if returncode:
            raise RuntimeError(f"GDAL extraction failed for {layer}: {stderr[:1500]}")


RAW_SQL = text(
    "INSERT INTO raw.osm_phase5_elements (source_file_id,osm_type,osm_id,element) "
    "VALUES (:source_id,:osm_type,:osm_id,CAST(:element AS jsonb)) "
    "ON CONFLICT (source_file_id,osm_type,osm_id) DO NOTHING"
)
CANDIDATE_SQL = text(
    "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) AS shape), "
    "p AS (SELECT CASE WHEN GeometryType(shape)='POINT' THEN shape "
    "ELSE ST_PointOnSurface(shape) END AS geom FROM g) "
    "INSERT INTO spatial.osm_destination_candidates "
    "(candidate_key,source_file_id,taxonomy_version,category,osm_type,osm_id,name,normalized_name,"
    "wikidata,tags,position_method,geom,geom_25832) "
    "SELECT :candidate_key,:source_id,:taxonomy,:category,:osm_type,:osm_id,:name,:normalized_name,"
    ":wikidata,CAST(:tags AS jsonb),:position_method,geom,ST_Transform(geom,25832) FROM p "
    "ON CONFLICT (candidate_key) DO NOTHING"
)


def import_destinations(engine, source_id: int, source_hash: str) -> dict:
    with engine.connect() as conn:
        previous = conn.scalar(text(
            "SELECT count(*) FROM meta.import_runs WHERE source_file_id=:id "
            "AND target_table='raw.osm_phase5_elements' AND status='success'"
        ), {"id": source_id})
        if previous:
            counts = dict(conn.execute(text(
                "SELECT count(*) AS raw_n FROM raw.osm_phase5_elements WHERE source_file_id=:id"
            ), {"id": source_id}).mappings().one())
            candidates = conn.scalar(text(
                "SELECT count(*) FROM spatial.osm_destination_candidates WHERE source_file_id=:id "
                "AND taxonomy_version=:taxonomy"
            ), {"id": source_id, "taxonomy": TAXONOMY_VERSION})
            if not counts["raw_n"] or not candidates:
                raise RuntimeError("Previous Phase 5 import is incomplete; inspect DB before retry")
            return {**counts, "candidate_n": candidates, "reused": True}
        existing = conn.scalar(text("SELECT count(*) FROM spatial.osm_destination_candidates"))
        if existing:
            raise RuntimeError("Other destination source exists; require an explicit source/version migration")

    options = {"layers": LAYERS, "where": WHERE, "gdal_config_sha256": sha256_file(CONFIG),
               "taxonomy": TAXONOMY_VERSION, "geometry": "node point or ST_PointOnSurface; EPSG:25832"}
    with engine.begin() as conn:
        run_id = conn.scalar(text(
            "INSERT INTO meta.import_runs (source_file_id,source_hash_sha256,target_table,import_options,status) "
            "VALUES (:id,:hash,'raw.osm_phase5_elements',CAST(:options AS jsonb),'running') "
            "RETURNING import_run_id"
        ), {"id": source_id, "hash": source_hash, "options": json.dumps(options)})
    started = time.monotonic()
    stats = Counter()
    try:
        with engine.begin() as conn:
            for layer in LAYERS:
                for feature in _features(layer):
                    props = feature.get("properties") or {}
                    osm_type, osm_id = _source_ref(layer, props)
                    tags = _tags(props)
                    base = {"source_id": source_id, "osm_type": osm_type, "osm_id": osm_id}
                    result = conn.execute(RAW_SQL, {**base, "element": json.dumps(feature, ensure_ascii=False)})
                    if result.rowcount == 0:
                        stats["repeated_object"] += 1
                        continue
                    stats["raw_n"] += 1
                    stats[f"layer_{layer}"] += 1
                    for category in categories(tags):
                        key = f"{TAXONOMY_VERSION}:{category}:{osm_type}:{osm_id}"
                        geometry = feature["geometry"]
                        position_method = "osm_node" if geometry["type"] == "Point" else "gdal_point_on_surface"
                        conn.execute(CANDIDATE_SQL, {
                            **base, "candidate_key": key, "taxonomy": TAXONOMY_VERSION,
                            "category": category, "name": tags.get("name"),
                            "normalized_name": normalize_name(tags.get("name")),
                            "wikidata": tags.get("wikidata"),
                            "tags": json.dumps(tags, ensure_ascii=False),
                            "geometry": json.dumps(geometry, ensure_ascii=False),
                            "position_method": position_method,
                        })
                        stats["candidate_n"] += 1
                        stats[f"category_{category}"] += 1
            if stats["raw_n"] == 0 or stats["category_station"] == 0:
                raise RuntimeError("No OSM destinations/stations extracted")
            conn.execute(text("UPDATE meta.source_files SET imported_at=now(),row_count=:n WHERE source_file_id=:id"),
                         {"id": source_id, "n": stats["raw_n"]})
            conn.execute(text(
                "UPDATE meta.import_runs SET status='success',finished_at=now(),rows_loaded=:n "
                "WHERE import_run_id=:run_id"
            ), {"n": stats["raw_n"], "run_id": run_id})
    except Exception as error:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE meta.import_runs SET status='failed',finished_at=now(),error_message=:error "
                "WHERE import_run_id=:run_id"
            ), {"run_id": run_id, "error": str(error)[:2000]})
        raise
    return {**stats, "import_seconds": round(time.monotonic() - started, 2), "reused": False}


def _same_entity(a: dict, b: dict) -> str | None:
    if a["category"] != b["category"]:
        return None
    distance = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
    if a["wikidata"] and a["wikidata"] == b["wikidata"] \
            and distance <= WIKIDATA_DEDUP_METRES[a["category"]]:
        return "same_wikidata_nearby"
    if a["normalized_name"] and a["normalized_name"] == b["normalized_name"] \
            and distance <= NAME_DEDUP_METRES[a["category"]]:
        return "same_name_nearby"
    return None


def deduplicate(engine, source_id: int) -> dict:
    with engine.connect() as conn:
        present = conn.scalar(text("SELECT count(*) FROM spatial.osm_pois")) + conn.scalar(
            text("SELECT count(*) FROM spatial.transit_stations"))
        if present:
            return {"reused": True, "canonical_n": present}
        rows = [dict(row) for row in conn.execute(text(
            "SELECT candidate_key,category,osm_type,osm_id,name,normalized_name,wikidata,tags,"
            "ST_X(geom_25832) AS x,ST_Y(geom_25832) AS y "
            "FROM spatial.osm_destination_candidates WHERE source_file_id=:id "
            "ORDER BY category,CASE osm_type WHEN 'node' THEN 0 WHEN 'way' THEN 1 ELSE 2 END,osm_id"
        ), {"id": source_id}).mappings()]
    if not rows:
        raise RuntimeError("No destination candidates to deduplicate")
    selected: dict[str, dict] = {}
    groups: dict[str, list[dict]] = defaultdict(list)
    by_name: dict[tuple, list[dict]] = defaultdict(list)
    by_wikidata: dict[tuple, list[dict]] = defaultdict(list)
    reasons = Counter()
    for row in rows:
        possibles: dict[str, dict] = {}
        if row["normalized_name"]:
            for other in by_name[(row["category"], row["normalized_name"])]:
                possibles[other["candidate_key"]] = other
        if row["wikidata"]:
            for other in by_wikidata[(row["category"], row["wikidata"])]:
                possibles[other["candidate_key"]] = other
        matches = [(other, _same_entity(row, other)) for other in possibles.values()]
        matches = [(other, reason) for other, reason in matches if reason]
        if matches:
            # Representative is deterministic: node, then way, then relation, then OSM ID.
            target, reason = min(matches, key=lambda match: (
                {"node": 0, "way": 1, "relation": 2}[match[0]["osm_type"]], match[0]["osm_id"]))
            canonical = target["candidate_key"]
            reasons[reason] += 1
        else:
            canonical, reason = row["candidate_key"], "canonical"
            selected[canonical] = row
            if row["normalized_name"]:
                by_name[(row["category"], row["normalized_name"])].append(row)
            if row["wikidata"]:
                by_wikidata[(row["category"], row["wikidata"])].append(row)
        groups[canonical].append(row)
        row["canonical"] = canonical
        row["dedup_reason"] = reason

    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE spatial.osm_destination_candidates SET canonical_candidate_key=:canonical,"
            "dedup_reason=:reason WHERE candidate_key=:candidate_key"
        ), [{"canonical": r["canonical"], "reason": r["dedup_reason"],
             "candidate_key": r["candidate_key"]} for r in rows])
        for key, row in selected.items():
            refs = [{"osm_type": r["osm_type"], "osm_id": r["osm_id"]} for r in groups[key]]
            common = {"key": key, "source_id": source_id, "taxonomy": TAXONOMY_VERSION,
                      "category": row["category"], "osm_type": row["osm_type"], "osm_id": row["osm_id"],
                      "name": row["name"], "tags": json.dumps(row["tags"], ensure_ascii=False),
                      "refs": json.dumps(refs), "duplicate_count": len(refs) - 1}
            if row["category"] == "station":
                conn.execute(text(
                    "INSERT INTO spatial.transit_stations "
                    "(station_key,source_file_id,taxonomy_version,station_mode,osm_type,osm_id,name,tags,"
                    "position_method,merged_osm_refs,duplicate_count,geom,geom_25832) "
                    "SELECT :key,:source_id,:taxonomy,:mode,:osm_type,:osm_id,:name,CAST(:tags AS jsonb),"
                    "c.position_method,CAST(:refs AS jsonb),:duplicate_count,c.geom,c.geom_25832 "
                    "FROM spatial.osm_destination_candidates c WHERE c.candidate_key=:key"
                ), {**common, "mode": station_mode(row["tags"])})
            else:
                conn.execute(text(
                    "INSERT INTO spatial.osm_pois "
                    "(destination_key,source_file_id,taxonomy_version,category,osm_type,osm_id,name,tags,"
                    "position_method,merged_osm_refs,duplicate_count,geom,geom_25832) "
                    "SELECT :key,:source_id,:taxonomy,:category,:osm_type,:osm_id,:name,CAST(:tags AS jsonb),"
                    "c.position_method,CAST(:refs AS jsonb),:duplicate_count,c.geom,c.geom_25832 "
                    "FROM spatial.osm_destination_candidates c WHERE c.candidate_key=:key"
                ), common)
    return {"reused": False, "canonical_n": len(selected), "duplicate_n": len(rows)-len(selected),
            "dedup_reasons": dict(reasons)}


def build_features(engine, source_id: int, poly_wkt: str) -> dict:
    started = time.monotonic()
    with engine.begin() as conn:
        existing = conn.execute(text(
            "SELECT count(*) AS n,count(*) FILTER (WHERE source_file_id<>:source OR taxonomy_version<>:taxonomy) AS stale "
            "FROM features.euclidean_accessibility WHERE snapshot_date=:snapshot"
        ), {"source": source_id, "taxonomy": TAXONOMY_VERSION, "snapshot": SNAPSHOT}).one()
        if existing.stale:
            raise RuntimeError("Different Phase 5 feature source/version exists; review before replacement")
        conn.execute(text("DELETE FROM features.euclidean_accessibility WHERE snapshot_date=:snapshot"),
                     {"snapshot": SNAPSHOT})
        conn.execute(text(
            "WITH src AS MATERIALIZED (SELECT ST_Transform(ST_GeomFromText(:poly,4326),25832) AS geom), "
            "base AS (SELECT l.snapshot_date,l.listing_id,l.valid_coordinates,l.geom_25832,"
            "CASE WHEN l.valid_coordinates THEN ST_Distance(l.geom_25832,ST_Boundary(src.geom)) END AS edge_m,"
            "CASE WHEN l.valid_coordinates THEN ST_Covers(src.geom,ST_Buffer(l.geom_25832,1600)) END AS covered "
            "FROM clean.airbnb_listings l CROSS JOIN src WHERE l.snapshot_date=:snapshot) "
            "INSERT INTO features.euclidean_accessibility "
            "(snapshot_date,listing_id,source_file_id,taxonomy_version,valid_coordinates,"
            "count_coverage_complete,source_edge_distance_m,nearest_station_coverage_complete,"
            "nearest_station_key,nearest_station_distance_m,food_social_800m,food_social_1200m,"
            "food_social_1600m,cultural_tourist_800m,cultural_tourist_1200m,cultural_tourist_1600m,distance_crs_epsg) "
            "SELECT b.snapshot_date,b.listing_id,:source,:taxonomy,b.valid_coordinates,b.covered,b.edge_m,"
            "CASE WHEN b.valid_coordinates THEN s.distance_m < b.edge_m END,s.station_key,s.distance_m,"
            "CASE WHEN b.valid_coordinates THEN p.f800 END,CASE WHEN b.valid_coordinates THEN p.f1200 END,"
            "CASE WHEN b.valid_coordinates THEN p.f1600 END,CASE WHEN b.valid_coordinates THEN p.c800 END,"
            "CASE WHEN b.valid_coordinates THEN p.c1200 END,CASE WHEN b.valid_coordinates THEN p.c1600 END,25832 "
            "FROM base b "
            "LEFT JOIN LATERAL (SELECT station_key,ST_Distance(geom_25832,b.geom_25832) AS distance_m "
            "FROM spatial.transit_stations ORDER BY geom_25832 <-> b.geom_25832 LIMIT 1) s ON b.valid_coordinates "
            "LEFT JOIN LATERAL (SELECT "
            "count(*) FILTER (WHERE category='food_social' AND ST_DWithin(geom_25832,b.geom_25832,800))::integer AS f800,"
            "count(*) FILTER (WHERE category='food_social' AND ST_DWithin(geom_25832,b.geom_25832,1200))::integer AS f1200,"
            "count(*) FILTER (WHERE category='food_social')::integer AS f1600,"
            "count(*) FILTER (WHERE category='cultural_tourist' AND ST_DWithin(geom_25832,b.geom_25832,800))::integer AS c800,"
            "count(*) FILTER (WHERE category='cultural_tourist' AND ST_DWithin(geom_25832,b.geom_25832,1200))::integer AS c1200,"
            "count(*) FILTER (WHERE category='cultural_tourist')::integer AS c1600 "
            "FROM spatial.osm_pois WHERE ST_DWithin(geom_25832,b.geom_25832,1600)) p ON b.valid_coordinates"
        ), {"poly": poly_wkt, "snapshot": SNAPSHOT, "source": source_id, "taxonomy": TAXONOMY_VERSION})
        qa = dict(conn.execute(text(
            "SELECT count(*) AS n,count(*) FILTER (WHERE valid_coordinates AND NOT count_coverage_complete) AS count_edge_n,"
            "count(*) FILTER (WHERE valid_coordinates AND NOT nearest_station_coverage_complete) AS station_edge_n,"
            "count(*) FILTER (WHERE valid_coordinates AND nearest_station_key IS NULL) AS station_missing_n,"
            "count(*) FILTER (WHERE valid_coordinates AND (food_social_800m>food_social_1200m "
            "OR food_social_1200m>food_social_1600m OR cultural_tourist_800m>cultural_tourist_1200m "
            "OR cultural_tourist_1200m>cultural_tourist_1600m)) AS nonmonotone_n "
            "FROM features.euclidean_accessibility WHERE snapshot_date=:snapshot"
        ), {"snapshot": SNAPSHOT}).mappings().one())
        listing_n = conn.scalar(text("SELECT count(*) FROM clean.airbnb_listings WHERE snapshot_date=:snapshot"),
                                {"snapshot": SNAPSHOT})
        if qa["n"] != listing_n or qa["count_edge_n"] or qa["station_missing_n"] or qa["nonmonotone_n"]:
            raise RuntimeError(f"Phase 5 feature QA failed: {qa}")
    return {**qa, "feature_seconds": round(time.monotonic() - started, 2)}


def export_aggregate_summaries(engine) -> None:
    """Derived CSVs only; PostGIS remains authoritative. Never export listing points."""
    target = PhaseDirectory("tables", "phase05")
    target.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        counts = [dict(row) for row in conn.execute(text(
            "WITH candidates AS (SELECT category,count(*) AS candidate_n "
            "FROM spatial.osm_destination_candidates GROUP BY category), "
            "canonical AS (SELECT category,count(*) AS canonical_n,sum(duplicate_count) AS duplicate_n "
            "FROM (SELECT category,duplicate_count FROM spatial.osm_pois "
            "UNION ALL SELECT 'station',duplicate_count FROM spatial.transit_stations) x GROUP BY category) "
            "SELECT c.category,c.candidate_n,k.canonical_n,k.duplicate_n "
            "FROM candidates c JOIN canonical k USING(category) ORDER BY c.category"
        )).mappings()]
        measures = (
            ("food_social_800m", "count"), ("food_social_1200m", "count"),
            ("food_social_1600m", "count"), ("cultural_tourist_800m", "count"),
            ("cultural_tourist_1200m", "count"), ("cultural_tourist_1600m", "count"),
            ("nearest_station_distance_m", "metres"),
        )
        summaries = []
        for column, unit in measures:
            # Column identifiers come exclusively from the fixed tuple above.
            row = conn.execute(text(
                f"SELECT count({column}) AS n,avg({column}) AS mean,"
                f"count(*) FILTER (WHERE {column}=0) AS zero_n,"
                f"percentile_cont(ARRAY[0.05,0.25,0.5,0.75,0.95]) "
                f"WITHIN GROUP (ORDER BY {column}) AS quantiles "
                "FROM features.euclidean_accessibility WHERE snapshot_date=:snapshot"
            ), {"snapshot": SNAPSHOT}).mappings().one()
            summaries.append({"measure": column, "unit": unit, "n": row["n"],
                              "mean": round(float(row["mean"]), 2), "zero_n": row["zero_n"],
                              **{key: round(value, 2) for key, value in zip(
                                  ("p05", "p25", "median", "p75", "p95"), row["quantiles"])} })
    for filename, rows in (("phase05_destination_counts.csv", counts),
                           ("phase05_feature_summary.csv", summaries)):
        with (target / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    if not (ARCHIVE / PBF_NAME).is_file() or not (ARCHIVE / POLY_NAME).is_file():
        raise FileNotFoundError("Run `make phase5-acquire` first")
    metadata = json.loads((ARCHIVE / "acquisition_metadata.json").read_text(encoding="utf-8"))
    # The PBF is tag-complete for selected objects; acquisition-era taxonomy is
    # provenance, not a constraint on a later pre-model category revision.
    engine = get_engine()
    try:
        migrate(engine)
        records = [prepare_source(ARCHIVE / name) for name in (PBF_NAME, POLY_NAME, "acquisition_metadata.json")]
        source_id = register_records(engine, records)[0]
        imported = import_destinations(engine, source_id, records[0]["file_hash_sha256"])
        dedup = deduplicate(engine, source_id)
        poly_wkt = polygon_wkt((ARCHIVE / POLY_NAME).read_text(encoding="utf-8"))
        built = build_features(engine, source_id, poly_wkt)
        export_aggregate_summaries(engine)
        print(json.dumps({"source_file_id": source_id, "import": imported, "dedup": dedup,
                          "features": built}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

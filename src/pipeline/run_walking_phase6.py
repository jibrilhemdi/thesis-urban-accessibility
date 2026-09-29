"""Build/persist the Phase 6 OSM walking graph and route to Phase 5 destinations."""

from __future__ import annotations

import csv
import io
import json
import time
from collections import Counter
from datetime import date
from importlib.metadata import version

import networkx as nx
import numpy as np
import osmium
import pyproj
from scipy.spatial import cKDTree
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline.acquire_osm_phase5 import PBF_NAME, existing_archive
from src.pipeline.osm_taxonomy_phase5 import TAXONOMY_VERSION
from src.spatial.walking_network import (
    DEFAULT_WALK, DENIED_FOOT, EXPLICIT_WALK_ONLY, FILTER_VERSION,
    FORBIDDEN_HIGHWAYS, LARGE_SNAP_M, METRES_PER_MINUTE, METRIC_EPSG,
    PERMITTED_FOOT, SEVERE_SNAP_M, WALK_SPEED_KMH, build_graph,
)
from src.spatial.walking_routing import grouped_opportunities, station_distance_labels


SNAPSHOT = date(2026, 6, 30)
BATCH_SIZE = 25000


def _copy_batches(cursor, sql: str, rows, batch_size: int = BATCH_SIZE) -> int:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    total = 0
    in_batch = 0
    for row in rows:
        writer.writerow(row)
        in_batch += 1
        if in_batch >= batch_size:
            buffer.seek(0)
            cursor.copy_expert(sql, buffer)
            total += in_batch
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            in_batch = 0
    if in_batch:
        buffer.seek(0)
        cursor.copy_expert(sql, buffer)
        total += in_batch
    return total


def persist_graph(engine, network_id, source_id, source_hash, source_date,
                  coordinates, metric, edges, component_by_node, stats) -> dict:
    with engine.connect() as conn:
        prior = conn.execute(text(
            "SELECT source_file_id,trim(source_sha256),filter_version,node_count,source_segment_count,"
            "directed_arc_count FROM spatial.walking_networks WHERE network_id=:id"
        ), {"id": network_id}).first()
        if prior:
            expected = (source_id, source_hash, FILTER_VERSION, stats["nodes"],
                        stats["source_segments"], stats["directed_arcs"])
            if tuple(prior) != expected:
                raise RuntimeError("Persisted walking graph metadata differs from source/code")
            actual = conn.execute(text(
                "SELECT (SELECT count(*) FROM spatial.walking_nodes WHERE network_id=:id),"
                "(SELECT count(*) FROM spatial.walking_edges WHERE network_id=:id)"
            ), {"id": network_id}).one()
            if tuple(actual) != (stats["nodes"], stats["source_segments"]):
                raise RuntimeError("Persisted walking graph row count is incomplete")
            return {"reused": True, "import_seconds": 0}

    spec = {
        "default_walk_highways": sorted(DEFAULT_WALK),
        "explicit_foot_only_highways": sorted(EXPLICIT_WALK_ONLY),
        "forbidden_highways": sorted(FORBIDDEN_HIGHWAYS),
        "denied_foot": sorted(DENIED_FOOT), "permitted_foot": sorted(PERMITTED_FOOT),
        "area_yes_excluded": True, "oneway_motor_ignored": True,
        "foot_directional_tags": ["oneway:foot", "foot:forward", "foot:backward", "conveying"],
        "ferries_included": False, "bridge_connectivity": "shared OSM node ID only",
        "walking_speed_kmh": WALK_SPEED_KMH, "snap_large_m": LARGE_SNAP_M,
        "snap_severe_m": SEVERE_SNAP_M,
        "libraries": {"networkx": nx.__version__, "pyosmium": version("osmium"),
                      "pyproj": pyproj.__version__},
    }
    with engine.begin() as conn:
        run_id = conn.scalar(text(
            "INSERT INTO meta.import_runs (source_file_id,source_hash_sha256,target_table,import_options,status) "
            "VALUES (:source,:hash,:target,CAST(:options AS jsonb),'running') RETURNING import_run_id"
        ), {"source": source_id, "hash": source_hash, "target": f"spatial.walking_networks:{FILTER_VERSION}",
            "options": json.dumps(spec)})
    started = time.monotonic()
    raw_connection = engine.raw_connection()
    try:
        cursor = raw_connection.cursor()
        cursor.execute(
            "INSERT INTO spatial.walking_networks "
            "(network_id,source_file_id,source_sha256,source_date,network_type,filter_version,filter_spec,"
            "source_crs_epsg,metric_crs_epsg,node_count,source_segment_count,directed_arc_count,"
            "weak_component_count,largest_component_nodes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,4326,25832,%s,%s,%s,%s,%s)",
            (network_id, source_id, source_hash, source_date, stats["network_type"],
             FILTER_VERSION, json.dumps(spec), stats["nodes"], stats["source_segments"],
             stats["directed_arcs"], stats["weak_components"], stats["largest_component_nodes"]),
        )

        def node_rows():
            for node_id, (lon, lat) in coordinates.items():
                x, y = metric[node_id]
                yield (network_id, node_id, lon, lat, component_by_node[node_id],
                       f"SRID=25832;POINT({x} {y})")

        nodes_loaded = _copy_batches(cursor,
            "COPY spatial.walking_nodes (network_id,osm_node_id,lon,lat,component_id,geom_25832) "
            "FROM STDIN WITH (FORMAT csv)", node_rows())

        def edge_rows():
            for segment, length in edges:
                yield (network_id, segment.way_id, segment.segment_index, segment.u, segment.v,
                       length, segment.highway, "t" if segment.forward else "f",
                       "t" if segment.reverse else "f")

        edges_loaded = _copy_batches(cursor,
            "COPY spatial.walking_edges "
            "(network_id,osm_way_id,segment_index,from_node_id,to_node_id,length_m,highway,"
            "forward_allowed,reverse_allowed) FROM STDIN WITH (FORMAT csv)", edge_rows())
        if nodes_loaded != stats["nodes"] or edges_loaded != stats["source_segments"]:
            raise RuntimeError("Walking graph COPY count mismatch")
        raw_connection.commit()
    except Exception as error:
        raw_connection.rollback()
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE meta.import_runs SET status='failed',finished_at=now(),error_message=:error "
                "WHERE import_run_id=:id"
            ), {"id": run_id, "error": str(error)[:2000]})
        raise
    finally:
        raw_connection.close()
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE meta.import_runs SET status='success',finished_at=now(),rows_loaded=:n "
            "WHERE import_run_id=:id"
        ), {"id": run_id, "n": nodes_loaded + edges_loaded})
    return {"reused": False, "import_seconds": round(time.monotonic()-started, 2),
            "nodes_loaded": nodes_loaded, "segments_loaded": edges_loaded}


def read_entities(engine, source_id: int) -> tuple[list[dict], list[dict]]:
    with engine.connect() as conn:
        listings = [dict(row) for row in conn.execute(text(
            "SELECT l.listing_id,l.valid_coordinates,l.primary_sample_candidate,"
            "ST_X(l.geom_25832) AS x,ST_Y(l.geom_25832) AS y,"
            "e.source_edge_distance_m,e.nearest_station_distance_m AS euclidean_station_m,"
            "e.food_social_800m,e.food_social_1200m,e.food_social_1600m,"
            "e.cultural_tourist_800m,e.cultural_tourist_1200m,e.cultural_tourist_1600m "
            "FROM clean.airbnb_listings l JOIN features.euclidean_accessibility e "
            "USING(snapshot_date,listing_id) WHERE l.snapshot_date=:snapshot AND e.source_file_id=:source "
            "AND e.taxonomy_version=:taxonomy ORDER BY l.listing_id"
        ), {"snapshot": SNAPSHOT, "source": source_id, "taxonomy": TAXONOMY_VERSION}).mappings()]
        destinations = [dict(row) for row in conn.execute(text(
            "SELECT 'poi' AS destination_kind,destination_key,category,ST_X(geom_25832) AS x,"
            "ST_Y(geom_25832) AS y FROM spatial.osm_pois "
            "WHERE source_file_id=:source AND taxonomy_version=:taxonomy "
            "UNION ALL SELECT 'station',station_key,'station',ST_X(geom_25832),ST_Y(geom_25832) "
            "FROM spatial.transit_stations WHERE source_file_id=:source AND taxonomy_version=:taxonomy"
        ), {"source": source_id, "taxonomy": TAXONOMY_VERSION}).mappings()]
    if len(listings) != 23144 or len(destinations) != 3612:
        raise RuntimeError("Phase 5 listing/destination sets differ from validated snapshot")
    return listings, destinations


def snap_entities(metric: dict, component_by_node: dict, listings: list[dict], destinations: list[dict]):
    node_ids = np.fromiter(metric.keys(), dtype=np.int64, count=len(metric))
    points = np.array(list(metric.values()), dtype=np.float64)
    tree = cKDTree(points)
    valid_listings = [row for row in listings if row["valid_coordinates"] and row["x"] is not None]
    for items in (valid_listings, destinations):
        query_points = np.array([(row["x"], row["y"]) for row in items], dtype=np.float64)
        distances, indices = tree.query(query_points, k=1)
        for row, distance, index in zip(items, distances, indices):
            node_id = int(node_ids[index])
            row["snapped_node_id"] = node_id
            row["snap_distance_m"] = float(distance)
            row["component_id"] = component_by_node[node_id]
            row["large_snap"] = bool(distance > LARGE_SNAP_M)
            row["severe_snap"] = bool(distance > SEVERE_SNAP_M)
    for row in listings:
        if not row["valid_coordinates"] or row["x"] is None:
            row.update(snapped_node_id=None, snap_distance_m=None, component_id=None,
                       large_snap=None, severe_snap=None)
    return {"listing_unique_nodes": len({r["snapped_node_id"] for r in valid_listings}),
            "listing_large_n": sum(r["large_snap"] for r in valid_listings),
            "listing_severe_n": sum(r["severe_snap"] for r in valid_listings),
            "poi_large_n": sum(r["large_snap"] for r in destinations if r["destination_kind"] == "poi"),
            "station_large_n": sum(r["large_snap"] for r in destinations if r["destination_kind"] == "station")}


def route_all(graph, listings, destinations) -> tuple[list[dict], dict]:
    started = time.monotonic()
    poi_snaps = [row for row in destinations if row["destination_kind"] == "poi"]
    station_snaps = [row for row in destinations if row["destination_kind"] == "station"]
    station_distance, station_key = station_distance_labels(graph, station_snaps)
    opportunity, bench = grouped_opportunities(graph, listings, poi_snaps)
    rows = []
    status_counts = Counter()
    incomplete_station = 0
    euclidean_count_violations = 0
    station_lower_bound_violations = 0
    for listing in listings:
        node = listing["snapped_node_id"]
        if node is None:
            status = "invalid_coordinates" if not listing["valid_coordinates"] else "no_walk_node"
            counts = None
            station = None
            distance = None
        else:
            counts = opportunity[listing["listing_id"]]
            station = station_key.get(node)
            distance = (listing["snap_distance_m"] + station_distance[node]
                        if station is not None else None)
            status = "ok" if station is not None else "no_reachable_station"
            for category in ("food_social", "cultural_tourist"):
                for radius in (800, 1200, 1600):
                    if counts[(category, radius)] > listing[f"{category}_{radius}m"]:
                        euclidean_count_violations += 1
            if distance is not None and distance + 0.1 < listing["euclidean_station_m"]:
                station_lower_bound_violations += 1
        coverage = (distance < listing["source_edge_distance_m"]
                    if distance is not None and listing["source_edge_distance_m"] is not None else None)
        if coverage is False:
            incomplete_station += 1
        status_counts[status] += 1
        rows.append({
            "listing_id": listing["listing_id"], "snapped_node_id": node,
            "snap_distance_m": listing["snap_distance_m"], "nearest_station_key": station,
            "nearest_station_network_distance_m": distance,
            "nearest_station_walking_minutes": distance / METRES_PER_MINUTE if distance is not None else None,
            "nearest_station_coverage_complete": coverage,
            "food_social_w_10": counts[("food_social", 800)] if counts is not None else None,
            "food_social_w_15": counts[("food_social", 1200)] if counts is not None else None,
            "food_social_w_20": counts[("food_social", 1600)] if counts is not None else None,
            "cultural_tourist_w_10": counts[("cultural_tourist", 800)] if counts is not None else None,
            "cultural_tourist_w_15": counts[("cultural_tourist", 1200)] if counts is not None else None,
            "cultural_tourist_w_20": counts[("cultural_tourist", 1600)] if counts is not None else None,
            "routing_status": status,
        })
    if euclidean_count_violations or station_lower_bound_violations:
        raise RuntimeError(f"Network/Euclidean lower-bound QA failed: counts={euclidean_count_violations}, "
                           f"station={station_lower_bound_violations}")
    return rows, {**bench, "station_reachable_nodes": len(station_distance),
                  "status_counts": dict(status_counts), "station_edge_incomplete_n": incomplete_station,
                  "route_seconds": round(time.monotonic()-started, 2)}


def persist_snaps_features(engine, network_id, listings, destinations, routes) -> None:
    with engine.begin() as conn:
        prior = conn.execute(text(
            "SELECT count(*) AS n,count(*) FILTER (WHERE network_id<>:network) AS other_n "
            "FROM features.walking_accessibility WHERE snapshot_date=:snapshot"
        ), {"network": network_id, "snapshot": SNAPSHOT}).one()
        if prior.other_n:
            raise RuntimeError("Another walking-network version already occupies Phase 6 feature rows")
        conn.execute(text("DELETE FROM features.walking_accessibility WHERE snapshot_date=:snapshot"),
                     {"snapshot": SNAPSHOT})
        conn.execute(text("DELETE FROM features.walking_listing_snaps WHERE network_id=:network AND snapshot_date=:snapshot"),
                     {"network": network_id, "snapshot": SNAPSHOT})
        conn.execute(text("DELETE FROM spatial.walking_destination_snaps WHERE network_id=:network"),
                     {"network": network_id})
        conn.execute(text(
            "INSERT INTO spatial.walking_destination_snaps "
            "(network_id,destination_kind,destination_key,category,snapped_node_id,component_id,"
            "snap_distance_m,large_snap,severe_snap) VALUES "
            "(:network,:destination_kind,:destination_key,:category,:snapped_node_id,:component_id,"
            ":snap_distance_m,:large_snap,:severe_snap)"
        ), [{**row, "network": network_id} for row in destinations])
        conn.execute(text(
            "INSERT INTO features.walking_listing_snaps "
            "(network_id,snapshot_date,listing_id,snapped_node_id,component_id,snap_distance_m,large_snap,severe_snap) "
            "VALUES (:network,:snapshot,:listing_id,:snapped_node_id,:component_id,:snap_distance_m,"
            ":large_snap,:severe_snap)"
        ), [{**row, "network": network_id, "snapshot": SNAPSHOT} for row in listings])
        conn.execute(text(
            "INSERT INTO features.walking_accessibility "
            "(snapshot_date,listing_id,network_id,destination_taxonomy_version,walking_speed_kmh,"
            "snapped_node_id,listing_snap_distance_m,nearest_station_key,nearest_station_network_distance_m,"
            "nearest_station_walking_minutes,nearest_station_coverage_complete,food_social_w_10,food_social_w_15,"
            "food_social_w_20,cultural_tourist_w_10,cultural_tourist_w_15,cultural_tourist_w_20,"
            "routing_status,distance_crs_epsg) VALUES "
            "(:snapshot,:listing_id,:network,:taxonomy,:speed,:snapped_node_id,:snap_distance_m,"
            ":nearest_station_key,:nearest_station_network_distance_m,:nearest_station_walking_minutes,"
            ":nearest_station_coverage_complete,:food_social_w_10,:food_social_w_15,:food_social_w_20,"
            ":cultural_tourist_w_10,:cultural_tourist_w_15,:cultural_tourist_w_20,:routing_status,:crs)"
        ), [{**row, "network": network_id, "snapshot": SNAPSHOT, "taxonomy": TAXONOMY_VERSION,
             "speed": WALK_SPEED_KMH, "crs": METRIC_EPSG} for row in routes])
        n = conn.scalar(text(
            "SELECT count(*) FROM features.walking_accessibility WHERE snapshot_date=:snapshot"
        ), {"snapshot": SNAPSHOT})
        if n != len(listings):
            raise RuntimeError("Walking feature row count differs from clean listings")


def main() -> None:
    archive = existing_archive()
    if archive is None or not (archive / PBF_NAME).is_file():
        raise FileNotFoundError("Run `make phase5-acquire` before Phase 6")
    source_path = archive / PBF_NAME
    started = time.monotonic()
    engine = get_engine()
    try:
        migrate(engine)
        source_hash = sha256_file(source_path)
        with engine.connect() as conn:
            source = conn.execute(text(
                "SELECT source_file_id,trim(file_hash_sha256),source_date FROM meta.source_files "
                "WHERE relative_path=:path"
            ), {"path": source_path.relative_to(PROJECT_ROOT).as_posix()}).one()
        if source is None or source[1] != source_hash:
            raise RuntimeError("Phase 5 PBF is not hash-verified in meta.source_files")
        source_id, _, source_date = source
        network_id = f"{FILTER_VERSION}_{source_hash[:16]}"
        graph_started = time.monotonic()
        graph, coordinates, metric, edges, components, graph_stats = build_graph(source_path)
        graph_stats["graph_build_seconds"] = round(time.monotonic()-graph_started, 2)
        print(json.dumps({"graph": graph_stats}, indent=2), flush=True)
        import_stats = persist_graph(engine, network_id, source_id, source_hash, source_date,
                                     coordinates, metric, edges, components, graph_stats)
        print(json.dumps({"database_graph": import_stats}, indent=2), flush=True)
        listings, destinations = read_entities(engine, source_id)
        snap_stats = snap_entities(metric, components, listings, destinations)
        print(json.dumps({"snaps": snap_stats}, indent=2), flush=True)
        routes, route_stats = route_all(graph, listings, destinations)
        print(json.dumps({"routing": route_stats}, indent=2), flush=True)
        persist_snaps_features(engine, network_id, listings, destinations, routes)
        print(json.dumps({"network_id": network_id, "total_seconds": round(time.monotonic()-started, 2)},
                         indent=2), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

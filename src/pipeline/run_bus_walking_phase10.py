"""Conservative bus-stop deduplication and nearest-stop walking sensitivity.

Reuses the *persisted* Phase 6 pedestrian edges and listing snaps, with their
EPSG:25832 metre lengths, rather than constructing a different network.
Nothing here changes Phase 9 station or bus-proximity tables.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT, sha256_file, write_json
from src.spatial.walking_network import METRES_PER_MINUTE


VERSION = "bus_walk_v1"


def normalise_name(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", str(value)).casefold()
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in value if not unicodedata.combining(c)))


def deduplicate(stops: pd.DataFrame) -> list[tuple[str, int]]:
    """Merge only co-located same-name OSM objects (<3m), not route directions.

    Unnamed objects merge only if within 0.5m. Deterministic canonical key is
    lexical minimum in each group. Opposite carriageway/platform objects stay
    separate unless effectively co-located.
    """
    xy = stops[["x", "y"]].to_numpy(float)
    names = [normalise_name(tag.get("name")) for tag in stops["tags"]]
    parent = list(range(len(stops)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in sorted(cKDTree(xy).query_pairs(r=3.0)):
        same_name = names[a] and names[a] == names[b]
        unnamed_exact = not names[a] and not names[b] and np.linalg.norm(xy[a] - xy[b]) <= .5
        if same_name or unnamed_exact:
            parent[root(b)] = root(a)
    groups = defaultdict(list)
    for i in range(len(stops)):
        groups[root(i)].append(i)
    return sorted((min(str(stops.iloc[j]["bus_stop_key"]) for j in members), len(members))
                  for members in groups.values())


def _node_graph(conn, network_id: str, node_ids: np.ndarray) -> csr_matrix:
    edges = pd.read_sql(text(
        "SELECT from_node_id,to_node_id,length_m,forward_allowed,reverse_allowed "
        "FROM spatial.walking_edges WHERE network_id=:network"
    ), conn, params={"network": network_id})
    u = np.searchsorted(node_ids, edges["from_node_id"].to_numpy(np.int64))
    v = np.searchsorted(node_ids, edges["to_node_id"].to_numpy(np.int64))
    length = edges["length_m"].to_numpy(float)
    forward = edges["forward_allowed"].to_numpy(bool)
    reverse = edges["reverse_allowed"].to_numpy(bool)
    n = len(node_ids)
    # Reverse original directed arcs. Super-source -> bus snap node connector.
    rows = np.concatenate([v[forward], u[reverse]])
    cols = np.concatenate([u[forward], v[reverse]])
    weight = np.concatenate([length[forward], length[reverse]])
    arcs = pd.DataFrame({"row": rows, "col": cols, "weight": weight})
    arcs = arcs.groupby(["row", "col"], sort=False, as_index=False)["weight"].min()
    return csr_matrix((arcs["weight"].to_numpy(float),
                       (arcs["row"].to_numpy(int), arcs["col"].to_numpy(int))),
                      shape=(n + 1, n + 1))


def run() -> dict:
    engine = get_engine()
    try:
        migrate(engine)
        with engine.connect() as conn:
            network = conn.execute(text("SELECT network_id,node_count FROM spatial.walking_networks")).one()
            source = conn.execute(text(
                "SELECT DISTINCT s.source_file_id,f.relative_path,f.file_hash_sha256 "
                "FROM spatial.bus_stops s JOIN meta.source_files f USING(source_file_id)"
            )).one()
            if len(conn.execute(text("SELECT DISTINCT source_file_id FROM spatial.bus_stops")).all()) != 1:
                raise RuntimeError("Bus-stop source changed")
            if sha256_file(PROJECT_ROOT / source.relative_path) != source.file_hash_sha256:
                raise RuntimeError("Immutable Phase 5 OSM PBF hash mismatch")
            stops = pd.read_sql(text(
                "SELECT bus_stop_key,tags,ST_X(geom_25832) x,ST_Y(geom_25832) y "
                "FROM spatial.bus_stops ORDER BY bus_stop_key"
            ), conn)
            nodes = pd.read_sql(text(
                "SELECT osm_node_id,ST_X(geom_25832) x,ST_Y(geom_25832) y "
                "FROM spatial.walking_nodes WHERE network_id=:network ORDER BY osm_node_id"
            ), conn, params={"network": network.network_id})
            listing = pd.read_sql(text(
                "SELECT l.snapshot_date,l.listing_id,s.snapped_node_id,s.snap_distance_m,"
                "ST_X(l.geom_25832) x,ST_Y(l.geom_25832) y "
                "FROM clean.airbnb_listings l JOIN features.walking_listing_snaps s "
                "USING(snapshot_date,listing_id) WHERE s.network_id=:network "
                "ORDER BY l.snapshot_date,l.listing_id"
            ), conn, params={"network": network.network_id})
        if len(nodes) != network.node_count or len(listing) != 23144:
            raise RuntimeError("Persisted pedestrian network or listing snaps incomplete")
        canonical = deduplicate(stops)
        with engine.connect() as conn:
            existing_canonical = conn.execute(text(
                "SELECT count(*) n,count(*) FILTER(WHERE dedup_version<>:version) wrong_version "
                "FROM spatial.bus_stops_canonical"
            ), {"version": VERSION}).one()
            existing_features = conn.execute(text(
                "SELECT count(*) n,count(*) FILTER(WHERE dedup_version<>:version "
                "OR network_id<>:network OR distance_crs_epsg<>25832 OR walking_speed_kmh<>4.80) wrong_version "
                "FROM features.bus_accessibility"
            ), {"version": VERSION, "network": network.network_id}).one()
        if (existing_canonical.n or existing_features.n) and (
                existing_canonical.n != len(canonical) or existing_features.n != len(listing)
                or existing_canonical.wrong_version or existing_features.wrong_version):
            raise RuntimeError("Existing Phase 10 bus tables differ or are partial; refusing overwrite")
        chosen = stops.set_index("bus_stop_key").loc[[key for key, _ in canonical]].reset_index()
        node_ids = nodes["osm_node_id"].to_numpy(np.int64)
        node_xy = nodes[["x", "y"]].to_numpy(float)
        snap_m, snap_idx = cKDTree(node_xy).query(chosen[["x", "y"]].to_numpy(float))
        graph = None
        with engine.connect() as conn:
            graph = _node_graph(conn, network.network_id, node_ids)
        n = len(node_ids)
        src_idx = np.full(len(chosen), n, dtype=np.int64)
        # Sparse duplicate snap nodes keep the minimum connector; canonical
        # destination identity is recovered deterministically from that node.
        snap_best = {}
        for key, idx, connector in zip(chosen["bus_stop_key"], snap_idx, snap_m):
            if idx not in snap_best or connector < snap_best[idx][1]:
                snap_best[idx] = (key, float(connector))
        unique_idx = np.fromiter(snap_best, dtype=np.int64)
        unique_m = np.array([snap_best[idx][1] for idx in unique_idx])
        source_arcs = csr_matrix((unique_m + 1e-7,
                                  (np.full(len(unique_idx), n), unique_idx)),
                                 shape=(n + 1, n + 1))
        graph = graph + source_arcs
        distance, predecessor = dijkstra(graph, directed=True, indices=n, return_predecessors=True)

        def destination(index: int):
            traversed = 0
            while index >= 0 and index != n and traversed < n:
                parent = int(predecessor[index])
                if parent == n:
                    return snap_best.get(index, (None, None))
                index = parent
                traversed += 1
            return None, None

        eu_m, eu_idx = cKDTree(chosen[["x", "y"]].to_numpy(float)).query(listing[["x", "y"]].to_numpy(float))
        rows = []
        for i, item in listing.iterrows():
            near_key = chosen.iloc[int(eu_idx[i])]["bus_stop_key"] if np.isfinite(eu_m[i]) else None
            node = item["snapped_node_id"]
            if pd.isna(node):
                status, walk_m, walk_key, stop_snap = "no_walk_node", None, None, None
            else:
                idx = int(np.searchsorted(node_ids, int(node)))
                if idx >= n or node_ids[idx] != int(node) or not np.isfinite(distance[idx]):
                    status, walk_m, walk_key, stop_snap = "no_reachable_bus_stop", None, None, None
                else:
                    walk_key, stop_snap = destination(idx)
                    walk_m = float(distance[idx] + item["snap_distance_m"])
                    status = "ok" if walk_key else "no_reachable_bus_stop"
            rows.append({"snapshot": item["snapshot_date"], "id": int(item["listing_id"]),
                         "network": network.network_id, "version": VERSION,
                         "eu_key": near_key, "eu_m": float(eu_m[i]) if np.isfinite(eu_m[i]) else None,
                         "walk_key": walk_key, "walk_m": walk_m,
                         "walk_min": walk_m / METRES_PER_MINUTE if walk_m is not None else None,
                         "stop_snap": stop_snap, "status": status})
        with engine.begin() as conn:
            existing = conn.scalar(text("SELECT count(*) FROM features.bus_accessibility"))
            if existing:
                if existing != len(rows):
                    raise RuntimeError("Existing bus accessibility is partial; refusing overwrite")
            else:
                conn.execute(text(
                    "INSERT INTO spatial.bus_stops_canonical(bus_stop_key,dedup_version,duplicate_count,geom_25832) "
                    "SELECT s.bus_stop_key,:version,:count,s.geom_25832 FROM spatial.bus_stops s "
                    "WHERE s.bus_stop_key=:key"
                ), [{"key": key, "count": count, "version": VERSION} for key, count in canonical])
                conn.execute(text(
                    "INSERT INTO features.bus_accessibility(snapshot_date,listing_id,network_id,dedup_version,"
                    "nearest_euclidean_stop_key,bus_distance_euclidean_m,nearest_walking_stop_key,"
                    "bus_walk_distance_m,bus_walk_time_min,bus_stop_snap_distance_m,routing_status,"
                    "distance_crs_epsg,walking_speed_kmh) VALUES "
                    "(:snapshot,:id,:network,:version,:eu_key,:eu_m,:walk_key,:walk_m,:walk_min,"
                    ":stop_snap,:status,25832,4.80)"
                ), rows)
        primary = pd.DataFrame(rows)
        metadata = {"version": VERSION, "source_sha256": source.file_hash_sha256,
                    "source_date": "2026-09-26", "acquisition_date": "2026-09-29",
                    "tag_selection": "highway=bus_stop OR public_transport=platform AND bus=yes",
                    "study_extent": "Phase 5 BBBike Copenhagen buffered extract; unchanged",
                    "raw_bus_objects": len(stops), "canonical_stops": len(canonical),
                    "co_located_duplicates": len(stops) - len(canonical),
                    "dedup_rule": "same normalised name within 3m; both unnamed within 0.5m; preserve directions otherwise",
                    "network_id": network.network_id, "network_nodes": n,
                    "listings": len(rows), "unreachable": int((primary["status"] != "ok").sum()),
                    "bus_snap_median_m": float(np.median(snap_m)),
                    "bus_snap_over_100m": int((snap_m > 100).sum()),
                    "bus_snap_over_250m": int((snap_m > 250).sum()),
                    "crs_epsg": 25832, "walking_speed_kmh": 4.8,
                    "algorithm": "reverse directed sparse Dijkstra from super-source; source connector + path + listing connector"}
        write_json(PROJECT_ROOT / "outputs/tables/phase10/bus_feature_metadata.json", metadata)
        return metadata
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

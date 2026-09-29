"""NetworkX-backed, destination-preserving pedestrian accessibility algorithms."""

from __future__ import annotations

import heapq
from bisect import bisect_right
from collections import defaultdict

import networkx as nx

from src.spatial.walking_network import RADII_M


def station_distance_labels(graph: nx.DiGraph, station_snaps: list[dict]):
    """One reverse multi-source Dijkstra with station connector costs.

    For every node, return the minimum walking metres to a station point and
    the exact canonical station key. Directional pedestrian restrictions apply.
    """
    best_distance: dict[int, float] = {}
    best_key: dict[int, str] = {}
    queue = []
    for station in station_snaps:
        node, distance, key = station["snapped_node_id"], station["snap_distance_m"], station["destination_key"]
        if distance < best_distance.get(node, float("inf")):
            best_distance[node] = distance
            best_key[node] = key
            heapq.heappush(queue, (distance, node, key))
    while queue:
        distance, node, key = heapq.heappop(queue)
        if distance != best_distance[node] or key != best_key[node]:
            continue
        for predecessor, attributes in graph.pred[node].items():
            proposed = distance + attributes["length_m"]
            if proposed < best_distance.get(predecessor, float("inf")):
                best_distance[predecessor] = proposed
                best_key[predecessor] = key
                heapq.heappush(queue, (proposed, predecessor, key))
    return best_distance, best_key


def grouped_opportunities(graph: nx.DiGraph, listing_snaps: list[dict], poi_snaps: list[dict]):
    """One cutoff Dijkstra per snapped listing node; no all-pairs matrix.

    A path costs listing connector + network edges + destination connector.
    Distinct canonical POIs are counted even if several snap to one node.
    """
    destinations: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for poi in poi_snaps:
        destinations[poi["snapped_node_id"]].append((poi["category"], poi["snap_distance_m"]))
    origins: dict[int, list[dict]] = defaultdict(list)
    for listing in listing_snaps:
        if listing["snapped_node_id"] is not None:
            origins[listing["snapped_node_id"]].append(listing)
    result = {}
    explored_total = 0
    for origin, group in origins.items():
        max_cutoff = max(0.0, RADII_M[-1] - min(item["snap_distance_m"] for item in group))
        reached = nx.single_source_dijkstra_path_length(graph, origin, cutoff=max_cutoff, weight="length_m")
        explored_total += len(reached)
        arrivals: dict[str, list[float]] = {"food_social": [], "cultural_tourist": []}
        for node, path_metres in reached.items():
            for category, destination_snap in destinations.get(node, ()):
                arrivals[category].append(path_metres + destination_snap)
        for values in arrivals.values():
            values.sort()
        for item in group:
            connector = item["snap_distance_m"]
            result[item["listing_id"]] = {
                (category, radius): bisect_right(values, radius - connector)
                for category, values in arrivals.items() for radius in RADII_M
            }
    return result, {"unique_origin_nodes": len(origins), "dijkstra_nodes_explored": explored_total}

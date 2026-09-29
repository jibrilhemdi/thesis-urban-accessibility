"""Reproducible pedestrian graph from an immutable OSM PBF.

Topology uses original OSM node IDs, so coincident bridge/underpass coordinates
are not incorrectly connected. Edge weights are projected EPSG:25832 metres.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import osmium
from pyproj import Transformer


FILTER_VERSION = "walk_phase06_v1"
METRIC_EPSG = 25832
WALK_SPEED_KMH = 4.8
METRES_PER_MINUTE = WALK_SPEED_KMH * 1000 / 60
RADII_M = (800, 1200, 1600)
LARGE_SNAP_M = 100.0
SEVERE_SNAP_M = 250.0

# Pedestrian-permitted highway classes; conservative treatment of cycleways
# and bridleways. Explicit foot/access restrictions supersede defaults.
DEFAULT_WALK = frozenset({
    "footway", "pedestrian", "path", "steps", "living_street", "residential",
    "service", "unclassified", "tertiary", "tertiary_link", "secondary",
    "secondary_link", "primary", "primary_link", "track", "road", "platform",
})
EXPLICIT_WALK_ONLY = frozenset({"cycleway", "bridleway", "busway"})
FORBIDDEN_HIGHWAYS = frozenset({
    "motorway", "motorway_link", "trunk", "trunk_link", "raceway", "construction",
    "proposed", "abandoned", "corridor", "escape",
})
PERMITTED_FOOT = frozenset({"yes", "designated", "permissive", "official"})
DENIED_FOOT = frozenset({"no", "private", "restricted"})


def walking_directions(tags: dict[str, str]) -> tuple[bool, bool]:
    """Return forward/backward pedestrian permissions for an OSM way."""
    highway = tags.get("highway", "")
    if not highway or highway in FORBIDDEN_HIGHWAYS or tags.get("area") == "yes":
        return False, False
    foot = tags.get("foot", "")
    if foot in DENIED_FOOT:
        return False, False
    if tags.get("access") in {"no", "private"} and foot not in PERMITTED_FOOT:
        return False, False
    if highway not in DEFAULT_WALK and not (highway in EXPLICIT_WALK_ONLY and foot in PERMITTED_FOOT):
        return False, False
    forward = tags.get("foot:forward") not in DENIED_FOOT
    backward = tags.get("foot:backward") not in DENIED_FOOT
    foot_oneway = tags.get("oneway:foot", "")
    conveying = tags.get("conveying", "")
    if foot_oneway in {"yes", "1", "true"} or conveying == "forward":
        backward = False
    elif foot_oneway in {"-1", "reverse"} or conveying == "backward":
        forward = False
    # Motor-vehicle oneway=* alone does not impose pedestrian directionality.
    return forward, backward


@dataclass(frozen=True)
class Segment:
    way_id: int
    segment_index: int
    u: int
    v: int
    highway: str
    forward: bool
    reverse: bool


class WalkHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.coordinates: dict[int, tuple[float, float]] = {}
        self.segments: list[Segment] = []
        self.highway_counts = Counter()
        self.excluded_counts = Counter()
        self.missing_location_nodes = 0
        self.included_ways = 0

    def way(self, way) -> None:
        tags = {tag.k: tag.v for tag in way.tags}
        highway = tags.get("highway")
        if not highway:
            return
        forward, reverse = walking_directions(tags)
        if not (forward or reverse):
            self.excluded_counts[highway] += 1
            return
        nodes = []
        for node in way.nodes:
            if not node.location.valid():
                self.missing_location_nodes += 1
                return
            node_id = int(node.ref)
            nodes.append(node_id)
            if node_id not in self.coordinates:
                self.coordinates[node_id] = (node.location.lon, node.location.lat)
        if len(nodes) < 2:
            return
        self.included_ways += 1
        self.highway_counts[highway] += 1
        for index, (u, v) in enumerate(zip(nodes, nodes[1:])):
            if u != v:
                self.segments.append(Segment(int(way.id), index, u, v, highway, forward, reverse))


def build_graph(pbf_path: Path):
    """Parse PBF once, then project unique node coordinates and add directed arcs."""
    handler = WalkHandler()
    handler.apply_file(str(pbf_path), locations=True)
    if handler.missing_location_nodes:
        raise RuntimeError(f"PBF has {handler.missing_location_nodes} walking-way nodes without locations")
    if not handler.segments:
        raise RuntimeError("No pedestrian ways extracted from PBF")
    node_ids = list(handler.coordinates)
    lons, lats = zip(*(handler.coordinates[node] for node in node_ids))
    transformer = Transformer.from_crs(4326, METRIC_EPSG, always_xy=True)
    xs, ys = transformer.transform(lons, lats)
    metric = {node: (float(x), float(y)) for node, x, y in zip(node_ids, xs, ys)}
    graph = nx.DiGraph()
    graph.add_nodes_from(node_ids)
    edges = []
    zero_length = 0
    for segment in handler.segments:
        x1, y1 = metric[segment.u]
        x2, y2 = metric[segment.v]
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 0.01:
            zero_length += 1
            continue
        if segment.forward:
            previous = graph.get_edge_data(segment.u, segment.v)
            if previous is None or length < previous["length_m"]:
                graph.add_edge(segment.u, segment.v, length_m=length)
        if segment.reverse:
            previous = graph.get_edge_data(segment.v, segment.u)
            if previous is None or length < previous["length_m"]:
                graph.add_edge(segment.v, segment.u, length_m=length)
        edges.append((segment, length))
    components = sorted(nx.weakly_connected_components(graph), key=len, reverse=True)
    component_by_node = {node: index + 1 for index, members in enumerate(components) for node in members}
    stats = {
        "network_type": "OSM pedestrian-permitted highway ways; directed foot restrictions",
        "nodes": graph.number_of_nodes(), "directed_arcs": graph.number_of_edges(),
        "source_segments": len(edges), "included_ways": handler.included_ways,
        "weak_components": len(components), "largest_component_nodes": len(components[0]),
        "zero_length_segments": zero_length,
        "highway_way_counts": dict(handler.highway_counts),
        "excluded_way_counts": dict(handler.excluded_counts),
        "crs_epsg": METRIC_EPSG,
    }
    return graph, handler.coordinates, metric, edges, component_by_node, stats

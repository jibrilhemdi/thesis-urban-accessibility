"""Source-preserving secondary bus-stop proximity from the archived Phase 5 PBF.

This is NOT a bus timetable, service frequency, bus trip time, or an amendment
to the canonical rail/metro station destination set. No price enters selection.
"""

from __future__ import annotations

import json

import osmium
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline.acquire_osm_phase5 import existing_archive


VERSION = "bus_stop_proximity_v1"


def selection_rule(tags: dict[str, str]) -> str | None:
    if tags.get("highway") == "bus_stop":
        return "highway=bus_stop"
    if tags.get("public_transport") == "platform" and tags.get("bus") == "yes":
        return "public_transport=platform;bus=yes"
    return None


class BusHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self.missing_way_locations = 0

    def node(self, node) -> None:
        tags = {tag.k: tag.v for tag in node.tags}
        rule = selection_rule(tags)
        if rule and node.location.valid():
            self.rows.append({"key": f"node/{node.id}", "type": "node", "id": int(node.id),
                              "rule": rule, "tags": json.dumps(tags, ensure_ascii=False),
                              "lon": node.location.lon, "lat": node.location.lat})

    def way(self, way) -> None:
        tags = {tag.k: tag.v for tag in way.tags}
        rule = selection_rule(tags)
        if not rule:
            return
        locations = [(part.location.lon, part.location.lat) for part in way.nodes
                     if part.location.valid()]
        if len(locations) != len(way.nodes) or not locations:
            self.missing_way_locations += 1
            return
        self.rows.append({"key": f"way/{way.id}", "type": "way", "id": int(way.id),
                          "rule": rule, "tags": json.dumps(tags, ensure_ascii=False),
                          "lon": sum(point[0] for point in locations) / len(locations),
                          "lat": sum(point[1] for point in locations) / len(locations)})


def run() -> dict:
    archive = existing_archive()
    if archive is None:
        raise RuntimeError("Archived Phase 5 OSM PBF is required; do not use a newer live extract")
    metadata = json.loads((archive / "acquisition_metadata.json").read_text(encoding="utf-8"))
    pbf = archive / "Copenhagen.osm.pbf"
    source_hash = sha256_file(pbf)
    if source_hash != metadata["files"][pbf.name]["sha256"]:
        raise RuntimeError("Immutable OSM PBF hash differs from its acquisition record")
    handler = BusHandler()
    handler.apply_file(str(pbf), locations=True)
    if not handler.rows or handler.missing_way_locations:
        raise RuntimeError("Bus-stop extraction is empty or has unlocated ways")
    engine = get_engine()
    try:
        migrate(engine)
        relative_path = pbf.relative_to(PROJECT_ROOT).as_posix()
        with engine.begin() as conn:
            source = conn.execute(text(
                "SELECT source_file_id,file_hash_sha256 FROM meta.source_files "
                "WHERE relative_path=:path"
            ), {"path": relative_path}).one_or_none()
            if source is None or source.file_hash_sha256 != source_hash:
                raise RuntimeError("Bus extraction PBF is not registered with its verified SHA-256")
            existing = conn.scalar(text("SELECT count(*) FROM spatial.bus_stops"))
            if existing:
                if existing != len(handler.rows) or conn.scalar(text(
                    "SELECT count(*) FROM spatial.bus_stops WHERE source_file_id<>:source "
                    "OR taxonomy_version<>:version"
                ), {"source": source.source_file_id, "version": VERSION}):
                    raise RuntimeError("Existing bus stop table differs; refusing overwrite")
            else:
                conn.execute(text(
                    "INSERT INTO spatial.bus_stops "
                    "(bus_stop_key,source_file_id,taxonomy_version,osm_object_type,osm_id,"
                    "selection_rule,tags,geom,geom_25832) "
                    "SELECT :key,:source,:version,:type,:id,:rule,CAST(:tags AS jsonb),"
                    "ST_SetSRID(ST_MakePoint(:lon,:lat),4326),"
                    "ST_Transform(ST_SetSRID(ST_MakePoint(:lon,:lat),4326),25832)"
                ), [{**row, "source": source.source_file_id, "version": VERSION}
                    for row in handler.rows])
            feature_n = conn.scalar(text("SELECT count(*) FROM features.bus_stop_proximity"))
            listing_n = conn.scalar(text("SELECT count(*) FROM clean.airbnb_listings"))
            if feature_n:
                if feature_n != listing_n or conn.scalar(text(
                    "SELECT count(*) FROM features.bus_stop_proximity "
                    "WHERE source_file_id<>:source OR taxonomy_version<>:version"
                ), {"source": source.source_file_id, "version": VERSION}):
                    raise RuntimeError("Existing bus proximity features differ; refusing overwrite")
            else:
                conn.execute(text(
                    "INSERT INTO features.bus_stop_proximity "
                    "(snapshot_date,listing_id,source_file_id,taxonomy_version,"
                    "nearest_bus_stop_key,nearest_bus_stop_euclidean_m,distance_crs_epsg) "
                    "SELECT l.snapshot_date,l.listing_id,:source,:version,b.bus_stop_key,b.distance_m,25832 "
                    "FROM clean.airbnb_listings l "
                    "LEFT JOIN LATERAL (SELECT bus_stop_key,"
                    "ST_Distance(geom_25832,l.geom_25832) AS distance_m "
                    "FROM spatial.bus_stops ORDER BY geom_25832 <-> l.geom_25832 LIMIT 1) b "
                    "ON l.valid_coordinates"
                ), {"source": source.source_file_id, "version": VERSION})
            qa = conn.execute(text(
                "SELECT count(*) n,count(*) FILTER (WHERE b.nearest_bus_stop_euclidean_m IS NULL) missing_n,"
                "count(*) FILTER (WHERE b.nearest_bus_stop_euclidean_m > e.source_edge_distance_m) edge_n,"
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY b.nearest_bus_stop_euclidean_m) median_m "
                "FROM features.bus_stop_proximity b "
                "JOIN features.euclidean_accessibility e USING(snapshot_date,listing_id)"
            )).mappings().one()
            if qa["n"] != listing_n or qa["edge_n"]:
                raise RuntimeError("Bus proximity row or source-edge coverage QA failed")
            return {"source_sha256": source_hash, "taxonomy_version": VERSION,
                    "bus_stop_objects": len(handler.rows), "listing_features": int(qa["n"]),
                    "missing_distance": int(qa["missing_n"]),
                    "beyond_source_edge": int(qa["edge_n"]),
                    "median_distance_m": float(qa["median_m"]),
                    "crs_epsg": 25832}
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

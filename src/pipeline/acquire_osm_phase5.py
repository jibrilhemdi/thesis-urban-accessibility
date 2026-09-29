"""Archive BBBike's Copenhagen OSM PBF after verifying 1,600 m listing coverage."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, USER_AGENT
from src.pipeline.osm_taxonomy_phase5 import TAXONOMY_VERSION


BASE_URL = "https://download3.bbbike.org/osm/bbbike/Copenhagen"
PBF_NAME = "Copenhagen.osm.pbf"
POLY_NAME = "Copenhagen.poly"
MAX_COUNT_RADIUS_METRES = 1600
ARCHIVE_ROOT = PROJECT_ROOT / "data/raw/osm/phase05"


def existing_archive():
    """Reuse exactly one archived city extract rather than silently switching vintages."""
    archives = sorted(path.parent for path in ARCHIVE_ROOT.glob("*/acquisition_metadata.json"))
    if len(archives) > 1:
        raise RuntimeError("Multiple Phase 5 OSM archives; select a source/version explicitly")
    return archives[0] if archives else None


def polygon_wkt(poly_text: str) -> str:
    lines = [line.strip() for line in poly_text.splitlines()]
    points = []
    for line in lines[2:]:
        if line.upper() == "END":
            break
        lon, lat = (float(value) for value in line.split()[:2])
        points.append((lon, lat))
    if len(points) < 3:
        raise ValueError("Unexpected BBBike Copenhagen polygon format")
    if points[0] != points[-1]:
        points.append(points[0])
    return "POLYGON((" + ",".join(f"{lon} {lat}" for lon, lat in points) + "))"


def validate_listing_coverage(poly_text: str) -> dict:
    wkt = polygon_wkt(poly_text)
    engine = get_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "WITH p AS (SELECT ST_Transform(ST_GeomFromText(:wkt,4326),25832) AS geom) "
                "SELECT count(*) AS listings,"
                "count(*) FILTER (WHERE l.valid_coordinates AND NOT "
                "ST_Covers(p.geom,ST_Buffer(l.geom_25832,:radius))) AS insufficient_1600m,"
                "count(*) FILTER (WHERE l.primary_sample_candidate AND NOT "
                "ST_Covers(p.geom,ST_Buffer(l.geom_25832,:radius))) AS primary_insufficient_1600m "
                "FROM clean.airbnb_listings l CROSS JOIN p"
            ), {"wkt": wkt, "radius": MAX_COUNT_RADIUS_METRES}).mappings().one()
    finally:
        engine.dispose()
    result = dict(row)
    if result["insufficient_1600m"]:
        raise ValueError("BBBike city extract does not cover every listing's 1,600 m radius")
    return result


def acquire() -> str:
    now = datetime.now(timezone.utc)
    directory = existing_archive() or ARCHIVE_ROOT / now.date().isoformat()
    metadata_path = directory / "acquisition_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        # Taxonomy can be revised before modelling without re-downloading the PBF.
        for name in (PBF_NAME, POLY_NAME):
            path = directory / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != metadata["files"][name]["sha256"]:
                raise ValueError(f"Archived Phase 5 raw file changed or is missing: {path}")
        validate_listing_coverage((directory / POLY_NAME).read_text(encoding="utf-8"))
        return str(directory)
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Incomplete/nonempty Phase 5 raw archive; inspect before retry: {directory}")

    requests = {}
    for name in (POLY_NAME, PBF_NAME):
        url = f"{BASE_URL}/{name}"
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=180) as response:
            payload = response.read()
            headers = {"last_modified": response.headers.get("Last-Modified"),
                       "etag": response.headers.get("ETag")}
        if name == POLY_NAME:
            coverage = validate_listing_coverage(payload.decode("utf-8"))
        elif len(payload) < 1000000:
            raise ValueError("Unexpectedly small BBBike PBF response")
        requests[name] = {"payload": payload, "url": url, **headers}

    metadata = {
        "acquired_at_utc": now.isoformat(),
        "source": "OpenStreetMap Copenhagen city extract via BBBike",
        "source_page": f"{BASE_URL}/",
        "license": "Open Database License (ODbL); © OpenStreetMap contributors",
        "taxonomy_version": TAXONOMY_VERSION,
        "study_extent": "Copenhagen and Frederiksberg listings; source boundary in Copenhagen.poly",
        "coverage_qa": coverage,
        "python_version": platform.python_version(),
        "gdal_version": subprocess.check_output(["ogrinfo", "--version"], text=True).strip(),
        "files": {},
    }
    for name, record in requests.items():
        payload = record["payload"]
        metadata["files"][name] = {
            "source_url": record["url"], "acquired_at_utc": now.isoformat(),
            "source_date": (parsedate_to_datetime(record["last_modified"]).date().isoformat()
                            if record["last_modified"] else None),
            "geographic_extent": "BBBike Copenhagen extract polygon; see Copenhagen.poly",
            "source_crs": "OSM WGS84 longitude/latitude (EPSG:4326)",
            "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload),
            "http_last_modified": record["last_modified"], "http_etag": record["etag"],
        }
    directory.mkdir(parents=True, exist_ok=False)
    for name, record in requests.items():
        with (directory / name).open("xb") as handle:
            handle.write(record["payload"])
    with metadata_path.open("x", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return str(directory)


if __name__ == "__main__":
    print(acquire())

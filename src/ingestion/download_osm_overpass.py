"""Extract Copenhagen OSM walking-network and POI data via Overpass.

The bounding box is derived from the downloaded Inside Airbnb detailed listings
and expanded by a small buffer. Exact queries are saved with the responses.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from common import PROJECT_ROOT, USER_AGENT, sha256_bytes, sha256_file, update_manifest, utc_now, write_json


DEFAULT_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("SOUTH", "WEST", "NORTH", "EAST"))
    parser.add_argument("--margin", type=float, default=0.02, help="Degree margin when deriving the bbox from listings.")
    parser.add_argument("--retrieval-date", default=date.today().isoformat())
    parser.add_argument("--force", action="store_true", help="Re-query Overpass if raw responses already exist.")
    parser.add_argument("--endpoint", action="append", dest="endpoints", help="Overpass endpoint; may be supplied more than once.")
    return parser.parse_args()


def latest_listings_file() -> Path:
    candidates = sorted(
        (PROJECT_ROOT / "data" / "raw" / "inside_airbnb" / "copenhagen").glob("*/data/listings.csv.gz")
    )
    if not candidates:
        raise FileNotFoundError(
            "No detailed Inside Airbnb listings found. Run download_inside_airbnb.py before the OSM extraction."
        )
    return candidates[-1]


def listing_bbox(path: Path, margin: float) -> tuple[float, float, float, float]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = {field.strip().lower(): field for field in (reader.fieldnames or [])}
        lat_key = fields.get("latitude")
        lon_key = fields.get("longitude")
        if not lat_key or not lon_key:
            raise ValueError(f"Could not find latitude/longitude in {path}")

        latitudes: list[float] = []
        longitudes: list[float] = []
        for row in reader:
            try:
                lat = float(row[lat_key])
                lon = float(row[lon_key])
            except (TypeError, ValueError):
                continue
            if math.isfinite(lat) and math.isfinite(lon):
                latitudes.append(lat)
                longitudes.append(lon)

    if not latitudes:
        raise ValueError(f"No valid coordinates found in {path}")
    return (
        min(latitudes) - margin,
        min(longitudes) - margin,
        max(latitudes) + margin,
        max(longitudes) + margin,
    )


def format_bbox(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    return ",".join(f"{value:.6f}" for value in (south, west, north, east))


def query_texts(bbox: tuple[float, float, float, float]) -> dict[str, str]:
    box = format_bbox(bbox)
    network = f'''[out:json][timeout:300];
(
  way["highway"]["highway"!~"^(motorway|motorway_link|trunk|trunk_link)$"]({box});
);
out body;
>;
out skel qt;
'''
    pois = f'''[out:json][timeout:300];
(
  nwr["amenity"~"^(restaurant|cafe|bar|fast_food|pub|marketplace|supermarket|pharmacy|hospital|clinic|school|university|library|theatre|cinema|place_of_worship|bank|post_office)$"]({box});
  nwr["tourism"]({box});
  nwr["leisure"~"^(park|garden|playground|sports_centre|stadium|pitch)$"]({box});
  nwr["shop"]({box});
  nwr["public_transport"]({box});
  nwr["railway"~"^(station|halt|tram_stop|subway_entrance|stop)$"]({box});
);
out center tags;
'''
    return {"walking_network": network, "amenities_and_transport": pois}


def fetch_overpass(query: str, endpoints: list[str], *, force: bool) -> tuple[bytes, str]:
    body = urlencode({"data": query}).encode("utf-8")
    errors: list[str] = []
    for endpoint in endpoints:
        request = Request(
            endpoint,
            data=body,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=360) as response:
                payload = response.read()
            json.loads(payload)
            return payload, endpoint
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            errors.append(f"{endpoint}: {exc}")
            if not force:
                continue
    raise RuntimeError("All Overpass endpoints failed:\n" + "\n".join(errors))


def save_query(path: Path, text: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "local_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "status": "created",
    }


def main() -> None:
    args = parse_args()
    bbox_source = None
    if args.bbox:
        bbox = tuple(args.bbox)  # type: ignore[assignment]
    else:
        bbox_source = latest_listings_file()
        bbox = listing_bbox(bbox_source, args.margin)

    endpoints = args.endpoints or DEFAULT_ENDPOINTS
    raw_root = PROJECT_ROOT / "data" / "raw" / "osm" / "copenhagen" / args.retrieval_date
    query_root = raw_root / "queries"
    response_root = raw_root / "responses"
    texts = query_texts(bbox)
    query_entries = []
    manifest_entries = []
    response_meta: dict[str, Any] = {}

    print(f"OSM bbox (south, west, north, east): {format_bbox(bbox)}")
    if bbox_source:
        print(f"Derived from: {bbox_source.relative_to(PROJECT_ROOT)}")

    for name, query in texts.items():
        query_path = query_root / f"{name}.overpassql"
        query_entries.append(save_query(query_path, query))
        response_path = response_root / f"{name}.json"
        if response_path.exists() and not args.force:
            payload = response_path.read_bytes()
            endpoint = "existing local response"
            status = "already_present"
        else:
            print(f"Querying Overpass for {name}…")
            payload, endpoint = fetch_overpass(query, endpoints, force=args.force)
            response_path.parent.mkdir(parents=True, exist_ok=True)
            response_path.write_bytes(payload)
            status = "downloaded"
        parsed = json.loads(payload)
        response_meta[name] = {
            "endpoint": endpoint,
            "status": status,
            "elements": len(parsed.get("elements", [])),
            "osm_timestamp": parsed.get("osm3s", {}).get("timestamp_osm_base"),
            "sha256": sha256_bytes(payload),
            "size_bytes": len(payload),
        }
        manifest_entries.append(
            {
                "provider": "OpenStreetMap via Overpass API",
                "asset": name,
                "source_url": endpoint,
                "local_path": response_path.relative_to(PROJECT_ROOT).as_posix(),
                "downloaded_at_utc": utc_now(),
                "size_bytes": len(payload),
                "sha256": sha256_bytes(payload),
                "status": status,
                "osm_timestamp": parsed.get("osm3s", {}).get("timestamp_osm_base"),
            }
        )
        print(f"  -> {status}: {len(parsed.get('elements', [])):,} elements; sha256={sha256_bytes(payload)[:16]}…")

    manifest_entries.extend(
        {
            "provider": "OpenStreetMap via Overpass API",
            "asset": "query",
            "source_url": "https://overpass-api.de/",
            **entry,
        }
        for entry in query_entries
    )
    update_manifest(manifest_entries)
    metadata = {
        "provider": "OpenStreetMap via Overpass API",
        "study_area": "Copenhagen, Denmark",
        "retrieved_at_utc": utc_now(),
        "retrieval_date": args.retrieval_date,
        "bbox_south_west_north_east": list(bbox),
        "bbox_source": bbox_source.relative_to(PROJECT_ROOT).as_posix() if bbox_source else "command line",
        "bbox_margin_degrees": args.margin if not args.bbox else 0,
        "endpoints_tried": endpoints,
        "license": "Open Database License (ODbL); © OpenStreetMap contributors",
        "query_files": [entry["local_path"] for entry in query_entries],
        "responses": response_meta,
        "notes": [
            "The walking-network response contains OSM highway ways and their referenced nodes.",
            "The amenities_and_transport response uses a documented tag taxonomy and includes node/way/relation centers.",
            "Do not interpret OSM tag absence as absence of an amenity; coverage and tagging vary spatially.",
        ],
    }
    write_json(raw_root / "extraction_metadata.json", metadata)
    print(f"\nSaved OSM metadata to {raw_root.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

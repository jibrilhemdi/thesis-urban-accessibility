"""Archive official boundary API responses once; never overwrite raw files."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from src.ingestion.common import PROJECT_ROOT


SOURCES = {
    "copenhagen_municipality.geojson": (
        "https://api.dataforsyningen.dk/kommuner/0101?format=geojson", "0101"
    ),
    "frederiksberg_municipality.geojson": (
        "https://api.dataforsyningen.dk/kommuner/0147?format=geojson", "0147"
    ),
    "copenhagen_districts.geojson": (
        "https://wfs-kbhkort.kk.dk/k101/ows?service=WFS&version=1.0.0&request=GetFeature"
        "&typeName=k101:bydel&outputFormat=json&SRSNAME=EPSG:4326", "bydel"
    ),
}


def acquire() -> Path:
    now = datetime.now(timezone.utc)
    directory = PROJECT_ROOT / "data/raw/official_boundaries" / now.date().isoformat()
    metadata_path = directory / "acquisition_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for name, info in metadata["files"].items():
            path = directory / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
                raise ValueError(f"Archived boundary source changed or is missing: {path}")
        return directory
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Incomplete/nonempty raw archive; inspect before retry: {directory}")

    payloads = {}
    metadata = {"acquired_at_utc": now.isoformat(), "files": {}}
    for name, (url, expected) in SOURCES.items():
        with urlopen(Request(url, headers={"User-Agent": "thesis-urban-accessibility/phase4"}), timeout=45) as response:
            payload = response.read()
        data = json.loads(payload)
        if expected == "bydel":
            features = data.get("features", [])
            codes = [f.get("properties", {}).get("bydel_nr") for f in features]
            if data.get("type") != "FeatureCollection" or sorted(codes) != list(range(1, 11)):
                raise ValueError("Official Copenhagen WFS did not return exactly ten numbered districts")
            source_date = None  # WFS feature response does not supply a district vintage.
        else:
            if data.get("type") != "Feature" or data.get("properties", {}).get("kode") != expected:
                raise ValueError(f"Unexpected municipality feature for {expected}")
            source_date = data["properties"].get("geo_ændret", "")[:10] or None
        for feature in features if expected == "bydel" else [data]:
            if feature.get("geometry", {}).get("type") != "MultiPolygon":
                raise ValueError(f"Unexpected geometry type in {name}")
        payloads[name] = payload
        metadata["files"][name] = {
            "source_url": url,
            "source_date": source_date,
            "acquired_at_utc": now.isoformat(),
            "source_crs": "EPSG:4326 requested from service; GeoJSON longitude/latitude",
            "geographic_extent": "Copenhagen districts" if expected == "bydel" else f"Municipality {expected}",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    directory.mkdir(parents=True, exist_ok=False)
    for name, payload in payloads.items():
        with (directory / name).open("xb") as handle:
            handle.write(payload)
    with metadata_path.open("x", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return directory


if __name__ == "__main__":
    print(acquire())

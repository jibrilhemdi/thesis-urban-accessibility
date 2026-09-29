"""Archive official Capital Region municipality polygons for map context only."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from src.ingestion.common import PROJECT_ROOT


SOURCE_URL = (
    "https://api.dataforsyningen.dk/kommuner?regionskode=1084"
    "&udenforkommuneinddeling=false&format=geojson"
)
SOURCE_NAME = "capital_region_municipalities.geojson"


def acquire() -> str:
    now = datetime.now(timezone.utc)
    directory = PROJECT_ROOT / "data/raw/official_map_context" / now.date().isoformat()
    source_path = directory / SOURCE_NAME
    metadata_path = directory / "acquisition_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_hash = metadata["files"][SOURCE_NAME]["sha256"]
        if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"Archived map-context source changed or is missing: {source_path}")
        return str(directory)
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Incomplete/nonempty raw archive; inspect before retry: {directory}")

    with urlopen(Request(SOURCE_URL, headers={"User-Agent": "thesis-urban-accessibility/phase4"}),
                 timeout=60) as response:
        payload = response.read()
    data = json.loads(payload)
    features = data.get("features", [])
    codes = [feature.get("properties", {}).get("kode") for feature in features]
    if (data.get("type") != "FeatureCollection" or len(features) < 20 or len(codes) != len(set(codes))
            or not {"0101", "0147"}.issubset(codes)
            or any(feature.get("properties", {}).get("udenforkommuneinddeling")
                   or feature.get("geometry", {}).get("type") != "MultiPolygon"
                   for feature in features)):
        raise ValueError("Unexpected Capital Region municipality GeoJSON; review before archiving")

    metadata = {
        "acquired_at_utc": now.isoformat(),
        "files": {SOURCE_NAME: {
            "source_url": SOURCE_URL,
            "acquired_at_utc": now.isoformat(),
            "source_crs": "EPSG:4326 GeoJSON longitude/latitude",
            "geographic_extent": "Capital Region of Denmark; actual municipalities only",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "feature_count": len(features),
            "purpose": "Cartographic context; not study-area membership or analytical covariates",
        }},
    }
    directory.mkdir(parents=True, exist_ok=False)
    with source_path.open("xb") as handle:
        handle.write(payload)
    with metadata_path.open("x", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return str(directory)


if __name__ == "__main__":
    print(acquire())

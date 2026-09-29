"""Pre-model Phase 5 OSM destination taxonomy and deterministic selection rules."""

from __future__ import annotations

import re
import unicodedata


TAXONOMY_VERSION = "phase05_v2"
FOOD_AMENITIES = frozenset({"restaurant", "cafe", "bar", "pub"})
CULTURE_TOURISM = frozenset({"museum", "gallery", "attraction", "viewpoint"})
CULTURE_AMENITIES = frozenset({"theatre"})
CULTURE_HISTORIC = frozenset({"monument", "castle", "palace"})
STATION_RAILWAY = frozenset({"station", "halt"})
STATION_MODES = frozenset({"subway", "light_rail", "train"})

# Same-name duplicates are merged only within these metric radii. Distinct names
# are never merged merely because they occupy the same building or stop complex.
NAME_DEDUP_METRES = {"food_social": 35.0, "cultural_tourist": 60.0, "station": 250.0}
WIKIDATA_DEDUP_METRES = {"food_social": 100.0, "cultural_tourist": 150.0, "station": 500.0}


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = re.sub(r"\b(station|st\.?)\b", "st", normalized)
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def categories(tags: dict) -> tuple[str, ...]:
    selected = []
    if tags.get("amenity") in FOOD_AMENITIES:
        selected.append("food_social")
    if (tags.get("tourism") in CULTURE_TOURISM
            or tags.get("amenity") in CULTURE_AMENITIES
            or tags.get("historic") in CULTURE_HISTORIC):
        selected.append("cultural_tourist")
    if (tags.get("railway") in STATION_RAILWAY
            or (tags.get("public_transport") == "station"
                and (tags.get("train") == "yes" or tags.get("subway") == "yes"
                     or tags.get("station") in STATION_MODES))):
        # Unnamed stops and entrances are not reliable station entities.
        if tags.get("name"):
            selected.append("station")
    return tuple(selected)


def station_mode(tags: dict) -> str:
    if tags.get("station") == "subway" or tags.get("subway") == "yes":
        return "metro"
    if tags.get("station") == "light_rail" or tags.get("network") == "S-tog":
        return "urban_rail"
    return "rail"


def query_text(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    box = ",".join(f"{value:.7f}" for value in (south, west, north, east))
    return ("[out:json][timeout:300];\n(\n"
            f'  nwr["amenity"~"^(restaurant|cafe|bar|pub|theatre)$"]({box});\n'
            f'  nwr["tourism"~"^(museum|gallery|attraction|viewpoint)$"]({box});\n'
            f'  nwr["historic"~"^(monument|memorial|castle|palace)$"]({box});\n'
            f'  nwr["railway"~"^(station|halt)$"]({box});\n'
            f'  nwr["public_transport"="station"]["subway"="yes"]({box});\n'
            f'  nwr["public_transport"="station"]["train"="yes"]({box});\n'
            f'  nwr["public_transport"="station"]["station"~"^(subway|light_rail|train)$"]({box});\n'
            ");\nout center tags;\n")

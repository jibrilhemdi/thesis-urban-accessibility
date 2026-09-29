"""Run the available non-GTFS technical pipeline for Copenhagen.

This module deliberately uses the already cached raw files and only packages
that are present in the base environment. It implements the available minimum
version of section 7 of the research plan:

1. validate the raw source manifest;
2. clean listing outcomes and non-identifying controls;
3. project WGS84 coordinates to an EPSG:25832-compatible metric system;
4. parse the cached OSM walking network and opportunity layer;
5. snap listings and OSM opportunities to the network;
6. compute nearest-category walking times and a small accessibility index;
7. join City of Copenhagen district context and define 11 mixed-scale analysis areas;
8. write a local analytical table and run metadata.

GTFS is recorded as unavailable rather than inferred. Frederiksberg is a single
analysis area, not an official Copenhagen district. Strict district and pooled
mixed-scale context fields remain separate.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import heapq
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from src.ingestion.common import PROJECT_ROOT, sha256_file, utc_now, write_json


WGS84 = "EPSG:4326"
PROJECTED_CRS = "EPSG:25832"
WALK_SPEED_MPS = 1.4
ACCESS_DECAY_PER_MINUTE = 0.10
COPENHAGEN_CENTRE = (12.5683, 55.6761)  # lon, lat; fixed descriptive reference point
AIRBNB_TO_STATBANK = {
    "Indre By": "Indre By",
    "sterbro": "Østerbro",
    "Østerbro": "Østerbro",
    "Nrrebro": "Nørrebro",
    "Nørrebro": "Nørrebro",
    "Vesterbro-Kongens Enghave": "Vesterbro/Kongens Enghave",
    "Vesterbro/Kongens Enghave": "Vesterbro/Kongens Enghave",
    "Valby": "Valby",
    "Vanlse": "Vanløse",
    "Vanløse": "Vanløse",
    "Brnshj-Husum": "Brønshøj-Husum",
    "Brønshøj-Husum": "Brønshøj-Husum",
    "Bispebjerg": "Bispebjerg",
    "Amager st": "Amager Øst",
    "Amager Øst": "Amager Øst",
    "Amager Vest": "Amager Vest",
}

FOOD_AMENITIES = {
    "restaurant",
    "cafe",
    "bar",
    "fast_food",
    "pub",
    "marketplace",
    "supermarket",
}
SERVICE_AMENITIES = {
    "pharmacy",
    "hospital",
    "clinic",
    "school",
    "university",
    "library",
    "theatre",
    "cinema",
    "place_of_worship",
    "bank",
    "post_office",
}
GREEN_LEISURE = {"park", "garden", "playground", "sports_centre", "stadium", "pitch"}
TRANSPORT_RAILWAY = {"station", "halt", "tram_stop", "subway_entrance", "stop"}

LISTING_USECOLS = [
    "id",
    "last_scraped",
    "host_response_time",
    "host_response_rate",
    "host_acceptance_rate",
    "host_is_superhost",
    "host_listings_count",
    "host_total_listings_count",
    "neighbourhood_cleansed",
    "neighbourhood_group_cleansed",
    "latitude",
    "longitude",
    "property_type",
    "room_type",
    "accommodates",
    "bathrooms",
    "bathrooms_text",
    "bedrooms",
    "beds",
    "price",
    "minimum_nights",
    "maximum_nights",
    "minimum_nights_avg_ntm",
    "maximum_nights_avg_ntm",
    "has_availability",
    "availability_30",
    "availability_60",
    "availability_90",
    "availability_365",
    "number_of_reviews",
    "number_of_reviews_ltm",
    "number_of_reviews_l30d",
    "review_scores_rating",
    "review_scores_accuracy",
    "review_scores_cleanliness",
    "review_scores_checkin",
    "review_scores_communication",
    "review_scores_location",
    "review_scores_value",
    "instant_bookable",
    "calculated_host_listings_count",
    "calculated_host_listings_count_entire_homes",
    "reviews_per_month",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="Inside Airbnb snapshot date; defaults to the latest local snapshot.")
    parser.add_argument("--osm-date", help="OSM extraction date; defaults to the latest local extraction.")
    parser.add_argument("--force", action="store_true", help="Overwrite the local processed output.")
    return parser.parse_args()


def latest_path(pattern: str) -> Path:
    candidates = sorted(PROJECT_ROOT.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No local input matches {pattern}")
    return candidates[-1]


def parse_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype("string").str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")


def parse_percent_series(series: pd.Series) -> pd.Series:
    value = parse_numeric_series(series)
    return value / 100.0


def first_number(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return math.nan
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else math.nan


def clean_listings(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    available = pd.read_csv(path, compression="gzip", nrows=0).columns.tolist()
    usecols = [column for column in LISTING_USECOLS if column in available]
    df = pd.read_csv(path, compression="gzip", usecols=usecols, low_memory=False)
    rename = {
        "id": "listing_id",
        "neighbourhood_cleansed": "airbnb_neighbourhood",
        "neighbourhood_group_cleansed": "airbnb_neighbourhood_group",
    }
    df = df.rename(columns=rename)

    numeric_columns = [
        "latitude",
        "longitude",
        "accommodates",
        "bathrooms",
        "bedrooms",
        "beds",
        "minimum_nights",
        "maximum_nights",
        "minimum_nights_avg_ntm",
        "maximum_nights_avg_ntm",
        "availability_30",
        "availability_60",
        "availability_90",
        "availability_365",
        "number_of_reviews",
        "number_of_reviews_ltm",
        "number_of_reviews_l30d",
        "review_scores_rating",
        "review_scores_accuracy",
        "review_scores_cleanliness",
        "review_scores_checkin",
        "review_scores_communication",
        "review_scores_location",
        "review_scores_value",
        "host_listings_count",
        "host_total_listings_count",
        "calculated_host_listings_count",
        "calculated_host_listings_count_entire_homes",
        "reviews_per_month",
    ]
    for column in numeric_columns:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "listing_id" in df:
        df["listing_id"] = pd.to_numeric(df["listing_id"], errors="coerce").astype("Int64")

    price_series = parse_numeric_series(df["price"] if "price" in df else pd.Series(index=df.index))
    df["source_price_numeric"] = price_series.astype(float)
    df["log_price_source_currency"] = np.nan
    positive_price = df["source_price_numeric"].gt(0)
    df.loc[positive_price, "log_price_source_currency"] = np.log(
        df.loc[positive_price, "source_price_numeric"]
    )
    if "host_response_rate" in df:
        df["host_response_rate_fraction"] = parse_percent_series(df["host_response_rate"])
    if "host_acceptance_rate" in df:
        df["host_acceptance_rate_fraction"] = parse_percent_series(df["host_acceptance_rate"])
    if "host_is_superhost" in df:
        df["host_is_superhost_flag"] = df["host_is_superhost"].map({"t": 1, "f": 0})
    if "instant_bookable" in df:
        df["instant_bookable_flag"] = df["instant_bookable"].map({"t": 1, "f": 0})
    if "has_availability" in df:
        df["has_availability_flag"] = df["has_availability"].map({"t": 1, "f": 0})
    if "bathrooms_text" in df:
        df["bathrooms_numeric_from_text"] = df["bathrooms_text"].map(first_number)

    # The source contains host names, URLs, descriptions, amenities text, and
    # host IDs. They are intentionally not carried into the analytical table.
    df["valid_coordinate"] = df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)
    df["valid_source_price"] = df["source_price_numeric"].gt(0)
    df["eligible_for_price_model"] = df["valid_coordinate"] & df["valid_source_price"]

    summary = {
        "source_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": sha256_file(path),
        "rows": int(len(df)),
        "columns_read": usecols,
        "valid_coordinate_rows": int(df["valid_coordinate"].sum()),
        "valid_source_price_rows": int(df["valid_source_price"].sum()),
        "eligible_for_price_model_rows": int(df["eligible_for_price_model"].sum()),
        "missing_source_price_rows": int(df["source_price_numeric"].isna().sum()),
        "source_price_note": "Numeric value retained without currency conversion; downloaded values display '$'.",
    }
    return df, summary


def join_statbank_context(
    df: pd.DataFrame,
    context_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    context = pd.read_csv(context_path)
    if len(context) != 10 or "Frederiksberg" in context["district_name_statbank"].values:
        raise ValueError("Expected only the 10 City of Copenhagen districts")
    if context["district_name_statbank"].duplicated().any():
        raise ValueError("City Statbank context has duplicate district labels")
    context["statbank_context_provider"] = "City of Copenhagen Statbank"
    context["statbank_context_geography"] = "district"
    context["statbank_area_code"] = context["statbank_district_code"].astype("string")
    context["statbank_context_provider"] = context["statbank_context_provider"].astype("string")
    context["statbank_context_geography"] = context["statbank_context_geography"].astype("string")
    df["statbank_district_name"] = df["airbnb_neighbourhood"].map(AIRBNB_TO_STATBANK)
    df = df.merge(
        context,
        left_on="statbank_district_name",
        right_on="district_name_statbank",
        how="left",
        validate="many_to_one",
    )
    df["statbank_context_missing"] = df["population_count"].isna()
    df["eligible_for_district_context_model"] = ~df["statbank_context_missing"]
    unmatched = sorted(
        str(value)
        for value in df.loc[df["statbank_context_missing"], "airbnb_neighbourhood"].dropna().unique()
    )
    summary = {
        "source_path": context_path.relative_to(PROJECT_ROOT).as_posix(),
        "context_rows": int(len(context)),
        "listings_with_statbank_context": int((~df["statbank_context_missing"]).sum()),
        "listings_without_statbank_context": int(df["statbank_context_missing"].sum()),
        "unmatched_airbnb_neighbourhoods": unmatched,
        "joined_context_by_geography": {
            str(key): int(value)
            for key, value in df.loc[~df["statbank_context_missing"], "statbank_context_geography"]
            .value_counts(dropna=False)
            .items()
        },
        "join_rule": "explicit Airbnb-to-City-district aliases; Frederiksberg district fields are missing by design",
    }
    return df, summary


def join_analysis_area_context(
    df: pd.DataFrame, district_path: Path, municipality_path: Path
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Append one Frederiksberg proxy area to the ten City districts.

    The original district columns remain City-only. The new analysis-area
    columns carry explicit geography and period flags so a mixed-source model
    cannot be mistaken for a strictly harmonised district comparison.
    """
    municipality = pd.read_csv(municipality_path, dtype={"municipality_code": "string"})
    if len(municipality) != 2 or set(municipality["municipality_code"]) != {"101", "147"}:
        raise ValueError("Expected exactly Copenhagen (101) and Frederiksberg (147) national rows")
    city_meta = json.loads((PROJECT_ROOT / "data/metadata/copenhagen_statbank_run.json").read_text())
    national_meta = json.loads((PROJECT_ROOT / "data/metadata/municipality_statbank_run.json").read_text())
    if city_meta["tidy_context"] != district_path.relative_to(PROJECT_ROOT).as_posix():
        raise ValueError("City district context does not match its collection metadata")
    if national_meta["tidy_context"] != municipality_path.relative_to(PROJECT_ROOT).as_posix():
        raise ValueError("National municipality context does not match its collection metadata")
    city_tables = {item["table"]: item for item in city_meta["tables"]}
    national_tables = {item["table"]: item for item in national_meta["tables"]}
    periods = {
        "population": (city_tables["KKBEF1"]["selected_labels"]["var5"][0], national_tables["FOLK1A"]["period"]),
        "households": (city_tables["KKHUS1"]["selected_labels"]["var5"][0], national_tables["FAM55N"]["period"]),
        "income": (city_tables["KKIND3"]["selected_labels"]["var5"][0], national_tables["INDKP106"]["period"]),
        "dwellings": (city_tables["KKBOL3"]["selected_labels"]["var6"][0], national_tables["BOL101"]["period"]),
    }
    if periods["population"][0] != periods["population"][1]:
        raise ValueError("Pooled population periods are not aligned")
    city_household_period, national_household_period = periods["households"]
    quarter = re.fullmatch(r"(\d{4})Q([1-4])", city_household_period)
    if quarter is None:
        raise ValueError(f"Unexpected City household quarter: {city_household_period}")
    city_household_reference_date = f"{quarter.group(1)}-{1 + (int(quarter.group(2)) - 1) * 3:02d}-01"
    if city_household_reference_date != national_household_period:
        raise ValueError("Pooled household reference dates are not aligned")
    frb = municipality.loc[municipality["municipality_code"] == "147"].iloc[0]
    is_frederiksberg = df["airbnb_neighbourhood"].eq("Frederiksberg")
    if not is_frederiksberg.any() or not df.loc[is_frederiksberg, "statbank_context_missing"].all():
        raise ValueError("Frederiksberg listings must be present and have no City district context")

    df["analysis_area_code"] = ("CPH_DISTRICT_" + df["statbank_area_code"]).astype("string")
    df.loc[is_frederiksberg, "analysis_area_code"] = "FRB_SINGLE_AREA_147"
    df["analysis_area_name"] = df["statbank_district_name"].astype("string")
    df.loc[is_frederiksberg, "analysis_area_name"] = "Frederiksberg"
    df["analysis_area_geography"] = "Copenhagen district"
    df.loc[is_frederiksberg, "analysis_area_geography"] = "Frederiksberg municipality as one analysis area"
    df["analysis_area_source_provider"] = "City of Copenhagen Statbank"
    df.loc[is_frederiksberg, "analysis_area_source_provider"] = "Statistics Denmark StatBank"
    df["analysis_area_is_municipality_proxy"] = is_frederiksberg

    fields = {
        "population_count": "municipality_population_count",
        "household_count": "municipality_household_count",
        "average_disposable_income_dkk": "municipality_average_disposable_income_dkk",
        "dwelling_count": "municipality_dwelling_count",
    }
    pooled_columns = []
    for district_field, municipality_field in fields.items():
        output_field = f"analysis_area_{district_field}"
        pooled_columns.append(output_field)
        df[output_field] = df[district_field].copy()
        df.loc[is_frederiksberg, output_field] = frb[municipality_field]

    for measure, (city_period, frb_period) in periods.items():
        field = f"analysis_area_{measure}_period"
        df[field] = city_period
        df.loc[is_frederiksberg, field] = frb_period
    df["analysis_area_households_reference_date"] = city_household_reference_date
    df["analysis_area_household_period_differs"] = False
    df["analysis_area_household_definition_unverified"] = is_frederiksberg
    df["analysis_area_income_definition_differs"] = is_frederiksberg
    df["analysis_area_dwelling_definition_unverified"] = is_frederiksberg
    df["eligible_for_mixed_analysis_area_context"] = df[pooled_columns].notna().all(axis=1)

    areas = df[["analysis_area_code", "analysis_area_name", "analysis_area_geography"]].drop_duplicates()
    if len(areas) != 11 or df["analysis_area_code"].isna().any():
        raise ValueError("Expected exactly 11 named analysis areas covering every listing")
    summary = {
        "source_paths": [
            district_path.relative_to(PROJECT_ROOT).as_posix(),
            municipality_path.relative_to(PROJECT_ROOT).as_posix(),
        ],
        "analysis_areas": 11,
        "copenhagen_districts": 10,
        "frederiksberg_single_area": 1,
        "listings_with_mixed_area_context": int(df["eligible_for_mixed_analysis_area_context"].sum()),
        "frederiksberg_proxy_listings": int(is_frederiksberg.sum()),
        "pooled_fields": list(fields),
        "field_lineage": {
            "population_count": f"KKBEF1 {periods['population'][0]} / FOLK1A {periods['population'][1]}",
            "household_count": f"KKHUS1 {periods['households'][0]} / FAM55N {periods['households'][1]}; same 1 January reference date, definitions not independently harmonised",
            "average_disposable_income_dkk": f"KKIND3 {periods['income'][0]} / INDKP106 {periods['income'][1]}; denominators differ",
            "dwelling_count": f"KKBOL3 {periods['dwellings'][0]} / BOL101 {periods['dwellings'][1]}; definitions not independently harmonised",
        },
        "excluded_from_pooled_fields": [
            "resident_count_statbank",
            "occupied_dwelling_count",
            "average_residents_per_occupied_dwelling",
        ],
        "interpretation": "Frederiksberg is a municipality used as one analysis area, not an official Copenhagen district. Mixed-source covariates are sensitivity measures; use strict City district fields for harmonised within-Copenhagen analyses.",
        "households_reference_date": city_household_reference_date,
    }
    return df, summary


def project_wgs84_to_utm32(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project WGS84 lon/lat to UTM zone 32N, close to EPSG:25832 for Copenhagen."""
    # Standard UTM forward equations. ETRS89/WGS84 differences are negligible
    # for the intended city-scale thesis features.
    a = 6378137.0
    ecc_sq = 0.0066943799901413165
    ecc_prime_sq = ecc_sq / (1 - ecc_sq)
    k0 = 0.9996
    long_origin = math.radians(9.0)

    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    n = a / np.sqrt(1 - ecc_sq * np.sin(lat_rad) ** 2)
    t = np.tan(lat_rad) ** 2
    c = ecc_prime_sq * np.cos(lat_rad) ** 2
    aa = np.cos(lat_rad) * (lon_rad - long_origin)
    m = a * (
        (1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256) * lat_rad
        - (3 * ecc_sq / 8 + 3 * ecc_sq**2 / 32 + 45 * ecc_sq**3 / 1024) * np.sin(2 * lat_rad)
        + (15 * ecc_sq**2 / 256 + 45 * ecc_sq**3 / 1024) * np.sin(4 * lat_rad)
        - (35 * ecc_sq**3 / 3072) * np.sin(6 * lat_rad)
    )
    east = k0 * n * (
        aa
        + (1 - t + c) * aa**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * ecc_prime_sq) * aa**5 / 120
    ) + 500000.0
    north = k0 * (
        m
        + n
        * np.tan(lat_rad)
        * (
            aa**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * ecc_prime_sq) * aa**6 / 720
        )
    )
    return east, north


def element_point(element: dict[str, Any]) -> tuple[float, float] | None:
    if element.get("type") == "node" and "lat" in element and "lon" in element:
        return float(element["lon"]), float(element["lat"])
    center = element.get("center")
    if center and "lat" in center and "lon" in center:
        return float(center["lon"]), float(center["lat"])
    return None


def poi_categories(tags: dict[str, Any]) -> set[str]:
    categories: set[str] = set()
    amenity = str(tags.get("amenity", ""))
    leisure = str(tags.get("leisure", ""))
    tourism = str(tags.get("tourism", ""))
    railway = str(tags.get("railway", ""))
    if amenity in FOOD_AMENITIES:
        categories.add("food_drink")
    if amenity in SERVICE_AMENITIES:
        categories.add("services")
    if leisure in GREEN_LEISURE:
        categories.add("green_space")
    if tourism:
        categories.add("tourism")
    if "shop" in tags:
        categories.add("retail")
    if tags.get("public_transport") or railway in TRANSPORT_RAILWAY:
        categories.add("transport")
    return categories


def load_network(network_path: Path) -> tuple[list[int], np.ndarray, np.ndarray, list[list[tuple[int, float]]], dict[str, Any]]:
    payload = json.loads(network_path.read_text(encoding="utf-8"))
    node_coordinates: dict[int, tuple[float, float]] = {}
    ways: list[dict[str, Any]] = []
    for element in payload.get("elements", []):
        if element.get("type") == "node" and "lat" in element and "lon" in element:
            node_coordinates[int(element["id"])] = (float(element["lon"]), float(element["lat"]))
        elif element.get("type") == "way" and element.get("nodes"):
            ways.append(element)

    node_ids = list(node_coordinates)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    lons = np.array([node_coordinates[node_id][0] for node_id in node_ids], dtype=float)
    lats = np.array([node_coordinates[node_id][1] for node_id in node_ids], dtype=float)
    east, north = project_wgs84_to_utm32(lons, lats)
    adjacency: list[list[tuple[int, float]]] = [[] for _ in node_ids]
    edge_count = 0

    for way in ways:
        tags = way.get("tags", {})
        speed = 0.9 if tags.get("highway") == "steps" else WALK_SPEED_MPS
        refs = way.get("nodes", [])
        for start, end in zip(refs, refs[1:]):
            first = node_index.get(int(start))
            second = node_index.get(int(end))
            if first is None or second is None or first == second:
                continue
            length_m = math.hypot(east[first] - east[second], north[first] - north[second])
            if length_m <= 0:
                continue
            travel_seconds = length_m / speed
            adjacency[first].append((second, travel_seconds))
            adjacency[second].append((first, travel_seconds))
            edge_count += 1

    metadata = {
        "source_path": network_path.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": sha256_file(network_path),
        "osm_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
        "network_nodes": len(node_ids),
        "network_ways": len(ways),
        "undirected_edges_added": edge_count,
        "routing_assumptions": {
            "graph_direction": "undirected for pedestrian accessibility",
            "default_walking_speed_mps": WALK_SPEED_MPS,
            "steps_walking_speed_mps": 0.9,
        },
    }
    return node_ids, east, north, adjacency, metadata


def load_poi_sources(poi_path: Path, tree: cKDTree, node_count: int) -> tuple[dict[str, set[int]], dict[str, Any]]:
    payload = json.loads(poi_path.read_text(encoding="utf-8"))
    lons: list[float] = []
    lats: list[float] = []
    categories_for_point: list[set[str]] = []
    element_count = 0
    for element in payload.get("elements", []):
        point = element_point(element)
        if point is None:
            continue
        categories = poi_categories(element.get("tags", {}))
        if not categories:
            continue
        lons.append(point[0])
        lats.append(point[1])
        categories_for_point.append(categories)
        element_count += 1

    if not lons:
        raise ValueError(f"No categorised OSM opportunities found in {poi_path}")
    east, north = project_wgs84_to_utm32(np.array(lons), np.array(lats))
    _, nearest = tree.query(np.column_stack([east, north]), k=1)
    sources: dict[str, set[int]] = defaultdict(set)
    for node_index, categories in zip(np.asarray(nearest, dtype=int), categories_for_point):
        if 0 <= node_index < node_count:
            for category in categories:
                sources[category].add(int(node_index))

    metadata = {
        "source_path": poi_path.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": sha256_file(poi_path),
        "osm_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
        "categorised_elements_with_points": element_count,
        "source_nodes_by_category": {key: len(value) for key, value in sorted(sources.items())},
        "taxonomy": {
            "food_drink": "selected amenity food and drink tags",
            "services": "selected civic, education, health, culture, finance and post tags",
            "green_space": "selected leisure park/garden/playground/sports tags",
            "tourism": "any tourism tag returned by the query",
            "retail": "any shop tag returned by the query",
            "transport": "public_transport or selected railway tags",
        },
    }
    return sources, metadata


def multisource_dijkstra(adjacency: list[list[tuple[int, float]]], sources: Iterable[int]) -> np.ndarray:
    distances = np.full(len(adjacency), np.inf, dtype=float)
    heap: list[tuple[float, int]] = []
    for source in set(sources):
        if distances[source] != 0:
            distances[source] = 0.0
            heapq.heappush(heap, (0.0, source))
    while heap:
        distance, node = heapq.heappop(heap)
        if distance != distances[node]:
            continue
        for neighbour, weight in adjacency[node]:
            candidate = distance + weight
            if candidate < distances[neighbour]:
                distances[neighbour] = candidate
                heapq.heappush(heap, (candidate, neighbour))
    return distances


def attach_spatial_features(
    df: pd.DataFrame,
    node_ids: list[int],
    node_east: np.ndarray,
    node_north: np.ndarray,
    adjacency: list[list[tuple[int, float]]],
    sources: dict[str, set[int]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    valid = df["valid_coordinate"].to_numpy(dtype=bool)
    listing_east, listing_north = project_wgs84_to_utm32(
        df["longitude"].fillna(0).to_numpy(dtype=float), df["latitude"].fillna(0).to_numpy(dtype=float)
    )
    centre_east, centre_north = project_wgs84_to_utm32(
        np.array([COPENHAGEN_CENTRE[0]]), np.array([COPENHAGEN_CENTRE[1]])
    )
    df["x_utm32_m"] = listing_east
    df["y_utm32_m"] = listing_north
    df["distance_to_copenhagen_centre_km"] = np.hypot(
        listing_east - centre_east[0], listing_north - centre_north[0]
    ) / 1000.0
    tree = cKDTree(np.column_stack([node_east, node_north]))
    query_points = np.column_stack([listing_east, listing_north])
    snap_distances, nearest = tree.query(query_points, k=1)
    nearest = np.asarray(nearest, dtype=int)
    snap_distances = np.asarray(snap_distances, dtype=float)
    df["nearest_network_node_id"] = [node_ids[index] for index in nearest]
    df["distance_to_network_m"] = np.where(valid, snap_distances, np.nan)
    df["network_degree"] = [len(adjacency[index]) if is_valid else np.nan for index, is_valid in zip(nearest, valid)]

    feature_columns: list[str] = []
    category_minutes: dict[str, np.ndarray] = {}
    for category in sorted(sources):
        print(f"  routing to nearest OSM category: {category} ({len(sources[category]):,} snapped sources)")
        distances = multisource_dijkstra(adjacency, sources[category])
        total_seconds = distances[nearest] + np.where(valid, snap_distances / WALK_SPEED_MPS, np.nan)
        minutes = total_seconds / 60.0
        minutes[~np.isfinite(minutes)] = np.nan
        category_minutes[category] = minutes
        column = f"walk_time_to_nearest_{category}_min"
        df[column] = minutes
        feature_columns.append(column)

    accessibility = np.zeros(len(df), dtype=float)
    for minutes in category_minutes.values():
        accessibility += np.where(np.isfinite(minutes), np.exp(-ACCESS_DECAY_PER_MINUTE * minutes), 0.0)
    accessibility[~valid] = np.nan
    df["network_nearest_category_accessibility_index"] = accessibility
    summary = {
        "valid_coordinate_rows_snapped": int(valid.sum()),
        "nearest_network_feature_columns": feature_columns,
        "network_accessibility_index": {
            "formula": "sum(exp(-0.10 * walking_minutes_to_nearest_category)) across available OSM categories",
            "interpretation": "minimum-version nearest-category accessibility score, not a full opportunity count",
        },
    }
    return df, summary


def write_outputs(df: pd.DataFrame, snapshot_date: str, metadata: dict[str, Any], force: bool) -> None:
    output_root = PROJECT_ROOT / "data" / "processed" / "copenhagen" / snapshot_date
    output_root.mkdir(parents=True, exist_ok=True)
    parquet_path = output_root / "listing_accessibility.parquet"
    csv_path = output_root / "listing_accessibility.csv.gz"
    if not force and (parquet_path.exists() or csv_path.exists()):
        raise FileExistsError(f"Processed output exists under {output_root}; use --force to replace it.")
    df.to_parquet(parquet_path, index=False)
    df.to_csv(csv_path, index=False, compression="gzip")
    metadata.update(
        {
            "outputs": {
                "parquet": parquet_path.relative_to(PROJECT_ROOT).as_posix(),
                "csv_gzip": csv_path.relative_to(PROJECT_ROOT).as_posix(),
            },
            "output_columns": df.columns.tolist(),
            "output_rows": int(len(df)),
            "privacy_note": "Processed files retain coordinates for local spatial work and remain gitignored; aggregate before sharing.",
        }
    )
    write_json(PROJECT_ROOT / "data" / "metadata" / "pipeline_run.json", metadata)


def main() -> None:
    args = parse_args()
    listings_path = (
        latest_path("data/raw/inside_airbnb/copenhagen/*/data/listings.csv.gz")
        if not args.snapshot
        else PROJECT_ROOT / "data" / "raw" / "inside_airbnb" / "copenhagen" / args.snapshot / "data" / "listings.csv.gz"
    )
    if not listings_path.exists():
        raise FileNotFoundError(listings_path)
    snapshot_date = listings_path.parents[1].name
    osm_network_path = (
        latest_path("data/raw/osm/copenhagen/*/responses/walking_network.json")
        if not args.osm_date
        else PROJECT_ROOT / "data" / "raw" / "osm" / "copenhagen" / args.osm_date / "responses" / "walking_network.json"
    )
    osm_poi_path = osm_network_path.parent / "amenities_and_transport.json"
    if not osm_poi_path.exists():
        raise FileNotFoundError(osm_poi_path)
    osm_date = osm_network_path.parents[1].name

    started = utc_now()
    print(f"Cleaning listings from {listings_path.relative_to(PROJECT_ROOT)}")
    df, listing_summary = clean_listings(listings_path)
    print(f"  {len(df):,} rows; {listing_summary['eligible_for_price_model_rows']:,} price-model eligible")
    print(f"Loading OSM network from {osm_network_path.relative_to(PROJECT_ROOT)}")
    node_ids, node_east, node_north, adjacency, network_summary = load_network(osm_network_path)
    tree = cKDTree(np.column_stack([node_east, node_north]))
    sources, poi_summary = load_poi_sources(osm_poi_path, tree, len(node_ids))
    print(f"  {len(node_ids):,} nodes; {sum(len(values) for values in sources.values()):,} category sources")
    df, spatial_summary = attach_spatial_features(
        df, node_ids, node_east, node_north, adjacency, sources
    )
    statbank_context_path = latest_path("data/interim/copenhagen_statbank_district_context_*.csv")
    print(f"Joining City district context from {statbank_context_path.relative_to(PROJECT_ROOT)}")
    df, statbank_summary = join_statbank_context(df, statbank_context_path)
    print(
        f"  {statbank_summary['listings_with_statbank_context']:,} listings joined; "
        f"{statbank_summary['listings_without_statbank_context']:,} unmatched"
    )
    municipality_context_path = latest_path("data/interim/municipality_statbank_context_*.csv")
    print(f"Adding Frederiksberg single-area context from {municipality_context_path.relative_to(PROJECT_ROOT)}")
    df, analysis_area_summary = join_analysis_area_context(df, statbank_context_path, municipality_context_path)
    print(f"  {analysis_area_summary['analysis_areas']} analysis areas; {analysis_area_summary['listings_with_mixed_area_context']:,} listings covered")

    metadata = {
        "pipeline": "available_minimum_non_gtfs",
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "study_area": "Copenhagen, Denmark",
        "snapshot_date": snapshot_date,
        "osm_extraction_date": osm_date,
        "input_crs": WGS84,
        "projected_crs": PROJECTED_CRS,
        "listing_summary": listing_summary,
        "network_summary": network_summary,
        "poi_summary": poi_summary,
        "spatial_summary": spatial_summary,
        "statbank_summary": statbank_summary,
        "analysis_area_summary": analysis_area_summary,
        "completed_steps": [
            "source manifest was verified before run",
            "listing outcomes and non-identifying controls cleaned",
            "WGS84 coordinates projected to UTM zone 32N / EPSG:25832-compatible metres",
            "cached OSM walking network parsed into an undirected pedestrian graph",
            "listings and OSM opportunity elements snapped to the network",
            "nearest-category walking times and minimum accessibility index computed",
            "City district context retained separately; Frederiksberg municipality added as one flagged mixed-scale analysis area",
            "local analytical table written as Parquet and compressed CSV",
        ],
        "not_available_yet": [
            "GTFS stops, routes, trips, stop_times, and timetable accessibility",
            "PostGIS database load; the current run uses local Parquet and cached JSON",
        ],
        "method_limits": [
            "The pedestrian graph is treated as undirected and uses assumed walking speeds of 1.4 m/s, or 0.9 m/s on steps.",
            "The accessibility index uses nearest OSM opportunities by category, not full counts of opportunities within thresholds.",
            "Airbnb coordinates are provider-anonymised; do not make address-level claims.",
            "The source price remains unconverted because the downloaded values display '$'.",
            "Frederiksberg is a single municipality-sized analysis area, not an official Copenhagen district; strict district models exclude it.",
            "Pooled household reference dates are aligned at 1 January 2026, but City versus national household definitions may differ; pooled income denominators and dwelling definitions are not harmonised. Treat these as sensitivity covariates.",
        ],
    }
    write_outputs(df, snapshot_date, metadata, args.force)
    print(f"Completed. Output rows: {len(df):,}")


if __name__ == "__main__":
    main()

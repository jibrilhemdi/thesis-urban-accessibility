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
7. join available City of Copenhagen district context and Frederiksberg
   municipality context;
8. write a local analytical table and run metadata.

GTFS is recorded as unavailable rather than inferred. Statbank context retains
the provider geography: City of Copenhagen districts and Frederiksberg
municipality.
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
from datetime import datetime, timezone
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
    "Frederiksberg": "Frederiksberg",
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
    supplemental_context_paths: Iterable[Path] = (),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    context_parts = []
    for source_path in [context_path, *supplemental_context_paths]:
        part = pd.read_csv(source_path)
        if "statbank_context_provider" not in part:
            part["statbank_context_provider"] = "City of Copenhagen Statbank"
        if "statbank_context_geography" not in part:
            part["statbank_context_geography"] = "district"
        if "statbank_area_code" not in part:
            if "statbank_district_code" in part:
                part["statbank_area_code"] = part["statbank_district_code"].astype("string")
            else:
                part["statbank_area_code"] = pd.NA
        context_parts.append(part)
    context = pd.concat(context_parts, ignore_index=True, sort=False)
    if context["district_name_statbank"].duplicated().any():
        raise ValueError("Statbank context sources contain duplicate join labels")
    context["statbank_area_code"] = context["statbank_area_code"].astype("string")
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
    unmatched = sorted(
        str(value)
        for value in df.loc[df["statbank_context_missing"], "airbnb_neighbourhood"].dropna().unique()
    )
    summary = {
        "source_path": context_path.relative_to(PROJECT_ROOT).as_posix(),
        "source_paths": [path.relative_to(PROJECT_ROOT).as_posix() for path in [context_path, *supplemental_context_paths]],
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
        "join_rule": "explicit Airbnb-to-Statbank aliases; City of Copenhagen uses district context and Frederiksberg uses municipality context",
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
    frederiksberg_context_matches = sorted(
        PROJECT_ROOT.glob("data/interim/frederiksberg_statbank_municipality_context_*.csv")
    )
    frederiksberg_context_path = frederiksberg_context_matches[-1] if frederiksberg_context_matches else None
    context_sources = [statbank_context_path]
    if frederiksberg_context_path is not None:
        context_sources.append(frederiksberg_context_path)
    print(
        "Joining Statbank context from "
        + ", ".join(path.relative_to(PROJECT_ROOT).as_posix() for path in context_sources)
    )
    df, statbank_summary = join_statbank_context(
        df,
        statbank_context_path,
        [frederiksberg_context_path] if frederiksberg_context_path is not None else [],
    )
    print(
        f"  {statbank_summary['listings_with_statbank_context']:,} listings joined; "
        f"{statbank_summary['listings_without_statbank_context']:,} unmatched"
    )

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
        "completed_steps": [
            "source manifest was verified before run",
            "listing outcomes and non-identifying controls cleaned",
            "WGS84 coordinates projected to UTM zone 32N / EPSG:25832-compatible metres",
            "cached OSM walking network parsed into an undirected pedestrian graph",
            "listings and OSM opportunity elements snapped to the network",
            "nearest-category walking times and minimum accessibility index computed",
            "City of Copenhagen district and Frederiksberg municipality Statbank context joined with explicit boundary aliases",
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
        ],
    }
    write_outputs(df, snapshot_date, metadata, args.force)
    print(f"Completed. Output rows: {len(df):,}")


if __name__ == "__main__":
    main()

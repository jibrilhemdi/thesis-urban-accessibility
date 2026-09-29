"""Validate the Phase 7 PostGIS view and export aggregate pre-analysis diagnostics.

No model is fit and no missing database value is replaced. Public outputs never
contain listing identifiers, host data, free text, or point coordinates.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT


VIEW = "analysis.analysis_dataset_v1"
OUT = PROJECT_ROOT / "outputs" / "tables"
FIG = PROJECT_ROOT / "outputs" / "figures"
AMENITIES = (
    "amenity_wifi", "amenity_dishwasher", "amenity_washer", "amenity_dryer",
    "amenity_workspace", "amenity_free_parking", "amenity_private_balcony",
    "amenity_self_checkin",
)
CONTROLS = (
    "property_type", "accommodates", "bedrooms", "beds", "bathrooms_structured",
    "bathrooms_effective", "log1p_minimum_nights", "instant_bookable",
    "superhost", "log1p_host_listings_count", "official_municipality_code",
    "official_cv_area_id", "distance_centre_euclidean_km",
    *AMENITIES, "number_of_reviews", "review_scores_rating",
    "nearest_station_euclidean_m", "nearest_station_walking_minutes",
    "food_social_800m", "food_social_w_10", "cultural_tourist_800m",
    "cultural_tourist_w_10", "district_income_2024_dkk_person",
    "district_population_2026q3", "frb_municipality_income_2024_dkk_person",
)
DIAGNOSTIC_NUMERIC = (
    "accommodates", "bedrooms", "beds", "bathrooms_effective",
    "log1p_minimum_nights", "log1p_host_listings_count",
    "distance_centre_euclidean_km", "nearest_station_euclidean_m",
    "nearest_station_walking_minutes", "food_social_800m", "food_social_w_10",
    "cultural_tourist_800m", "cultural_tourist_w_10",
)
TARGET_PAIRS = {
    frozenset(("accommodates", "bedrooms")),
    frozenset(("accommodates", "beds")),
    frozenset(("bedrooms", "beds")),
    frozenset(("nearest_station_euclidean_m", "nearest_station_walking_minutes")),
    frozenset(("food_social_800m", "food_social_w_10")),
    frozenset(("cultural_tourist_800m", "cultural_tourist_w_10")),
}
FOLD_SEED = 20260929
DICTIONARY = {
    "snapshot_date": ("Inside Airbnb snapshot date", "clean.airbnb_listings", "date", "key"),
    "listing_id": ("Original Inside Airbnb listing ID; confidential join key", "clean.airbnb_listings", "ID", "key"),
    "source_file_id": ("Registered listing source file ID", "clean.airbnb_listings/meta.source_files", "ID", "provenance"),
    "last_scraped": ("Listing's source scrape date; not a price-selection control", "clean.airbnb_listings", "date", "provenance"),
    "price_nightly": ("Positive source listed nightly price; NULL if missing/unparseable; DKK by user confirmation", "clean.airbnb_listings", "DKK/night", "outcome"),
    "observed_positive_price": ("True when source listed price is valid and positive", "clean.airbnb_listings", "boolean", "selection"),
    "log_price": ("Natural log of positive source listed nightly price; never imputed", "price_nightly", "ln(DKK/night)", "outcome"),
    "missing_or_invalid_price": ("True when no valid positive price exists", "clean.airbnb_listings", "boolean", "selection"),
    "in_study_area": ("Phase 2 provider-label study-area flag; official assignment is separate", "clean.airbnb_listings", "boolean", "selection"),
    "entire_home_apt": ("Source room type equals Entire home/apt", "clean.airbnb_listings", "boolean", "selection"),
    "conventional_residential": ("Phase 2 predeclared six-property-type inclusion", "clean.airbnb_listings", "boolean", "selection"),
    "valid_price": ("Phase 2 positive-price validation flag", "clean.airbnb_listings", "boolean", "selection"),
    "valid_coordinates": ("Phase 2 valid WGS84 coordinate flag", "clean.airbnb_listings", "boolean", "selection"),
    "primary_sample_candidate": ("All Phase 2 study/room/property/price/coordinate requirements met", "clean.airbnb_listings", "boolean", "selection"),
    "property_type": ("Original listing property category", "clean.airbnb_listings", "category", "primary_control"),
    "room_type": ("Original listing room category", "clean.airbnb_listings", "category", "selection"),
    "accommodates": ("Number of guests the listing accommodates", "clean.airbnb_listings", "persons", "primary_control"),
    "bedrooms": ("Structured bedroom count; no database imputation", "clean.airbnb_listings", "rooms", "primary_control"),
    "bathrooms_structured": ("Structured bathroom count as parsed in Phase 2", "clean.airbnb_listings", "rooms", "diagnostic"),
    "bathrooms_text": ("Original bathroom text retained to audit source-supported fallback; not public output", "clean.airbnb_listings", "text", "provenance"),
    "bathrooms_effective": ("Structured count, else explicitly parsed numeric/half-bath source text", "clean.airbnb_listings.bathrooms/bathrooms_text", "rooms", "primary_control"),
    "bathrooms_source": ("Whether effective bathrooms came from structured field, source text, or neither", "clean.airbnb_listings", "category", "provenance"),
    "bathrooms_source_disagreement": ("Structured/text bathroom numbers disagree; structured takes precedence", "clean.airbnb_listings", "boolean", "diagnostic"),
    "minimum_nights": ("Minimum listed stay length", "clean.airbnb_listings", "nights", "diagnostic"),
    "log1p_minimum_nights": ("ln(1 + minimum_nights); NULL if invalid negative", "minimum_nights", "log nights", "primary_control"),
    "instant_bookable": ("Boolean parsed from source field; entirely missing in current snapshot", "clean.airbnb_listings", "boolean", "unusable"),
    "superhost": ("Host superhost status parsed from source t/f", "clean.airbnb_listings", "boolean", "primary_control"),
    "host_listings_count": ("Source host listing count", "clean.airbnb_listings", "count", "diagnostic"),
    "log1p_host_listings_count": ("ln(1 + source host listing count)", "host_listings_count", "log count", "primary_control"),
    "calculated_host_listings_count": ("Provider-calculated host listing count; not the primary host-count field", "clean.airbnb_listings", "count", "diagnostic"),
    "number_of_reviews": ("Lifetime review count; activity proxy, not bookings", "clean.airbnb_listings", "count", "robustness"),
    "number_of_reviews_ltm": ("Last-12-month review count; activity proxy", "clean.airbnb_listings", "count", "robustness"),
    "review_scores_rating": ("Published listing rating where reviews permit", "clean.airbnb_listings", "rating", "robustness"),
    "official_municipality_code": ("Official ST_Covers municipality: 0101 Copenhagen or 0147 Frederiksberg", "features.listing_spatial_base", "code", "location_control"),
    "official_cv_area_id": ("Official Copenhagen district or Frederiksberg municipality-sized area; NULL if unresolved", "features.listing_spatial_base", "area ID", "diagnostic"),
    "official_assignment_status": ("Official point/polygon assignment QA status", "features.listing_spatial_base", "category", "diagnostic"),
    "near_official_border_100m": ("Listing point within 100 m of official area boundary", "features.listing_spatial_base", "boolean", "robustness"),
    "distance_centre_euclidean_km": ("Projected straight-line distance to City Hall Square", "features.listing_spatial_base", "km", "location_control"),
    "distance_crs_epsg": ("EPSG used for centre-distance calculation (25832)", "features.listing_spatial_base", "EPSG", "provenance"),
    "euclidean_taxonomy_version": ("Phase 5 canonical OSM destination taxonomy version", "features.euclidean_accessibility", "version", "provenance"),
    "euclidean_count_coverage_complete": ("POI-count source-edge coverage check", "features.euclidean_accessibility", "boolean", "diagnostic"),
    "euclidean_station_coverage_complete": ("Nearest-station source-edge coverage check", "features.euclidean_accessibility", "boolean", "diagnostic"),
    "nearest_station_euclidean_m": ("Straight-line projected distance to nearest canonical rail/metro station", "features.euclidean_accessibility", "m", "accessibility"),
    "network_id": ("Versioned Phase 6 pedestrian graph identifier", "features.walking_accessibility", "ID", "provenance"),
    "destination_taxonomy_version": ("Canonical POI/station destination taxonomy for walking counts", "features.walking_accessibility", "version", "provenance"),
    "walking_speed_kmh": ("Assumed constant walking speed (4.8)", "features.walking_accessibility", "km/h", "provenance"),
    "routing_status": ("Walking route status; disconnected station routes remain NULL", "features.walking_accessibility", "category", "diagnostic"),
    "listing_snap_distance_m": ("Straight connector from listing point to nearest routable walk node", "features.walking_accessibility", "m", "diagnostic"),
    "walking_station_coverage_complete": ("Reachable station path passes source-edge coverage check", "features.walking_accessibility", "boolean", "diagnostic"),
    "nearest_station_network_distance_m": ("Shortest routable station path plus endpoint connectors", "features.walking_accessibility", "m", "diagnostic"),
    "nearest_station_walking_minutes": ("Network station path at 4.8 km/h; NULL when no station is reachable", "features.walking_accessibility", "minutes", "accessibility"),
    "context_join_status": ("District code/name match with unverified boundary vintage, Frederiksberg proxy, or gap", "clean context + official geography", "category", "provenance"),
    "context_district_code": ("City StatBank district code, Copenhagen only", "clean.copenhagen_district_context_measures", "code", "robustness"),
    "context_district_name": ("City StatBank district label, Copenhagen only", "clean.copenhagen_district_context_measures", "name", "robustness"),
    "district_population_2026q3": ("City district registered population, 2026 Q3; post-listing snapshot", "clean.copenhagen_district_context_measures", "persons/area", "robustness"),
    "district_households_2026q1": ("City district households, 1 January 2026", "clean.copenhagen_district_context_measures", "households/area", "robustness"),
    "district_income_2024_dkk_person": ("City district mean personal disposable income; denominator not harmonised to national series", "clean.copenhagen_district_context_measures", "DKK/person/area", "robustness"),
    "frb_municipality_population_2026q3": ("Frederiksberg municipality population, not a neighbourhood attribute", "clean.municipality_context_measures", "persons/municipality", "descriptive_only"),
    "frb_municipality_households_2026q1": ("Frederiksberg municipality households, 1 January 2026", "clean.municipality_context_measures", "households/municipality", "descriptive_only"),
    "frb_municipality_income_2024_dkk_person": ("Frederiksberg municipality mean disposable income; not harmonised to City district income", "clean.municipality_context_measures", "DKK/person/municipality", "descriptive_only"),
}
for code, label in {
    "wifi": "Wifi", "dishwasher": "Dishwasher", "washer": "Washer", "dryer": "Dryer",
    "workspace": "Dedicated workspace", "free_parking": "Free parking on premises",
    "private_balcony": "Private patio or balcony", "self_checkin": "Self check-in",
}.items():
    DICTIONARY[f"amenity_{code}"] = (f"Exact {label} token in source amenities JSON; NULL if source array absent",
                                    "clean.airbnb_listings.amenities_raw", "boolean", "primary_control")
for category in ("food_social", "cultural_tourist"):
    for radius in (800, 1200, 1600):
        DICTIONARY[f"{category}_{radius}m"] = (
            f"Canonical {category} POIs within {radius} m projected straight-line radius",
            "features.euclidean_accessibility", "count", "accessibility")
    for minutes in (10, 15, 20):
        DICTIONARY[f"{category}_w_{minutes}"] = (
            f"Same canonical {category} POIs reachable within {minutes} min on walk graph, connectors included",
            "features.walking_accessibility", "count", "accessibility")


def _freeze_cv_folds(engine) -> list[dict]:
    from sklearn.model_selection import StratifiedGroupKFold

    with engine.begin() as conn:
        location = pd.read_sql(text(
            "SELECT l.snapshot_date,l.listing_id,s.official_municipality_code AS municipality_code,"
            "floor(ST_X(l.geom_25832)/1000)::integer AS grid_x,"
            "floor(ST_Y(l.geom_25832)/1000)::integer AS grid_y "
            "FROM clean.airbnb_listings l JOIN features.listing_spatial_base s "
            "USING(snapshot_date,listing_id) WHERE s.official_cv_area_id IS NOT NULL "
            "AND s.official_municipality_code IN ('0101','0147') "
            "ORDER BY l.snapshot_date,l.listing_id"
        ), conn)
        if location.empty or location[["grid_x", "grid_y"]].isna().any().any():
            raise RuntimeError("Officially assigned listings need projected coordinates for CV")
        location["block_id"] = (location["grid_x"].astype(str) + ":" + location["grid_y"].astype(str))
        splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=FOLD_SEED)
        location["fold_id"] = 0
        for fold, (_, test_idx) in enumerate(splitter.split(
            np.zeros(len(location)), location["municipality_code"], location["block_id"]
        ), start=1):
            location.loc[test_idx, "fold_id"] = fold
        if (location["fold_id"] == 0).any() or location.groupby("block_id")["fold_id"].nunique().max() != 1:
            raise RuntimeError("Spatial block split is incomplete or leaks across folds")
        fold_muni = location.groupby("fold_id")["municipality_code"].nunique()
        if len(fold_muni) != 5 or (fold_muni != 2).any():
            raise RuntimeError("Every frozen outer fold must represent both municipalities")
        records = [{"snapshot_date": row.snapshot_date, "listing_id": int(row.listing_id),
                    "block_id": row.block_id, "fold_id": int(row.fold_id),
                    "municipality_code": row.municipality_code}
                   for row in location.itertuples(index=False)]
        existing = pd.read_sql(text(
            "SELECT snapshot_date,listing_id,block_id,fold_id,municipality_code "
            "FROM analysis.spatial_cv_folds_v1 ORDER BY snapshot_date,listing_id"
        ), conn)
        if len(existing):
            expected = location[["snapshot_date", "listing_id", "block_id", "fold_id", "municipality_code"]]
            if not existing.reset_index(drop=True).equals(expected.reset_index(drop=True)):
                raise RuntimeError("Existing spatial CV freeze differs; do not overwrite it")
        else:
            conn.execute(text(
                "INSERT INTO analysis.spatial_cv_folds_v1 "
                "(snapshot_date,listing_id,block_id,fold_id,municipality_code,crs_epsg,grid_size_m,"
                "assignment_method,random_seed) VALUES "
                "(:snapshot_date,:listing_id,:block_id,:fold_id,:municipality_code,25832,1000,"
                "'StratifiedGroupKFold',20260929)"
            ), records)
        return [dict(row) for row in conn.execute(text(
            "SELECT f.fold_id, f.municipality_code,count(*) AS all_assigned_n,"
            "count(*) FILTER (WHERE a.primary_sample_candidate) AS primary_priced_n,"
            "count(*) FILTER (WHERE a.primary_sample_candidate "
            "AND a.nearest_station_walking_minutes IS NOT NULL) AS common_model_n,"
            "count(DISTINCT f.block_id) AS blocks_n "
            "FROM analysis.spatial_cv_folds_v1 f JOIN analysis.analysis_dataset_v1 a "
            "USING(snapshot_date,listing_id) GROUP BY 1,2 ORDER BY 1,2"
        )).mappings()]


def _csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _dictionary(conn, frame: pd.DataFrame) -> list[dict]:
    columns = conn.execute(text(
        "SELECT column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='analysis' AND table_name='analysis_dataset_v1' "
        "ORDER BY ordinal_position"
    )).all()
    names = {name for name, _ in columns}
    if names != set(DICTIONARY):
        raise RuntimeError(f"Analytical dictionary does not match view: missing={names - set(DICTIONARY)}, "
                           f"extra={set(DICTIONARY) - names}")
    primary = frame.loc[frame["primary_sample_candidate"]]
    return [
        {"variable": name, "sql_type": dtype, "definition": DICTIONARY[name][0],
         "source": DICTIONARY[name][1], "unit": DICTIONARY[name][2],
         "intended_use": DICTIONARY[name][3],
         "null_n_all_23144": int(frame[name].isna().sum()),
         "null_n_primary_12521": int(primary[name].isna().sum())}
        for name, dtype in columns
    ]


def _as_number(value):
    if pd.isna(value):
        return None
    return round(float(value), 4)


def _validate(conn, frame: pd.DataFrame) -> dict:
    clean_n = conn.scalar(text("SELECT count(*) FROM clean.airbnb_listings"))
    if len(frame) != clean_n or frame[["snapshot_date", "listing_id"]].duplicated().any():
        raise RuntimeError("Analysis view lost or multiplied listing rows")
    if frame["beds"].notna().sum() == 0:
        raise RuntimeError("Raw beds diagnostic join is empty")
    for table in ("features.listing_spatial_base", "features.euclidean_accessibility",
                  "features.walking_accessibility"):
        if conn.scalar(text(f"SELECT count(*) FROM {table}")) != clean_n:
            raise RuntimeError(f"Phase 7 requires one {table} row per listing")
    if frame["observed_positive_price"].isna().any():
        raise RuntimeError("Price-observed flag may not be NULL")
    observed = frame["observed_positive_price"].astype(bool)
    if frame.loc[observed, "price_nightly"].isna().any() or not frame.loc[~observed, "log_price"].isna().all():
        raise RuntimeError("Outcome/price flags are inconsistent")
    if not np.allclose(np.log(frame.loc[observed, "price_nightly"].astype(float)),
                       frame.loc[observed, "log_price"].astype(float)):
        raise RuntimeError("Log price does not equal ln(observed positive source price)")
    if frame.loc[frame["primary_sample_candidate"], "missing_or_invalid_price"].any():
        raise RuntimeError("A primary sample candidate has no valid price")
    if (frame["context_join_status"] == "district_code_or_name_mismatch").any():
        raise RuntimeError("District code/name crosswalk no longer matches the official source")
    if ((frame["official_municipality_code"] == "0147") &
            frame["district_income_2024_dkk_person"].notna()).any():
        raise RuntimeError("Copenhagen district context leaked onto Frederiksberg")
    if ((frame["official_municipality_code"] == "0101") &
            frame["frb_municipality_income_2024_dkk_person"].notna()).any():
        raise RuntimeError("Frederiksberg context leaked onto Copenhagen")
    if frame.loc[frame["primary_sample_candidate"], "bathrooms_effective"].isna().any():
        raise RuntimeError("Source bathroom text no longer supports all primary candidate rows")
    versions = conn.execute(text("SELECT count(DISTINCT network_id),count(DISTINCT destination_taxonomy_version) "
                                 "FROM features.walking_accessibility")).one()
    if versions != (1, 1):
        raise RuntimeError("Mixed walking network or destination taxonomy versions")
    primary = frame["primary_sample_candidate"]
    common = primary & frame["official_cv_area_id"].notna() & frame["nearest_station_walking_minutes"].notna()
    return {
        "view": VIEW, "listing_rows": len(frame), "observed_positive_prices": int(observed.sum()),
        "missing_or_invalid_prices": int((~observed).sum()),
        "primary_candidates": int(primary.sum()),
        "primary_with_official_cv_area": int((primary & frame["official_cv_area_id"].notna()).sum()),
        "primary_common_accessibility_cv": int(common.sum()),
        "primary_missing_walking_station": int((primary & frame["nearest_station_walking_minutes"].isna()).sum()),
        "primary_bathrooms_text_fallback": int((primary & (frame["bathrooms_source"] == "source_text")).sum()),
        "primary_bathroom_disagreements": int((primary & frame["bathrooms_source_disagreement"]).sum()),
    }


def _missingness(frame: pd.DataFrame) -> list[dict]:
    residential = frame["in_study_area"] & frame["entire_home_apt"] & frame["conventional_residential"] & frame["valid_coordinates"]
    cohorts = {
        "all_listings": frame,
        "residential_before_price": frame.loc[residential],
        "primary_priced": frame.loc[frame["primary_sample_candidate"]],
    }
    rows = []
    for cohort_name, data in cohorts.items():
        diagnostic = data.copy()
        if cohort_name == "primary_priced":
            diagnostic["observed_price_quartile"] = pd.qcut(
                diagnostic["price_nightly"].astype(float), 4,
                labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop"
            ).astype(str)
        groups = [("overall", "all", data)]
        for field in ("official_municipality_code", "official_cv_area_id", "property_type", "last_scraped"):
            groups.extend((field, "unassigned" if pd.isna(key) else str(key), part)
                          for key, part in data.groupby(field, dropna=False))
        if cohort_name == "primary_priced":
            groups.extend(("observed_price_quartile", str(key), part)
                          for key, part in diagnostic.groupby("observed_price_quartile"))
        for group_type, group_value, part in groups:
            for variable in ("price_nightly", *CONTROLS):
                n_missing = int(part[variable].isna().sum())
                rows.append({"cohort": cohort_name, "group_type": group_type,
                             "group_value": group_value, "variable": variable,
                             "n": len(part), "missing_n": n_missing,
                             "missing_pct": round(100 * n_missing / len(part), 3)})
    return rows


def _price_selection(frame: pd.DataFrame) -> list[dict]:
    residential = frame.loc[frame["in_study_area"] & frame["entire_home_apt"] &
                            frame["conventional_residential"] & frame["valid_coordinates"]].copy()
    residential["price_status"] = np.where(residential["observed_positive_price"], "observed", "missing_or_invalid")
    rows = []
    for status, part in residential.groupby("price_status"):
        rows.append({
            "price_status": status, "n": len(part),
            "pct_residential": round(100 * len(part) / len(residential), 2),
            "accommodates_median": _as_number(part["accommodates"].median()),
            "bedrooms_median": _as_number(part["bedrooms"].median()),
            "bathrooms_effective_median": _as_number(part["bathrooms_effective"].median()),
            "minimum_nights_median": _as_number(part["minimum_nights"].median()),
            "centre_distance_km_median": _as_number(part["distance_centre_euclidean_km"].median()),
            "frederiksberg_n": int((part["official_municipality_code"] == "0147").sum()),
            "unassigned_official_area_n": int(part["official_cv_area_id"].isna().sum()),
            "review_zero_n": int((part["number_of_reviews"] == 0).sum()),
        })
    return rows


def _redundancy(frame: pd.DataFrame) -> tuple[list[dict], list[dict], list[dict]]:
    data = frame.loc[frame["primary_sample_candidate"]]
    pair_rows = []
    for i, left in enumerate(DIAGNOSTIC_NUMERIC):
        for right in DIAGNOSTIC_NUMERIC[i + 1:]:
            pair = data[[left, right]].dropna().astype(float)
            if len(pair) < 30 or pair[left].nunique() < 2 or pair[right].nunique() < 2:
                continue
            rho = pair[left].corr(pair[right], method="spearman")
            if abs(rho) >= 0.7 or frozenset((left, right)) in TARGET_PAIRS:
                pair_rows.append({"left": left, "right": right, "n_complete": len(pair),
                                  "spearman_rho": round(float(rho), 4),
                                  "diagnostic_only": True})
    for i, left in enumerate(AMENITIES):
        for right in AMENITIES[i + 1:]:
            pair = data[[left, right]].dropna().astype(float)
            if len(pair) and pair[left].nunique() > 1 and pair[right].nunique() > 1:
                rho = pair[left].corr(pair[right])  # Phi correlation for two binary fields.
                pair_rows.append({"left": left, "right": right, "n_complete": len(pair),
                                  "spearman_rho": round(float(rho), 4),
                                  "diagnostic_only": True})
    complete = data[list(DIAGNOSTIC_NUMERIC)].dropna().astype(float)
    correlation = complete.corr().to_numpy()
    if np.linalg.matrix_rank(correlation) != len(DIAGNOSTIC_NUMERIC):
        raise RuntimeError("Numeric VIF matrix is singular; investigate redundant controls")
    vif_rows = [
        {"variable": name, "n_complete": len(complete), "vif": round(float(value), 4),
         "diagnostic_only": True}
        for name, value in zip(DIAGNOSTIC_NUMERIC, np.diag(np.linalg.inv(correlation)))
    ]
    area = data.loc[data["context_district_code"].notna()].groupby("context_district_code").agg(
        population=("district_population_2026q3", "first"),
        income=("district_income_2024_dkk_person", "first"),
        households=("district_households_2026q1", "first"),
    ).astype(float)
    area_rows = []
    for left, right in (("population", "income"), ("population", "households"),
                        ("income", "households")):
        pair = area[[left, right]].dropna()
        area_rows.append({"left": left, "right": right, "n_areas": len(pair),
                          "spearman_rho": round(float(pair[left].corr(pair[right], method="spearman")), 4),
                          "scope": "Copenhagen districts only; not listing-level independent observations"})
    return pair_rows, area_rows, vif_rows


def _price_map(conn, frame: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cm, colors
    from matplotlib.patches import Patch, Rectangle

    from src.pipeline.run_official_geography_phase4 import _map_frame, _rings

    grid_size_m = 500
    minimum_cell_missing = 5
    residential = frame.loc[frame["in_study_area"] & frame["entire_home_apt"] &
                            frame["conventional_residential"] & frame["valid_coordinates"]]
    # The private point geometry is used only inside PostGIS for aggregation.
    # No listing-level coordinate or grid assignment is exported.
    cells = conn.execute(text(
        "SELECT floor(ST_X(l.geom_25832)/:size)::integer AS grid_x,"
        "floor(ST_Y(l.geom_25832)/:size)::integer AS grid_y,"
        "count(*) AS listing_n,"
        "count(*) FILTER (WHERE a.missing_or_invalid_price) AS missing_n "
        "FROM analysis.analysis_dataset_v1 a JOIN clean.airbnb_listings l "
        "USING(snapshot_date,listing_id) "
        "WHERE a.in_study_area AND a.entire_home_apt "
        "AND a.conventional_residential AND a.valid_coordinates "
        "GROUP BY 1,2 HAVING count(*) FILTER "
        "(WHERE a.missing_or_invalid_price) >= :minimum "
        "ORDER BY 1,2"
    ), {"size": grid_size_m, "minimum": minimum_cell_missing}).mappings().all()
    raw = conn.execute(text(
        "SELECT area_id,area_name,ST_AsGeoJSON(geom_25832) AS geom_json "
        "FROM spatial.official_cv_areas ORDER BY area_id"
    )).mappings().all()
    neighbours = conn.execute(text(
        "SELECT ST_AsGeoJSON(c.geom_25832) AS geom_json "
        "FROM spatial.map_context_municipalities c CROSS JOIN spatial.study_area s "
        "WHERE s.area_kind='official_study_area' "
        "AND c.municipality_code NOT IN ('0101','0147') "
        "AND ST_DWithin(c.geom_25832,s.geom_25832,3500)"
    )).mappings().all()
    bounds = conn.execute(text(
        "SELECT ST_XMin(g),ST_YMin(g),ST_XMax(g),ST_YMax(g) "
        "FROM (SELECT ST_Extent(geom_25832)::geometry AS g "
        "FROM spatial.official_municipalities) x"
    )).one()
    rates = residential.groupby("official_cv_area_id", dropna=True).agg(
        n=("listing_id", "size"), missing_n=("missing_or_invalid_price", "sum")
    )
    rates["missing_pct"] = 100 * rates["missing_n"] / rates["n"]
    mapped_missing = sum(row["missing_n"] for row in cells)
    all_missing = int(residential["missing_or_invalid_price"].sum())
    if len(raw) != 11 or not cells or mapped_missing > all_missing or set(rates.index) != {
        row["area_id"] for row in raw
    }:
        raise RuntimeError("Missing-price grid, area rate, or official outline failed validation")
    if any(row["missing_n"] < minimum_cell_missing or row["listing_n"] < minimum_cell_missing
           for row in cells):
        raise RuntimeError("A low-count square escaped disclosure suppression")
    context = [json.loads(row["geom_json"]) for row in neighbours]
    areas = [(row["area_id"], json.loads(row["geom_json"])) for row in raw]
    palette = plt.get_cmap("YlGnBu")
    source = ("Sources: Inside Airbnb listings, 2026-06-30 snapshot; official DAGI/DAWA and "
              "City WFS boundaries, acquired 29 Sep 2026. Map CRS: EPSG:25832.")
    context_legend = (Patch(facecolor="#E4EAE7", edgecolor="#A5B4B0"),
                      "Neighbouring municipalities")

    def canvas():
        fig, ax = plt.subplots(figsize=(11, 7.5), dpi=180)
        fig.subplots_adjust(left=0.045, right=0.735, top=0.84, bottom=0.105)
        for geometry in context:
            _rings(ax, geometry, fill="#E4EAE7", edge="#A5B4B0", linewidth=0.65)
        return fig, ax

    def color_key(fig, norm, label: str, note: str) -> None:
        fig.text(0.76, 0.745, label, fontsize=10, fontweight="bold", color="#183449")
        cax = fig.add_axes((0.79, 0.35, 0.025, 0.34))
        bar = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=palette), cax=cax)
        bar.ax.tick_params(labelsize=8, colors="#183449")
        bar.outline.set_edgecolor("#A5B4B0")
        fig.text(0.76, 0.285, note, fontsize=8.2, color="#486174", linespacing=1.45)

    FIG.mkdir(parents=True, exist_ok=True)

    # Map 1: fixed projected square cells. Count is deliberately not interpreted
    # as a missingness rate; sparse cells are suppressed before plotting.
    fig, ax = canvas()
    grid_norm = colors.PowerNorm(gamma=0.55, vmin=minimum_cell_missing,
                                 vmax=max(row["missing_n"] for row in cells))
    for _, geometry in areas:
        _rings(ax, geometry, fill="#D9E8EE", edge="white", linewidth=0.7)
    for row in cells:
        ax.add_patch(Rectangle((row["grid_x"] * grid_size_m, row["grid_y"] * grid_size_m),
                               grid_size_m, grid_size_m,
                               facecolor=palette(grid_norm(row["missing_n"])),
                               edgecolor="white", linewidth=0.2, zorder=3))
    for _, geometry in areas:
        _rings(ax, geometry, fill="none", edge="#385C70", linewidth=0.65,
               outline_only=True)
    _map_frame(ax, fig, bounds, "Missing listed prices", "500 m square grid · counts, not percentages",
               source, legend=[context_legend])
    color_key(fig, grid_norm, "Missing prices / cell",
              f"{len(cells)} cells shown\n{mapped_missing:,} of {all_missing:,} missing\n"
              f"Cells with <{minimum_cell_missing} omitted")
    fig.savefig(FIG / "phase07_missing_price_grid.png", dpi=180)
    plt.close(fig)

    # Map 2: the original denominator-aware district/municipality percentage
    # view, restored as a separate figure in the identical Phase 4 frame.
    fig, ax = canvas()
    low, high = rates["missing_pct"].min(), rates["missing_pct"].max()
    rate_norm = colors.Normalize(vmin=max(0, np.floor(low / 5) * 5 - 5),
                                  vmax=min(100, np.ceil(high / 5) * 5 + 5))
    for area_id, geometry in areas:
        _rings(ax, geometry, fill=palette(rate_norm(rates.loc[area_id, "missing_pct"])),
               edge="white", linewidth=1.1)
    _map_frame(ax, fig, bounds, "Missing listed prices", "Share of conventional entire homes without a valid price",
               source, legend=[context_legend])
    color_key(fig, rate_norm, "Missing price (%)",
              f"{int(rates['n'].sum()):,} listings assigned\n"
              f"{len(residential) - int(rates['n'].sum())} without an official area\n"
              "Colour shows a share, not a count")
    fig.savefig(FIG / "phase07_missing_price_area.png", dpi=180)
    plt.close(fig)


def run() -> dict:
    engine = get_engine()
    try:
        migrate(engine)
        folds = _freeze_cv_folds(engine)
        with engine.connect() as conn:
            frame = pd.read_sql(text(
                f"SELECT a.*, CASE WHEN r.beds ~ '^[0-9]+([.][0-9]+)?$' "
                "THEN r.beds::numeric END AS beds "
                f"FROM {VIEW} a LEFT JOIN raw.inside_airbnb_listings r "
                "ON r._source_file_id=a.source_file_id AND r.id=a.listing_id::text"
            ), conn)
            summary = _validate(conn, frame)
            dictionary = _dictionary(conn, frame)
            missing = _missingness(frame)
            selection = _price_selection(frame)
            pairs, area_pairs, vifs = _redundancy(frame)
            if summary["missing_or_invalid_prices"] / summary["listing_rows"] >= 0.05:
                _price_map(conn, frame)
        _csv(OUT / "missingness_report.csv", missing,
             ["cohort", "group_type", "group_value", "variable", "n", "missing_n", "missing_pct"])
        _csv(OUT / "price_missingness_comparison.csv", selection, list(selection[0]))
        _csv(OUT / "redundancy_pairs.csv", pairs,
             ["left", "right", "n_complete", "spearman_rho", "diagnostic_only"])
        _csv(OUT / "context_area_redundancy.csv", area_pairs,
             ["left", "right", "n_areas", "spearman_rho", "scope"])
        _csv(OUT / "vif_diagnostics.csv", vifs,
             ["variable", "n_complete", "vif", "diagnostic_only"])
        _csv(OUT / "phase07_sample_summary.csv", [summary], list(summary))
        _csv(OUT / "phase07_spatial_cv_folds.csv", folds, list(folds[0]))
        _csv(PROJECT_ROOT / "docs/data_dictionary_analysis.csv", dictionary, list(dictionary[0]))
        return summary
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

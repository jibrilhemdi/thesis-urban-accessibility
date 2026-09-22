"""Run the current non-GTFS analysis for the Copenhagen thesis dataset.

The runner keeps the main price sample inclusive of valid late-scrape prices,
while recording their provenance explicitly. It writes aggregate descriptive
tables, listing-level secondary summaries, model comparisons, diagnostics,
figures, and a run metadata file. Raw comments, host fields, and row-level
coordinates are never written to analysis outputs intended for sharing.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import warnings
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.ingestion.common import PROJECT_ROOT, utc_now, write_json
from src.pipeline.run_minimum_pipeline import element_point, poi_categories, project_wgs84_to_utm32


DEFAULT_SNAPSHOT = "2026-06-30"
WALK_SPEED_MPS = 1.4
SEED = 20260922


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Processed Parquet input; defaults to the latest local Copenhagen output.",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--force", action="store_true", help="Replace existing analysis outputs.")
    return parser.parse_args()


def latest_processed() -> Path:
    paths = sorted(PROJECT_ROOT.glob("data/processed/copenhagen/*/listing_accessibility.parquet"))
    if not paths:
        raise FileNotFoundError("No processed listing_accessibility.parquet file found")
    return paths[-1]


def ensure_price_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Backfill the new price provenance fields for an older processed table."""
    df = df.copy()
    positive = df["source_price_numeric"].gt(0)
    dates = df["last_scraped"].astype("string")
    early = dates.isin(["2026-06-30", "2026-07-01"])
    late = dates.isin(["2026-07-03", "2026-07-04"])
    if "price_scrape_batch" not in df:
        df["price_scrape_batch"] = np.select([early, late], ["early", "late"], default="unknown")
    if "price_from_late_scrape_batch" not in df:
        df["price_from_late_scrape_batch"] = positive & late
    if "price_data_status" not in df:
        df["price_data_status"] = np.select(
            [positive & early, positive & late],
            ["early_price", "late_batch_price"],
            default="missing_price",
        )
    return df


def write_table(frame: pd.DataFrame, path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; use --force to replace analysis outputs")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def summarise_listings(df: pd.DataFrame, tables_root: Path, force: bool) -> dict[str, Any]:
    eligible = df.loc[df["eligible_for_price_model"]].copy()
    eligible["price_batch"] = eligible["price_data_status"]
    batch = (
        df.groupby(["price_scrape_batch", "price_data_status"], dropna=False)
        .agg(listings=("listing_id", "size"), valid_coordinates=("valid_coordinate", "sum"))
        .reset_index()
    )
    write_table(batch, tables_root / "price_scrape_batch_summary.csv", force)

    neighbourhood = (
        df.groupby("airbnb_neighbourhood", dropna=False)
        .agg(
            listings=("listing_id", "size"),
            priced_listings=("eligible_for_price_model", "sum"),
            median_source_price=("source_price_numeric", "median"),
            median_log_price=("log_price_source_currency", "median"),
            median_accessibility_index=("network_nearest_category_accessibility_index", "median"),
            median_centre_distance_km=("distance_to_copenhagen_centre_km", "median"),
        )
        .reset_index()
    )
    neighbourhood["price_coverage"] = neighbourhood["priced_listings"] / neighbourhood["listings"]
    write_table(neighbourhood, tables_root / "listing_neighbourhood_summary.csv", force)

    room_type = (
        df.groupby("room_type", dropna=False)
        .agg(
            listings=("listing_id", "size"),
            priced_listings=("eligible_for_price_model", "sum"),
            median_source_price=("source_price_numeric", "median"),
            median_log_price=("log_price_source_currency", "median"),
        )
        .reset_index()
    )
    room_type["price_coverage"] = room_type["priced_listings"] / room_type["listings"]
    write_table(room_type, tables_root / "listing_room_type_summary.csv", force)

    context = (
        df.groupby(
            [
                "district_name_statbank",
                "statbank_context_provider",
                "statbank_context_geography",
            ],
            dropna=False,
        )
        .agg(
            listings=("listing_id", "size"),
            priced_listings=("eligible_for_price_model", "sum"),
            median_source_price=("source_price_numeric", "median"),
            median_accessibility_index=("network_nearest_category_accessibility_index", "median"),
            population_count=("population_count", "first"),
            household_count=("household_count", "first"),
            average_disposable_income_dkk=("average_disposable_income_dkk", "first"),
            dwelling_count=("dwelling_count", "first"),
        )
        .reset_index()
    )
    context["listings_per_1000_population"] = context["listings"] / context["population_count"] * 1000
    context["listings_per_1000_dwellings"] = context["listings"] / context["dwelling_count"] * 1000
    write_table(context, tables_root / "statbank_context_summary.csv", force)

    overview = {
        "total_listings": int(len(df)),
        "valid_coordinates": int(df["valid_coordinate"].sum()),
        "valid_source_prices": int(df["valid_source_price"].sum()),
        "early_valid_prices": int(((df["price_data_status"] == "early_price") & df["valid_source_price"]).sum()),
        "late_valid_prices": int(((df["price_data_status"] == "late_batch_price") & df["valid_source_price"]).sum()),
        "missing_prices": int((~df["valid_source_price"]).sum()),
        "unique_listing_ids": int(df["listing_id"].nunique()),
        "duplicate_listing_id_rows": int(df["listing_id"].duplicated(keep=False).sum()),
        "price_quantiles": {
            str(q): float(value)
            for q, value in df.loc[df["valid_source_price"], "source_price_numeric"]
            .quantile([0.01, 0.5, 0.99])
            .items()
        },
    }
    write_json(tables_root / "listing_overview.json", overview)
    return overview


def aggregate_calendar(calendar_path: Path, listings: pd.DataFrame, tables_root: Path, force: bool) -> dict[str, Any]:
    listing_parts: list[pd.DataFrame] = []
    monthly_parts: list[pd.DataFrame] = []
    total_rows = 0
    unique_ids: set[int] = set()
    for chunk in pd.read_csv(calendar_path, compression="gzip", chunksize=500_000, low_memory=False):
        total_rows += len(chunk)
        unique_ids.update(chunk["listing_id"].dropna().astype("int64").unique().tolist())
        chunk["available_flag"] = chunk["available"].astype("string").str.lower().isin(["t", "true", "1"])
        chunk["minimum_nights_numeric"] = pd.to_numeric(chunk["minimum_nights"], errors="coerce")
        chunk["maximum_nights_numeric"] = pd.to_numeric(chunk["maximum_nights"], errors="coerce")
        chunk["date_parsed"] = pd.to_datetime(chunk["date"], errors="coerce")
        chunk["month"] = chunk["date_parsed"].dt.to_period("M").astype("string")
        listing_parts.append(
            chunk.groupby("listing_id", dropna=False).agg(
                calendar_rows=("listing_id", "size"),
                calendar_available_days=("available_flag", "sum"),
                calendar_minimum_nights_sum=("minimum_nights_numeric", "sum"),
                calendar_maximum_nights_sum=("maximum_nights_numeric", "sum"),
                calendar_minimum_nights_observations=("minimum_nights_numeric", "count"),
                calendar_maximum_nights_observations=("maximum_nights_numeric", "count"),
                calendar_first_date=("date_parsed", "min"),
                calendar_last_date=("date_parsed", "max"),
            ).reset_index()
        )
        monthly_parts.append(
            chunk.groupby("month", dropna=False).agg(
                calendar_rows=("listing_id", "size"),
                available_days=("available_flag", "sum"),
                mean_minimum_nights=("minimum_nights_numeric", "mean"),
            ).reset_index()
        )

    listing_chunks = pd.concat(listing_parts, ignore_index=True)
    by_listing = listing_chunks.groupby("listing_id", as_index=False).agg(
        calendar_rows=("calendar_rows", "sum"),
        calendar_available_days=("calendar_available_days", "sum"),
        calendar_minimum_nights_sum=("calendar_minimum_nights_sum", "sum"),
        calendar_maximum_nights_sum=("calendar_maximum_nights_sum", "sum"),
        calendar_minimum_nights_observations=("calendar_minimum_nights_observations", "sum"),
        calendar_maximum_nights_observations=("calendar_maximum_nights_observations", "sum"),
        calendar_first_date=("calendar_first_date", "min"),
        calendar_last_date=("calendar_last_date", "max"),
    )
    by_listing["calendar_availability_rate"] = by_listing["calendar_available_days"] / by_listing["calendar_rows"]
    by_listing["calendar_mean_minimum_nights"] = by_listing["calendar_minimum_nights_sum"] / by_listing["calendar_minimum_nights_observations"]
    by_listing["calendar_mean_maximum_nights"] = by_listing["calendar_maximum_nights_sum"] / by_listing["calendar_maximum_nights_observations"]
    by_listing = by_listing.drop(
        columns=[
            "calendar_minimum_nights_sum",
            "calendar_maximum_nights_sum",
            "calendar_minimum_nights_observations",
            "calendar_maximum_nights_observations",
        ]
    )
    by_listing["listing_id"] = pd.to_numeric(by_listing["listing_id"], errors="coerce").astype("Int64")
    write_table(by_listing, tables_root / "calendar_listing_summary.csv", force)

    monthly = pd.concat(monthly_parts, ignore_index=True).groupby("month", as_index=False).agg(
        calendar_rows=("calendar_rows", "sum"),
        available_days=("available_days", "sum"),
        mean_minimum_nights=("mean_minimum_nights", "mean"),
    )
    monthly["availability_rate"] = monthly["available_days"] / monthly["calendar_rows"]
    write_table(monthly, tables_root / "calendar_monthly_summary.csv", force)

    listing_labels = listings[["listing_id", "airbnb_neighbourhood"]].drop_duplicates("listing_id")
    joined = by_listing.merge(listing_labels, on="listing_id", how="left", validate="one_to_one")
    neighbourhood = joined.groupby("airbnb_neighbourhood", dropna=False).agg(
        listings_with_calendar=("listing_id", "nunique"),
        mean_availability_rate=("calendar_availability_rate", "mean"),
        median_availability_rate=("calendar_availability_rate", "median"),
        mean_minimum_nights=("calendar_mean_minimum_nights", "mean"),
    ).reset_index()
    write_table(neighbourhood, tables_root / "calendar_neighbourhood_summary.csv", force)
    return {
        "source_path": calendar_path.relative_to(PROJECT_ROOT).as_posix(),
        "rows": total_rows,
        "unique_listing_ids": len(unique_ids),
        "listing_summary_rows": int(len(by_listing)),
        "date_min": str(by_listing["calendar_first_date"].min().date()),
        "date_max": str(by_listing["calendar_last_date"].max().date()),
        "availability_rate": float(by_listing["calendar_available_days"].sum() / by_listing["calendar_rows"].sum()),
    }


def aggregate_reviews(reviews_path: Path, listings: pd.DataFrame, tables_root: Path, force: bool, snapshot_date: pd.Timestamp) -> dict[str, Any]:
    parts: list[pd.DataFrame] = []
    total_rows = 0
    unique_ids: set[int] = set()
    global_min_date: pd.Timestamp | None = None
    global_max_date: pd.Timestamp | None = None
    for chunk in pd.read_csv(reviews_path, compression="gzip", usecols=["listing_id", "date"], chunksize=500_000, low_memory=False):
        total_rows += len(chunk)
        unique_ids.update(chunk["listing_id"].dropna().astype("int64").unique().tolist())
        chunk["date_parsed"] = pd.to_datetime(chunk["date"], errors="coerce")
        chunk_min = chunk["date_parsed"].min()
        chunk_max = chunk["date_parsed"].max()
        global_min_date = chunk_min if global_min_date is None else min(global_min_date, chunk_min)
        global_max_date = chunk_max if global_max_date is None else max(global_max_date, chunk_max)
        chunk["recent_12m"] = chunk["date_parsed"].between(snapshot_date - pd.Timedelta(days=365), snapshot_date)
        chunk["recent_3m"] = chunk["date_parsed"].between(snapshot_date - pd.Timedelta(days=92), snapshot_date)
        parts.append(
            chunk.groupby("listing_id", dropna=False).agg(
                review_count_all=("listing_id", "size"),
                review_count_12m=("recent_12m", "sum"),
                review_count_3m=("recent_3m", "sum"),
                last_review_date=("date_parsed", "max"),
            ).reset_index()
        )
    by_listing = pd.concat(parts, ignore_index=True).groupby("listing_id", as_index=False).agg(
        review_count_all=("review_count_all", "sum"),
        review_count_12m=("review_count_12m", "sum"),
        review_count_3m=("review_count_3m", "sum"),
        last_review_date=("last_review_date", "max"),
    )
    by_listing["listing_id"] = pd.to_numeric(by_listing["listing_id"], errors="coerce").astype("Int64")
    write_table(by_listing, tables_root / "review_listing_summary.csv", force)

    labels = listings[["listing_id", "airbnb_neighbourhood"]].drop_duplicates("listing_id")
    joined = by_listing.merge(labels, on="listing_id", how="left", validate="one_to_one")
    neighbourhood = joined.groupby("airbnb_neighbourhood", dropna=False).agg(
        listings_with_reviews=("listing_id", "nunique"),
        mean_review_count_12m=("review_count_12m", "mean"),
        median_review_count_12m=("review_count_12m", "median"),
        mean_review_count_all=("review_count_all", "mean"),
    ).reset_index()
    write_table(neighbourhood, tables_root / "review_neighbourhood_summary.csv", force)
    return {
        "source_path": reviews_path.relative_to(PROJECT_ROOT).as_posix(),
        "rows": total_rows,
        "unique_listing_ids": len(unique_ids),
        "listing_summary_rows": int(len(by_listing)),
        "date_min": str(global_min_date.date()),
        "date_max": str(global_max_date.date()),
    }


PROPERTY_NUMERIC = [
    "accommodates",
    "bathrooms_model",
    "bedrooms",
    "beds",
    "minimum_nights",
    "maximum_nights",
    "availability_365",
    "number_of_reviews",
    "number_of_reviews_ltm",
    "review_scores_rating",
    "calculated_host_listings_count",
    "calculated_host_listings_count_entire_homes",
]
PROPERTY_CATEGORICAL = ["room_type", "property_type"]
LOCATION_NUMERIC = ["distance_to_copenhagen_centre_km"]
LOCATION_CATEGORICAL = ["airbnb_neighbourhood"]
ACCESS_INDEX = ["network_nearest_category_accessibility_index"]
ACCESS_COMPONENTS = [
    "walk_time_to_nearest_food_drink_min",
    "walk_time_to_nearest_green_space_min",
    "walk_time_to_nearest_retail_min",
    "walk_time_to_nearest_services_min",
    "walk_time_to_nearest_tourism_min",
    "walk_time_to_nearest_transport_min",
]
CONTEXT_NUMERIC = [
    "population_count",
    "household_count",
    "average_disposable_income_dkk",
    "dwelling_count",
    "average_residents_per_occupied_dwelling",
]
QUALITY_NUMERIC = ["price_from_late_scrape_batch"]


def add_model_features(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_price_flags(df)
    df = df.copy()
    df["bathrooms_model"] = df["bathrooms"].fillna(df["bathrooms_numeric_from_text"])
    df["price_from_late_scrape_batch"] = df["price_from_late_scrape_batch"].astype(int)
    return df


def available_features(df: pd.DataFrame, columns: Iterable[str]) -> list[str]:
    return [column for column in columns if column in df.columns]


def model_specs(df: pd.DataFrame) -> dict[str, list[str]]:
    prop = available_features(df, PROPERTY_NUMERIC + PROPERTY_CATEGORICAL + QUALITY_NUMERIC)
    loc = prop + available_features(df, LOCATION_NUMERIC + LOCATION_CATEGORICAL)
    access_index = loc + available_features(df, ACCESS_INDEX)
    components = loc + available_features(df, ACCESS_COMPONENTS)
    context = prop + available_features(df, LOCATION_NUMERIC + CONTEXT_NUMERIC + ACCESS_INDEX)
    catchments = loc + available_features(
        df,
        [
            f"osm_count_{category}_within_10min_euclidean"
            for category in ["food_drink", "green_space", "retail", "services", "tourism", "transport"]
        ],
    )
    return {
        "property": prop,
        "property_location": loc,
        "accessibility_index": access_index,
        "accessibility_components": components,
        "statbank_context": context,
        "osm_10min_catchments": catchments,
    }


def make_preprocessor(frame: pd.DataFrame, features: list[str]) -> ColumnTransformer:
    numeric = [column for column in features if pd.api.types.is_numeric_dtype(frame[column])]
    categorical = [column for column in features if column not in numeric]
    numeric_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        [("numeric", numeric_pipe, numeric), ("categorical", categorical_pipe, categorical)],
        remainder="drop",
        sparse_threshold=0,
    )


def estimator(name: str, seed: int):
    if name == "ols":
        return LinearRegression()
    if name == "elastic_net":
        return ElasticNet(alpha=0.001, l1_ratio=0.2, max_iter=5000, random_state=seed)
    if name == "gradient_boosting":
        return HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=100,
            max_leaf_nodes=15,
            l2_regularization=0.1,
            random_state=seed,
        )
    raise ValueError(name)


def spatial_groups(frame: pd.DataFrame, block_size_m: int = 1000) -> pd.Series:
    x = np.floor(frame["x_utm32_m"].to_numpy(dtype=float) / block_size_m).astype("int64")
    y = np.floor(frame["y_utm32_m"].to_numpy(dtype=float) / block_size_m).astype("int64")
    return pd.Series(x.astype(str) + "_" + y.astype(str), index=frame.index)


def model_metrics(y_true: np.ndarray, predictions: np.ndarray) -> dict[str, float]:
    return {
        "rmse_log_price": float(np.sqrt(mean_squared_error(y_true, predictions))),
        "mae_log_price": float(mean_absolute_error(y_true, predictions)),
        "r2_log_price": float(r2_score(y_true, predictions)),
    }


def run_cross_validated_models(
    frame: pd.DataFrame,
    specs: dict[str, list[str]],
    sample_name: str,
    seed: int,
    only_specs: set[str] | None = None,
    algorithms: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, dict[str, np.ndarray]]]:
    target = frame["log_price_source_currency"].to_numpy(dtype=float)
    groups = spatial_groups(frame)
    if groups.nunique() < 5:
        raise ValueError("At least five spatial groups are required for GroupKFold")
    splitter = GroupKFold(n_splits=5)
    results: list[dict[str, Any]] = []
    stored_predictions: dict[str, dict[str, np.ndarray]] = {}
    algorithms = algorithms or ["ols", "elastic_net", "gradient_boosting"]
    for spec_name, features in specs.items():
        if only_specs is not None and spec_name not in only_specs:
            continue
        predictions_by_algorithm: dict[str, np.ndarray] = {}
        for algorithm in algorithms:
            print(f"  {sample_name}/{spec_name}/{algorithm}")
            predictions = np.full(len(frame), np.nan, dtype=float)
            for train, test in splitter.split(frame, target, groups):
                preprocessor = make_preprocessor(frame.iloc[train], features)
                model = Pipeline([("preprocess", preprocessor), ("model", estimator(algorithm, seed))])
                model.fit(frame.iloc[train][features], target[train])
                predictions[test] = model.predict(frame.iloc[test][features])
            metrics = model_metrics(target, predictions)
            results.append(
                {
                    "sample": sample_name,
                    "model_spec": spec_name,
                    "algorithm": algorithm,
                    "n": int(len(frame)),
                    "spatial_blocks": int(groups.nunique()),
                    **metrics,
                }
            )
            predictions_by_algorithm[algorithm] = predictions
        stored_predictions[spec_name] = predictions_by_algorithm
    return pd.DataFrame(results), stored_predictions


def fit_primary_coefficients(frame: pd.DataFrame, features: list[str], tables_root: Path, force: bool, seed: int) -> None:
    target = frame["log_price_source_currency"].to_numpy(dtype=float)
    preprocessor = make_preprocessor(frame, features)
    model = Pipeline([("preprocess", preprocessor), ("model", estimator("ols", seed))])
    model.fit(frame[features], target)
    names = model.named_steps["preprocess"].get_feature_names_out()
    coefficients = pd.DataFrame(
        {
            "feature": names,
            "coefficient_log_price": model.named_steps["model"].coef_,
        }
    ).sort_values("coefficient_log_price", key=lambda values: values.abs(), ascending=False)
    coefficients.insert(0, "intercept_log_price", model.named_steps["model"].intercept_)
    write_table(coefficients, tables_root / "primary_ols_coefficients.csv", force)


def morans_i_knn(coordinates: np.ndarray, residuals: np.ndarray, k: int = 8) -> float:
    if len(coordinates) <= k:
        return math.nan
    neighbours = NearestNeighbors(n_neighbors=k + 1).fit(coordinates)
    indices = neighbours.kneighbors(return_distance=False)[:, 1:]
    centred = residuals - residuals.mean()
    numerator = float(sum(centred[i] * centred[j] for i in range(len(centred)) for j in indices[i]))
    denominator = float(np.sum(centred**2))
    if denominator == 0:
        return math.nan
    return float(len(centred) / (len(centred) * k) * numerator / denominator)


def load_osm_points(osm_path: Path) -> dict[str, np.ndarray]:
    payload = json.loads(osm_path.read_text(encoding="utf-8"))
    points: dict[str, list[tuple[float, float]]] = {}
    for element in payload.get("elements", []):
        point = element_point(element)
        if point is None:
            continue
        for category in poi_categories(element.get("tags", {})):
            points.setdefault(category, []).append(point)
    output: dict[str, np.ndarray] = {}
    for category, values in points.items():
        lons = np.array([value[0] for value in values], dtype=float)
        lats = np.array([value[1] for value in values], dtype=float)
        east, north = project_wgs84_to_utm32(lons, lats)
        output[category] = np.column_stack([east, north])
    return output


def add_osm_catchment_features(frame: pd.DataFrame, osm_path: Path, tables_root: Path, force: bool) -> dict[str, Any]:
    points = load_osm_points(osm_path)
    listing_points = frame[["x_utm32_m", "y_utm32_m"]].to_numpy(dtype=float)
    thresholds = {5: WALK_SPEED_MPS * 5 * 60, 10: WALK_SPEED_MPS * 10 * 60, 15: WALK_SPEED_MPS * 15 * 60}
    summary_rows: list[dict[str, Any]] = []
    for category, category_points in sorted(points.items()):
        tree = cKDTree(category_points)
        for minutes, radius in thresholds.items():
            column = f"osm_count_{category}_within_{minutes}min_euclidean"
            frame[column] = tree.query_ball_point(listing_points, r=radius, return_length=True)
            summary_rows.append(
                {
                    "category": category,
                    "threshold_minutes": minutes,
                    "radius_m": radius,
                    "mean_count": float(frame[column].mean()),
                    "median_count": float(frame[column].median()),
                    "zero_count_listings": int((frame[column] == 0).sum()),
                }
            )
    summary = pd.DataFrame(summary_rows)
    write_table(summary, tables_root / "osm_catchment_summary.csv", force)
    return {
        "source_path": osm_path.relative_to(PROJECT_ROOT).as_posix(),
        "categories": {category: int(len(values)) for category, values in points.items()},
        "thresholds_minutes": [5, 10, 15],
        "method": "Euclidean counts around projected listing coordinates using 1.4 m/s radii; not network-reachable counts.",
    }


def make_figures(
    df: pd.DataFrame,
    neighbourhood: pd.DataFrame,
    model_results: pd.DataFrame,
    figures_root: Path,
    force: bool,
) -> list[str]:
    os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/thesis-urban-accessibility-mpl")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_root.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    price_path = figures_root / "price_distribution_by_scrape_batch.png"
    if price_path.exists() and not force:
        raise FileExistsError(price_path)
    fig, ax = plt.subplots(figsize=(8, 5))
    for label, part in df.loc[df["valid_source_price"]].groupby("price_scrape_batch"):
        ax.hist(np.log1p(part["source_price_numeric"]), bins=50, alpha=0.55, label=label)
    ax.set_xlabel("log(1 + source-listed price)")
    ax.set_ylabel("Listings")
    ax.set_title("Source-listed price distribution by scrape batch")
    ax.legend()
    fig.tight_layout()
    fig.savefig(price_path, dpi=160)
    plt.close(fig)
    outputs.append(price_path.relative_to(PROJECT_ROOT).as_posix())

    summary_path = figures_root / "neighbourhood_price_accessibility.png"
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(neighbourhood["median_accessibility_index"], neighbourhood["median_log_price"], s=45)
    for _, row in neighbourhood.iterrows():
        ax.annotate(str(row["airbnb_neighbourhood"]), (row["median_accessibility_index"], row["median_log_price"]), fontsize=7)
    ax.set_xlabel("Median OSM nearest-category accessibility index")
    ax.set_ylabel("Median log source-listed price")
    ax.set_title("Aggregated neighbourhood price and accessibility")
    fig.tight_layout()
    fig.savefig(summary_path, dpi=160)
    plt.close(fig)
    outputs.append(summary_path.relative_to(PROJECT_ROOT).as_posix())

    metrics_path = figures_root / "model_performance.png"
    primary = model_results[model_results["sample"] == "all_valid"]
    pivot = primary.pivot_table(index="model_spec", columns="algorithm", values="rmse_log_price")
    ax = pivot.plot(kind="bar", figsize=(10, 5))
    ax.set_ylabel("Spatial CV RMSE, log price")
    ax.set_title("Spatial cross-validated model performance")
    ax.legend(title="Algorithm")
    fig = ax.get_figure()
    fig.tight_layout()
    fig.savefig(metrics_path, dpi=160)
    plt.close(fig)
    outputs.append(metrics_path.relative_to(PROJECT_ROOT).as_posix())
    return outputs


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve() if args.input else latest_processed()
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    snapshot = input_path.parent.name
    tables_root = PROJECT_ROOT / "outputs" / "tables" / snapshot
    figures_root = PROJECT_ROOT / "outputs" / "figures" / snapshot
    metadata_path = PROJECT_ROOT / "data" / "metadata" / "analysis_run.json"

    print(f"Loading {input_path.relative_to(PROJECT_ROOT)}")
    df = add_model_features(pd.read_parquet(input_path))
    if df["listing_id"].duplicated().any():
        raise ValueError("Processed input contains duplicate listing IDs")
    overview = summarise_listings(df, tables_root, args.force)
    if overview["total_listings"] != 23144 or overview["valid_source_prices"] != 13860:
        warnings.warn(f"Observed counts differ from expected current snapshot counts: {overview}")

    raw_root = PROJECT_ROOT / "data" / "raw" / "inside_airbnb" / "copenhagen" / snapshot
    calendar_summary = aggregate_calendar(raw_root / "data" / "calendar.csv.gz", df, tables_root, args.force)
    review_summary = aggregate_reviews(
        raw_root / "data" / "reviews.csv.gz",
        df,
        tables_root,
        args.force,
        pd.Timestamp(snapshot),
    )

    osm_path = Path(df.attrs.get("osm_path", "")) if df.attrs.get("osm_path") else None
    osm_matches = sorted(PROJECT_ROOT.glob("data/raw/osm/copenhagen/*/responses/amenities_and_transport.json"))
    if not osm_matches:
        raise FileNotFoundError("No OSM amenities_and_transport.json found")
    osm_path = osm_matches[-1]
    catchment_summary = add_osm_catchment_features(df, osm_path, tables_root, args.force)

    model_input = df.loc[df["eligible_for_price_model"]].copy()
    model_input = model_input.replace([np.inf, -np.inf], np.nan)
    model_specs_map = model_specs(model_input)
    all_results: list[pd.DataFrame] = []
    stored_primary_predictions: dict[str, dict[str, np.ndarray]] = {}

    sample_definitions: dict[str, pd.Series] = {
        "all_valid": model_input["valid_source_price"].astype(bool),
        "early_only": model_input["price_data_status"].eq("early_price"),
        "trimmed_all": model_input["source_price_numeric"].between(
            model_input["source_price_numeric"].quantile(0.01),
            model_input["source_price_numeric"].quantile(0.99),
        ),
        "exclude_frederiksberg": model_input["airbnb_neighbourhood"].ne("Frederiksberg"),
    }
    for sample_name, mask in sample_definitions.items():
        sample = model_input.loc[mask].copy()
        print(f"Running models for {sample_name}: {len(sample):,} listings")
        if sample_name == "all_valid":
            selected_specs = {"property", "property_location", "accessibility_index", "accessibility_components", "statbank_context", "osm_10min_catchments"}
            selected_algorithms = ["ols", "elastic_net", "gradient_boosting"]
        else:
            selected_specs = {"property", "property_location", "accessibility_index"}
            selected_algorithms = ["ols", "elastic_net"]
        results, predictions = run_cross_validated_models(
            sample,
            model_specs_map,
            sample_name,
            args.seed,
            only_specs=selected_specs,
            algorithms=selected_algorithms,
        )
        all_results.append(results)
        if sample_name == "all_valid":
            stored_primary_predictions = predictions

    model_results = pd.concat(all_results, ignore_index=True)
    write_table(model_results, tables_root / "model_comparison.csv", args.force)

    primary_frame = model_input.loc[sample_definitions["all_valid"]].copy()
    fit_primary_coefficients(primary_frame, model_specs_map["accessibility_index"], tables_root, args.force, args.seed)
    primary_predictions = stored_primary_predictions["accessibility_index"]["ols"]
    primary_residuals = primary_frame["log_price_source_currency"].to_numpy(dtype=float) - primary_predictions
    moran = morans_i_knn(primary_frame[["x_utm32_m", "y_utm32_m"]].to_numpy(dtype=float), primary_residuals)
    residual_summary = pd.DataFrame(
        [
            {
                "sample": "all_valid",
                "model": "accessibility_index",
                "algorithm": "ols",
                "n": len(primary_frame),
                "moran_i_knn8_oof_residual": moran,
            }
        ]
    )
    write_table(residual_summary, tables_root / "spatial_residual_diagnostics.csv", args.force)

    neighbourhood = pd.read_csv(tables_root / "listing_neighbourhood_summary.csv")
    figure_paths = make_figures(df, neighbourhood, model_results, figures_root, args.force)
    metadata = {
        "analysis": "copenhagen_accessibility_price_and_secondary_outcomes",
        "started_at_utc": utc_now(),
        "completed_at_utc": utc_now(),
        "input": input_path.relative_to(PROJECT_ROOT).as_posix(),
        "snapshot_date": snapshot,
        "random_seed": args.seed,
        "price_rules": {
            "primary_sample": "all valid positive source prices, including late batch",
            "early_only_sensitivity": "price_data_status == early_price",
            "late_batch_flag": "price_from_late_scrape_batch == true",
            "source_currency": "not labelled as DKK or USD",
            "duplicate_listing_ids_in_current_source": int(df["listing_id"].duplicated(keep=False).sum()),
        },
        "expected_validation_counts": {
            "total_listings": 23144,
            "valid_source_prices": 13860,
            "early_valid_prices": 13177,
            "late_valid_prices": 683,
            "missing_prices": 9284,
        },
        "observed_validation_counts": overview,
        "calendar_summary": calendar_summary,
        "review_summary": review_summary,
        "osm_catchment_summary": catchment_summary,
        "model_specs": {name: features for name, features in model_specs_map.items()},
        "model_algorithms": ["ols", "elastic_net", "gradient_boosting"],
        "spatial_cross_validation": "5-fold GroupKFold using 1 km projected coordinate blocks; preprocessing is fitted inside each fold.",
        "spatial_residual_diagnostic": "Moran's I using 8-nearest-neighbour row-standardised weights on out-of-fold OLS residuals.",
        "catchment_feature_caveat": "The 5/10/15-minute OSM catchment counts use Euclidean radii converted from the assumed walking speed; they are not network-reachable counts.",
        "outputs": {
            "tables_directory": tables_root.relative_to(PROJECT_ROOT).as_posix(),
            "figures": figure_paths,
            "metadata": metadata_path.relative_to(PROJECT_ROOT).as_posix(),
        },
        "privacy": "Analysis outputs are aggregated or model summaries; raw comments, host fields, and row-level public coordinates are not exported.",
    }
    write_json(metadata_path, metadata)
    print(f"Completed analysis. Tables: {tables_root.relative_to(PROJECT_ROOT)}")
    print(f"Figures: {figures_root.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

"""Phase 8 descriptive/spatial diagnostics and outcome-blind fixed CV schemes.

The PostGIS analytical view is authoritative. Outputs are aggregate-only; no
listing ID, host field, free text, or private point coordinate is exported.
No price model is fit here.
"""

from __future__ import annotations

import csv
import json
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.model_selection import StratifiedGroupKFold
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.osm_taxonomy_phase5 import TAXONOMY_VERSION
from src.spatial.spatial_diagnostics import distance_bin_covariance, moran_knn


OUT = PROJECT_ROOT / "outputs/tables"
FIG = PROJECT_ROOT / "outputs/figures"
RANDOM_SEED = 20260929
BLOCK_1500_SEED = 20261034  # First geography-only seed meeting municipality support rule.
VERSION = "phase08_v1"
BUFFER_RADII_M = (500, 1000)
DESCRIPTIVE_VARIABLES = (
    "price_nightly", "log_price", "accommodates", "bedrooms", "bathrooms_effective",
    "minimum_nights", "host_listings_count", "number_of_reviews", "review_scores_rating",
    "distance_centre_euclidean_km", "nearest_station_euclidean_m",
    "nearest_station_walking_minutes", "food_social_800m", "food_social_w_10",
    "cultural_tourist_800m", "cultural_tourist_w_10",
)
SUPPORT_VARIABLES = (
    "accommodates", "bedrooms", "bathrooms_effective", "distance_centre_euclidean_km",
    "nearest_station_euclidean_m", "nearest_station_walking_minutes",
    "food_social_800m", "food_social_w_10", "cultural_tourist_800m",
    "cultural_tourist_w_10",
)
MATCHED_PAIRS = (
    ("food_social_800m", "food_social_w_10", "food/social", 800, 10),
    ("food_social_1200m", "food_social_w_15", "food/social", 1200, 15),
    ("food_social_1600m", "food_social_w_20", "food/social", 1600, 20),
    ("cultural_tourist_800m", "cultural_tourist_w_10", "cultural/tourist", 800, 10),
    ("cultural_tourist_1200m", "cultural_tourist_w_15", "cultural/tourist", 1200, 15),
    ("cultural_tourist_1600m", "cultural_tourist_w_20", "cultural/tourist", 1600, 20),
    ("nearest_station_euclidean_m", "nearest_station_network_distance_m", "station", None, None),
)


def _csv(name: str, rows: list[dict], columns: list[str] | None = None) -> None:
    if not rows and columns is None:
        raise ValueError(f"No rows to export: {name}")
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _number(value, places=3):
    return None if pd.isna(value) else round(float(value), places)


def _load(conn) -> pd.DataFrame:
    fields = (
        "snapshot_date,listing_id,price_nightly,log_price,missing_or_invalid_price,"
        "in_study_area,entire_home_apt,conventional_residential,valid_coordinates,"
        "primary_sample_candidate,property_type,room_type,official_municipality_code,"
        "official_cv_area_id,accommodates,bedrooms,bathrooms_effective,minimum_nights,"
        "host_listings_count,number_of_reviews,review_scores_rating,"
        "distance_centre_euclidean_km,nearest_station_euclidean_m,"
        "nearest_station_network_distance_m,nearest_station_walking_minutes,"
        "food_social_800m,food_social_1200m,food_social_1600m,"
        "food_social_w_10,food_social_w_15,food_social_w_20,"
        "cultural_tourist_800m,cultural_tourist_1200m,cultural_tourist_1600m,"
        "cultural_tourist_w_10,cultural_tourist_w_15,cultural_tourist_w_20"
    )
    selected = ",".join("a." + field for field in fields.split(","))
    frame = pd.read_sql(text(
        f"SELECT {selected},ST_X(l.geom_25832) AS metric_x,ST_Y(l.geom_25832) AS metric_y "
        "FROM analysis.analysis_dataset_v1 a JOIN clean.airbnb_listings l "
        "USING(snapshot_date,listing_id) ORDER BY snapshot_date,listing_id"
    ), conn)
    if len(frame) != 23144 or frame[["snapshot_date", "listing_id"]].duplicated().any():
        raise RuntimeError("Phase 8 requires the validated 23,144-row Phase 7 snapshot")
    if frame.loc[frame["primary_sample_candidate"], ["metric_x", "metric_y"]].isna().any().any():
        raise RuntimeError("Priced candidate has no projected EPSG:25832 point")
    return frame


def _frozen_assignments(engine, frame: pd.DataFrame) -> pd.DataFrame:
    """Insert once; later reruns require exact equality, never silently reassign."""
    with engine.begin() as conn:
        areas = [row[0] for row in conn.execute(text(
            "SELECT area_id FROM spatial.official_cv_areas ORDER BY area_id"
        ))]
        if len(areas) != 11:
            raise RuntimeError("Expected ten official Copenhagen districts and Frederiksberg")
        area_fold = {area: number for number, area in enumerate(areas, 1)}
        assigned = frame["official_cv_area_id"].notna()
        if assigned.sum() != 23066 or not set(frame.loc[assigned, "official_cv_area_id"]).issubset(areas):
            raise RuntimeError("Official area assignments changed since Phase 7")
        phase7 = pd.read_sql(text(
            "SELECT snapshot_date,listing_id,block_id,fold_id "
            "FROM analysis.spatial_cv_folds_v1"
        ), conn)
        if len(phase7) != int(assigned.sum()):
            raise RuntimeError("Phase 7 frozen 1-km assignments are incomplete")
        rows = frame[["snapshot_date", "listing_id", "official_cv_area_id",
                      "official_municipality_code", "metric_x", "metric_y"]].merge(
            phase7, on=["snapshot_date", "listing_id"], how="left", validate="one_to_one"
        )
        rows = rows.sort_values(["snapshot_date", "listing_id"]).reset_index(drop=True)
        if rows.loc[assigned, "fold_id"].isna().any() or rows.loc[~assigned, "fold_id"].notna().any():
            raise RuntimeError("Phase 7 spatial folds differ from official assignments")
        rng = np.random.default_rng(RANDOM_SEED)
        random_fold = np.empty(len(rows), dtype=np.int16)
        random_fold[rng.permutation(len(rows))] = np.arange(len(rows)) % 5 + 1
        rows["random_fold"] = random_fold
        rows["geographic_fold"] = rows["official_cv_area_id"].map(area_fold)
        group = rows.loc[assigned].copy()
        group["block_1500m_id"] = (
            np.floor(group["metric_x"].astype(float) / 1500).astype(int).astype(str) + ":" +
            np.floor(group["metric_y"].astype(float) / 1500).astype(int).astype(str)
        )
        groups = group["block_1500m_id"].to_numpy()
        group["block_1500m_fold"] = 0
        splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=BLOCK_1500_SEED)
        for fold, (_, test_idx) in enumerate(splitter.split(
            np.zeros(len(group)), group["official_municipality_code"], groups
        ), start=1):
            group.iloc[test_idx, group.columns.get_loc("block_1500m_fold")] = fold
        if (group["block_1500m_fold"] == 0).any() or group.groupby("block_1500m_id")["block_1500m_fold"].nunique().max() != 1:
            raise RuntimeError("1.5-km robustness blocks are not isolated")
        support = group.groupby("block_1500m_fold")["official_municipality_code"].value_counts().unstack(fill_value=0)
        if len(support) != 5 or support.get("0147", pd.Series(dtype=int)).min() < 100:
            raise RuntimeError("1.5-km robustness folds lack Frederiksberg support")
        rows = rows.merge(group[["snapshot_date", "listing_id", "block_1500m_id", "block_1500m_fold"]],
                          on=["snapshot_date", "listing_id"], how="left", validate="one_to_one")
        records = []
        for row in rows.itertuples(index=False):
            records.append({
                "snapshot_date": row.snapshot_date, "listing_id": int(row.listing_id),
                "random_fold": int(row.random_fold),
                "geographic_fold": None if pd.isna(row.geographic_fold) else int(row.geographic_fold),
                "heldout_area": None if pd.isna(row.official_cv_area_id) else row.official_cv_area_id,
                "block_1km_id": None if pd.isna(row.block_id) else row.block_id,
                "block_1km_fold": None if pd.isna(row.fold_id) else int(row.fold_id),
                "block_1500m_id": None if pd.isna(row.block_1500m_id) else row.block_1500m_id,
                "block_1500m_fold": None if pd.isna(row.block_1500m_fold) else int(row.block_1500m_fold),
            })
        columns = tuple(records[0])
        existing = [dict(row) for row in conn.execute(text(
            f"SELECT {','.join(columns)} FROM analysis.cv_assignments "
            "ORDER BY snapshot_date,listing_id"
        )).mappings()]
        if existing:
            if existing != records:
                raise RuntimeError("Frozen Phase 8 CV assignments differ; refusing overwrite")
        else:
            conn.execute(text(
                "INSERT INTO analysis.cv_assignments ("
                + ",".join(columns) + ",random_seed,block_1500m_seed,assignment_version,block_crs_epsg) "
                "VALUES (" + ",".join(f":{column}" for column in columns) + ","
                ":random_seed,:block_1500m_seed,:assignment_version,25832)"
            ), [{**record, "random_seed": RANDOM_SEED, "block_1500m_seed": BLOCK_1500_SEED,
                 "assignment_version": VERSION} for record in records])
    return rows


_BUFFER_EXPECTED = (
    "SELECT a.area_id AS heldout_area,r.buffer_m,l.snapshot_date,l.listing_id "
    "FROM spatial.official_cv_areas a "
    "CROSS JOIN (VALUES (500),(1000)) AS r(buffer_m) "
    "JOIN features.listing_spatial_base s "
    "ON s.official_cv_area_id IS NOT NULL AND s.official_cv_area_id<>a.area_id "
    "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
    "WHERE ST_DWithin(l.geom_25832,a.geom_25832,r.buffer_m)"
)


def _freeze_buffers(engine) -> None:
    with engine.begin() as conn:
        existing_n = conn.scalar(text("SELECT count(*) FROM analysis.cv_buffer_exclusions"))
        if existing_n:
            mismatch = conn.scalar(text(
                "WITH expected AS (" + _BUFFER_EXPECTED + "),"
                "actual AS (SELECT heldout_area,buffer_m,snapshot_date,listing_id "
                "FROM analysis.cv_buffer_exclusions) "
                "SELECT count(*) FROM ((SELECT * FROM expected EXCEPT SELECT * FROM actual) "
                "UNION ALL (SELECT * FROM actual EXCEPT SELECT * FROM expected)) q"
            ))
            if mismatch:
                raise RuntimeError("Frozen buffered leave-area-out exclusions differ; refusing overwrite")
        else:
            conn.execute(text(
                "INSERT INTO analysis.cv_buffer_exclusions "
                "(heldout_area,buffer_m,snapshot_date,listing_id,crs_epsg,assignment_version) "
                "SELECT heldout_area,buffer_m,snapshot_date,listing_id,25832,:version "
                "FROM (" + _BUFFER_EXPECTED + ") q"
            ), {"version": VERSION})


def _descriptives(frame: pd.DataFrame) -> tuple[list[dict], list[dict], list[dict]]:
    residential = frame["in_study_area"] & frame["entire_home_apt"] & frame["conventional_residential"] & frame["valid_coordinates"]
    primary = frame["primary_sample_candidate"]
    common = primary & frame["official_cv_area_id"].notna() & frame["nearest_station_walking_minutes"].notna()
    cohorts = {"all_listings": frame, "residential_before_price": frame.loc[residential],
               "priced_primary": frame.loc[primary], "common_model_comparison": frame.loc[common]}
    descriptive = []
    for cohort, part in cohorts.items():
        for variable in DESCRIPTIVE_VARIABLES:
            value = pd.to_numeric(part[variable], errors="coerce").dropna().astype(float)
            descriptive.append({"cohort": cohort, "variable": variable, "n_cohort": len(part),
                                "n_observed": len(value), "missing_n": len(part) - len(value),
                                "mean": _number(value.mean()), "sd": _number(value.std()),
                                "min": _number(value.min()), "p05": _number(value.quantile(.05)),
                                "q1": _number(value.quantile(.25)), "median": _number(value.median()),
                                "q3": _number(value.quantile(.75)), "p95": _number(value.quantile(.95)),
                                "max": _number(value.max())})
    composition = []
    for cohort, part in cohorts.items():
        if cohort in ("all_listings", "residential_before_price"):
            counts = part["missing_or_invalid_price"].value_counts(dropna=False)
            for missing, n in counts.items():
                composition.append({"cohort": cohort, "dimension": "price_status",
                                    "category": "missing_or_invalid" if missing else "observed",
                                    "n": int(n), "pct": round(100 * n / len(part), 2)})
        for field in ("property_type", "official_municipality_code", "official_cv_area_id"):
            if field == "property_type" and cohort not in ("priced_primary", "common_model_comparison"):
                continue  # Avoid publishing singleton rare property types.
            for category, n in part[field].fillna("unassigned").value_counts().items():
                composition.append({"cohort": cohort, "dimension": field, "category": category,
                                    "n": int(n), "pct": round(100 * n / len(part), 2)})
    correlations = []
    for euclidean, walking, category, radius, minutes in MATCHED_PAIRS:
        pair = frame.loc[primary, [euclidean, walking]].dropna().astype(float)
        correlations.append({"category": category, "euclidean_variable": euclidean,
                             "network_variable": walking, "straight_radius_m": radius,
                             "walking_minutes": minutes, "n_matched": len(pair),
                             "pearson_r": round(float(pearsonr(pair[euclidean], pair[walking]).statistic), 4),
                             "spearman_rho": round(float(spearmanr(pair[euclidean], pair[walking]).statistic), 4)})
    return descriptive, composition, correlations


def _spatial_diagnostics(frame: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    primary = frame.loc[frame["primary_sample_candidate"]]
    variables = ("log_price", "food_social_800m", "food_social_w_10",
                 "cultural_tourist_800m", "cultural_tourist_w_10",
                 "nearest_station_walking_minutes")
    moran = []
    bins = []
    for offset, variable in enumerate(variables):
        part = primary[["metric_x", "metric_y", variable]].dropna()
        coordinates = part[["metric_x", "metric_y"]].to_numpy(dtype=float)
        values = part[variable].to_numpy(dtype=float)
        result = moran_knn(values, coordinates, k=8, permutations=499,
                           seed=RANDOM_SEED + offset)
        moran.append({"variable": variable, **{key: _number(value, 6) if isinstance(value, float) else value
                                                 for key, value in result.items()},
                      "weights": "directed 8-nearest-neighbour, row-standardised; self excluded"})
        if variable in ("log_price", "food_social_w_10", "nearest_station_walking_minutes"):
            bins.extend({"variable": variable, **{key: _number(value, 6) if isinstance(value, float) else value
                                                   for key, value in row.items()}}
                        for row in distance_bin_covariance(values, coordinates,
                                                             seed=RANDOM_SEED + 100 + offset))
    return moran, bins


def _cv_diagnostics(frame: pd.DataFrame, assignments: pd.DataFrame,
                    buffer_rows: list[dict]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    full = frame.merge(assignments[["snapshot_date", "listing_id", "random_fold", "geographic_fold",
                                    "block_1500m_fold", "fold_id"]],
                       on=["snapshot_date", "listing_id"], validate="one_to_one")
    primary = full.loc[full["primary_sample_candidate"]].copy()
    common = primary.loc[primary["official_cv_area_id"].notna() &
                         primary["nearest_station_walking_minutes"].notna()].copy()
    fold_rows = []
    for scheme, key in (("random_5", "random_fold"), ("grid_1km_5_primary", "fold_id"),
                        ("grid_1500m_5_robustness", "block_1500m_fold"),
                        ("leave_one_official_area_out_11", "official_cv_area_id")):
        for fold, test in common.groupby(key):
            price = test["price_nightly"].astype(float)
            fold_rows.append({"scheme": scheme, "fold": str(int(fold)) if isinstance(fold, (int, float)) else fold,
                              "test_n": len(test), "train_n": len(common) - len(test),
                              "price_min_dkk": _number(price.min()), "price_q1_dkk": _number(price.quantile(.25)),
                              "price_median_dkk": _number(price.median()),
                              "price_q3_dkk": _number(price.quantile(.75)),
                              "price_max_dkk": _number(price.max()),
                              "log_price_sd": _number(test["log_price"].astype(float).std()),
                              "food_e800_median": _number(test["food_social_800m"].median()),
                              "food_w10_median": _number(test["food_social_w_10"].median()),
                              "culture_e800_median": _number(test["cultural_tourist_800m"].median()),
                              "culture_w10_median": _number(test["cultural_tourist_w_10"].median()),
                              "station_walk_min_median": _number(test["nearest_station_walking_minutes"].median()),
                              "accommodates_min": _number(test["accommodates"].min()),
                              "accommodates_max": _number(test["accommodates"].max()),
                              "centre_km_min": _number(test["distance_centre_euclidean_km"].min()),
                              "centre_km_max": _number(test["distance_centre_euclidean_km"].max())})
    support_rows = []
    for area, test in common.groupby("official_cv_area_id"):
        train = common.loc[common["official_cv_area_id"] != area]
        for variable in SUPPORT_VARIABLES:
            t = test[variable].dropna().astype(float)
            r = train[variable].dropna().astype(float)
            support_rows.append({"heldout_area": area, "variable": variable,
                                 "train_n": len(r), "test_n": len(t),
                                 "train_min": _number(r.min()), "train_p05": _number(r.quantile(.05)),
                                 "train_median": _number(r.median()), "train_p95": _number(r.quantile(.95)),
                                 "train_max": _number(r.max()), "test_min": _number(t.min()),
                                 "test_p05": _number(t.quantile(.05)), "test_median": _number(t.median()),
                                 "test_p95": _number(t.quantile(.95)), "test_max": _number(t.max()),
                                 "test_outside_train_range_n": int(((t < r.min()) | (t > r.max())).sum()),
                                 "test_outside_train_range_pct": round(100 * ((t < r.min()) | (t > r.max())).mean(), 2)})
        unseen_municipality = ~test["official_municipality_code"].isin(train["official_municipality_code"])
        unseen_property = ~test["property_type"].isin(train["property_type"])
        support_rows.extend((
            {"heldout_area": area, "variable": "municipality_category", "train_n": len(train),
             "test_n": len(test), "train_min": None, "train_p05": None, "train_median": None,
             "train_p95": None, "train_max": None, "test_min": None, "test_p05": None,
             "test_median": None, "test_p95": None, "test_max": None,
             "test_outside_train_range_n": int(unseen_municipality.sum()),
             "test_outside_train_range_pct": round(100 * unseen_municipality.mean(), 2)},
            {"heldout_area": area, "variable": "property_type_category", "train_n": len(train),
             "test_n": len(test), "train_min": None, "train_p05": None, "train_median": None,
             "train_p95": None, "train_max": None, "test_min": None, "test_p05": None,
             "test_median": None, "test_p95": None, "test_max": None,
             "test_outside_train_range_n": int(unseen_property.sum()),
             "test_outside_train_range_pct": round(100 * unseen_property.mean(), 2)},
        ))
    excluded = {(row["heldout_area"], row["buffer_m"]): row["n_common"] for row in buffer_rows}
    buffer_feasibility = []
    for area, test in common.groupby("official_cv_area_id"):
        unbuffered_train = len(common) - len(test)
        for radius in BUFFER_RADII_M:
            n_excluded = excluded.get((area, radius), 0)
            buffer_feasibility.append({"heldout_area": area, "buffer_m": radius,
                                       "test_n": len(test), "unbuffered_train_n": unbuffered_train,
                                       "additional_train_excluded_n": n_excluded,
                                       "buffered_train_n": unbuffered_train - n_excluded,
                                       "excluded_train_pct": round(100 * n_excluded / unbuffered_train, 2),
                                       "crs_epsg": 25832})
    return fold_rows, support_rows, buffer_feasibility, common


def _plot_distributions(frame: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    primary = frame.loc[frame["primary_sample_candidate"]]
    prices = primary["price_nightly"].astype(float).to_numpy()
    logs = primary["log_price"].astype(float).to_numpy()
    cap = float(np.quantile(prices, .99))
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.7), dpi=180)
    fig.patch.set_facecolor("white")
    for ax in axes:
        ax.set_facecolor("#F2F6F8")
        ax.grid(axis="y", color="white", linewidth=1)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].hist(prices, bins=80, color="#4487A3", edgecolor="none")
    axes[0].set_yscale("log", base=10)
    axes[0].set_xlabel("Listed nightly price (DKK)")
    axes[0].set_ylabel("Listings per bin (log₁₀ y-axis)")
    axes[0].set_title("Full raw distribution", color="#183449")
    axes[1].hist(prices[prices <= cap], bins=60, color="#4487A3", edgecolor="none")
    axes[1].set_xlabel("Listed nightly price (DKK)")
    axes[1].set_ylabel("Listings per bin (linear y-axis)")
    axes[1].set_title(f"Detail ≤ P99 ({cap:,.0f} DKK)", color="#183449")
    axes[2].hist(logs, bins=60, color="#2C5969", edgecolor="none")
    axes[2].set_xlabel("ln(listed nightly price)")
    axes[2].set_ylabel("Listings per bin (linear y-axis)")
    axes[2].set_title("Full log-price distribution", color="#183449")
    fig.suptitle("Listed-price distributions · priced conventional entire homes",
                 fontsize=16, fontweight="bold", color="#183449", y=1.02)
    fig.text(.02, -.055,
             f"Inside Airbnb 2026-06-30 · N={len(prices):,}. Left/right use all listings; centre omits prices above P99 for display only.\n"
             "Each bar counts listings inside one panel-specific price bin; different bin widths mean heights should not be compared across panels.",
             fontsize=8, color="#506575", linespacing=1.45)
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "phase08_price_distributions.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_accessibility_scatter(frame: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import colors, cm
    from matplotlib.ticker import MultipleLocator

    primary = frame.loc[frame["primary_sample_candidate"]]
    panels = (
        ("food_social_800m", "food_social_w_10", "Food/social opportunities", "POIs"),
        ("cultural_tourist_800m", "cultural_tourist_w_10", "Cultural/tourist opportunities", "POIs"),
        ("nearest_station_euclidean_m", "nearest_station_network_distance_m", "Nearest rail/metro station", "metres"),
    )
    paired = [primary[[euclidean, walking]].dropna().astype(float)
              for euclidean, walking, _, _ in panels]
    # Identical transformed axes and bin extents make x/y and colour directly
    # comparable across panels, even though underlying units remain distinct.
    limit = 9.0
    fig, axes = plt.subplots(1, 3, figsize=(14.2, 5.1), dpi=180)
    fig.subplots_adjust(left=.065, right=.86, bottom=.21, top=.80, wspace=.34)
    plots = []
    for ax, pair, (_, _, title, unit) in zip(axes, paired, panels):
        x, y = np.log1p(pair.iloc[:, 0]), np.log1p(pair.iloc[:, 1])
        if not np.isfinite(x).all() or not np.isfinite(y).all() or max(x.max(), y.max()) > limit:
            raise RuntimeError(f"Matched-measure value exceeds the fixed log1p 0–9 range: {title}")
        plot = ax.hexbin(x, y, gridsize=34, mincnt=5, cmap="YlGnBu",
                         linewidths=0, extent=(0, limit, 0, limit))
        plots.append(plot)
        ax.plot([0, limit], [0, limit], linestyle="--",
                linewidth=.9, color="#4C6270")
        ax.set_xlim(0, limit)
        ax.set_ylim(0, limit)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(title, fontsize=11, color="#183449")
        ax.set_xlabel(f"log1p(straight-line {unit})", fontsize=9)
        ax.set_ylabel(f"log1p(walk-network {unit})", fontsize=9)
        ax.xaxis.set_major_locator(MultipleLocator(1.5))
        ax.yaxis.set_major_locator(MultipleLocator(1.5))
        ax.grid(color="#E7EEF1", linewidth=.6)
        ax.set_axisbelow(True)
    max_bin = max(float(plot.get_array().max()) for plot in plots)
    shared_norm = colors.LogNorm(vmin=5, vmax=max_bin)
    for plot in plots:
        plot.set_norm(shared_norm)
    cax = fig.add_axes((.885, .25, .017, .48))
    colour_bar = fig.colorbar(cm.ScalarMappable(norm=shared_norm, cmap="YlGnBu"), cax=cax)
    colour_bar.set_label("Listings per hexagon · shared log scale", fontsize=9)
    fig.suptitle("Matched destinations · straight-line versus walking network", fontsize=16,
                 fontweight="bold", color="#183449", y=.94)
    fig.text(.065, .08, "Same canonical destinations. Both axes in every panel run 0–9 on the log1p scale. "
             "Ticks show ln(1 + POI count or metres); colour shows listings per hexagon. Bins <5 omitted.",
             fontsize=8, color="#506575")
    fig.savefig(FIG / "phase08_euclidean_network_hexbin.png", dpi=180)
    plt.close(fig)


def _map_geography(conn):
    areas = [(row["area_id"], json.loads(row["geojson"])) for row in conn.execute(text(
        "SELECT area_id,ST_AsGeoJSON(geom_25832) geojson FROM spatial.official_cv_areas ORDER BY area_id"
    )).mappings()]
    neighbours = [json.loads(row["geojson"]) for row in conn.execute(text(
        "SELECT ST_AsGeoJSON(c.geom_25832) geojson "
        "FROM spatial.map_context_municipalities c CROSS JOIN spatial.study_area s "
        "WHERE s.area_kind='official_study_area' AND c.municipality_code NOT IN ('0101','0147') "
        "AND ST_DWithin(c.geom_25832,s.geom_25832,3500)"
    )).mappings()]
    bounds = conn.execute(text(
        "SELECT ST_XMin(g),ST_YMin(g),ST_XMax(g),ST_YMax(g) FROM "
        "(SELECT ST_Extent(geom_25832)::geometry g FROM spatial.official_municipalities) x"
    )).one()
    if len(areas) != 11:
        raise RuntimeError("Phase 8 maps require eleven official areas")
    return areas, neighbours, bounds


def _phase4_canvas(neighbours):
    import matplotlib.pyplot as plt
    from src.pipeline.run_official_geography_phase4 import _rings

    fig, ax = plt.subplots(figsize=(11, 7.5), dpi=180)
    fig.subplots_adjust(left=0.045, right=0.735, top=0.84, bottom=0.105)
    for geometry in neighbours:
        _rings(ax, geometry, fill="#E4EAE7", edge="#A5B4B0", linewidth=.65)
    return fig, ax


def _phase4_key(fig, norm, cmap, label, note, legend_rows=1):
    import matplotlib.pyplot as plt
    from matplotlib import cm

    title_y, bar_bottom, bar_height, note_y = {
        1: (.745, .40, .29, .37),
        2: (.70, .37, .27, .34),
        4: (.63, .32, .27, .29),
    }[legend_rows]
    fig.text(.76, title_y, label, fontsize=10, fontweight="bold", color="#183449")
    cax = fig.add_axes((.79, bar_bottom, .025, bar_height))
    bar = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=plt.get_cmap(cmap)), cax=cax)
    bar.ax.tick_params(labelsize=8, colors="#183449")
    bar.outline.set_edgecolor("#A5B4B0")
    fig.text(.76, note_y, note, fontsize=8.2, color="#486174", linespacing=1.45, va="top")


def _map_destinations(conn) -> pd.DataFrame:
    """Public OSM canonical points only, never private listing coordinates."""
    omitted_nearest = conn.scalar(text(
        "SELECT count(DISTINCT w.nearest_station_key) "
        "FROM features.walking_accessibility w "
        "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
        "JOIN spatial.transit_stations p ON p.station_key=w.nearest_station_key "
        "JOIN spatial.study_area s ON s.area_kind='official_study_area' "
        "WHERE l.primary_sample_candidate "
        "AND NOT ST_DWithin(p.geom_25832,s.geom_25832,3500)"
    ))
    if omitted_nearest:
        raise RuntimeError("3.5-km POI display extent omits a selected primary-sample station")
    rows = [dict(row) for row in conn.execute(text(
        "SELECT category,NULL::text AS station_mode,"
        "ST_X(p.geom_25832) AS x,ST_Y(p.geom_25832) AS y "
        "FROM spatial.osm_pois p JOIN spatial.study_area s "
        "ON s.area_kind='official_study_area' AND ST_DWithin(p.geom_25832,s.geom_25832,3500) "
        "WHERE p.taxonomy_version=:taxonomy "
        "UNION ALL "
        "SELECT 'station',p.station_mode,ST_X(p.geom_25832),ST_Y(p.geom_25832) "
        "FROM spatial.transit_stations p JOIN spatial.study_area s "
        "ON s.area_kind='official_study_area' AND ST_DWithin(p.geom_25832,s.geom_25832,3500) "
        "WHERE p.taxonomy_version=:taxonomy"
    ), {"taxonomy": TAXONOMY_VERSION}).mappings()]
    destinations = pd.DataFrame(rows)
    if set(destinations["category"]) != {"food_social", "cultural_tourist", "station"}:
        raise RuntimeError("Phase 8 maps cannot find the frozen Phase 5 destination categories")
    if not set(destinations.loc[destinations["category"] == "station", "station_mode"]).issubset(
            {"metro", "urban_rail", "rail"}):
        raise RuntimeError("Unexpected station type: map would mislabel the frozen measure")
    return destinations


def _plot_maps(conn, frame: pd.DataFrame) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import colors
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from src.pipeline.run_official_geography_phase4 import _map_frame, _rings

    areas, neighbours, bounds = _map_geography(conn)
    source = ("Sources: Airbnb (30 Jun 2026); DAGI/City WFS; OSM BBBike (26 Sep 2026), "
              "© OpenStreetMap contributors. CRS: EPSG:25832.")
    context_legend = [(Patch(facecolor="#E4EAE7", edgecolor="#A5B4B0"), "Neighbouring municipalities")]
    destinations = _map_destinations(conn)
    station_styles = {
        "metro": ("o", "#B44E32", "Metro"),
        "urban_rail": ("s", "#813F68", "Urban/light rail"),
        "rail": ("^", "#A9752C", "Other rail"),
    }

    def destination_legend(family):
        if family == "food":
            return [(Line2D([], [], linestyle="", marker="o", markersize=6,
                            markerfacecolor="#A84D32", markeredgecolor="white"),
                     "Food/social POI")]
        if family == "cultural":
            return [(Line2D([], [], linestyle="", marker="o", markersize=6,
                            markerfacecolor="#A84D32", markeredgecolor="white"),
                     "Cultural/tourist POI")]
        if family == "station":
            return [(Line2D([], [], linestyle="", marker=marker, markersize=7,
                            markerfacecolor=colour, markeredgecolor="white"), name)
                    for marker, colour, name in station_styles.values()]
        return []

    def draw_destinations(ax, family):
        if family == "price":
            return
        category = {"food": "food_social", "cultural": "cultural_tourist",
                    "station": "station"}[family]
        points = destinations.loc[destinations["category"] == category]
        if family == "station":
            for mode, (marker, colour, _) in station_styles.items():
                group = points.loc[points["station_mode"] == mode]
                ax.scatter(group["x"], group["y"], s=32, c=colour, marker=marker,
                           edgecolors="white", linewidths=.45, alpha=.95,
                           zorder=5, rasterized=True)
        else:
            ax.scatter(points["x"], points["y"],
                       s=5 if family == "food" else 11, c="#A84D32",
                       marker="o", alpha=.5 if family == "food" else .75,
                       edgecolors="none", zorder=5, rasterized=True)

    cmap = plt.get_cmap("YlGnBu")
    residential = frame.loc[frame["in_study_area"] & frame["entire_home_apt"] &
                            frame["conventional_residential"] & frame["valid_coordinates"]].copy()
    residential["gx"] = np.floor(residential["metric_x"].astype(float) / 500).astype(int)
    residential["gy"] = np.floor(residential["metric_y"].astype(float) / 500).astype(int)
    cells = residential.groupby(["gx", "gy"]).size().reset_index(name="listing_n")
    cells = cells.loc[cells["listing_n"] >= 5].copy()
    cells["density_km2"] = 4 * cells["listing_n"]  # 500 m square = 0.25 km².
    primary = frame.loc[frame["primary_sample_candidate"] & frame["official_cv_area_id"].notna()].copy()
    primary["gx"] = np.floor(primary["metric_x"].astype(float) / 500).astype(int)
    primary["gy"] = np.floor(primary["metric_y"].astype(float) / 500).astype(int)
    requested_cells = set(zip(cells["gx"], cells["gy"])) | set(zip(primary["gx"], primary["gy"]))
    # Integers come only from floor(projected coordinates); PostGIS handles
    # clipping, so the Python map renderer needs no alternative geometry layer.
    values_sql = ",".join(f"({int(gx)},{int(gy)})" for gx, gy in sorted(requested_cells))
    clipped_cells = {(row["gx"], row["gy"]): json.loads(row["geojson"])
                     for row in conn.execute(text(
                         "WITH grid(gx,gy) AS (VALUES " + values_sql + "), "
                         "clipped AS (SELECT g.gx,g.gy,"
                         "ST_CollectionExtract(ST_Intersection("
                         "ST_MakeEnvelope(g.gx*500,g.gy*500,(g.gx+1)*500,(g.gy+1)*500,25832),"
                         "s.geom_25832),3) AS geom "
                         "FROM grid g CROSS JOIN spatial.study_area s "
                         "WHERE s.area_kind='official_study_area') "
                         "SELECT gx,gy,ST_AsGeoJSON(geom) geojson FROM clipped "
                         "WHERE NOT ST_IsEmpty(geom)"
                     )).mappings()}

    def filled_cell(ax, gx, gy, colour):
        """Render a listing-assigned square clipped to the official study footprint."""
        geometry = clipped_cells.get((int(gx), int(gy)))
        if geometry is None:
            raise RuntimeError(f"Displayed grid cell {gx}:{gy} misses the official study area")
        _rings(ax, geometry, fill=colour, edge="white", linewidth=.2)

    fig, ax = _phase4_canvas(neighbours)
    norm = colors.PowerNorm(gamma=.55, vmin=20, vmax=float(cells["density_km2"].max()))
    for _, geometry in areas:
        _rings(ax, geometry, fill="#D9E8EE", edge="white", linewidth=.7)
    for row in cells.itertuples(index=False):
        filled_cell(ax, row.gx, row.gy, cmap(norm(row.density_km2)))
    for _, geometry in areas:
        _rings(ax, geometry, fill="none", edge="#385C70", linewidth=.65, outline_only=True)
    _map_frame(ax, fig, bounds, "Listing density", "Conventional entire homes · 500 m square grid",
               source, legend=context_legend)
    _phase4_key(fig, norm, "YlGnBu", "Listings / km²",
                f"{len(cells)} cells with ≥5 listings\n{int(cells['listing_n'].sum()):,}/{len(residential):,} shown\n"
                "Density is a 500 m cell count / area")
    fig.savefig(FIG / "phase08_listing_density.png", dpi=180)
    plt.close(fig)

    layers = (
        ("price_nightly", "median_price", "Median listed price", "DKK/night", "Median price (DKK)", "price"),
        ("food_social_800m", "food_euclidean", "Food/social accessibility", "800 m straight-line", "POIs / 800 m", "food"),
        ("food_social_w_10", "food_walking", "Food/social accessibility", "10 minutes walking", "POIs / 10 min", "food"),
        ("cultural_tourist_800m", "cultural_euclidean", "Cultural/tourist accessibility", "800 m straight-line", "POIs / 800 m", "cultural"),
        ("cultural_tourist_w_10", "cultural_walking", "Cultural/tourist accessibility", "10 minutes walking", "POIs / 10 min", "cultural"),
        ("nearest_station_walking_minutes", "station_walking", "Rail/metro station access", "nearest reachable rail/metro; bus stops excluded", "Walk minutes", "station"),
    )
    summaries = {}
    for variable, stem, _, _, _, _ in layers:
        area_summary = primary.groupby("official_cv_area_id")[variable].agg(["count", "median"])
        grid_summary = primary.groupby(["gx", "gy"])[variable].agg(["count", "median"])
        grid_summary = grid_summary.loc[grid_summary["count"] >= 5].reset_index()
        if (set(area_summary.index) != {area for area, _ in areas} or
                area_summary["count"].min() < 5 or grid_summary.empty):
            raise RuntimeError(f"Map {variable} has an incomplete/small-cell denominator")
        summaries[variable] = (area_summary, grid_summary)

    # A matched straight-line/walking pair uses the same colour scale in both
    # geographic resolutions; scales are descriptive and never fit a model.
    norms = {}
    for group in ("price", "food", "cultural", "station"):
        values = np.concatenate([
            summary["median"].to_numpy(dtype=float)
            for variable, _, _, _, _, family in layers if family == group
            for summary in summaries[variable]
        ])
        if not np.isfinite(values).all():
            raise RuntimeError(f"Non-finite map median in {group}")
        norms[group] = (colors.PowerNorm(gamma=.65, vmin=0, vmax=float(values.max()))
                        if group in ("food", "cultural")
                        else colors.Normalize(vmin=float(values.min()), vmax=float(values.max())))
    coverage = []
    for variable, stem, title, measure, label, family in layers:
        area_summary, grid_summary = summaries[variable]
        norm = norms[family]
        observed = int(primary[variable].count())
        shown_grid = int(grid_summary["count"].sum())
        destination_category = {"price": None, "food": "food_social",
                                "cultural": "cultural_tourist", "station": "station"}[family]
        marker_count = (0 if destination_category is None else
                        int((destinations["category"] == destination_category).sum()))
        coverage.extend((
            {"variable": variable, "geography": "official_area", "n_units": len(area_summary),
             "n_available_listings": observed, "n_displayed_listings": observed,
             "n_not_displayed": 0, "smallest_displayed_unit_n": int(area_summary["count"].min()),
             "minimum_cell_n": 5, "destination_marker_count": marker_count,
             "destination_taxonomy_version": TAXONOMY_VERSION, "crs_epsg": 25832},
            {"variable": variable, "geography": "500m_grid", "n_units": len(grid_summary),
             "n_available_listings": observed, "n_displayed_listings": shown_grid,
             "n_not_displayed": observed - shown_grid,
             "smallest_displayed_unit_n": int(grid_summary["count"].min()),
             "minimum_cell_n": 5, "destination_marker_count": marker_count,
             "destination_taxonomy_version": TAXONOMY_VERSION, "crs_epsg": 25832},
        ))
        map_legend = context_legend + destination_legend(family)

        fig, ax = _phase4_canvas(neighbours)
        for area, geometry in areas:
            _rings(ax, geometry, fill=cmap(norm(area_summary.loc[area, "median"])),
                   edge="white", linewidth=1.1)
        draw_destinations(ax, family)
        _map_frame(ax, fig, bounds, title, f"Area median · {measure}", source, legend=map_legend)
        _phase4_key(fig, norm, "YlGnBu", label,
                    f"11 official analysis areas\n{observed:,} contributing listings\n"
                    "Frederiksberg is one municipal unit\nShared scale for matched maps",
                    legend_rows=len(map_legend))
        fig.savefig(FIG / f"phase08_{stem}_area.png", dpi=180)
        plt.close(fig)

        fig, ax = _phase4_canvas(neighbours)
        for _, geometry in areas:
            _rings(ax, geometry, fill="#D9E8EE", edge="white", linewidth=.7)
        for row in grid_summary.itertuples(index=False):
            filled_cell(ax, row.gx, row.gy, cmap(norm(row.median)))
        for _, geometry in areas:
            _rings(ax, geometry, fill="none", edge="#385C70", linewidth=.65,
                   outline_only=True)
        draw_destinations(ax, family)
        _map_frame(ax, fig, bounds, title, f"Listing median · 500 m square grid · {measure}",
                   source, legend=map_legend)
        _phase4_key(fig, norm, "YlGnBu", label,
                    f"{len(grid_summary)} cells with ≥5 values\n{shown_grid:,}/{observed:,} listings shown\n"
                    "Pale blue: none or <5\nClipped to study area\nShared matched-map scale",
                    legend_rows=len(map_legend))
        fig.savefig(FIG / f"phase08_{stem}_grid.png", dpi=180)
        plt.close(fig)
    return coverage


def run() -> dict:
    engine = get_engine()
    try:
        migrate(engine)
        with engine.connect() as conn:
            frame = _load(conn)
        assignments = _frozen_assignments(engine, frame)
        _freeze_buffers(engine)
        with engine.connect() as conn:
            buffer_rows = [dict(row) for row in conn.execute(text(
                "SELECT b.heldout_area,b.buffer_m,"
                "count(*) FILTER (WHERE a.primary_sample_candidate "
                "AND a.nearest_station_walking_minutes IS NOT NULL) AS n_common "
                "FROM analysis.cv_buffer_exclusions b JOIN analysis.analysis_dataset_v1 a "
                "USING(snapshot_date,listing_id) GROUP BY 1,2 ORDER BY 1,2"
            )).mappings()]
            map_coverage = _plot_maps(conn, frame)
        descriptive, composition, correlations = _descriptives(frame)
        moran, distance_bins = _spatial_diagnostics(frame)
        fold_rows, support, buffers, common = _cv_diagnostics(frame, assignments, buffer_rows)
        if len(common) != 12412:
            raise RuntimeError("Fixed Phase 7 common comparison sample changed")
        _plot_distributions(frame)
        _plot_accessibility_scatter(frame)
        _csv("phase08_descriptive_statistics.csv", descriptive)
        _csv("phase08_sample_composition.csv", composition)
        _csv("phase08_accessibility_correlations.csv", correlations)
        _csv("phase08_spatial_moran.csv", moran)
        _csv("phase08_distance_bin_covariance.csv", distance_bins)
        _csv("phase08_cv_fold_summary.csv", fold_rows)
        _csv("phase08_geographic_support.csv", support)
        _csv("phase08_buffer_feasibility.csv", buffers)
        _csv("phase08_map_coverage.csv", map_coverage)
        return {"source_rows": len(frame), "primary_n": int(frame["primary_sample_candidate"].sum()),
                "common_n": len(common), "random_folds": 5, "official_area_folds": 11,
                "phase7_grid_folds_preserved": 5, "robustness_grid_folds": 5,
                "buffer_radii_m": BUFFER_RADII_M, "moran_variables": len(moran),
                "figures": 15, "tables": 9}
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

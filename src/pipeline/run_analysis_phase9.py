"""Phase 9 primary models from the frozen PostGIS analytical view and CV keys.

All public outputs are aggregate. Private listing coordinates and individual
out-of-fold predictions exist only in memory for residual diagnostics.
"""

from __future__ import annotations

import csv
import json
import warnings
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
import sklearn
import statsmodels.api as sm
import xgboost
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import text
from xgboost import XGBRegressor

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, sha256_file, write_json
from src.spatial.spatial_diagnostics import moran_knn


OUT = PROJECT_ROOT / "outputs/tables"
FIG = PROJECT_ROOT / "outputs/figures"
SPEC = PROJECT_ROOT / "docs/preanalysis_specification.md"
VERSION = "phase09_v1"
SEED = 20260929
INNER_SEED = 20260930
PERMUTATIONS = 499
CHART_COLOURS = {
    "M0": "#B8C9D6", "ME": "#EFC8A8", "MW": "#99D3BF", "MEW": "#CBBBE4",
    "OLS": "#91C6B3", "XGBoost": "#C4B2DE", "neutral": "#A9B6C2",
    "text": "#34404A", "grid": "#E7EBEE",
}

AMENITIES = (
    "amenity_wifi", "amenity_dishwasher", "amenity_washer", "amenity_dryer",
    "amenity_workspace", "amenity_free_parking", "amenity_private_balcony",
    "amenity_self_checkin",
)
CATEGORICAL = ("property_type", "official_municipality_code")
BASE_NUMERIC = (
    "accommodates", "bedrooms", "bathrooms_effective", "log1p_minimum_nights",
    "superhost", "log1p_host_listings_count", *AMENITIES,
    "distance_centre_euclidean_km",
)
E_NUMERIC = ("nearest_station_euclidean_km", "log1p_food_e800", "log1p_culture_e800")
W_NUMERIC = ("nearest_station_walking_minutes", "log1p_food_w10", "log1p_culture_w10")
BUS_NUMERIC = ("nearest_bus_stop_euclidean_km",)
FEATURES = {
    "M0": BASE_NUMERIC + CATEGORICAL,
    "ME": BASE_NUMERIC + E_NUMERIC + CATEGORICAL,
    "MW": BASE_NUMERIC + W_NUMERIC + CATEGORICAL,
    "MEW": BASE_NUMERIC + E_NUMERIC + W_NUMERIC + CATEGORICAL,
}
ALL_FEATURES = {**FEATURES, "MW_BUS": FEATURES["MW"] + BUS_NUMERIC}
# Fixed before fitting; three modest, regularised configurations, not a model zoo.
XGB_CANDIDATES = (
    {"max_depth": 2, "n_estimators": 180, "min_child_weight": 10, "reg_lambda": 15},
    {"max_depth": 3, "n_estimators": 240, "min_child_weight": 7, "reg_lambda": 15},
    {"max_depth": 4, "n_estimators": 300, "min_child_weight": 10, "reg_lambda": 25},
)


def _csv(name: str, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {name}")
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _load(conn) -> pd.DataFrame:
    fields = (
        "a.snapshot_date,a.listing_id,a.log_price,a.price_nightly,a.property_type,"
        "a.official_municipality_code,a.official_cv_area_id,a.accommodates,a.bedrooms,"
        "a.bathrooms_effective,a.log1p_minimum_nights,a.superhost,"
        "a.log1p_host_listings_count,a.distance_centre_euclidean_km,"
        "a.nearest_station_euclidean_m,a.nearest_station_walking_minutes,"
        "a.food_social_800m,a.cultural_tourist_800m,a.food_social_w_10,"
        "a.cultural_tourist_w_10,b.nearest_bus_stop_euclidean_m," +
        ",".join("a." + name for name in AMENITIES)
    )
    frame = pd.read_sql(text(
        f"SELECT {fields},c.random_fold,c.heldout_area,c.block_1km_id,"
        "ST_X(l.geom_25832) AS metric_x,ST_Y(l.geom_25832) AS metric_y "
        "FROM analysis.analysis_dataset_v1 a "
        "JOIN analysis.cv_assignments c USING(snapshot_date,listing_id) "
        "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
        "JOIN features.bus_stop_proximity b USING(snapshot_date,listing_id) "
        "WHERE a.primary_sample_candidate AND a.official_cv_area_id IS NOT NULL "
        "AND a.nearest_station_walking_minutes IS NOT NULL "
        "ORDER BY a.snapshot_date,a.listing_id"
    ), conn)
    if len(frame) != 12412 or frame[["snapshot_date", "listing_id"]].duplicated().any():
        raise RuntimeError("Phase 9 requires the frozen 12,412-row unique common sample")
    if frame["log_price"].isna().any() or (frame["price_nightly"] <= 0).any():
        raise RuntimeError("Outcome is missing/non-positive in the common sample")
    if frame[["random_fold", "heldout_area", "block_1km_id", "metric_x", "metric_y"]].isna().any().any():
        raise RuntimeError("A saved CV assignment or EPSG:25832 point is missing")
    if frame["nearest_bus_stop_euclidean_m"].isna().any():
        raise RuntimeError("Secondary bus-stop proximity is incomplete; do not silently impute")
    if frame["random_fold"].nunique() != 5 or frame["heldout_area"].nunique() != 11:
        raise RuntimeError("Frozen random/geographic folds have changed")
    return frame


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Only deterministic, source-defined transforms; no learned statistic here."""
    result = frame.copy()
    result["nearest_station_euclidean_km"] = pd.to_numeric(
        result["nearest_station_euclidean_m"], errors="raise") / 1000.0
    result["nearest_bus_stop_euclidean_km"] = pd.to_numeric(
        result["nearest_bus_stop_euclidean_m"], errors="raise") / 1000.0
    for source, name in (("food_social_800m", "log1p_food_e800"),
                         ("cultural_tourist_800m", "log1p_culture_e800"),
                         ("food_social_w_10", "log1p_food_w10"),
                         ("cultural_tourist_w_10", "log1p_culture_w10")):
        value = pd.to_numeric(result[source], errors="raise")
        if (value.dropna() < 0).any():
            raise RuntimeError(f"Negative opportunity count: {source}")
        result[name] = np.log1p(value)
    for name in set(BASE_NUMERIC + E_NUMERIC + W_NUMERIC + BUS_NUMERIC):
        result[name] = pd.to_numeric(result[name], errors="raise").astype(float)
    if result[list(CATEGORICAL)].isna().any().any():
        raise RuntimeError("Categorical primary controls cannot be NULL")
    return result


def build_preprocessor(feature_set: str) -> ColumnTransformer:
    columns = ALL_FEATURES[feature_set]
    numeric = [column for column in columns if column not in CATEGORICAL]
    # This median and the presence of a missingness indicator are learned anew
    # by each training fold, including every XGBoost inner training split.
    return ColumnTransformer((
        ("numeric", SimpleImputer(strategy="median", add_indicator=True,
                                   keep_empty_features=True), numeric),
        ("category", OneHotEncoder(drop="first", handle_unknown="ignore",
                                    sparse_output=False), list(CATEGORICAL)),
    ), remainder="drop", verbose_feature_names_out=False)


def _outer_splits(frame: pd.DataFrame, scheme: str):
    key = "random_fold" if scheme == "random_5" else "heldout_area"
    for fold, test in frame.groupby(key, sort=True):
        test_idx = test.index.to_numpy(dtype=int)
        train_idx = frame.index[frame[key] != fold].to_numpy(dtype=int)
        if len(test_idx) < 200 or len(train_idx) < 5000:
            raise RuntimeError(f"Unstable {scheme} fold {fold}: {len(train_idx)}/{len(test_idx)}")
        yield str(fold), train_idx, test_idx


def _inner_splits(train: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    splitter = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=INNER_SEED)
    groups = train["block_1km_id"].to_numpy()
    if pd.isna(groups).any() or len(set(groups)) < 4:
        raise RuntimeError("Cannot make four grouped inner folds from training blocks")
    splits = list(splitter.split(np.zeros(len(train)),
                                  train["official_municipality_code"].to_numpy(), groups))
    for learning, validation in splits:
        if len(validation) < 100 or set(groups[learning]) & set(groups[validation]):
            raise RuntimeError("Inner grouped fold is empty or leaks a grid block")
    return splits


def _metrics(y: np.ndarray, prediction: np.ndarray) -> dict:
    return {"n": len(y), "rmse_log": float(np.sqrt(mean_squared_error(y, prediction))),
            "mae_log": float(mean_absolute_error(y, prediction)),
            "r2_log": float(r2_score(y, prediction))}


def _xgb_pipeline(feature_set: str) -> Pipeline:
    return Pipeline((
        ("prep", build_preprocessor(feature_set)),
        ("xgb", XGBRegressor(
            objective="reg:squarederror", tree_method="hist", learning_rate=.05,
            subsample=.85, colsample_bytree=.85, random_state=SEED,
            n_jobs=2, verbosity=0,
        )),
    ))


def _run_cv(frame: pd.DataFrame):
    y = frame["log_price"].to_numpy(dtype=float)
    fold_rows: list[dict] = []
    tuning_rows: list[dict] = []
    oof: dict[tuple[str, str, str], np.ndarray] = {}
    candidates = [{"xgb__" + key: [value] for key, value in candidate.items()}
                  for candidate in XGB_CANDIDATES]
    for scheme in ("random_5", "geographic_11"):
        keys = [("train_mean", "none")] + [
            (model, feature_set) for model in ("OLS", "XGBoost") for feature_set in FEATURES
        ]
        for key in keys:
            oof[(scheme, *key)] = np.full(len(frame), np.nan, dtype=float)
        for fold, train_idx, test_idx in _outer_splits(frame, scheme):
            train = frame.iloc[train_idx]
            test = frame.iloc[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            inner = _inner_splits(train)
            baseline = np.full(len(test), float(y_train.mean()))
            oof[(scheme, "train_mean", "none")][test_idx] = baseline
            fold_rows.append({"cv_scheme": scheme, "fold": fold, "model": "train_mean",
                              "feature_set": "none", "train_n": len(train),
                              **_metrics(y_test, baseline)})
            print(f"Phase 9 {scheme} fold {fold}: train={len(train)} test={len(test)}", flush=True)
            for feature_set, columns in FEATURES.items():
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Found unknown categories")
                    ols = Pipeline((("prep", build_preprocessor(feature_set)),
                                    ("model", LinearRegression())))
                    ols.fit(train[list(columns)], y_train)
                    pred_ols = ols.predict(test[list(columns)])
                    search = GridSearchCV(
                        _xgb_pipeline(feature_set), candidates, cv=inner,
                        scoring="neg_root_mean_squared_error", refit=True,
                        n_jobs=1, error_score="raise", return_train_score=False,
                    )
                    search.fit(train[list(columns)], y_train)
                    pred_xgb = search.predict(test[list(columns)])
                for model, prediction in (("OLS", pred_ols), ("XGBoost", pred_xgb)):
                    if not np.isfinite(prediction).all():
                        raise RuntimeError(f"Non-finite {model}/{feature_set}/{scheme}/{fold} prediction")
                    oof[(scheme, model, feature_set)][test_idx] = prediction
                    fold_rows.append({"cv_scheme": scheme, "fold": fold, "model": model,
                                      "feature_set": feature_set, "train_n": len(train),
                                      **_metrics(y_test, prediction)})
                tuning_rows.append({
                    "cv_scheme": scheme, "fold": fold, "feature_set": feature_set,
                    "inner_folds": len(inner), "inner_group": "phase7_1km_block",
                    "best_inner_rmse_log": -float(search.best_score_),
                    **{key.removeprefix("xgb__"): value for key, value in search.best_params_.items()},
                })
    for key, prediction in oof.items():
        if not np.isfinite(prediction).all():
            raise RuntimeError(f"Incomplete outer OOF predictions: {key}")
    return fold_rows, tuning_rows, oof


def _performance(frame: pd.DataFrame, fold_rows: list[dict], oof: dict):
    y = frame["log_price"].to_numpy(dtype=float)
    pooled = [{"cv_scheme": scheme, "model": model, "feature_set": feature_set,
               **_metrics(y, prediction)}
              for (scheme, model, feature_set), prediction in oof.items()]
    by_key = {(r["cv_scheme"], r["model"], r["feature_set"]): r for r in pooled}
    comparison = []
    for model, feature_set in (("train_mean", "none"), *(
        (model, feature_set) for model in ("OLS", "XGBoost") for feature_set in FEATURES
    )):
        random = by_key[("random_5", model, feature_set)]
        geo = by_key[("geographic_11", model, feature_set)]
        comparison.append({"model": model, "feature_set": feature_set,
                           "random_rmse_log": random["rmse_log"],
                           "geographic_rmse_log": geo["rmse_log"],
                           "geographic_minus_random_rmse": geo["rmse_log"] - random["rmse_log"],
                           "random_r2_log": random["r2_log"],
                           "geographic_r2_log": geo["r2_log"]})
    incremental = []
    for scheme in ("random_5", "geographic_11"):
        for model in ("OLS", "XGBoost"):
            for base, added in (("M0", "ME"), ("M0", "MW"), ("M0", "MEW"),
                                ("ME", "MW"), ("MW", "MEW")):
                old = by_key[(scheme, model, base)]["rmse_log"]
                new = by_key[(scheme, model, added)]["rmse_log"]
                incremental.append({"cv_scheme": scheme, "model": model,
                                    "comparison": f"{added} versus {base}",
                                    "reference_rmse_log": old, "new_rmse_log": new,
                                    "rmse_reduction_log": old - new,
                                    "relative_rmse_reduction_pct": 100 * (old - new) / old})
    geo_summary = []
    folds = pd.DataFrame(fold_rows)
    for (model, feature_set), part in folds.loc[folds["cv_scheme"] == "geographic_11"].groupby(
            ["model", "feature_set"], sort=True):
        geo_summary.append({"model": model, "feature_set": feature_set,
                            "folds": len(part), "fold_n_min": int(part["n"].min()),
                            "fold_n_max": int(part["n"].max()),
                            "median_fold_rmse_log": float(part["rmse_log"].median()),
                            "q1_fold_rmse_log": float(part["rmse_log"].quantile(.25)),
                            "q3_fold_rmse_log": float(part["rmse_log"].quantile(.75)),
                            "median_fold_mae_log": float(part["mae_log"].median()),
                            "median_fold_r2_log": float(part["r2_log"].median())})
    return pooled, comparison, incremental, geo_summary


def _bus_robustness(frame: pd.DataFrame, primary_oof: dict):
    """Separately labelled MW+bus proximity; never changes the primary ladder."""
    y = frame["log_price"].to_numpy(dtype=float)
    columns = ALL_FEATURES["MW_BUS"]
    candidates = [{"xgb__" + key: [value] for key, value in candidate.items()}
                  for candidate in XGB_CANDIDATES]
    predictions = {(scheme, model): np.full(len(frame), np.nan)
                   for scheme in ("random_5", "geographic_11")
                   for model in ("OLS", "XGBoost")}
    folds = []
    tuning = []
    for scheme in ("random_5", "geographic_11"):
        for fold, train_idx, test_idx in _outer_splits(frame, scheme):
            train, test = frame.iloc[train_idx], frame.iloc[test_idx]
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Found unknown categories")
                ols = Pipeline((("prep", build_preprocessor("MW_BUS")),
                                ("model", LinearRegression())))
                ols.fit(train[list(columns)], y[train_idx])
                ols_pred = ols.predict(test[list(columns)])
                search = GridSearchCV(_xgb_pipeline("MW_BUS"), candidates,
                                      cv=_inner_splits(train),
                                      scoring="neg_root_mean_squared_error", refit=True,
                                      n_jobs=1, error_score="raise")
                search.fit(train[list(columns)], y[train_idx])
                xgb_pred = search.predict(test[list(columns)])
            for model, prediction in (("OLS", ols_pred), ("XGBoost", xgb_pred)):
                predictions[(scheme, model)][test_idx] = prediction
                folds.append({"cv_scheme": scheme, "fold": fold, "model": model,
                              "feature_set": "MW_BUS_secondary", "train_n": len(train),
                              **_metrics(y[test_idx], prediction)})
            tuning.append({"cv_scheme": scheme, "fold": fold, "feature_set": "MW_BUS_secondary",
                           "inner_folds": 4, "inner_group": "phase7_1km_block",
                           "best_inner_rmse_log": -float(search.best_score_),
                           **{key.removeprefix("xgb__"): value for key, value in search.best_params_.items()}})
    summary = []
    for (scheme, model), prediction in predictions.items():
        if not np.isfinite(prediction).all():
            raise RuntimeError("Secondary bus robustness has incomplete OOF predictions")
        previous = _metrics(y, primary_oof[(scheme, model, "MW")])
        current = _metrics(y, prediction)
        summary.append({"cv_scheme": scheme, "model": model,
                        "comparison": "MW+bus-stop proximity versus MW",
                        "n": len(frame), "mw_rmse_log": previous["rmse_log"],
                        "mw_bus_rmse_log": current["rmse_log"],
                        "rmse_reduction_log": previous["rmse_log"] - current["rmse_log"],
                        "mw_bus_mae_log": current["mae_log"],
                        "mw_bus_r2_log": current["r2_log"]})
    prep = build_preprocessor("MW_BUS")
    x = np.asarray(prep.fit_transform(frame[list(columns)]), dtype=float)
    names = list(prep.get_feature_names_out())
    fit = sm.OLS(y, sm.add_constant(x, has_constant="add")).fit(cov_type="HC3")
    index = names.index("nearest_bus_stop_euclidean_km") + 1
    ci = fit.conf_int(alpha=.05)[index]
    coefficient = {"feature_set": "MW_BUS_secondary", "term": "nearest_bus_stop_euclidean_km",
                   "n": int(fit.nobs), "beta_log_price": float(fit.params[index]),
                   "robust_se_hc3": float(fit.bse[index]), "ci95_low": float(ci[0]),
                   "ci95_high": float(ci[1]), "p_value": float(fit.pvalues[index]),
                   "interpretation": "association per 1 km farther from an OSM bus-stop point; no service data"}
    return summary, folds, tuning, coefficient


def _full_sample_ols(frame: pd.DataFrame):
    y = frame["log_price"].to_numpy(dtype=float)
    summaries = []
    coefficients = []
    for feature_set, columns in FEATURES.items():
        prep = build_preprocessor(feature_set)
        x = prep.fit_transform(frame[list(columns)])
        names = list(prep.get_feature_names_out())
        design = sm.add_constant(np.asarray(x, dtype=float), has_constant="add")
        fit = sm.OLS(y, design).fit(cov_type="HC3")
        ci = fit.conf_int(alpha=.05)
        summaries.append({"feature_set": feature_set, "n": int(fit.nobs),
                          "parameters": len(fit.params), "r2_in_sample": float(fit.rsquared),
                          "adjusted_r2_in_sample": float(fit.rsquared_adj),
                          "aic": float(fit.aic), "bic": float(fit.bic),
                          "covariance": "HC3", "condition_number": float(fit.condition_number)})
        for i, name in enumerate(("Intercept", *names)):
            beta = float(fit.params[i])
            lower, upper = float(ci[i, 0]), float(ci[i, 1])
            coefficients.append({"feature_set": feature_set, "term": name,
                                 "beta_log_price": beta, "robust_se_hc3": float(fit.bse[i]),
                                 "ci95_low": lower, "ci95_high": upper,
                                 "p_value": float(fit.pvalues[i]),
                                 "approx_percent_change_one_unit": 100 * np.expm1(beta),
                                 "percent_ci95_low": 100 * np.expm1(lower),
                                 "percent_ci95_high": 100 * np.expm1(upper),
                                 "interpretation": "association; one model-unit increase"})
    return summaries, coefficients


def _complete_case_ols(frame: pd.DataFrame) -> list[dict]:
    """Frozen low-missingness explanatory sensitivity; no outcome imputation."""
    complete = frame.loc[frame["bedrooms"].notna()].copy()
    y = complete["log_price"].to_numpy(dtype=float)
    rows = []
    for feature_set, columns in FEATURES.items():
        prep = build_preprocessor(feature_set)
        x = np.asarray(prep.fit_transform(complete[list(columns)]), dtype=float)
        names = list(prep.get_feature_names_out())
        fit = sm.OLS(y, sm.add_constant(x, has_constant="add")).fit(cov_type="HC3")
        ci = fit.conf_int(alpha=.05)
        for term in ("nearest_station_euclidean_km", "nearest_station_walking_minutes",
                     "log1p_food_e800", "log1p_food_w10", "log1p_culture_e800",
                     "log1p_culture_w10"):
            if term in names:
                i = names.index(term) + 1
                rows.append({"feature_set": feature_set, "n_complete_case": len(complete),
                             "n_excluded_missing_bedrooms": len(frame) - len(complete),
                             "term": term, "beta_log_price": float(fit.params[i]),
                             "robust_se_hc3": float(fit.bse[i]),
                             "ci95_low": float(ci[i, 0]), "ci95_high": float(ci[i, 1])})
    return rows


def _residual_moran(frame: pd.DataFrame, oof: dict) -> list[dict]:
    y = frame["log_price"].to_numpy(dtype=float)
    coordinates = frame[["metric_x", "metric_y"]].to_numpy(dtype=float)
    rows = []
    for scheme in ("random_5", "geographic_11"):
        for model in ("OLS", "XGBoost"):
            for feature_set in ("M0", "MW"):
                residual = y - oof[(scheme, model, feature_set)]
                result = moran_knn(residual, coordinates, k=8,
                                   permutations=PERMUTATIONS, seed=SEED + len(rows) + 10)
                rows.append({"cv_scheme": scheme, "model": model,
                             "feature_set": feature_set, "residual_kind": "outer_out_of_fold",
                             "weights": "directed 8-nearest-neighbour, row-standardised; self excluded",
                             **result})
    return rows


def _xgb_shap_summary(frame: pd.DataFrame) -> list[dict]:
    """Full-sample, fixed-configuration descriptive TreeSHAP; never CV evidence."""
    columns = FEATURES["MW"]
    prep = build_preprocessor("MW")
    matrix = np.asarray(prep.fit_transform(frame[list(columns)]), dtype=float)
    feature_names = list(prep.get_feature_names_out())
    candidate = XGB_CANDIDATES[1]
    model = XGBRegressor(objective="reg:squarederror", tree_method="hist", learning_rate=.05,
                         subsample=.85, colsample_bytree=.85, random_state=SEED,
                         n_jobs=2, verbosity=0, **candidate)
    model.fit(matrix, frame["log_price"].to_numpy(dtype=float))
    contributions = model.get_booster().predict(xgboost.DMatrix(matrix), pred_contribs=True)
    if contributions.shape != (len(frame), len(feature_names) + 1):
        raise RuntimeError("Unexpected XGBoost contribution shape")
    if not np.allclose(contributions.sum(axis=1), model.predict(matrix), atol=1e-4):
        raise RuntimeError("XGBoost feature contributions do not sum to predictions")
    return [{"feature": name, "mean_abs_shap_log_price": float(np.abs(contributions[:, i]).mean()),
             "mean_shap_log_price": float(contributions[:, i].mean()),
             "model": "XGBoost MW, full-sample descriptive", "source": "TreeSHAP pred_contribs"}
            for i, name in enumerate(feature_names)]


def _figures(pooled: list[dict], incremental: list[dict], coefficients: list[dict],
             residual: list[dict], shap: list[dict]) -> None:
    from matplotlib.patches import Patch

    FIG.mkdir(parents=True, exist_ok=True)
    pooled_df = pd.DataFrame(pooled)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=180, sharey=True)
    for ax, scheme, title in zip(axes, ("random_5", "geographic_11"),
                                 ("Random five-fold", "Leave one official area out")):
        part = pooled_df.loc[pooled_df["cv_scheme"] == scheme]
        for i, feature_set in enumerate(FEATURES):
            x = np.array([0, 1]) + (i - 1.5) * .17
            heights = [part.loc[(part["model"] == model) &
                                (part["feature_set"] == feature_set), "rmse_log"].iloc[0]
                       for model in ("OLS", "XGBoost")]
            bars = ax.bar(x, heights, width=.16, color=CHART_COLOURS[feature_set],
                          edgecolor="white", linewidth=.5,
                          label=feature_set if ax is axes[0] else None)
            for bar, value in zip(bars, heights):
                ax.text(bar.get_x() + bar.get_width() / 2, value + .006,
                        f"{value:.4f}", ha="center", va="bottom", fontsize=7,
                        color=CHART_COLOURS["text"])
        benchmark = part.loc[part["model"] == "train_mean", "rmse_log"].iloc[0]
        ax.axhline(benchmark, color=CHART_COLOURS["text"], ls="--", lw=1,
                   label="Training mean" if ax is axes[0] else None)
        ax.set_xticks([0, 1], ["OLS", "XGBoost"])
        ax.set_title(title, color=CHART_COLOURS["text"])
        ax.set_ylabel("Pooled out-of-fold RMSE · log price" if ax is axes[0] else "")
        ax.set_facecolor("#F7F6F4")
        ax.grid(axis="y", color="white")
        ax.set_axisbelow(True)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=5, loc="upper center", bbox_to_anchor=(.5, .88),
               frameon=False, fontsize=8)
    fig.suptitle("Predictive error across the fixed outer folds",
                 color=CHART_COLOURS["text"], fontsize=15, y=.98)
    fig.subplots_adjust(top=.75, bottom=.16, left=.08, right=.98, wspace=.24)
    fig.savefig(FIG / "phase09_model_performance.png", dpi=180)
    plt.close(fig)

    inc = pd.DataFrame(incremental)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=180, sharey=True)
    choices = ("ME versus M0", "MW versus M0", "MEW versus M0", "MW versus ME", "MEW versus MW")
    x_min, x_max = -.004, .012
    for ax, scheme, title in zip(axes, ("random_5", "geographic_11"), ("Random", "Geographic")):
        for model, marker in (("OLS", "o"), ("XGBoost", "s")):
            part = inc.loc[(inc["cv_scheme"] == scheme) & (inc["model"] == model)].set_index("comparison")
            values = part.loc[list(choices), "rmse_reduction_log"].to_numpy(dtype=float)
            positions = np.arange(len(choices))
            if not ((values > x_min) & (values < x_max)).all():
                raise RuntimeError("Increment plot range must contain every result")
            ax.scatter(values, positions, marker=marker, s=45,
                       c=CHART_COLOURS[model], edgecolors=CHART_COLOURS["text"],
                       linewidths=.4, label=model)
        ax.axvline(0, color=CHART_COLOURS["neutral"], lw=.8)
        ax.set_xlim(x_min, x_max)
        ax.set_xticks(np.arange(x_min, x_max + .0001, .002))
        ax.set_yticks(range(len(choices)), choices)
        ax.invert_yaxis()
        ax.set_title(title, color=CHART_COLOURS["text"])
        ax.set_xlabel("RMSE reduction in log price (positive = better)")
        ax.grid(axis="x", color=CHART_COLOURS["grid"])
    axes[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "phase09_accessibility_increment.png", dpi=180)
    plt.close(fig)

    coef = pd.DataFrame(coefficients)
    chosen = coef.loc[(coef["feature_set"] == "MW") &
                      (coef["term"].isin(W_NUMERIC))].set_index("term").loc[list(W_NUMERIC)]
    fig, ax = plt.subplots(figsize=(7.5, 3.8), dpi=180)
    for i, (_, row) in enumerate(chosen.iterrows()):
        ax.errorbar(row["beta_log_price"], i,
                    xerr=[[row["beta_log_price"] - row["ci95_low"]],
                          [row["ci95_high"] - row["beta_log_price"]]],
                    fmt="o", color=CHART_COLOURS["MW"],
                    markeredgecolor=CHART_COLOURS["text"], markeredgewidth=.5,
                    capsize=3)
    ax.axvline(0, color=CHART_COLOURS["neutral"], lw=.8)
    ax.set_yticks(range(len(chosen)), ["Station walk minutes", "log1p(food/social count)",
                                        "log1p(cultural/tourist count)"])
    ax.invert_yaxis()
    ax.set_xlabel("Semilog OLS coefficient (HC3 95% interval)")
    ax.set_title("MW associations; not causal effects", color=CHART_COLOURS["text"])
    ax.grid(axis="x", color=CHART_COLOURS["grid"])
    fig.tight_layout()
    fig.savefig(FIG / "phase09_ols_mw_coefficients.png", dpi=180)
    plt.close(fig)

    moran = pd.DataFrame(residual)
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=180)
    labels = [f"{model} {feature_set}" for model in ("OLS", "XGBoost") for feature_set in ("M0", "MW")]
    for i, scheme in enumerate(("random_5", "geographic_11")):
        values = [moran.loc[(moran["cv_scheme"] == scheme) & (moran["model"] == model) &
                            (moran["feature_set"] == feature_set), "moran_i"].iloc[0]
                  for model in ("OLS", "XGBoost") for feature_set in ("M0", "MW")]
        ax.bar(np.arange(4) + (i - .5) * .34, values, width=.32,
               color=(CHART_COLOURS["neutral"], CHART_COLOURS["MW"])[i],
               edgecolor="white", linewidth=.5,
               label=("Random", "Geographic")[i])
    ax.set_xticks(range(4), labels)
    ax.set_ylabel("Moran's I · outer out-of-fold residuals")
    ax.set_title("Residual spatial dependence (8-nearest-neighbour)",
                 color=CHART_COLOURS["text"])
    ax.legend(frameon=False)
    ax.grid(axis="y", color=CHART_COLOURS["grid"])
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(FIG / "phase09_oof_residual_moran.png", dpi=180)
    plt.close(fig)

    importance = pd.DataFrame(shap).sort_values("mean_abs_shap_log_price", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(8.5, 5.4), dpi=180)
    ordered = importance.iloc[::-1]
    bars = ax.barh(ordered["feature"], ordered["mean_abs_shap_log_price"],
                   color=[CHART_COLOURS["MW"] if feature in W_NUMERIC else CHART_COLOURS["M0"]
                          for feature in ordered["feature"]],
                   edgecolor="white", linewidth=.4)
    maximum = float(ordered["mean_abs_shap_log_price"].max())
    ax.set_xlim(0, maximum * 1.16)
    for bar, value in zip(bars, ordered["mean_abs_shap_log_price"]):
        ax.text(float(value) + maximum * .008, bar.get_y() + bar.get_height() / 2,
                f"{value:.4f}", va="center", ha="left", fontsize=7.5,
                color=CHART_COLOURS["text"])
    ax.legend(handles=[Patch(facecolor=CHART_COLOURS["MW"], label="Walking accessibility"),
                       Patch(facecolor=CHART_COLOURS["M0"], label="Other controls")],
              loc="lower right", frameon=False, fontsize=8)
    ax.set_xlabel("Mean |TreeSHAP contribution| · log-price units")
    ax.set_title("XGBoost MW: descriptive feature contributions",
                 color=CHART_COLOURS["text"])
    ax.grid(axis="x", color=CHART_COLOURS["grid"])
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(FIG / "phase09_xgb_mw_shap.png", dpi=180)
    plt.close(fig)


def _geographic_residual_maps(conn, frame: pd.DataFrame, oof: dict) -> tuple[list[dict], list[dict]]:
    """Area and suppressed 500 m grid summaries of geographic OOF residuals."""
    from matplotlib import colors
    from matplotlib.patches import Patch
    from src.pipeline.run_analysis_phase8 import _map_geography, _phase4_canvas, _phase4_key
    from src.pipeline.run_official_geography_phase4 import _map_frame, _rings

    areas, neighbours, bounds = _map_geography(conn)
    area_ids = {area for area, _ in areas}
    y = frame["log_price"].to_numpy(dtype=float)
    cells = pd.DataFrame({"gx": np.floor(frame["metric_x"].to_numpy(dtype=float) / 500).astype(int),
                          "gy": np.floor(frame["metric_y"].to_numpy(dtype=float) / 500).astype(int)})
    summaries = {}
    grids = {}
    rows = []
    coverage = []
    for model in ("OLS", "XGBoost"):
        part = pd.DataFrame({"area": frame["official_cv_area_id"],
                             "gx": cells["gx"], "gy": cells["gy"],
                             "residual": y - oof[("geographic_11", model, "MW")]})
        grouped = part.groupby("area")["residual"].agg(["count", "mean", "median"])
        if set(grouped.index) != area_ids or grouped["count"].min() < 5:
            raise RuntimeError("Geographic OOF residual map denominator changed")
        summaries[model] = grouped
        grid = part.groupby(["gx", "gy"])["residual"].agg(["count", "mean"])
        grid = grid.loc[grid["count"] >= 10]
        if grid.empty or not np.isfinite(grid["mean"]).all():
            raise RuntimeError("Geographic OOF residual grid has no displayable cells")
        grids[model] = grid
        shown = int(grid["count"].sum())
        coverage.append({"model": model, "feature_set": "MW", "cv_scheme": "geographic_11",
                         "geography": "500m_grid", "crs_epsg": 25832,
                         "n_available_listings": len(part), "n_displayed_listings": shown,
                         "n_not_displayed": len(part) - shown, "n_displayed_cells": len(grid),
                         "minimum_cell_n": 10,
                         "smallest_displayed_cell_n": int(grid["count"].min()),
                         "value": "mean observed minus geographic OOF predicted log price"})
        rows.extend({"model": model, "feature_set": "MW", "cv_scheme": "geographic_11",
                     "heldout_area": area, "n": int(row["count"]),
                     "mean_residual_log": float(row["mean"]),
                     "median_residual_log": float(row["median"]),
                     "definition": "observed minus outer-out-of-fold predicted log price"}
                    for area, row in grouped.iterrows())
    requested_cells = set().union(*(set(grid.index) for grid in grids.values()))
    values_sql = ",".join(f"({int(gx)},{int(gy)})" for gx, gy in sorted(requested_cells))
    clipped_cells = {(row["gx"], row["gy"]): json.loads(row["geojson"])
                     for row in conn.execute(text(
                         "WITH grid(gx,gy) AS (VALUES " + values_sql + "), "
                         "clipped AS (SELECT g.gx,g.gy,ST_CollectionExtract(ST_Intersection("
                         "ST_MakeEnvelope(g.gx*500,g.gy*500,(g.gx+1)*500,(g.gy+1)*500,25832),"
                         "s.geom_25832),3) AS geom "
                         "FROM grid g CROSS JOIN spatial.study_area s "
                         "WHERE s.area_kind='official_study_area') "
                         "SELECT gx,gy,ST_AsGeoJSON(geom) geojson FROM clipped "
                         "WHERE NOT ST_IsEmpty(geom)"
                     )).mappings()}
    if set(clipped_cells) != requested_cells:
        raise RuntimeError("Some displayable residual grid cells miss the official study area")
    limit = max(float(summary["mean"].abs().max())
                for summary in (*summaries.values(), *grids.values()))
    norm = colors.TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)
    cmap = plt.get_cmap("RdBu_r")
    source = ("Sources: Inside Airbnb 30 Jun 2026; official DAGI/City WFS geography. "
              "Model predictions are held-out-area out of fold. CRS: EPSG:25832.")
    context_legend = [(Patch(facecolor="#E4EAE7", edgecolor="#A5B4B0"),
                       "Neighbouring municipalities")]
    for model in ("OLS", "XGBoost"):
        fig, ax = _phase4_canvas(neighbours)
        for area, geometry in areas:
            _rings(ax, geometry, fill=cmap(norm(summaries[model].loc[area, "mean"])),
                   edge="white", linewidth=1.1)
        _map_frame(ax, fig, bounds, f"{model} MW · geographic held-out residuals",
                   "Area mean of observed − predicted ln(price); positive means underprediction",
                   source, legend=context_legend)
        _phase4_key(fig, norm, "RdBu_r", "Mean residual · log price",
                    "11 held-out areas; ≥221 listings each\n"
                    "Shared scale across both models\n"
                    "Frederiksberg is one municipality")
        stem = "ols" if model == "OLS" else "xgboost"
        fig.savefig(FIG / f"phase09_geographic_oof_residual_{stem}_mw_area.png", dpi=180)
        plt.close(fig)

        fig, ax = _phase4_canvas(neighbours)
        for _, geometry in areas:
            _rings(ax, geometry, fill="#D9E8EE", edge="white", linewidth=.7)
        for (gx, gy), record in grids[model].iterrows():
            _rings(ax, clipped_cells[(gx, gy)], fill=cmap(norm(record["mean"])),
                   edge="white", linewidth=.2)
        for _, geometry in areas:
            _rings(ax, geometry, fill="none", edge="#385C70", linewidth=.65,
                   outline_only=True)
        _map_frame(ax, fig, bounds, f"{model} MW · geographic held-out residuals",
                   "500 m grid mean of observed − predicted ln(price); positive means underprediction",
                   source, legend=context_legend)
        shown = int(grids[model]["count"].sum())
        _phase4_key(fig, norm, "RdBu_r", "Mean residual · log price",
                    f"{len(grids[model])} cells with ≥10 listings\n"
                    f"{shown:,}/{len(frame):,} listings shown\n"
                    "Pale blue: none or <10\n"
                    "Clipped to study area\nShared scale across four maps")
        fig.savefig(FIG / f"phase09_geographic_oof_residual_{stem}_mw_grid.png", dpi=180)
        plt.close(fig)
    return rows, coverage


def run() -> dict:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            frame = prepare_features(_load(conn))
        fold_rows, tuning_rows, oof = _run_cv(frame)
        pooled, comparison, incremental, geo_summary = _performance(frame, fold_rows, oof)
        ols_ladder, coefficients = _full_sample_ols(frame)
        complete_case = _complete_case_ols(frame)
        bus_summary, bus_folds, bus_tuning, bus_coefficient = _bus_robustness(frame, oof)
        tuning_rows.extend(bus_tuning)
        residual = _residual_moran(frame, oof)
        shap = _xgb_shap_summary(frame)
        _figures(pooled, incremental, coefficients, residual, shap)
        with engine.connect() as conn:
            area_residuals, grid_coverage = _geographic_residual_maps(conn, frame, oof)
        for name, rows in (
            ("phase09_ols_ladder.csv", ols_ladder),
            ("phase09_ols_coefficients.csv", coefficients),
            ("phase09_ols_complete_case_sensitivity.csv", complete_case),
            ("phase09_model_performance.csv", pooled),
            ("phase09_random_vs_geographic_cv.csv", comparison),
            ("phase09_incremental_accessibility.csv", incremental),
            ("phase09_fold_performance.csv", fold_rows),
            ("phase09_geographic_fold_summary.csv", geo_summary),
            ("phase09_residual_moran.csv", residual),
            ("phase09_geographic_residual_by_area.csv", area_residuals),
            ("phase09_geographic_residual_grid_coverage.csv", grid_coverage),
            ("phase09_xgboost_tuning.csv", tuning_rows),
            ("phase09_xgb_mw_shap.csv", shap),
            ("phase09_bus_robustness.csv", bus_summary),
            ("phase09_bus_fold_performance.csv", bus_folds),
            ("phase09_bus_ols_coefficient.csv", [bus_coefficient]),
        ):
            _csv(name, rows)
        metadata = {
            "version": VERSION, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_view": "analysis.analysis_dataset_v1",
            "secondary_bus_source": "features.bus_stop_proximity; bus_stop_proximity_v1; archived Phase 5 PBF",
            "cv_assignments": "analysis.cv_assignments; phase08_v1",
            "common_sample_n": len(frame), "outcome": "ln(positive listed DKK/night)",
            "source_currency_note": "DKK confirmed by user, not explicit in source",
            "preanalysis_spec_sha256": sha256_file(SPEC),
            "feature_sets": {key: list(value) for key, value in FEATURES.items()},
            "secondary_feature_set": list(ALL_FEATURES["MW_BUS"]),
            "cv_schemes": ["random_5", "geographic_11"],
            "inner_cv": "four municipality-stratified grouped 1km folds on outer training only",
            "seed": SEED, "inner_seed": INNER_SEED,
            "xgb_candidates": XGB_CANDIDATES,
            "missingness": "training-fold median plus indicator; database NULLs unchanged",
            "model_families": ["training mean", "semilog OLS", "XGBoost"],
            "residual_weights": "directed 8-NN EPSG:25832, row-standardised; 499 permutations",
            "versions": {"numpy": np.__version__, "pandas": pd.__version__,
                         "scipy": scipy.__version__, "scikit_learn": sklearn.__version__,
                         "statsmodels": sm.__version__, "xgboost": xgboost.__version__},
            "public_output_policy": "aggregate tables and figures only; no row-level coordinates/predictions",
        }
        write_json(OUT / "phase09_run_metadata.json", metadata)
        return {"sample_n": len(frame), "outer_folds": 16,
                "pooled_models": len(pooled), "fold_metrics_rows": len(fold_rows),
                "residual_diagnostics": len(residual), "tables": 17, "figures": 9}
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

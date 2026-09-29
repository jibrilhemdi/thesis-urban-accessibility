"""Frozen-Phase-9-compatible Phase 10 robustness analyses.

Only reads Phase 9 outputs/assignments; creates Phase 10 outputs. No row-level
public coordinates, IDs, outcomes or predictions are exported.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import warnings
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import text
from xgboost import XGBRegressor
import xgboost

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, sha256_file, write_json
from src.pipeline.output_paths import PhaseDirectory
from src.pipeline.run_analysis_phase9 import (
    BASE_NUMERIC, CATEGORICAL, E_NUMERIC, FEATURES, SEED, W_NUMERIC,
    XGB_CANDIDATES, _inner_splits, _metrics, prepare_features,
)

OUT = PhaseDirectory("tables", "phase10")
FIG = PhaseDirectory("figures", "phase10")
VERSION = "phase10_v1"
BUS_COL = "bus_walk_time_min"
REV_COL = "log1p_number_of_reviews"
APARTMENT = {"Entire rental unit", "Entire condo"}
SCHEMES = ("random_5", "geographic_11")
STATUS = {
    "phase9": "primary Phase 9",
    "planned": "pre-specified robustness",
    "bus": "post-Phase-9 amendment",
    "exploratory": "exploratory extension",
}


def _csv(name: str, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"No rows to export: {name}")
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / name, index=False)


def _freeze(conn) -> dict:
    """Hash all published Phase 9 artifacts and the full saved CV assignment."""
    paths = sorted((OUT.glob("phase09_*"))) + sorted(FIG.glob("phase09_*"))
    files = {p.relative_to(PROJECT_ROOT).as_posix(): sha256_file(p) for p in paths if p.is_file()}
    cv = hashlib.sha256()
    rows = conn.execute(text(
        "SELECT snapshot_date,listing_id,random_fold,geographic_fold,heldout_area,"
        "block_1km_id,block_1km_fold,block_1500m_id,block_1500m_fold,"
        "random_seed,block_1500m_seed,assignment_version,block_crs_epsg "
        "FROM analysis.cv_assignments ORDER BY snapshot_date,listing_id"
    ))
    n = 0
    for row in rows:
        cv.update(("|".join("" if value is None else str(value) for value in row) + "\n").encode())
        n += 1
    return {"phase9_file_sha256": files, "cv_assignments_sha256": cv.hexdigest(),
            "cv_assignment_rows": n}


def _load(conn) -> tuple[pd.DataFrame, set[tuple[str, int, int]]]:
    amenity = ",".join("a." + x for x in BASE_NUMERIC if x.startswith("amenity_"))
    sql = (
        "SELECT a.snapshot_date,a.listing_id,a.log_price,a.price_nightly,a.property_type,"
        "a.official_municipality_code,a.official_cv_area_id,a.accommodates,a.bedrooms,"
        "a.bathrooms_effective,a.log1p_minimum_nights,a.superhost,"
        "a.log1p_host_listings_count,a.distance_centre_euclidean_km,"
        "a.nearest_station_euclidean_m,a.nearest_station_walking_minutes,"
        "a.food_social_800m,a.cultural_tourist_800m,a.food_social_w_10,"
        "a.cultural_tourist_w_10,a.food_social_1200m,a.cultural_tourist_1200m,"
        "a.food_social_1600m,a.cultural_tourist_1600m,"
        "a.food_social_w_15,a.cultural_tourist_w_15,"
        "a.food_social_w_20,a.cultural_tourist_w_20,"
        "a.number_of_reviews,a.review_scores_rating,"
        "p.nearest_bus_stop_euclidean_m,b.bus_distance_euclidean_m,b.bus_walk_time_min,"
        "c.random_fold,c.heldout_area,c.block_1km_id,c.block_1500m_fold,"
        "ST_X(l.geom_25832) metric_x,ST_Y(l.geom_25832) metric_y,"
        + amenity + " FROM analysis.analysis_dataset_v1 a "
        "JOIN analysis.cv_assignments c USING(snapshot_date,listing_id) "
        "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
        "JOIN features.bus_stop_proximity p USING(snapshot_date,listing_id) "
        "JOIN features.bus_accessibility b USING(snapshot_date,listing_id) "
        "WHERE a.primary_sample_candidate AND a.official_cv_area_id IS NOT NULL "
        "AND a.nearest_station_walking_minutes IS NOT NULL "
        "ORDER BY a.snapshot_date,a.listing_id"
    )
    frame = pd.read_sql(text(sql), conn)
    if len(frame) != 12412 or frame[["snapshot_date", "listing_id"]].duplicated().any():
        raise RuntimeError("Phase 9 common sample changed")
    if frame[["log_price", "price_nightly", "random_fold", "heldout_area",
              "block_1500m_fold", "metric_x", "metric_y", BUS_COL]].isna().any().any():
        raise RuntimeError("Frozen outcome/assignment or new bus feature missing")
    if (frame["price_nightly"] <= 0).any() or not np.allclose(np.log(frame["price_nightly"]),
                                                              frame["log_price"]):
        raise RuntimeError("Invalid DKK price/log relationship")
    frame = prepare_features(frame).reset_index(drop=True)
    frame[REV_COL] = np.log1p(pd.to_numeric(frame["number_of_reviews"]))
    for minute, radius in ((15, 1200), (20, 1600)):
        for short, src in (("food", "food_social"), ("culture", "cultural_tourist")):
            frame[f"log1p_{short}_e{radius}"] = np.log1p(frame[f"{src}_{radius}m"])
            frame[f"log1p_{short}_w{minute}"] = np.log1p(frame[f"{src}_w_{minute}"])
    exclusions = {(row.heldout_area, row.buffer_m, row.listing_id)
                  for row in conn.execute(text(
                      "SELECT heldout_area,buffer_m,listing_id FROM analysis.cv_buffer_exclusions"
                  ))}
    return frame, exclusions


def _feature_sets() -> dict[str, tuple[str, ...]]:
    result = {key: tuple(value) for key, value in FEATURES.items()}
    result["MW_review"] = tuple(FEATURES["MW"]) + (REV_COL,)
    result["M0_review"] = tuple(FEATURES["M0"]) + (REV_COL,)
    result["MW_bus"] = tuple(FEATURES["MW"]) + (BUS_COL,)
    for minute, radius in ((15, 1200), (20, 1600)):
        result[f"ME_{minute}"] = tuple(BASE_NUMERIC) + (
            "nearest_station_euclidean_km", f"log1p_food_e{radius}",
            f"log1p_culture_e{radius}") + tuple(CATEGORICAL)
        result[f"MW_{minute}"] = tuple(BASE_NUMERIC) + (
            "nearest_station_walking_minutes", f"log1p_food_w{minute}",
            f"log1p_culture_w{minute}") + tuple(CATEGORICAL)
    return result


SETS = _feature_sets()


def _preprocessor(columns: tuple[str, ...]) -> ColumnTransformer:
    numeric = [name for name in columns if name not in CATEGORICAL and name != "official_cv_area_id"]
    categorical = [name for name in columns if name in CATEGORICAL or name == "official_cv_area_id"]
    return ColumnTransformer((
        ("numeric", SimpleImputer(strategy="median", add_indicator=True,
                                   keep_empty_features=True), numeric),
        ("category", OneHotEncoder(drop="first", handle_unknown="ignore",
                                    sparse_output=False), categorical),
    ), remainder="drop", verbose_feature_names_out=False)


def _pipeline(model: str, columns: tuple[str, ...]) -> Pipeline:
    if model == "OLS":
        estimator = LinearRegression()
    else:
        estimator = XGBRegressor(
            objective="reg:squarederror", tree_method="hist", learning_rate=.05,
            subsample=.85, colsample_bytree=.85, random_state=SEED,
            n_jobs=2, verbosity=0)
    return Pipeline((("prep", _preprocessor(columns)),
                     ("model" if model == "OLS" else "xgb", estimator)))


def _splits(frame: pd.DataFrame, scheme: str, exclusions: set | None = None,
            buffer_m: int | None = None):
    key = {"random_5": "random_fold", "geographic_11": "heldout_area",
           "block_1500m_5": "block_1500m_fold"}[scheme]
    for fold, test in frame.groupby(key, sort=True):
        test_idx = test.index.to_numpy(int)
        train = frame.loc[frame[key] != fold]
        if buffer_m is not None:
            train = train.loc[~train["listing_id"].map(
                lambda x: (fold, buffer_m, int(x)) in exclusions)]
        train_idx = train.index.to_numpy(int)
        if len(test_idx) < 50 or len(train_idx) < 1000:
            raise RuntimeError(f"Insufficient {scheme}/{fold} support")
        yield str(fold), train_idx, test_idx


def _run_scenario(frame: pd.DataFrame, analysis: str, specs: tuple[str, ...],
                  schemes: tuple[str, ...], models: tuple[str, ...],
                  exclusions: set | None = None, buffer_m: int | None = None,
                  trim: bool = False) -> tuple[list[dict], list[dict], list[dict]]:
    fold_rows, pooled_rows, tuned = [], [], []
    candidates = [{"xgb__" + key: [value] for key, value in candidate.items()}
                  for candidate in XGB_CANDIDATES]
    for scheme in schemes:
        for fold, train_idx, test_idx in _splits(frame, scheme, exclusions, buffer_m):
            train_removed_buffer = len(frame) - len(test_idx) - len(train_idx)
            outer_train = frame.loc[train_idx]
            outer_test = frame.loc[test_idx]
            cut_low = cut_high = None
            if trim:
                cut_low, cut_high = outer_train["price_nightly"].quantile([.01, .99])
                outer_train = outer_train.loc[outer_train["price_nightly"].between(cut_low, cut_high)]
                outer_test = outer_test.loc[outer_test["price_nightly"].between(cut_low, cut_high)]
            train_removed_trim = len(train_idx) - len(outer_train)
            if len(outer_test) < 40:
                raise RuntimeError(f"Trimmed test fold too small: {fold}")
            print(f"Phase10 {analysis}/{scheme}/{fold}: train={len(outer_train)} test={len(outer_test)}", flush=True)
            inner = _inner_splits(outer_train) if "XGBoost" in models else None
            for feature_set in specs:
                columns = SETS[feature_set]
                for model in models:
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", message="Found unknown categories")
                        if model == "OLS":
                            fitted = _pipeline(model, columns).fit(
                                outer_train[list(columns)], outer_train["log_price"])
                        else:
                            fitted = GridSearchCV(
                                _pipeline(model, columns), candidates, cv=inner,
                                scoring="neg_root_mean_squared_error", refit=True,
                                n_jobs=1, error_score="raise", return_train_score=False)
                            fitted.fit(outer_train[list(columns)], outer_train["log_price"])
                            tuned.append({"analysis": analysis, "cv_scheme": scheme,
                                          "fold": fold, "feature_set": feature_set,
                                          "best_inner_rmse_log": -float(fitted.best_score_),
                                          **{k.removeprefix("xgb__"): v for k, v in fitted.best_params_.items()}})
                        pred = fitted.predict(outer_test[list(columns)])
                    if not np.isfinite(pred).all():
                        raise RuntimeError("Nonfinite prediction")
                    fold_rows.append({"analysis": analysis, "cv_scheme": scheme,
                                      "fold": fold, "model": model,
                                      "feature_set": feature_set,
                                      "train_n": len(outer_train),
                                      "test_n_available": len(test_idx),
                                      "train_removed": train_removed_buffer + train_removed_trim,
                                      "train_removed_buffer": train_removed_buffer,
                                      "train_removed_trim": train_removed_trim,
                                      "test_removed": len(test_idx) - len(outer_test),
                                      "train_price_p01_dkk": cut_low,
                                      "train_price_p99_dkk": cut_high,
                                      **_metrics(outer_test["log_price"].to_numpy(float), pred)})
                    pooled_rows.append({"analysis": analysis, "cv_scheme": scheme,
                                        "model": model, "feature_set": feature_set,
                                        "fold": fold, "index": outer_test.index.to_numpy(int),
                                        "actual": outer_test["log_price"].to_numpy(float),
                                        "predicted": pred})
    grouped = defaultdict(list)
    for item in pooled_rows:
        grouped[item["cv_scheme"], item["model"], item["feature_set"]].append(item)
    summary = []
    for (scheme, model, feature_set), parts in grouped.items():
        actual = np.concatenate([p["actual"] for p in parts])
        pred = np.concatenate([p["predicted"] for p in parts])
        summary.append({"analysis": analysis, "cv_scheme": scheme,
                        "model": model, "feature_set": feature_set,
                        **_metrics(actual, pred)})
    return fold_rows, summary, tuned


def _ols_associations(frame: pd.DataFrame) -> list[dict]:
    """Full-sample HC3 associations; FE is within-area and not LOAO prediction."""
    low, high = frame["price_nightly"].quantile([.01, .99])
    cases = {
        "apartment_condo": (frame.loc[frame["property_type"].isin(APARTMENT)], SETS["MW"]),
        "reviewed_only": (frame.loc[frame["number_of_reviews"] > 0], SETS["MW"]),
        "review_count": (frame, SETS["MW_review"]),
        "threshold_15": (frame, SETS["MW_15"]),
        "threshold_20": (frame, SETS["MW_20"]),
        "price_trim_1_99_full_sample_association":
            (frame.loc[frame.price_nightly.between(low, high)], SETS["MW"]),
        "bus_walking": (frame, SETS["MW_bus"]),
        "area_fixed_effects": (frame, tuple(x for x in SETS["MW"]
                                            if x != "official_municipality_code") +
                               ("official_cv_area_id",)),
    }
    rows = []
    for analysis, (part, columns) in cases.items():
        prep = _preprocessor(columns)
        design = np.asarray(prep.fit_transform(part[list(columns)]), dtype=float)
        names = list(prep.get_feature_names_out())
        fit = sm.OLS(part["log_price"].to_numpy(float),
                     sm.add_constant(design, has_constant="add")).fit(cov_type="HC3")
        intervals = fit.conf_int()
        for term in ("nearest_station_walking_minutes", "log1p_food_w10",
                     "log1p_culture_w10", "log1p_food_w15", "log1p_culture_w15",
                     "log1p_food_w20", "log1p_culture_w20", BUS_COL, REV_COL):
            if term not in names:
                continue
            k = names.index(term) + 1
            rows.append({"analysis": analysis, "sample_n": len(part), "term": term,
                         "beta_log_price": float(fit.params[k]),
                         "robust_se_hc3": float(fit.bse[k]),
                         "ci95_low": float(intervals[k, 0]),
                         "ci95_high": float(intervals[k, 1]),
                         "adjusted_r2_in_sample": float(fit.rsquared_adj),
                         "condition_number": float(fit.condition_number),
                         "interpretation": "association only; fixed effects are within-area" if
                         analysis == "area_fixed_effects" else "association only"})
    return rows


def _bus_diagnostics(frame: pd.DataFrame) -> list[dict]:
    variables = ("bus_distance_euclidean_m", BUS_COL,
                 "nearest_station_euclidean_m", "nearest_station_walking_minutes",
                 "distance_centre_euclidean_km")
    rows = []
    for name in variables:
        values = frame[name].astype(float)
        rows.append({"measure": name, "n": int(values.notna().sum()),
                     "median": float(values.median()), "p05": float(values.quantile(.05)),
                     "p95": float(values.quantile(.95)),
                     "corr_bus_euclidean": float(values.corr(frame["bus_distance_euclidean_m"])),
                     "corr_bus_walking": float(values.corr(frame[BUS_COL])),
                     "unit": "m" if name.endswith("_m") else
                             "km" if name.endswith("_km") else "minutes",
                     "crs_epsg": 25832})
    return rows


def _bus_vif(frame: pd.DataFrame) -> list[dict]:
    columns = SETS["MW_bus"]
    prep = _preprocessor(columns)
    design = np.asarray(prep.fit_transform(frame[list(columns)]), dtype=float)
    names = list(prep.get_feature_names_out())
    design = sm.add_constant(design, has_constant="add")
    rows = []
    for term in (BUS_COL, "nearest_station_walking_minutes", "distance_centre_euclidean_km",
                 "log1p_food_w10", "log1p_culture_w10"):
        index = names.index(term) + 1
        rows.append({"term": term, "vif": float(variance_inflation_factor(design, index)),
                     "n": len(frame), "model": "full-sample MW_bus OLS; descriptive only"})
    return rows


def _bus_spotcheck_groups(frame: pd.DataFrame) -> list[dict]:
    rail_q25, rail_q75 = frame["nearest_station_walking_minutes"].quantile([.25, .75])
    bus_q25 = frame[BUS_COL].quantile(.25)
    groups = {
        "central_within_2km_city_hall": frame.distance_centre_euclidean_km < 2,
        "peripheral_6km_or_more_city_hall": frame.distance_centre_euclidean_km >= 6,
        "far_rail_close_bus": (frame.nearest_station_walking_minutes >= rail_q75) &
                              (frame[BUS_COL] <= bus_q25),
        "close_rail_close_bus": (frame.nearest_station_walking_minutes <= rail_q25) &
                                (frame[BUS_COL] <= bus_q25),
    }
    rows = []
    for label, flag in groups.items():
        part = frame.loc[flag]
        if len(part) < 10:
            raise RuntimeError(f"Unsafe/sparse bus spot-check group: {label}")
        rows.append({"group": label, "n": len(part),
                     "median_bus_walk_time_min": float(part[BUS_COL].median()),
                     "median_bus_euclidean_m": float(part.bus_distance_euclidean_m.median()),
                     "median_rail_walk_time_min": float(part.nearest_station_walking_minutes.median()),
                     "rail_q25_min": rail_q25, "rail_q75_min": rail_q75,
                     "bus_q25_min": bus_q25, "crs_epsg": 25832})
    return rows


def _bus_shap_descriptive(frame: pd.DataFrame) -> list[dict]:
    """Fixed-candidate full-sample TreeSHAP; never used for feature selection."""
    columns = SETS["MW_bus"]
    prep = _preprocessor(columns)
    matrix = np.asarray(prep.fit_transform(frame[list(columns)]), dtype=float)
    names = list(prep.get_feature_names_out())
    model = XGBRegressor(objective="reg:squarederror", tree_method="hist",
                         learning_rate=.05, subsample=.85, colsample_bytree=.85,
                         random_state=SEED, n_jobs=2, verbosity=0,
                         **XGB_CANDIDATES[1])
    model.fit(matrix, frame["log_price"].to_numpy(float))
    contribution = model.get_booster().predict(xgboost.DMatrix(matrix), pred_contribs=True)
    if not np.allclose(contribution.sum(axis=1), model.predict(matrix), atol=1e-4):
        raise RuntimeError("Bus TreeSHAP contributions fail prediction reconciliation")
    baseline = pd.read_csv(OUT / "phase09_xgb_mw_shap.csv").set_index("feature")
    rows = []
    for term in (BUS_COL, "nearest_station_walking_minutes", "log1p_food_w10",
                 "log1p_culture_w10", "distance_centre_euclidean_km"):
        index = names.index(term)
        rows.append({"feature": term,
                     "mean_abs_shap_MW_bus_log_price": float(np.abs(contribution[:, index]).mean()),
                     "mean_abs_shap_phase9_MW_log_price":
                         float(baseline.loc[term, "mean_abs_shap_log_price"]) if term in baseline.index
                         else np.nan,
                     "n": len(frame),
                     "interpretation": "full-sample descriptive contribution; not causal or out-of-fold"})
    return rows


def _representation_diagnostics(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for minute, radius in ((10, 800), (15, 1200), (20, 1600)):
        for short, source in (("food_social", "food_social"),
                              ("cultural_tourist", "cultural_tourist")):
            e = frame[f"{source}_{radius}m"].astype(float)
            w = frame[f"{source}_w_{minute}"].astype(float)
            if (w > e).any():
                raise RuntimeError("Network reachability exceeds same-budget Euclidean count")
            rows.append({"category": short, "walking_minutes": minute,
                         "euclidean_radius_m": radius, "n": len(frame),
                         "different_share": float((e != w).mean()),
                         "median_euclidean_minus_walking": float((e - w).median()),
                         "spearman_correlation": float(e.corr(w, method="spearman")),
                         "crs_epsg": 25832})
    return rows


def _baseline_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (pd.read_csv(OUT / "phase09_model_performance.csv"),
            pd.read_csv(OUT / "phase09_fold_performance.csv"))


def _master(pooled: list[dict], folds: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    baseline, base_folds = _baseline_rows()
    master = []
    for row in baseline.to_dict("records"):
        if row["model"] == "train_mean":
            continue
        ref = baseline.loc[(baseline.cv_scheme == row["cv_scheme"]) &
                           (baseline.model == row["model"]) &
                           (baseline.feature_set == "M0"), "rmse_log"].iloc[0]
        master.append({"analysis": "phase9", "status": STATUS["phase9"],
                       "sample_N": int(row["n"]), "model": row["model"],
                       "accessibility_specification": row["feature_set"],
                       "validation_method": row["cv_scheme"],
                       "RMSE": row["rmse_log"], "MAE": row["mae_log"], "R2": row["r2_log"],
                       "Delta_RMSE_vs_relevant_baseline": ref - row["rmse_log"],
                       "main_accessibility_conclusion": "Phase 9 frozen benchmark",
                       "changes_primary_conclusion": "no", "notes": "Unchanged published Phase 9 output"})
    results = pd.DataFrame(pooled)
    for row in pooled:
        analysis, scheme, model = row["analysis"], row["cv_scheme"], row["model"]
        feature_set = row["feature_set"]
        group = results.loc[(results.analysis == analysis) &
                            (results.cv_scheme == scheme) & (results.model == model)]
        target_baseline = "MW" if analysis == "bus_walking" else "M0"
        if analysis == "review_count":
            target_baseline = "M0_review"
        relevant = group.loc[group.feature_set == target_baseline, "rmse_log"]
        if len(relevant):
            reference = float(relevant.iloc[0])
        else:
            reference = float(baseline.loc[(baseline.cv_scheme == scheme) &
                (baseline.model == model) &
                (baseline.feature_set == target_baseline), "rmse_log"].iloc[0])
        delta = reference - row["rmse_log"]
        sample_changed = row["n"] != 12412
        timing = ("Declared in Phase 10 brief before these fits; not in Phase 7 freeze. "
                  if analysis in {"apartment_condo", "reviewed_only"} else "")
        master.append({"analysis": analysis,
                       "status": STATUS["bus"] if analysis == "bus_walking" else STATUS["planned"],
                       "sample_N": row["n"], "model": model,
                       "accessibility_specification": feature_set,
                       "validation_method": scheme,
                       "RMSE": row["rmse_log"], "MAE": row["mae_log"], "R2": row["r2_log"],
                       "Delta_RMSE_vs_relevant_baseline": delta,
                       "main_accessibility_conclusion": "increment beyond matched baseline" if
                       feature_set != target_baseline else "baseline",
                       "changes_primary_conclusion": "no — sensitivity cannot replace primary",
                       "notes": timing + ("Changed evaluation sample; compare only within this analysis"
                                          if sample_changed else
                                          "Same 12,412 observations and frozen outer assignments")})
    paired = []
    all_folds = pd.concat([base_folds.assign(analysis="phase9"), pd.DataFrame(folds)],
                          ignore_index=True)
    for (analysis, model, scheme, fold), part in all_folds.groupby(
            ["analysis", "model", "cv_scheme", "fold"], sort=True):
        if scheme != "geographic_11":
            continue
        by_spec = part.set_index("feature_set")
        def rmse(name):
            if name in by_spec.index:
                return float(by_spec.loc[name, "rmse_log"])
            if analysis in {"bus_walking", "threshold_15", "threshold_20"}:
                b = base_folds.loc[(base_folds.cv_scheme == scheme) &
                    (base_folds.model == model) & (base_folds.fold.astype(str) == str(fold)) &
                    (base_folds.feature_set == name), "rmse_log"]
                return float(b.iloc[0]) if len(b) else np.nan
            return np.nan
        baseline_name = "M0_review" if analysis == "review_count" else "M0"
        walking_name = ("MW_15" if analysis == "threshold_15" else
                        "MW_20" if analysis == "threshold_20" else
                        "MW_review" if analysis == "review_count" else "MW")
        m0, mw, bus = rmse(baseline_name), rmse(walking_name), rmse("MW_bus")
        mw_reference = rmse("MW") if analysis == "bus_walking" else np.nan
        paired.append({"analysis": analysis, "model": model, "heldout_area": fold,
                       "N_test": int(part["n"].max()), "RMSE_M0": m0, "RMSE_MW": mw,
                       "RMSE_MW_bus": bus, "Delta_MW_vs_M0": m0 - mw,
                       "Delta_bus_vs_MW": mw_reference - bus if analysis == "bus_walking" else np.nan})
    stability = []
    for analysis in sorted(set(row["analysis"] for row in master)):
        if analysis == "phase9":
            continue
        subset = [row for row in master if row["analysis"] == analysis and
                  row["model"] == "XGBoost" and row["validation_method"] == "geographic_11"
                  and row["accessibility_specification"].startswith("MW")]
        signal = max((row["Delta_RMSE_vs_relevant_baseline"] for row in subset), default=np.nan)
        folds_part = [p for p in paired if p["analysis"] == analysis and p["model"] == "XGBoost"]
        positive = sum(np.isfinite(p["Delta_MW_vs_M0"]) and p["Delta_MW_vs_M0"] > 0
                       for p in folds_part)
        for claim in ("C1_E_vs_W_distinct", "C2_access_adds_information",
                      "C3_W_increment_over_E", "C4_geographic_differs_from_random"):
            if claim == "C2_access_adds_information" and analysis == "bus_walking":
                verdict = "not applicable"
                explanation = "MW_bus tests bus information beyond MW, not the original MW-versus-M0 claim"
            elif claim == "C2_access_adds_information" and analysis == "block_1500m":
                block_rows = [r for r in master if r["analysis"] == analysis and
                              r["validation_method"] == "block_1500m_5"]
                delta_x = next(r["Delta_RMSE_vs_relevant_baseline"] for r in block_rows
                               if r["model"] == "XGBoost" and r["accessibility_specification"] == "MW")
                delta_o = next(r["Delta_RMSE_vs_relevant_baseline"] for r in block_rows
                               if r["model"] == "OLS" and r["accessibility_specification"] == "MW")
                verdict = "consistent" if delta_x > 0 and delta_o > 0 else "partially consistent"
                explanation = f"1.5-km block RMSE reductions XGBoost {delta_x:+.4f}, OLS {delta_o:+.4f}"
            elif claim == "C2_access_adds_information" and np.isfinite(signal):
                ols = next((r["Delta_RMSE_vs_relevant_baseline"] for r in master
                            if r["analysis"] == analysis and r["model"] == "OLS" and
                            r["validation_method"] == "geographic_11" and
                            r["accessibility_specification"].startswith("MW")), np.nan)
                verdict = ("partially consistent" if analysis == "buffer_1000m" else
                           "consistent" if signal > 0 and ols > 0 and positive >= 6 else
                           "partially consistent" if signal > 0 or ols > 0 else "inconsistent")
                explanation = (f"Geographic RMSE reductions: XGBoost {signal:+.4f}, "
                               f"OLS {ols:+.4f}; MW improves in {positive}/{len(folds_part)} XGBoost areas")
            elif claim == "C3_W_increment_over_E" and analysis in {"threshold_15", "threshold_20"}:
                e = next((r for r in master if r["analysis"] == analysis and
                          r["model"] == "XGBoost" and r["validation_method"] == "geographic_11" and
                          r["accessibility_specification"].startswith("ME_")), None)
                w = subset[0] if subset else None
                e_ols = next(r for r in master if r["analysis"] == analysis and
                             r["model"] == "OLS" and r["validation_method"] == "geographic_11" and
                             r["accessibility_specification"].startswith("ME_"))
                w_ols = next(r for r in master if r["analysis"] == analysis and
                             r["model"] == "OLS" and r["validation_method"] == "geographic_11" and
                             r["accessibility_specification"].startswith("MW_"))
                xgb_diff = w["RMSE"] - e["RMSE"]
                ols_diff = w_ols["RMSE"] - e_ols["RMSE"]
                verdict = ("consistent" if xgb_diff >= 0 and ols_diff >= 0 else
                           "inconsistent" if xgb_diff < 0 and ols_diff < 0 else
                           "partially consistent")
                explanation = (f"Matched-threshold geographic MW−ME RMSE: "
                               f"XGBoost {xgb_diff:+.4f}, OLS {ols_diff:+.4f}; "
                               "consistent denotes Phase 9's lack of a stable walking advantage")
            elif claim == "C4_geographic_differs_from_random":
                random_w = next((r["RMSE"] for r in master if r["analysis"] == analysis and
                                 r["model"] == "XGBoost" and r["validation_method"] == "random_5"
                                 and r["accessibility_specification"].startswith("MW")), np.nan)
                geographic_w = next((r["RMSE"] for r in master if r["analysis"] == analysis and
                                    r["model"] == "XGBoost" and r["validation_method"] == "geographic_11"
                                    and r["accessibility_specification"].startswith("MW")), np.nan)
                if analysis.startswith("buffer_"):
                    random_w = float(next(r["RMSE"] for r in master if r["analysis"] == "phase9" and
                                          r["model"] == "XGBoost" and r["validation_method"] == "random_5"
                                          and r["accessibility_specification"] == "MW"))
                if analysis == "block_1500m":
                    geographic_w = float(next(r["RMSE"] for r in master if r["analysis"] == analysis and
                                              r["model"] == "XGBoost" and
                                              r["validation_method"] == "block_1500m_5" and
                                              r["accessibility_specification"] == "MW"))
                    random_w = float(next(r["RMSE"] for r in master if r["analysis"] == "phase9" and
                                          r["model"] == "XGBoost" and r["validation_method"] == "random_5"
                                          and r["accessibility_specification"] == "MW"))
                if np.isfinite(random_w) and np.isfinite(geographic_w):
                    verdict = "consistent" if geographic_w > random_w else "inconsistent"
                    explanation = f"Separated−random XGBoost MW RMSE {geographic_w-random_w:+.4f}"
                else:
                    verdict, explanation = "not applicable", "No paired random/geographic comparison"
            elif claim == "C1_E_vs_W_distinct" and analysis in {"threshold_15", "threshold_20"}:
                verdict = "consistent"
                explanation = "Matched straight-line and route-budget measures remain distinct constructs; see representation diagnostics"
            else:
                verdict, explanation = "not applicable", "This analysis does not independently test this claim"
            stability.append({"analysis": analysis, "claim": claim, "assessment": verdict,
                              "explanation": explanation})
    return master, paired, stability


def synthesize_only() -> None:
    """Regenerate synthesis/figures from saved Phase 10 fits without refitting."""
    fold_frame = pd.read_csv(OUT / "phase10_fold_performance.csv")
    pooled = pd.read_csv(OUT / "phase10_model_performance.csv").to_dict("records")
    scenario_n = {r["analysis"]: int(r["n"]) for r in pooled
                  if r["feature_set"] in {"M0", "M0_review", "ME_15", "ME_20", "MW_bus"}}
    scenario_n["price_trim_1_99"] = 12412  # pre-trim eligibility, not OOF evaluated N
    for analysis in fold_frame.analysis.unique():
        if analysis not in scenario_n:
            scenario_n[analysis] = 12412
    fold_frame["train_removed"] = fold_frame.apply(
        lambda row: scenario_n[row.analysis] - int(row.test_n_available) - int(row.train_n), axis=1)
    fold_frame["train_removed_buffer"] = np.where(
        fold_frame.analysis.str.startswith("buffer_"), fold_frame.train_removed, 0)
    fold_frame["train_removed_trim"] = np.where(
        fold_frame.analysis.eq("price_trim_1_99"), fold_frame.train_removed, 0)
    fold_frame.to_csv(OUT / "phase10_fold_performance.csv", index=False)
    folds = fold_frame.to_dict("records")
    base_folds = pd.read_csv(OUT / "phase09_fold_performance.csv")
    base_area = base_folds.loc[(base_folds.cv_scheme == "geographic_11") &
                               (base_folds.model == "OLS") &
                               (base_folds.feature_set == "M0"), ["fold", "n"]]
    sample_change = []
    for analysis in ("apartment_condo", "reviewed_only"):
        part = fold_frame.loc[(fold_frame.analysis == analysis) &
                              (fold_frame.cv_scheme == "geographic_11") &
                              (fold_frame.model == "OLS") &
                              (fold_frame.feature_set == "M0")]
        for _, row in part.iterrows():
            original = int(base_area.loc[base_area.fold == row.fold, "n"].iloc[0])
            sample_change.append({"analysis": analysis, "heldout_area": row.fold,
                                  "primary_n": original, "sensitivity_n": int(row.n),
                                  "excluded_n": original - int(row.n),
                                  "excluded_share": (original - int(row.n)) / original})
    _csv("phase10_sample_change_by_area.csv", sample_change)
    trim = fold_frame.loc[(fold_frame.analysis == "price_trim_1_99") &
                          (fold_frame.cv_scheme == "geographic_11") &
                          (fold_frame.model == "OLS") & (fold_frame.feature_set == "M0")]
    _csv("phase10_price_trim_by_area.csv", trim[["fold", "test_n_available", "n",
        "test_removed", "train_price_p01_dkk", "train_price_p99_dkk"]].rename(
            columns={"fold": "heldout_area", "n": "test_n_after_trim"}).to_dict("records"))
    buffer = fold_frame.loc[fold_frame.analysis.isin(["buffer_500m", "buffer_1000m"]) &
                            (fold_frame.model == "OLS") & (fold_frame.feature_set == "M0")]
    _csv("phase10_buffer_train_loss.csv", buffer[["analysis", "fold", "train_n",
         "test_n_available", "train_removed_buffer"]].rename(columns={
             "fold": "heldout_area", "test_n_available": "test_n"}).to_dict("records"))
    master, paired, stability = _master(pooled, folds)
    association_cases = (
        ("area_fixed_effects", "OLS MW + 11-area fixed effects",
         "Within-area food coefficient changes sign; culture coefficient attenuates sharply"),
        ("spatial_error_8nn", "GM_Error_Het MW",
         "8-NN spatial error association; not a geographic predictive comparison"),
    )
    for analysis, model, note in association_cases:
        if analysis == "spatial_error_8nn" and not (
                OUT / "phase10_spatial_error_coefficients.csv").is_file():
            continue
        master.append({"analysis": analysis, "status": STATUS["planned"],
                       "sample_N": 12412, "model": model,
                       "accessibility_specification": "MW + association sensitivity",
                       "validation_method": "full_sample_association_only",
                       "RMSE": np.nan, "MAE": np.nan, "R2": np.nan,
                       "Delta_RMSE_vs_relevant_baseline": np.nan,
                       "main_accessibility_conclusion": note,
                       "changes_primary_conclusion": "no predictive primary change",
                       "notes": "Do not compare in-sample association fit to out-of-fold prediction"})
        for claim in ("C1_E_vs_W_distinct", "C2_access_adds_information",
                      "C3_W_increment_over_E", "C4_geographic_differs_from_random"):
            if claim == "C2_access_adds_information" and analysis == "area_fixed_effects":
                assessment = "partially consistent"
                explanation = "Within-area cultural association shrinks and food association changes sign; prediction not tested"
            elif claim == "C2_access_adds_information" and analysis == "spatial_error_8nn":
                assessment = "consistent"
                explanation = "Spatial-error coefficient signs for station/food/culture match primary MW; predictive value not tested"
            else:
                assessment, explanation = "not applicable", "Association sensitivity does not independently test this claim"
            stability.append({"analysis": analysis, "claim": claim,
                              "assessment": assessment, "explanation": explanation})
    _csv("robustness_summary.csv", master)
    _csv("phase10_geographic_fold_pairs.csv", paired)
    _csv("conclusion_stability.csv", stability)
    pretty = pd.DataFrame(master)
    pretty = pretty.loc[(pretty.model == "XGBoost") &
                        ((pretty.accessibility_specification.str.startswith("MW")) |
                         (pretty.accessibility_specification.str.startswith("ME_") &
                          ~pretty.accessibility_specification.eq("MEW")) |
                         (pretty.accessibility_specification.isin(["M0", "M0_review", "ME"]))) &
                        (pretty.validation_method.isin(["geographic_11", "block_1500m_5"]))]
    pretty = pretty[["status", "analysis", "sample_N", "accessibility_specification",
                     "validation_method", "RMSE", "Delta_RMSE_vs_relevant_baseline"]].copy()
    for col in ("RMSE", "Delta_RMSE_vs_relevant_baseline"):
        pretty[col] = pretty[col].map(lambda x: f"{x:+.4f}" if col.startswith("Delta") else f"{x:.4f}")
    caption = ("# Phase 10 publication table — XGBoost geographic and block sensitivities\n\n"
               "RMSE and change are in log-price units. Positive change means lower error "
               "than the matched M0 (bus: matched MW) on the **same analysis sample**. "
               "Different sample rows are not directly comparable. "
               "The Phase 9 rows are frozen benchmarks.\n\n")
    (OUT / "robustness_summary.md").write_text(caption + pretty.to_markdown(index=False, disable_numparse=True) + "\n",
                                                encoding="utf-8")
    metadata_path = OUT / "phase10_run_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["package_versions"] = {name: importlib.metadata.version(name) for name in
                                        ("pandas", "numpy", "scikit-learn", "statsmodels",
                                         "xgboost", "scipy", "SQLAlchemy", "spreg", "libpysal")}
        write_json(metadata_path, metadata)
    _figures(master, paired, folds)


def buffer_separation_qa() -> None:
    """Actual nearest retained training point to each official held-out polygon."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            result = pd.read_sql(text(
                "WITH eligible AS ("
                "SELECT a.snapshot_date,a.listing_id,c.heldout_area,l.geom_25832 "
                "FROM analysis.analysis_dataset_v1 a "
                "JOIN analysis.cv_assignments c USING(snapshot_date,listing_id) "
                "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
                "WHERE a.primary_sample_candidate AND a.official_cv_area_id IS NOT NULL "
                "AND a.nearest_station_walking_minutes IS NOT NULL) "
                "SELECT area.area_id AS heldout_area,b.buffer_m,"
                "count(*) AS retained_train_n,"
                "min(ST_Distance(e.geom_25832,area.geom_25832)) AS actual_min_separation_m "
                "FROM spatial.official_cv_areas area "
                "CROSS JOIN (VALUES (500),(1000)) b(buffer_m) "
                "JOIN eligible e ON e.heldout_area<>area.area_id "
                "LEFT JOIN analysis.cv_buffer_exclusions x ON "
                "x.heldout_area=area.area_id AND x.buffer_m=b.buffer_m "
                "AND x.snapshot_date=e.snapshot_date AND x.listing_id=e.listing_id "
                "WHERE x.listing_id IS NULL "
                "GROUP BY area.area_id,b.buffer_m ORDER BY area.area_id,b.buffer_m"
            ), conn)
        if len(result) != 22 or (result.actual_min_separation_m < result.buffer_m).any():
            raise RuntimeError("Saved buffer exclusions failed metric separation QA")
        result["crs_epsg"] = 25832
        result.to_csv(OUT / "phase10_buffer_separation.csv", index=False)
    finally:
        engine.dispose()


def _figures(master: list[dict], paired: list[dict], folds: list[dict]) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    main = pd.DataFrame(master)
    selected = main.loc[(main.model == "XGBoost") &
                        (main.analysis.isin(["phase9", "threshold_15", "threshold_20"])) &
                        (main.accessibility_specification.isin(
                            ["M0", "ME", "MW", "ME_15", "MW_15", "ME_20", "MW_20"]))]
    fig, ax = plt.subplots(figsize=(8.5, 4.4), dpi=180)
    labels = ["M0 baseline", "ME Euclidean", "MW walking"]
    scheme_colours = {"random_5": "#C9D7E6", "geographic_11": "#91BDB3"}
    x = np.arange(3)
    for offset, scheme in ((-.17, "random_5"), (.17, "geographic_11")):
        values = []
        for analysis, feature in (("phase9", "M0"), ("phase9", "ME"), ("phase9", "MW")):
            values.append(float(selected.loc[(selected.analysis == analysis) &
                (selected.validation_method == scheme) &
                (selected.accessibility_specification == feature), "RMSE"].iloc[0]))
        bars = ax.bar(x + offset, values, width=.32,
                      color=scheme_colours[scheme],
                      edgecolor="#34404A", linewidth=.5,
                      label="Random" if scheme == "random_5" else "Geographic")
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, value+.002,
                    f"{value:.3f}", ha="center", fontsize=8)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, .42)
    ax.set_ylabel("Pooled out-of-fold RMSE · log listed price")
    ax.set_title("Frozen primary XGBoost comparison")
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="y", alpha=.2)
    fig.tight_layout()
    fig.savefig(FIG / "phase10_primary_validation_context.png")
    plt.close(fig)

    engine = get_engine()
    try:
        with engine.connect() as conn:
            official_names = dict(conn.execute(text(
                "SELECT area_id,area_name FROM spatial.official_cv_areas ORDER BY area_id"
            )).all())
    finally:
        engine.dispose()
    if len(official_names) != 11:
        raise RuntimeError("Official CV area-name mapping is incomplete")
    fold = pd.DataFrame(paired)
    fold = fold.loc[(fold.analysis == "phase9") & (fold.model == "XGBoost")].sort_values("Delta_MW_vs_M0")
    fold_labels = [official_names[area] + (" (municipality)" if area == "frederiksberg_0147" else "")
                   for area in fold.heldout_area]
    fig, ax = plt.subplots(figsize=(10.2, 5.1), dpi=180)
    ax.barh(np.arange(len(fold)), fold.Delta_MW_vs_M0,
            color=["#99D3BF" if x > 0 else "#EFC8A8" for x in fold.Delta_MW_vs_M0],
            edgecolor="#34404A", linewidth=.5)
    ax.set_yticks(np.arange(len(fold)), fold_labels)
    ax.axvline(0, color="#34404A", lw=.8)
    ax.set_xlabel("Held-out RMSE reduction: MW versus M0 (positive = improvement)")
    ax.set_title("Walking-access benefit varies by official area")
    ax.grid(axis="x", alpha=.2)
    fig.tight_layout()
    fig.savefig(FIG / "phase10_geographic_fold_stability.png")
    plt.close(fig)

    threshold = selected.loc[(selected.model == "XGBoost") &
        (selected.validation_method == "geographic_11") &
        (selected.accessibility_specification.isin(["ME", "MW", "ME_15", "MW_15", "ME_20", "MW_20"]))]
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=180)
    for prefix, colour, label in (("ME", "#D9AF8D", "Euclidean"),
                                  ("MW", "#78B69E", "Walking")):
        values = []
        for minute in (10, 15, 20):
            feature = prefix if minute == 10 else f"{prefix}_{minute}"
            values.append(float(threshold.loc[threshold.accessibility_specification == feature,
                                              "RMSE"].iloc[0]))
        ax.plot([10, 15, 20], values, marker="o", color=colour, label=label)
        for minute, value in zip((10, 15, 20), values):
            offset = -16 if prefix == "MW" and minute == 20 else 8
            ax.annotate(f"{value:.4f}", (minute, value), xytext=(0, offset),
                        textcoords="offset points", ha="center", fontsize=8)
    ax.set_xticks([10, 15, 20])
    ax.set_xlabel("Matched walking minutes / straight-line radius at 80 m/min")
    ax.set_ylabel("Geographic out-of-fold RMSE · log price")
    ax.set_title("Threshold sensitivity (not model selection)")
    ax.set_ylim(.3245, .3305)
    ax.legend(frameon=False)
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(FIG / "phase10_threshold_sensitivity.png")
    plt.close(fig)

    bus = main.loc[(main.analysis == "bus_walking") & (main.model == "XGBoost")]
    if len(bus):
        fig, ax = plt.subplots(figsize=(6.6, 3.8), dpi=180)
        x = np.arange(len(bus))
        ax.bar(x, bus.Delta_RMSE_vs_relevant_baseline,
               color="#99D3BF", edgecolor="#34404A", linewidth=.5)
        for i, value in enumerate(bus.Delta_RMSE_vs_relevant_baseline):
            ax.text(i, value + (.00008 if value >= 0 else -.00008), f"{value:+.5f}",
                    ha="center", va="bottom" if value >= 0 else "top", fontsize=9)
        ax.set_xticks(x, ["Random", "Geographic"])
        ax.axhline(0, color="#34404A", lw=.8)
        ax.set_ylabel("RMSE(MW) − RMSE(MW + bus walk time)")
        ax.set_title("Post-Phase-9 bus-walking sensitivity")
        ax.set_ylim(0, max(bus.Delta_RMSE_vs_relevant_baseline) * 1.3)
        ax.grid(axis="y", alpha=.2)
        fig.tight_layout()
        fig.savefig(FIG / "phase10_bus_increment.png")
        plt.close(fig)


def run() -> dict:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            before = _freeze(conn)
            if before["cv_assignment_rows"] != 23144 or not before["phase9_file_sha256"]:
                raise RuntimeError("Frozen Phase 9 artifacts or CV assignments missing")
            prior_path = OUT / "primary_freeze.json"
            if prior_path.is_file():
                if json.loads(prior_path.read_text()) != before:
                    raise RuntimeError("Phase 9 file/CV hashes differ from Phase 10 baseline")
            else:
                write_json(prior_path, before)
            frame, exclusions = _load(conn)
        scenario_list = (
            ("apartment_condo", frame.loc[frame.property_type.isin(APARTMENT)].copy(),
             ("M0", "MW"), SCHEMES, None, False),
            ("reviewed_only", frame.loc[frame.number_of_reviews > 0].copy(),
             ("M0", "MW"), SCHEMES, None, False),
            ("review_count", frame, ("M0_review", "MW_review"), SCHEMES, None, False),
            ("threshold_15", frame, ("ME_15", "MW_15"), SCHEMES, None, False),
            ("threshold_20", frame, ("ME_20", "MW_20"), SCHEMES, None, False),
            ("price_trim_1_99", frame, ("M0", "MW"), SCHEMES, None, True),
            ("buffer_500m", frame, ("M0", "MW"), ("geographic_11",), 500, False),
            ("buffer_1000m", frame, ("M0", "MW"), ("geographic_11",), 1000, False),
            ("block_1500m", frame, ("M0", "MW"), ("block_1500m_5",), None, False),
            ("bus_walking", frame, ("MW_bus",), SCHEMES, None, False),
        )
        fold_rows, pooled_rows, tuning_rows = [], [], []
        for analysis, part, specs, schemes, buffer_m, trim in scenario_list:
            rows, summary, tuning = _run_scenario(
                part, analysis, specs, schemes, ("OLS", "XGBoost"),
                exclusions=exclusions, buffer_m=buffer_m, trim=trim)
            fold_rows.extend(rows)
            pooled_rows.extend(summary)
            tuning_rows.extend(tuning)
            # Checkpoint after each completed sensitivity, never overwrite Phase 9.
            _csv("phase10_fold_performance.csv", fold_rows)
            _csv("phase10_model_performance.csv", pooled_rows)
            _csv("phase10_xgboost_tuning.csv", tuning_rows)
        coefficients = _ols_associations(frame)
        diagnostics = _bus_diagnostics(frame)
        vif = _bus_vif(frame)
        representation = _representation_diagnostics(frame)
        master, paired, stability = _master(pooled_rows, fold_rows)
        _csv("phase10_ols_associations.csv", coefficients)
        _csv("phase10_bus_diagnostics.csv", diagnostics)
        _csv("phase10_bus_vif.csv", vif)
        _csv("phase10_bus_spotcheck_groups.csv", _bus_spotcheck_groups(frame))
        _csv("phase10_bus_shap.csv", _bus_shap_descriptive(frame))
        _csv("phase10_accessibility_representation.csv", representation)
        _csv("robustness_summary.csv", master)
        _csv("phase10_geographic_fold_pairs.csv", paired)
        _csv("conclusion_stability.csv", stability)
        fold_df = pd.DataFrame(fold_rows)
        geo_summary = []
        for (analysis, model, spec), part in fold_df.loc[
                fold_df.cv_scheme == "geographic_11"].groupby(
                    ["analysis", "model", "feature_set"]):
            geo_summary.append({"analysis": analysis, "model": model,
                                "feature_set": spec, "median_fold_rmse": part.rmse_log.median(),
                                "iqr_fold_rmse": part.rmse_log.quantile(.75) - part.rmse_log.quantile(.25),
                                "min_fold_rmse": part.rmse_log.min(),
                                "max_fold_rmse": part.rmse_log.max(),
                                "min_test_n": part.n.min(), "max_test_n": part.n.max()})
        _csv("phase10_geographic_fold_summary.csv", geo_summary)
        _figures(master, paired, fold_rows)
        with engine.connect() as conn:
            after = _freeze(conn)
        if after != before:
            raise RuntimeError("Phase 9 artifacts or saved CV assignments changed during Phase 10")
        meta = {"version": VERSION, "phase9_frozen_hash_verified": True,
                "primary_n": len(frame), "apartment_condo_n": int(frame.property_type.isin(APARTMENT).sum()),
                "reviewed_n": int((frame.number_of_reviews > 0).sum()),
                "bus_nonmissing_primary_n": int(frame[BUS_COL].notna().sum()),
                "source_currency": "DKK; user-confirmed, source has $ glyph without currency code",
                "crs_epsg": 25832, "walking_speed_kmh": 4.8,
                "scenarios": [x[0] for x in scenario_list],
                "outer_folds": "saved Phase 8 random/geographic/1.5-km assignments",
                "inner_folds": "four training-only municipality-stratified 1-km grouped folds",
                "seeds": {"outer_random": 20260929, "inner": 20260930,
                          "block_1500m": 20261034},
                "price_trim": "1st/99th percentiles of each outer training set; apply same cutoffs to test outcomes; report test removal",
                "xgb_candidates": XGB_CANDIDATES,
                "phase9_freeze_sha256": sha256_file(prior_path)}
        write_json(OUT / "phase10_run_metadata.json", meta)
        return meta
    finally:
        engine.dispose()


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--synthesis-only"]:
        synthesize_only()
    elif sys.argv[1:] == ["--figures-only"]:
        _figures(pd.read_csv(OUT / "robustness_summary.csv").to_dict("records"),
                 pd.read_csv(OUT / "phase10_geographic_fold_pairs.csv").to_dict("records"),
                 pd.read_csv(OUT / "phase10_fold_performance.csv").to_dict("records"))
    elif sys.argv[1:] == ["--diagnostics-only"]:
        engine = get_engine()
        try:
            with engine.connect() as conn:
                frame, _ = _load(conn)
            _csv("phase10_accessibility_representation.csv", _representation_diagnostics(frame))
            _csv("phase10_bus_vif.csv", _bus_vif(frame))
            _csv("phase10_bus_spotcheck_groups.csv", _bus_spotcheck_groups(frame))
            _csv("phase10_bus_shap.csv", _bus_shap_descriptive(frame))
            _csv("phase10_ols_associations.csv", _ols_associations(frame))
        finally:
            engine.dispose()
    elif sys.argv[1:] == ["--buffer-qa"]:
        buffer_separation_qa()
    else:
        print(json.dumps(run(), indent=2))

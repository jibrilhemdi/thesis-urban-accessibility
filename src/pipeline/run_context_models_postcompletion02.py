"""Post-completion context ladder; frozen Phase 9 models and outputs are read-only."""

from __future__ import annotations

import argparse
import csv
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline import run_analysis_phase9 as p9
from src.pipeline.run_analysis_phase10 import _freeze


TABLES = PROJECT_ROOT / "outputs/tables"
FIGURES = PROJECT_ROOT / "outputs/figures"
MANIFEST = TABLES / "phase10/primary_freeze.json"
CONTEXT = ("log_analysis_area_population_density", "analysis_area_income_100k_dkk")
SETS = {f"{base}_CTX": p9.FEATURES[base] + CONTEXT for base in p9.FEATURES}
ACCESS = ("ME", "MW", "MEW")
VERSION = "postcompletion02_v1"
COLORS = {"primary": "#B8C9D6", "context": "#99D3BF", "text": "#34404A", "grid": "#E7EBEE"}


def freeze_check(conn) -> None:
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    current = _freeze(conn)
    if (current["cv_assignments_sha256"] != expected["cv_assignments_sha256"] or
            current["cv_assignment_rows"] != expected["cv_assignment_rows"]):
        raise RuntimeError("Saved Phase 9 CV assignments no longer match the freeze")
    changed = [path for path, digest in expected["phase9_file_sha256"].items()
               if not (PROJECT_ROOT / path).is_file() or sha256_file(PROJECT_ROOT / path) != digest]
    if changed:
        raise RuntimeError(f"Frozen Phase 9 artifacts differ: {changed}")


def load_sample(conn) -> pd.DataFrame:
    fields = (
        "a.snapshot_date,a.listing_id,a.log_price,a.price_nightly,a.property_type,"
        "a.official_municipality_code,a.official_cv_area_id,a.accommodates,a.bedrooms,"
        "a.bathrooms_effective,a.log1p_minimum_nights,a.superhost,"
        "a.log1p_host_listings_count,a.distance_centre_euclidean_km,"
        "a.nearest_station_euclidean_m,a.nearest_station_walking_minutes,"
        "a.food_social_800m,a.cultural_tourist_800m,a.food_social_w_10,"
        "a.cultural_tourist_w_10,a.log_analysis_area_population_density,"
        "a.analysis_area_income_100k_dkk,a.analysis_area_is_municipality_proxy," +
        ",".join("a." + name for name in p9.AMENITIES)
    )
    frame = pd.read_sql(text(
        f"SELECT {fields},c.random_fold,c.heldout_area,c.block_1km_id "
        "FROM analysis.analysis_dataset_context_v1 a "
        "JOIN analysis.cv_assignments c USING(snapshot_date,listing_id) "
        "WHERE a.primary_sample_candidate AND a.official_cv_area_id IS NOT NULL "
        "AND a.nearest_station_walking_minutes IS NOT NULL "
        "ORDER BY a.snapshot_date,a.listing_id"
    ), conn)
    if len(frame) != 12412 or frame[["snapshot_date", "listing_id"]].duplicated().any():
        raise RuntimeError("The context sample is not the 12,412-row frozen Phase 9 sample")
    if frame["log_price"].isna().any() or (frame["price_nightly"] <= 0).any():
        raise RuntimeError("The positive-price outcome rule changed")
    if frame[list(CONTEXT) + ["random_fold", "heldout_area", "block_1km_id"]].isna().any().any():
        raise RuntimeError("Context or saved CV key is missing in the primary sample")
    if frame["random_fold"].nunique() != 5 or frame["heldout_area"].nunique() != 11:
        raise RuntimeError("Saved outer assignments do not cover five random/11 area folds")
    if int(frame["analysis_area_is_municipality_proxy"].sum()) != 1304:
        raise RuntimeError("Frederiksberg proxy membership differs from frozen geography")
    return prepare_features(frame)


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Exactly Phase 9's deterministic E/W transforms; no learned statistic here."""
    result = frame.copy()
    result["nearest_station_euclidean_km"] = pd.to_numeric(
        result["nearest_station_euclidean_m"], errors="raise") / 1000.0
    for source, name in (("food_social_800m", "log1p_food_e800"),
                         ("cultural_tourist_800m", "log1p_culture_e800"),
                         ("food_social_w_10", "log1p_food_w10"),
                         ("cultural_tourist_w_10", "log1p_culture_w10")):
        value = pd.to_numeric(result[source], errors="raise")
        if value.isna().any() or (value < 0).any():
            raise RuntimeError(f"Invalid canonical opportunity count: {source}")
        result[name] = np.log1p(value)
    for name in set(p9.BASE_NUMERIC + p9.E_NUMERIC + p9.W_NUMERIC + CONTEXT):
        result[name] = pd.to_numeric(result[name], errors="raise").astype(float)
    if not np.isfinite(result[list(CONTEXT)].to_numpy(dtype=float)).all():
        raise RuntimeError("Context contains nonfinite values")
    if result[list(p9.CATEGORICAL)].isna().any().any():
        raise RuntimeError("A frozen categorical control is missing")
    return result


def preprocessor(name: str) -> ColumnTransformer:
    columns = SETS[name]
    numeric = [column for column in columns if column not in p9.CATEGORICAL]
    return ColumnTransformer((
        ("numeric", SimpleImputer(strategy="median", add_indicator=True,
                                   keep_empty_features=True), numeric),
        ("category", OneHotEncoder(drop="first", handle_unknown="ignore",
                                    sparse_output=False), list(p9.CATEGORICAL)),
    ), remainder="drop", verbose_feature_names_out=False)


def xgb_pipeline(name: str) -> Pipeline:
    # Same Phase 9 estimator defaults; only the explicit context columns differ.
    from xgboost import XGBRegressor
    return Pipeline((
        ("prep", preprocessor(name)),
        ("xgb", XGBRegressor(
            objective="reg:squarederror", tree_method="hist", learning_rate=.05,
            subsample=.85, colsample_bytree=.85, random_state=p9.SEED,
            n_jobs=2, verbosity=0,
        )),
    ))


def full_sample_ols(frame: pd.DataFrame, sample: str, names: tuple[str, ...]) -> list[dict]:
    y = frame["log_price"].to_numpy(dtype=float)
    rows = []
    for name in names:
        columns = SETS[name]
        prep = preprocessor(name)
        design = np.asarray(prep.fit_transform(frame[list(columns)]), dtype=float)
        feature_names = list(prep.get_feature_names_out())
        fit = sm.OLS(y, sm.add_constant(design, has_constant="add")).fit(cov_type="HC3")
        ci = fit.conf_int(alpha=.05)
        for i, term in enumerate(("Intercept", *feature_names)):
            beta = float(fit.params[i])
            rows.append({
                "sample": sample, "feature_set": name, "term": term, "n": int(fit.nobs),
                "beta_log_price": beta, "robust_se_hc3": float(fit.bse[i]),
                "ci95_low": float(ci[i, 0]), "ci95_high": float(ci[i, 1]),
                "p_value": float(fit.pvalues[i]),
                "approx_percent_change_one_unit": float(100 * np.expm1(beta)),
                "r2_in_sample": float(fit.rsquared),
                "adjusted_r2_in_sample": float(fit.rsquared_adj),
                "aic": float(fit.aic), "bic": float(fit.bic),
                "condition_number": float(fit.condition_number),
                "covariance": "HC3; not spatial-cluster robust",
            })
    return rows


def run_cv(frame: pd.DataFrame, sample: str, schemes: tuple[str, ...],
           names: tuple[str, ...], models: tuple[str, ...]) -> tuple[list[dict], list[dict], list[dict]]:
    frame = frame.reset_index(drop=True)
    y = frame["log_price"].to_numpy(dtype=float)
    fold_rows, pooled, tuning = [], [], []
    candidates = [{"xgb__" + key: [value] for key, value in candidate.items()}
                  for candidate in p9.XGB_CANDIDATES]
    for scheme in schemes:
        oof = {(model, name): np.full(len(frame), np.nan, dtype=float)
               for model in models for name in names}
        for fold, train_idx, test_idx in p9._outer_splits(frame, scheme):
            train, test = frame.iloc[train_idx], frame.iloc[test_idx]
            inner = p9._inner_splits(train) if "XGBoost" in models else None
            print(f"Context {sample} {scheme} {fold}: train={len(train)} test={len(test)}", flush=True)
            for name in names:
                columns = SETS[name]
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Found unknown categories")
                    if "OLS" in models:
                        ols = Pipeline((("prep", preprocessor(name)), ("model", LinearRegression())))
                        ols.fit(train[list(columns)], y[train_idx])
                        pred = ols.predict(test[list(columns)])
                        oof[("OLS", name)][test_idx] = pred
                    if "XGBoost" in models:
                        search = GridSearchCV(
                            xgb_pipeline(name), candidates, cv=inner,
                            scoring="neg_root_mean_squared_error", refit=True,
                            n_jobs=1, error_score="raise", return_train_score=False,
                        )
                        search.fit(train[list(columns)], y[train_idx])
                        pred = search.predict(test[list(columns)])
                        oof[("XGBoost", name)][test_idx] = pred
                        tuning.append({"sample": sample, "cv_scheme": scheme, "fold": fold,
                                       "feature_set": name, "inner_folds": len(inner),
                                       "inner_group": "phase7_1km_block",
                                       "best_inner_rmse_log": -float(search.best_score_),
                                       **{key.removeprefix("xgb__"): value
                                          for key, value in search.best_params_.items()}})
                for model in models:
                    prediction = oof[(model, name)][test_idx]
                    if not np.isfinite(prediction).all():
                        raise RuntimeError(f"Nonfinite test prediction: {sample}/{scheme}/{fold}/{model}/{name}")
                    fold_rows.append({
                        "sample": sample, "cv_scheme": scheme, "fold": fold,
                        "model": model, "feature_set": name, "train_n": len(train),
                        **p9._metrics(y[test_idx], prediction),
                    })
        for (model, name), prediction in oof.items():
            if not np.isfinite(prediction).all():
                raise RuntimeError(f"Incomplete OOF prediction: {sample}/{scheme}/{model}/{name}")
            pooled.append({"sample": sample, "cv_scheme": scheme, "model": model,
                           "feature_set": name, **p9._metrics(y, prediction)})
    return fold_rows, pooled, tuning


def _csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"Empty public table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def comparisons(pooled: list[dict]) -> list[dict]:
    old = pd.read_csv(TABLES / "phase09/model_performance.csv")
    if not (old["n"] == 12412).all():
        raise RuntimeError("Phase 9 performance table has an unexpected sample")
    original = {(r.cv_scheme, r.model, r.feature_set): r
                for r in old.itertuples(index=False)}
    current = {(r["cv_scheme"], r["model"], r["feature_set"]): r for r in pooled}
    rows = []
    for scheme in ("random_5", "geographic_11"):
        for model in ("OLS", "XGBoost"):
            for access in ACCESS:
                base_old = original[(scheme, model, "M0")]
                access_old = original[(scheme, model, access)]
                base_new = current[(scheme, model, "M0_CTX")]
                access_new = current[(scheme, model, f"{access}_CTX")]
                old_gain = base_old.rmse_log - access_old.rmse_log
                new_gain = base_new["rmse_log"] - access_new["rmse_log"]
                rows.append({
                    "sample": "phase9_common_12412", "cv_scheme": scheme, "model": model,
                    "accessibility": access, "n": 12412,
                    "rmse_m0_phase9": base_old.rmse_log, "rmse_access_phase9": access_old.rmse_log,
                    "delta_rmse_phase9": old_gain,
                    "rmse_m0_ctx": base_new["rmse_log"], "rmse_access_ctx": access_new["rmse_log"],
                    "delta_rmse_ctx": new_gain, "change_in_access_gain": new_gain - old_gain,
                    "mae_access_phase9": access_old.mae_log, "mae_access_ctx": access_new["mae_log"],
                    "r2_access_phase9": access_old.r2_log, "r2_access_ctx": access_new["r2_log"],
                })
    return rows


def geographic_pairs(folds: list[dict], conn) -> list[dict]:
    original = pd.read_csv(TABLES / "phase09/fold_performance.csv")
    original = original[(original.cv_scheme == "geographic_11") &
                        (original.model.isin(["OLS", "XGBoost"]))]
    old = {(r.fold, r.model, r.feature_set): r for r in original.itertuples(index=False)}
    new = {(r["fold"], r["model"], r["feature_set"]): r
           for r in folds if r["sample"] == "mixed_11_areas" and r["cv_scheme"] == "geographic_11"}
    area_names = dict(conn.execute(text("SELECT area_id,area_name FROM spatial.official_cv_areas")).all())
    rows = []
    for fold in sorted(area_names):
        for model in ("OLS", "XGBoost"):
            baseline = old[(fold, model, "M0")]
            ctx_base = new[(fold, model, "M0_CTX")]
            if int(baseline.n) != int(ctx_base["n"]):
                raise RuntimeError(f"Unpaired geographic fold: {fold}/{model}")
            row = {"heldout_area": fold,
                   "area": area_names[fold] + (" (municipality)" if fold == "frederiksberg_0147" else ""),
                   "model": model, "n_test": int(baseline.n),
                   "rmse_m0": baseline.rmse_log, "rmse_me": old[(fold, model, "ME")].rmse_log,
                   "rmse_mw": old[(fold, model, "MW")].rmse_log,
                   "rmse_m0_ctx": ctx_base["rmse_log"],
                   "rmse_me_ctx": new[(fold, model, "ME_CTX")]["rmse_log"],
                   "rmse_mw_ctx": new[(fold, model, "MW_CTX")]["rmse_log"]}
            row["delta_me_vs_m0_original"] = row["rmse_m0"] - row["rmse_me"]
            row["delta_mw_vs_m0_original"] = row["rmse_m0"] - row["rmse_mw"]
            row["delta_me_vs_m0_ctx"] = row["rmse_m0_ctx"] - row["rmse_me_ctx"]
            row["delta_mw_vs_m0_ctx"] = row["rmse_m0_ctx"] - row["rmse_mw_ctx"]
            rows.append(row)
    return rows


def copenhagen_summary(pooled: list[dict], ols: list[dict]) -> list[dict]:
    lookup = {(r["feature_set"], r["term"]): r for r in ols if r["sample"] == "copenhagen_10_districts"}
    metrics = {r["feature_set"]: r for r in pooled if r["model"] == "XGBoost"}
    base = metrics["M0_CTX"]["rmse_log"]
    rows = []
    for name in ("M0_CTX", "ME_CTX", "MW_CTX"):
        m = metrics[name]
        d = lookup[(name, CONTEXT[0])]
        i = lookup[(name, CONTEXT[1])]
        rows.append({
            "sample": "Copenhagen-only; 10 official district folds", "feature_set": name,
            "n": m["n"], "geographic_xgb_rmse_log": m["rmse_log"],
            "geographic_xgb_mae_log": m["mae_log"], "geographic_xgb_r2_log": m["r2_log"],
            "xgb_delta_rmse_vs_m0_ctx": base - m["rmse_log"],
            "ols_adjusted_r2_in_sample": d["adjusted_r2_in_sample"],
            "ols_density_beta": d["beta_log_price"], "ols_density_ci95_low": d["ci95_low"],
            "ols_density_ci95_high": d["ci95_high"],
            "ols_income_100k_beta": i["beta_log_price"],
            "ols_income_ci95_low": i["ci95_low"], "ols_income_ci95_high": i["ci95_high"],
        })
    return rows


def figure(comparison: list[dict]) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11.6, 5.1), dpi=180, sharey=True)
    for ax, model in zip(axes, ("OLS", "XGBoost")):
        subset = [r for r in comparison if r["cv_scheme"] == "geographic_11" and r["model"] == model]
        x = np.arange(len(ACCESS))
        old = [next(r["delta_rmse_phase9"] for r in subset if r["accessibility"] == name) for name in ACCESS]
        new = [next(r["delta_rmse_ctx"] for r in subset if r["accessibility"] == name) for name in ACCESS]
        bars_old = ax.bar(x - .18, old, width=.34, color=COLORS["primary"], edgecolor="#788A98",
                          label="Base specification: listing, host/rental and location")
        bars_new = ax.bar(x + .18, new, width=.34, color=COLORS["context"], edgecolor="#5F9E8B",
                          label="Area-context-adjusted core: base + density and income")
        for bar in (*bars_old, *bars_new):
            height = bar.get_height()
            label = f"{height:+.5f}" if 0 < abs(height) < .0001 else f"{height:+.4f}"
            ax.annotate(label, (bar.get_x() + bar.get_width()/2, height),
                        xytext=(0, 4 if height >= 0 else -11), textcoords="offset points",
                        ha="center", va="bottom" if height >= 0 else "top", fontsize=8,
                        color=COLORS["text"], clip_on=False)
        ax.set_xticks(x, ("Straight-line\naccess", "Walking-network\naccess", "Both types\n(exploratory)"))
        ax.set_title("Linear regression (OLS)" if model == "OLS" else "Gradient-boosted trees (XGBoost)",
                     color=COLORS["text"], pad=12)
        ax.set_ylim(-.0032, .0082)  # fixed, shared range with room for value labels
        ax.axhline(0, color=COLORS["text"], linewidth=.8)
        ax.grid(axis="y", color=COLORS["grid"], linewidth=.7)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Reduction in held-out log-price RMSE")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.suptitle("Incremental value of accessibility before and after area socioeconomic context", y=.985,
                 color=COLORS["text"], fontsize=13)
    fig.text(.5, .913,
             "Core RQ2 comparison · Context was planned conceptually and implemented after Phase 9; positive means lower error.",
             ha="center", color=COLORS["text"], fontsize=9)
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False,
               bbox_to_anchor=(.5, .875), fontsize=8.5, columnspacing=2.2)
    fig.text(.5, .045,
             "Same 12,412 listings and 11 held-out areas · Mixed district/municipality context; income and density definitions remain provisional.",
             ha="center", color=COLORS["text"], fontsize=8)
    fig.subplots_adjust(left=.105, right=.985, bottom=.2, top=.72, wspace=.13)
    fig.savefig(FIGURES / "context_incremental_accessibility.png", bbox_inches="tight", pad_inches=.15)
    plt.close(fig)


def run(preflight: bool = False, figures_only: bool = False) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        freeze_check(conn)
        if figures_only:
            comparison = pd.read_csv(TABLES / "context_comparison.csv").to_dict("records")
            figure(comparison)
            return
        frame = load_sample(conn)
        count = conn.scalar(text("SELECT count(*) FROM features.analysis_area_context"))
        if count != 11:
            raise RuntimeError("The prior 11-area context audit is missing")
        print(f"Preflight: {len(frame)} frozen-sample rows, 0 missing context, 11 saved areas; Phase 9 hashes intact", flush=True)
        if preflight:
            return
        area_names = dict(conn.execute(text("SELECT area_id,area_name FROM spatial.official_cv_areas")).all())
    cph = frame.loc[frame["official_municipality_code"] == "0101"].copy().reset_index(drop=True)
    if len(cph) != 11108 or cph["heldout_area"].nunique() != 10 or cph["analysis_area_is_municipality_proxy"].any():
        raise RuntimeError("Copenhagen-only ten-district sensitivity sample changed")

    ols = full_sample_ols(frame, "mixed_11_areas", tuple(SETS))
    ols += full_sample_ols(cph, "copenhagen_10_districts", ("M0_CTX", "ME_CTX", "MW_CTX"))
    mixed_folds, mixed_pooled, mixed_tuning = run_cv(
        frame, "mixed_11_areas", ("random_5", "geographic_11"), tuple(SETS), ("OLS", "XGBoost"))
    city_folds, city_pooled, city_tuning = run_cv(
        cph, "copenhagen_10_districts", ("geographic_11",),
        ("M0_CTX", "ME_CTX", "MW_CTX"), ("OLS", "XGBoost"))
    comparison = comparisons(mixed_pooled)
    with engine.connect() as conn:
        freeze_check(conn)
        pairs = geographic_pairs(mixed_folds, conn)
    if {r["heldout_area"] for r in pairs} != set(area_names):
        raise RuntimeError("Geographic pair table omits an official area")
    _csv(TABLES / "context_augmented_ols.csv", ols)
    _csv(TABLES / "context_augmented_performance.csv", mixed_pooled)
    _csv(TABLES / "context_augmented_fold_performance.csv", mixed_folds + city_folds)
    _csv(TABLES / "context_augmented_geographic_pairs.csv", pairs)
    _csv(TABLES / "context_comparison.csv", comparison)
    _csv(TABLES / "copenhagen_only_context_sensitivity.csv", copenhagen_summary(city_pooled, ols))
    _csv(TABLES / "context_augmented_tuning.csv", mixed_tuning + city_tuning)
    figure(comparison)
    metadata = {
        "version": VERSION, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_view": "analysis.analysis_dataset_context_v1",
        "sample_n_mixed": len(frame), "sample_n_copenhagen": len(cph),
        "outcome": "ln(positive listed DKK/night); never imputed",
        "context_fields": list(CONTEXT), "feature_sets": {k: list(v) for k, v in SETS.items()},
        "outer_assignments": "analysis.cv_assignments; random_5 and geographic_11",
        "phase9_freeze_sha256": sha256_file(MANIFEST),
        "random_seed": p9.SEED, "inner_seed": p9.INNER_SEED,
        "xgboost_candidates": list(p9.XGB_CANDIDATES),
        "imputation": "training-fold median plus indicator, including inner training folds",
        "categorical": "training-fold one-hot, drop first, unknown ignored",
        "income_limitation": "City KKIND3 and national INDKP106 denominator equivalence unverified",
        "area_limitation": "gross EPSG:25832 polygon area; City boundary vintage/water unverified",
        "model_status": "post-completion context robustness; not Phase 9 primary",
    }
    (TABLES / "context_augmented_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with engine.connect() as conn:
        freeze_check(conn)
    print("Context models complete; frozen Phase 9 artifacts and CV assignment unchanged", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", help="Verify inputs/freeze without fitting")
    parser.add_argument("--figures-only", action="store_true", help="Redraw figure from generated aggregate comparison table")
    args = parser.parse_args()
    if args.preflight and args.figures_only:
        parser.error("Choose only one mode")
    run(preflight=args.preflight, figures_only=args.figures_only)

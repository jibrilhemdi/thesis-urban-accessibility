"""Post-completion scrape-batch outcome-observability robustness.

The 90% rule is applied to the pre-price population before any model fit. The
Phase 9 artifacts, base view, raw files and saved CV assignments are read-only.
"""

from __future__ import annotations

import argparse
import csv
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline import run_analysis_phase9 as p9
from src.pipeline.run_analysis_phase10 import _freeze


OUT = PROJECT_ROOT / "outputs/tables"
MANIFEST = OUT / "phase10/primary_freeze.json"
THRESHOLD = 0.90  # fixed before seeing any robustness model results
FEATURE_SETS = ("M0", "ME", "MW")
SCHEMES = ("random_5", "geographic_11")
MODELS = ("OLS", "XGBoost")
VERSION = "postcompletion03_v1"


def check_freeze(conn) -> None:
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))
    current = _freeze(conn)
    if (current["cv_assignments_sha256"] != expected["cv_assignments_sha256"] or
            current["cv_assignment_rows"] != expected["cv_assignment_rows"]):
        raise RuntimeError("Frozen CV assignments changed")
    changed = [path for path, digest in expected["phase9_file_sha256"].items()
               if not (PROJECT_ROOT / path).is_file() or sha256_file(PROJECT_ROOT / path) != digest]
    if changed:
        raise RuntimeError(f"Frozen Phase 9 artifacts changed: {changed}")


def audit_batches(conn) -> tuple[list[dict], set]:
    """Use the full pre-price population, not the priced Phase 9 model sample."""
    rows = conn.execute(text("""
        SELECT last_scraped::date AS scrape_date,
               count(*) AS n_total,
               count(*) FILTER (WHERE observed_positive_price IS TRUE) AS n_valid_price
        FROM analysis.analysis_dataset_v1
        WHERE in_study_area AND entire_home_apt AND conventional_residential AND valid_coordinates
        GROUP BY last_scraped::date ORDER BY last_scraped::date NULLS LAST
    """)).mappings().all()
    if not rows:
        raise RuntimeError("No pre-price-eligibility listings available")
    unique_ids = conn.scalar(text("""
        SELECT count(DISTINCT listing_id) FROM analysis.analysis_dataset_v1
        WHERE in_study_area AND entire_home_apt AND conventional_residential AND valid_coordinates
    """))
    result, selected = [], set()
    for row in rows:
        total, valid = int(row["n_total"]), int(row["n_valid_price"])
        if not 0 <= valid <= total:
            raise RuntimeError("Invalid price-observability count")
        rate = valid / total
        date = row["scrape_date"]
        high = date is not None and rate >= THRESHOLD
        if high:
            selected.add(date)
        result.append({
            "scrape_date": date.isoformat() if date is not None else "unknown",
            "n_total": total, "n_valid_price": valid,
            "n_missing_price": total - valid,
            "valid_price_rate": rate, "missing_price_rate": 1 - rate,
            "high_completeness_threshold": THRESHOLD,
            "high_completeness_batch": high,
        })
    if sum(r["n_total"] for r in result) != unique_ids:
        raise RuntimeError("Listing IDs repeat across current scrape-date batches; investigate before selection")
    if not selected:
        raise RuntimeError("No high-completeness scrape batch meets the predeclared 90% rule")
    return result, selected


def load_robustness_sample(conn, selected_dates: set) -> tuple[pd.DataFrame, pd.DataFrame]:
    # The Phase 9 loader guarantees exact original sample rules and saved keys.
    full = p9._load(conn)
    dates = pd.read_sql(text("""
        SELECT snapshot_date, listing_id, last_scraped::date AS last_scraped
        FROM analysis.analysis_dataset_v1
        WHERE primary_sample_candidate AND official_cv_area_id IS NOT NULL
          AND nearest_station_walking_minutes IS NOT NULL
    """), conn)
    if len(dates) != len(full) or dates[["snapshot_date", "listing_id"]].duplicated().any():
        raise RuntimeError("Scrape-date join does not cover the Phase 9 common sample exactly")
    full = full.merge(dates, on=["snapshot_date", "listing_id"], how="left",
                      validate="one_to_one", sort=False)
    if len(full) != 12412 or full["last_scraped"].isna().any():
        raise RuntimeError("Phase 9 keys or scrape dates were lost")
    keep = pd.to_datetime(full["last_scraped"]).dt.date.isin(selected_dates)
    robust = full.loc[keep].copy().reset_index(drop=True)
    if robust.empty or robust["random_fold"].nunique() != 5 or robust["heldout_area"].nunique() != 11:
        raise RuntimeError("The high-completeness filter left unusable saved outer assignments")
    if robust["log_price"].isna().any() or (robust["price_nightly"] <= 0).any():
        raise RuntimeError("Missing or nonpositive outcome entered the robustness sample")
    # Phase 9 deterministic transforms; learned imputation still belongs inside folds.
    return p9.prepare_features(full), p9.prepare_features(robust)


def sample_profile(full: pd.DataFrame, robust: pd.DataFrame, area_names: dict) -> list[dict]:
    rows = []
    for sample, frame in (("phase9_common", full), ("high_completeness", robust)):
        for dimension in ("overall", "official_cv_area_id", "property_type", "last_scraped"):
            if dimension == "overall":
                parts = [("All eligible priced listings", frame)]
            else:
                parts = list(frame.groupby(dimension, dropna=False, sort=True))
            for label, part in parts:
                if dimension == "official_cv_area_id":
                    label = area_names[label] + (" (municipality)" if label == "frederiksberg_0147" else "")
                if dimension == "last_scraped":
                    label = str(label)
                prices = part["price_nightly"].to_numpy(dtype=float)
                if len(part) < 5:
                    raise RuntimeError("A public composition cell is smaller than five listings")
                rows.append({
                    "sample": sample, "dimension": dimension, "category": label,
                    "n": len(part), "share_of_sample": round(len(part) / len(frame), 6),
                    "price_mean_dkk": round(float(np.mean(prices)), 2),
                    "price_p25_dkk": round(float(np.quantile(prices, .25)), 2),
                    "price_median_dkk": round(float(np.median(prices)), 2),
                    "price_p75_dkk": round(float(np.quantile(prices, .75)), 2),
                    "price_min_dkk": round(float(np.min(prices)), 2),
                    "price_max_dkk": round(float(np.max(prices)), 2),
                })
    return rows


def fold_counts(full: pd.DataFrame, robust: pd.DataFrame, area_names: dict) -> list[dict]:
    rows = []
    for scheme, key in (("random_5", "random_fold"), ("geographic_11", "heldout_area")):
        old, new = full.groupby(key).size(), robust.groupby(key).size()
        if set(old.index) != set(new.index):
            raise RuntimeError("Filtering removed a saved outer fold")
        for fold in sorted(old.index):
            n_new = int(new[fold])
            if n_new < 200:  # Phase 9's pre-existing stability rule
                raise RuntimeError(f"Saved {scheme} fold {fold} has only {n_new} test listings")
            rows.append({
                "validation": scheme, "saved_fold": fold,
                "area_name": area_names[fold] + (" (municipality)" if fold == "frederiksberg_0147" else "")
                    if scheme == "geographic_11" else "",
                "n_phase9": int(old[fold]), "n_high_completeness": n_new,
                "retained_fraction": n_new / int(old[fold]),
            })
    return rows


def run_cv(frame: pd.DataFrame) -> tuple[list[dict], list[dict], list[dict]]:
    y = frame["log_price"].to_numpy(dtype=float)
    fold_rows, pooled, tuning = [], [], []
    candidates = [{"xgb__" + key: [value] for key, value in candidate.items()}
                  for candidate in p9.XGB_CANDIDATES]
    for scheme in SCHEMES:
        oof = {(model, feature): np.full(len(frame), np.nan)
               for model in MODELS for feature in FEATURE_SETS}
        for fold, train_idx, test_idx in p9._outer_splits(frame, scheme):
            train, test = frame.iloc[train_idx], frame.iloc[test_idx]
            inner = p9._inner_splits(train)
            print(f"Observability {scheme} {fold}: train={len(train)} test={len(test)}", flush=True)
            for feature in FEATURE_SETS:
                columns = p9.FEATURES[feature]
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Found unknown categories")
                    ols = Pipeline((("prep", p9.build_preprocessor(feature)),
                                    ("model", LinearRegression())))
                    ols.fit(train[list(columns)], y[train_idx])
                    oof[("OLS", feature)][test_idx] = ols.predict(test[list(columns)])
                    search = GridSearchCV(
                        p9._xgb_pipeline(feature), candidates, cv=inner,
                        scoring="neg_root_mean_squared_error", refit=True,
                        n_jobs=1, error_score="raise", return_train_score=False,
                    )
                    search.fit(train[list(columns)], y[train_idx])
                    oof[("XGBoost", feature)][test_idx] = search.predict(test[list(columns)])
                for model in MODELS:
                    prediction = oof[(model, feature)][test_idx]
                    if not np.isfinite(prediction).all():
                        raise RuntimeError(f"Nonfinite {scheme}/{fold}/{model}/{feature} prediction")
                    fold_rows.append({
                        "validation": scheme, "saved_fold": fold, "model": model,
                        "feature_set": feature, "train_n": len(train),
                        **p9._metrics(y[test_idx], prediction),
                    })
                tuning.append({
                    "validation": scheme, "saved_fold": fold, "feature_set": feature,
                    "inner_folds": len(inner), "inner_group": "phase7_1km_block",
                    "best_inner_rmse_log": -float(search.best_score_),
                    **{key.removeprefix("xgb__"): value for key, value in search.best_params_.items()},
                })
        for (model, feature), prediction in oof.items():
            if not np.isfinite(prediction).all():
                raise RuntimeError(f"Incomplete OOF predictions for {scheme}/{model}/{feature}")
            pooled.append({
                "validation": scheme, "model": model, "feature_set": feature,
                **p9._metrics(y, prediction),
            })
    return fold_rows, pooled, tuning


def comparison(pooled: list[dict]) -> list[dict]:
    old = pd.read_csv(OUT / "phase09/model_performance.csv")
    if not (old["n"] == 12412).all():
        raise RuntimeError("Frozen Phase 9 metric sample changed")
    original = {(r.cv_scheme, r.model, r.feature_set): r
                for r in old.itertuples(index=False)}
    current = {(r["validation"], r["model"], r["feature_set"]): r for r in pooled}
    rows = []
    for scheme in SCHEMES:
        for model in MODELS:
            for feature in FEATURE_SETS:
                base_old = original[(scheme, model, "M0")]
                access_old = original[(scheme, model, feature)]
                base_new = current[(scheme, model, "M0")]
                access_new = current[(scheme, model, feature)]
                rows.append({
                    "model": model, "feature_set": feature, "validation": scheme,
                    "n_phase9": 12412, "n_high_completeness": access_new["n"],
                    "rmse_phase9": access_old.rmse_log,
                    "rmse_high_completeness": access_new["rmse_log"],
                    "mae_phase9": access_old.mae_log,
                    "mae_high_completeness": access_new["mae_log"],
                    "r2_phase9": access_old.r2_log,
                    "r2_high_completeness": access_new["r2_log"],
                    "delta_access_phase9": base_old.rmse_log - access_old.rmse_log,
                    "delta_access_high_completeness": base_new["rmse_log"] - access_new["rmse_log"],
                    "comparison_note": "Different eligible samples; compare within-sample accessibility increments, not raw RMSE as paired errors",
                })
    return rows


def geographic_pairs(folds: list[dict], area_names: dict) -> list[dict]:
    original = pd.read_csv(OUT / "phase09/fold_performance.csv")
    original = original[(original.cv_scheme == "geographic_11") &
                        (original.model.isin(MODELS)) & original.feature_set.isin(FEATURE_SETS)]
    old = {(r.fold, r.model, r.feature_set): r for r in original.itertuples(index=False)}
    new = {(r["saved_fold"], r["model"], r["feature_set"]): r
           for r in folds if r["validation"] == "geographic_11"}
    rows = []
    for fold in sorted(area_names):
        for model in MODELS:
            b_old, b_new = old[(fold, model, "M0")], new[(fold, model, "M0")]
            row = {
                "saved_fold": fold,
                "area": area_names[fold] + (" (municipality)" if fold == "frederiksberg_0147" else ""),
                "model": model, "n_phase9": int(b_old.n), "n_high_completeness": int(b_new["n"]),
            }
            for feature in FEATURE_SETS:
                row[f"rmse_{feature.lower()}_phase9"] = old[(fold, model, feature)].rmse_log
                row[f"rmse_{feature.lower()}_high_completeness"] = new[(fold, model, feature)]["rmse_log"]
            for feature in ("ME", "MW"):
                row[f"delta_{feature.lower()}_phase9"] = row["rmse_m0_phase9"] - row[f"rmse_{feature.lower()}_phase9"]
                row[f"delta_{feature.lower()}_high_completeness"] = (
                    row["rmse_m0_high_completeness"] - row[f"rmse_{feature.lower()}_high_completeness"])
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(audit_only: bool = False) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        check_freeze(conn)
        audit, high_dates = audit_batches(conn)
        full, robust = load_robustness_sample(conn, high_dates)
        area_names = dict(conn.execute(text("SELECT area_id,area_name FROM spatial.official_cv_areas")).all())
        profile = sample_profile(full, robust, area_names)
        folds = fold_counts(full, robust, area_names)
    write_csv(OUT / "price_observability_by_scrape.csv", audit)
    write_csv(OUT / "price_observability_sample_profile.csv", profile)
    write_csv(OUT / "price_observability_fold_counts.csv", folds)
    print(f"90% rule retains {sorted(d.isoformat() for d in high_dates)}; "
          f"model sample {len(robust)}/{len(full)} ({len(robust)/len(full):.2%}); "
          f"smallest geographic test fold {min(r['n_high_completeness'] for r in folds if r['validation']=='geographic_11')}",
          flush=True)
    if audit_only:
        return
    fold_rows, pooled, tuning = run_cv(robust)
    compared = comparison(pooled)
    paired = geographic_pairs(fold_rows, area_names)
    with engine.connect() as conn:
        check_freeze(conn)
    write_csv(OUT / "price_observability_performance.csv", pooled)
    write_csv(OUT / "price_observability_fold_performance.csv", fold_rows)
    write_csv(OUT / "price_observability_tuning.csv", tuning)
    write_csv(OUT / "price_observability_comparison.csv", compared)
    write_csv(OUT / "price_observability_geographic_pairs.csv", paired)
    metadata = {
        "version": VERSION, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "pre_price_population": "analysis.analysis_dataset_v1: in_study_area AND entire_home_apt AND conventional_residential AND valid_coordinates",
        "valid_price_rule": "observed_positive_price IS TRUE; no outcome imputation",
        "high_completeness_threshold": THRESHOLD,
        "retained_scrape_dates": sorted(d.isoformat() for d in high_dates),
        "source_date_field": "last_scraped", "source_price_unit": "DKK, user-confirmed; ln for model outcome",
        "phase9_sample_n": len(full), "high_completeness_sample_n": len(robust),
        "sample_rule": "Phase 9 common sample AND last_scraped in retained high-completeness dates",
        "feature_sets": {name: list(p9.FEATURES[name]) for name in FEATURE_SETS},
        "outer_folds": "filtered analysis.cv_assignments random_5/geographic_11; never reassigned",
        "random_seed": p9.SEED, "inner_seed": p9.INNER_SEED,
        "xgboost_candidates": list(p9.XGB_CANDIDATES),
        "preprocessing": "Phase 9 training-fold median+missing indicator and one-hot; no test fit",
        "phase9_freeze_sha256": sha256_file(MANIFEST),
        "status": "post-completion outcome-observability robustness; not primary",
    }
    (OUT / "price_observability_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with engine.connect() as conn:
        check_freeze(conn)
    print("Outcome-observability robustness complete; Phase 9 files and CV assignments unchanged", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-only", action="store_true", help="Apply 90% rule and export sample QA without modelling")
    args = parser.parse_args()
    run(audit_only=args.audit_only)

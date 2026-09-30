"""Endpoint-only municipal-union sensitivity; never rewrites Phase 9 outputs."""

from __future__ import annotations

import argparse
import csv
import json
import warnings
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone

import networkx as nx
import numpy as np
import pandas as pd
import shapely
from psycopg2.extras import execute_values
from scipy.spatial import cKDTree
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline import run_analysis_phase9 as p9
from src.pipeline.run_context_models_postcompletion02 import freeze_check
from src.spatial.walking_network import FILTER_VERSION, METRES_PER_MINUTE, build_graph
from src.spatial.walking_routing import station_distance_labels


VERSION = "destination_boundary_v1"
OUT = PROJECT_ROOT / "outputs/tables"
MEASURES = (
    ("food_e800", "food_social_800m", "food_social_800m_clip"),
    ("food_w10", "food_social_w_10", "food_social_w_10_clip"),
    ("culture_e800", "cultural_tourist_800m", "cultural_tourist_800m_clip"),
    ("culture_w10", "cultural_tourist_w_10", "cultural_tourist_w_10_clip"),
    ("station_euclidean_m", "nearest_station_euclidean_m", "nearest_station_euclidean_m_clip"),
    ("station_walking_min", "nearest_station_walking_minutes", "nearest_station_walking_minutes_clip"),
)


def _csv(name: str, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {name}")
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _boundary_and_destination_counts(conn) -> list[dict]:
    boundary = conn.execute(text(
        "SELECT ST_IsValid(geom_25832),ST_SRID(geom_25832),ST_Area(geom_25832) "
        "FROM spatial.study_union_boundary_sensitivity"
    )).one()
    if not boundary[0] or boundary[1] != 25832 or boundary[2] <= 0:
        raise RuntimeError("Official municipal union is invalid or has the wrong CRS")
    if conn.scalar(text("SELECT count(*) FROM spatial.official_municipalities "
                        "WHERE municipality_code IN ('0101','0147')")) != 2:
        raise RuntimeError("Both official municipalities are required")
    rows = []
    for category, base, clipped, condition in (
        ("food_social", "spatial.osm_pois", "spatial.osm_pois_study_union_sensitivity",
         "category='food_social'"),
        ("cultural_tourist", "spatial.osm_pois", "spatial.osm_pois_study_union_sensitivity",
         "category='cultural_tourist'"),
        ("station", "spatial.transit_stations", "spatial.transit_stations_study_union_sensitivity",
         "station_mode IN ('metro','urban_rail','rail')"),
    ):
        total = int(conn.scalar(text(f"SELECT count(*) FROM {base} WHERE {condition}")))
        retained = int(conn.scalar(text(f"SELECT count(*) FROM {clipped} WHERE {condition}")))
        if retained <= 0 or retained > total:
            raise RuntimeError(f"Invalid clipped {category} destination count")
        rows.append({"category": category, "primary_buffered_n": total,
                     "retained_inside_or_on_union_n": retained, "removed_outside_n": total-retained,
                     "predicate": "ST_Covers(official municipal union, canonical endpoint)",
                     "crs_epsg": 25832})
    return rows


def _sample_keys(conn) -> pd.DataFrame:
    # No outcome/price column enters feature construction or the pre-fit audit.
    frame = pd.read_sql(text(
        "SELECT a.snapshot_date,a.listing_id,a.official_cv_area_id "
        "FROM analysis.analysis_dataset_v1 a "
        "JOIN analysis.cv_assignments c USING(snapshot_date,listing_id) "
        "WHERE a.primary_sample_candidate AND a.official_cv_area_id IS NOT NULL "
        "AND a.nearest_station_walking_minutes IS NOT NULL "
        "ORDER BY a.snapshot_date,a.listing_id"
    ), conn)
    if len(frame) != 12412 or frame[["snapshot_date", "listing_id"]].duplicated().any():
        raise RuntimeError("Frozen Phase 9 sample keys changed")
    return frame


def _euclidean(conn) -> pd.DataFrame:
    # Fetch authoritative clipped PostGIS points once; repeated lateral joins
    # otherwise repeatedly evaluate the union view for each listing.
    listing = pd.read_sql(text(
        "SELECT a.snapshot_date,a.listing_id,ST_X(l.geom_25832) x,ST_Y(l.geom_25832) y "
        "FROM analysis.analysis_dataset_v1 a JOIN clean.airbnb_listings l "
        "USING(snapshot_date,listing_id) WHERE a.primary_sample_candidate "
        "AND a.official_cv_area_id IS NOT NULL AND a.nearest_station_walking_minutes IS NOT NULL "
        "ORDER BY a.snapshot_date,a.listing_id"
    ), conn)
    pois = pd.read_sql(text(
        "SELECT category,ST_X(geom_25832) x,ST_Y(geom_25832) y "
        "FROM spatial.osm_pois_study_union_sensitivity ORDER BY destination_key"
    ), conn)
    stations = pd.read_sql(text(
        "SELECT ST_X(geom_25832) x,ST_Y(geom_25832) y "
        "FROM spatial.transit_stations_study_union_sensitivity ORDER BY station_key"
    ), conn)
    if len(listing) != 12412 or pois.empty or stations.empty:
        raise RuntimeError("Clipped Euclidean inputs are incomplete")
    points = listing[["x", "y"]].to_numpy(float)
    listing["nearest_station_euclidean_m_clip"] = cKDTree(
        stations[["x", "y"]].to_numpy(float)).query(points)[0]
    for category, column in (("food_social", "food_social_800m_clip"),
                              ("cultural_tourist", "cultural_tourist_800m_clip")):
        destinations = pois.loc[pois.category == category, ["x", "y"]].to_numpy(float)
        listing[column] = cKDTree(destinations).query_ball_point(points, r=800.0,
                                                                  return_length=True)
    return listing.drop(columns=["x", "y"])


def _walking(conn, keys: pd.DataFrame) -> tuple[pd.DataFrame, str, dict]:
    network = conn.execute(text(
        "SELECT n.network_id,n.filter_version,n.node_count,n.source_segment_count,n.directed_arc_count,"
        "f.relative_path,f.file_hash_sha256 "
        "FROM spatial.walking_networks n JOIN meta.source_files f ON f.source_file_id=n.source_file_id"
    )).one()
    if network.filter_version != FILTER_VERSION:
        raise RuntimeError("Saved graph filter version changed")
    pbf = PROJECT_ROOT / network.relative_path
    if not pbf.is_file() or sha256_file(pbf) != network.file_hash_sha256:
        raise RuntimeError("Immutable pedestrian PBF is absent or hash-mismatched")
    graph, _, _, _, _, stats = build_graph(pbf)
    if (stats["nodes"], stats["source_segments"], stats["directed_arcs"]) != (
            network.node_count, network.source_segment_count, network.directed_arc_count):
        raise RuntimeError("Rebuilt graph differs from persisted Phase 6 graph")
    listing = pd.read_sql(text(
        "SELECT s.snapshot_date,s.listing_id,s.snapped_node_id,s.snap_distance_m "
        "FROM features.walking_listing_snaps s "
        "JOIN analysis.analysis_dataset_v1 a USING(snapshot_date,listing_id) "
        "WHERE s.network_id=:network AND a.primary_sample_candidate "
        "AND a.official_cv_area_id IS NOT NULL AND a.nearest_station_walking_minutes IS NOT NULL "
        "ORDER BY s.snapshot_date,s.listing_id"
    ), conn, params={"network": network.network_id})
    if len(listing) != len(keys) or not listing[["snapshot_date", "listing_id"]].equals(keys[["snapshot_date", "listing_id"]]):
        raise RuntimeError("Persisted listing snaps do not match frozen keys")
    pois = pd.read_sql(text(
        "SELECT d.destination_key,d.category,s.snapped_node_id,s.snap_distance_m "
        "FROM spatial.osm_pois_study_union_sensitivity d "
        "JOIN spatial.walking_destination_snaps s ON s.destination_kind='poi' "
        "AND s.destination_key=d.destination_key AND s.network_id=:network "
        "ORDER BY d.destination_key"
    ), conn, params={"network": network.network_id})
    stations = pd.read_sql(text(
        "SELECT d.station_key AS destination_key,s.snapped_node_id,s.snap_distance_m "
        "FROM spatial.transit_stations_study_union_sensitivity d "
        "JOIN spatial.walking_destination_snaps s ON s.destination_kind='station' "
        "AND s.destination_key=d.station_key AND s.network_id=:network "
        "ORDER BY d.station_key"
    ), conn, params={"network": network.network_id})
    if len(pois) != conn.scalar(text("SELECT count(*) FROM spatial.osm_pois_study_union_sensitivity")) or \
            len(stations) != conn.scalar(text("SELECT count(*) FROM spatial.transit_stations_study_union_sensitivity")):
        raise RuntimeError("Clipped canonical destinations lack Phase 6 snaps")
    station_dist, _ = station_distance_labels(graph, stations.to_dict("records"))
    destinations = defaultdict(list)
    for row in pois.itertuples(index=False):
        destinations[int(row.snapped_node_id)].append((row.category, float(row.snap_distance_m)))
    origins = defaultdict(list)
    for row in listing.itertuples(index=False):
        origins[int(row.snapped_node_id)].append(row)
    result = []
    explored = 0
    for origin, group in origins.items():
        cutoff = max(0.0, 800.0 - min(float(item.snap_distance_m) for item in group))
        reached = nx.single_source_dijkstra_path_length(graph, origin, cutoff=cutoff, weight="length_m")
        explored += len(reached)
        arrivals = {"food_social": [], "cultural_tourist": []}
        for node, route_m in reached.items():
            for category, connector_m in destinations.get(node, ()):
                arrivals[category].append(route_m + connector_m)
        for values in arrivals.values():
            values.sort()
        for item in group:
            connector = float(item.snap_distance_m)
            metres = station_dist.get(origin)
            result.append({
                "snapshot_date": item.snapshot_date, "listing_id": int(item.listing_id),
                "nearest_station_walking_minutes_clip": (
                    (connector + metres) / METRES_PER_MINUTE if metres is not None else None),
                "food_social_w_10_clip": bisect_right(arrivals["food_social"], 800.0-connector),
                "cultural_tourist_w_10_clip": bisect_right(arrivals["cultural_tourist"], 800.0-connector),
            })
    return pd.DataFrame(result), network.network_id, {"unique_origin_nodes": len(origins),
                                                       "dijkstra_nodes_explored": explored,
                                                       "network_id": network.network_id,
                                                       "pbf_sha256": network.file_hash_sha256}


def _persist(conn, features: pd.DataFrame, network_id: str) -> None:
    existing = int(conn.scalar(text("SELECT count(*) FROM features.destination_boundary_sensitivity")))
    if existing:
        if existing != len(features):
            raise RuntimeError("Existing endpoint sensitivity table is partial; refusing overwrite")
        prior = pd.read_sql(text(
            "SELECT snapshot_date,listing_id,network_id,nearest_station_euclidean_m_clip,"
            "nearest_station_walking_minutes_clip,food_social_800m_clip,cultural_tourist_800m_clip,"
            "food_social_w_10_clip,cultural_tourist_w_10_clip "
            "FROM features.destination_boundary_sensitivity ORDER BY snapshot_date,listing_id"
        ), conn)
        check = features.sort_values(["snapshot_date", "listing_id"]).reset_index(drop=True).copy()
        check["network_id"] = network_id
        prior = prior[check.columns]
        if not prior.reset_index(drop=True).equals(check[prior.columns]):
            raise RuntimeError("Persisted endpoint features differ; refusing overwrite")
        return
    ordered = features.sort_values(["snapshot_date", "listing_id"])
    columns = ["snapshot_date", "listing_id", "nearest_station_euclidean_m_clip",
               "nearest_station_walking_minutes_clip", "food_social_800m_clip",
               "cultural_tourist_800m_clip", "food_social_w_10_clip", "cultural_tourist_w_10_clip"]
    rows = []
    for row in ordered[columns].itertuples(index=False, name=None):
        rows.append((row[0], int(row[1]), network_id,
                     None if pd.isna(row[2]) else float(row[2]),
                     None if pd.isna(row[3]) else float(row[3]),
                     *(int(value) for value in row[4:])))
    cursor = conn.connection.driver_connection.cursor()
    try:
        execute_values(cursor,
            "INSERT INTO features.destination_boundary_sensitivity "
            "(snapshot_date,listing_id,network_id,nearest_station_euclidean_m_clip,"
            "nearest_station_walking_minutes_clip,food_social_800m_clip,cultural_tourist_800m_clip,"
            "food_social_w_10_clip,cultural_tourist_w_10_clip) VALUES %s", rows, page_size=1000)
    finally:
        cursor.close()


def _feature_changes(conn, features: pd.DataFrame) -> list[dict]:
    primary = pd.read_sql(text(
        "SELECT snapshot_date,listing_id,official_cv_area_id,nearest_station_euclidean_m,"
        "nearest_station_walking_minutes,food_social_800m,cultural_tourist_800m,"
        "food_social_w_10,cultural_tourist_w_10 "
        "FROM analysis.analysis_dataset_v1 WHERE primary_sample_candidate "
        "AND official_cv_area_id IS NOT NULL AND nearest_station_walking_minutes IS NOT NULL "
        "ORDER BY snapshot_date,listing_id"
    ), conn)
    joined = primary.merge(features, on=["snapshot_date", "listing_id"], validate="one_to_one")
    if len(joined) != 12412:
        raise RuntimeError("Feature audit lost a frozen sample row")
    rows = []
    for name, old, new in MEASURES:
        delta = pd.to_numeric(joined[old], errors="raise") - pd.to_numeric(joined[new], errors="coerce")
        changed = delta.notna() & ~np.isclose(delta.fillna(0), 0, atol=1e-7, rtol=0)
        if not name.startswith("station") and (delta.dropna() < -1e-6).any():
            raise RuntimeError(f"Clipping unexpectedly increases {name} opportunity count")
        if name.startswith("station") and (delta.dropna() > 1e-6).any():
            raise RuntimeError(f"Clipping unexpectedly reduces {name} nearest-station distance")
        rows.append({"measure": name, "n_primary": 12412, "n_clipped_observed": int(delta.notna().sum()),
                     "n_clipped_missing": int(delta.isna().sum()), "n_changed": int(changed.sum()),
                     "pct_changed": float(100*changed.mean()),
                     "primary_minus_clipped_mean": float(delta.mean()),
                     "primary_minus_clipped_median": float(delta.median()),
                     "primary_minus_clipped_p95": float(delta.quantile(.95)),
                     "primary_minus_clipped_min": float(delta.min()),
                     "primary_minus_clipped_max": float(delta.max()),
                     "units": "metres" if name == "station_euclidean_m" else
                              "minutes" if name == "station_walking_min" else "canonical POIs"})
    return rows


def _edge_concentration(conn) -> list[dict]:
    # No outcome or listing-level coordinates are exported. The band is based
    # only on distance to the *outer* municipal-union boundary, EPSG:25832.
    boundary_wkb = conn.scalar(text(
        "SELECT ST_AsBinary(ST_Boundary(geom_25832)) "
        "FROM spatial.study_union_boundary_sensitivity"
    ))
    boundary = shapely.from_wkb(bytes(boundary_wkb))
    data = pd.read_sql(text(
        "SELECT ST_X(l.geom_25832) x,ST_Y(l.geom_25832) y,"
        "f.food_social_800m_clip,f.cultural_tourist_800m_clip,"
        "f.food_social_w_10_clip,f.cultural_tourist_w_10_clip,"
        "f.nearest_station_euclidean_m_clip,f.nearest_station_walking_minutes_clip,"
        "e.food_social_800m,e.cultural_tourist_800m,e.nearest_station_distance_m,"
        "w.food_social_w_10,w.cultural_tourist_w_10,w.nearest_station_walking_minutes "
        "FROM features.destination_boundary_sensitivity f "
        "JOIN clean.airbnb_listings l USING(snapshot_date,listing_id) "
        "JOIN features.euclidean_accessibility e USING(snapshot_date,listing_id) "
        "JOIN features.walking_accessibility w USING(snapshot_date,listing_id)"
    ), conn)
    distances = shapely.distance(shapely.points(data.x.to_numpy(float), data.y.to_numpy(float)), boundary)
    changed = np.zeros(len(data), dtype=bool)
    for old, new in (("food_social_800m", "food_social_800m_clip"),
                     ("cultural_tourist_800m", "cultural_tourist_800m_clip"),
                     ("food_social_w_10", "food_social_w_10_clip"),
                     ("cultural_tourist_w_10", "cultural_tourist_w_10_clip")):
        changed |= data[old].to_numpy() != data[new].to_numpy()
    for old, new in (("nearest_station_distance_m", "nearest_station_euclidean_m_clip"),
                     ("nearest_station_walking_minutes", "nearest_station_walking_minutes_clip")):
        changed |= ~np.isclose(data[old].to_numpy(float), data[new].to_numpy(float),
                               atol=1e-7, rtol=0)
    result = []
    for label, selected in (("0-800 m", distances <= 800),
                            ("800-1600 m", (distances > 800) & (distances <= 1600)),
                            (">1600 m", distances > 1600)):
        n = int(selected.sum())
        changed_n = int((selected & changed).sum())
        result.append({"outer_boundary_distance_band": label,
                       "n_listings": n, "n_any_access_changed": changed_n,
                       "pct_any_access_changed": float(100*changed_n/n) if n else None,
                       "crs_epsg": 25832})
    if sum(row["n_listings"] for row in result) != 12412:
        raise RuntimeError("Outer-boundary distance bands do not cover the model sample")
    return result


def _model_frame(conn) -> tuple[pd.DataFrame, pd.DataFrame]:
    original = p9.prepare_features(p9._load(conn))
    clip = pd.read_sql(text(
        "SELECT snapshot_date,listing_id,nearest_station_euclidean_m_clip,"
        "nearest_station_walking_minutes_clip,food_social_800m_clip,cultural_tourist_800m_clip,"
        "food_social_w_10_clip,cultural_tourist_w_10_clip "
        "FROM features.destination_boundary_sensitivity ORDER BY snapshot_date,listing_id"
    ), conn)
    frame = original.merge(clip, on=["snapshot_date", "listing_id"], validate="one_to_one")
    if len(frame) != 12412:
        raise RuntimeError("Sensitivity join changed primary sample")
    eligible = frame[frame["nearest_station_euclidean_m_clip"].notna() &
                     frame["nearest_station_walking_minutes_clip"].notna()].copy().reset_index(drop=True)
    if eligible.empty or eligible["heldout_area"].nunique() != 11 or eligible["random_fold"].nunique() != 5:
        raise RuntimeError("Clipped station coverage makes frozen folds unusable")
    for source, target in (
        ("nearest_station_euclidean_m_clip", "nearest_station_euclidean_km"),
        ("nearest_station_walking_minutes_clip", "nearest_station_walking_minutes"),
    ):
        eligible[target] = pd.to_numeric(eligible[source], errors="raise") / (1000 if "euclidean" in source else 1)
    for source, target in (
        ("food_social_800m_clip", "log1p_food_e800"),
        ("cultural_tourist_800m_clip", "log1p_culture_e800"),
        ("food_social_w_10_clip", "log1p_food_w10"),
        ("cultural_tourist_w_10_clip", "log1p_culture_w10"),
    ):
        eligible[target] = np.log1p(pd.to_numeric(eligible[source], errors="raise"))
    if eligible[list(p9.E_NUMERIC + p9.W_NUMERIC)].isna().any().any():
        raise RuntimeError("Clipped model predictors contain missing values")
    return original, eligible


def _fit(frame: pd.DataFrame) -> tuple[list[dict], list[dict], list[dict]]:
    y = frame["log_price"].to_numpy(float)
    candidates = [{"xgb__" + k: [v] for k, v in item.items()} for item in p9.XGB_CANDIDATES]
    folds, pooled, tuning = [], [], []
    for scheme in ("random_5", "geographic_11"):
        oof = {(model, name): np.full(len(frame), np.nan)
               for model in ("OLS", "XGBoost") for name in ("M0", "ME", "MW")}
        for fold, train_idx, test_idx in p9._outer_splits(frame, scheme):
            train, test = frame.iloc[train_idx], frame.iloc[test_idx]
            inner = p9._inner_splits(train)
            print(f"Boundary {scheme} {fold}: train={len(train)} test={len(test)}", flush=True)
            for name in ("M0", "ME", "MW"):
                columns = p9.FEATURES[name]
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Found unknown categories")
                    ols = Pipeline((("prep", p9.build_preprocessor(name)), ("model", LinearRegression())))
                    ols.fit(train[list(columns)], y[train_idx])
                    oof[("OLS", name)][test_idx] = ols.predict(test[list(columns)])
                    search = GridSearchCV(p9._xgb_pipeline(name), candidates, cv=inner,
                                          scoring="neg_root_mean_squared_error", refit=True,
                                          n_jobs=1, error_score="raise", return_train_score=False)
                    search.fit(train[list(columns)], y[train_idx])
                    oof[("XGBoost", name)][test_idx] = search.predict(test[list(columns)])
                tuning.append({"cv_scheme": scheme, "fold": fold, "feature_set": name,
                               "best_inner_rmse_log": -float(search.best_score_),
                               **{k.removeprefix("xgb__"): v for k, v in search.best_params_.items()}})
                for model in ("OLS", "XGBoost"):
                    pred = oof[(model, name)][test_idx]
                    if not np.isfinite(pred).all():
                        raise RuntimeError("Nonfinite held-out prediction")
                    folds.append({"cv_scheme": scheme, "fold": fold, "model": model,
                                  "feature_set": name, "train_n": len(train),
                                  **p9._metrics(y[test_idx], pred)})
        for (model, name), pred in oof.items():
            if not np.isfinite(pred).all():
                raise RuntimeError("Incomplete out-of-fold predictions")
            pooled.append({"cv_scheme": scheme, "model": model,
                           "feature_set": name, **p9._metrics(y, pred)})
    return folds, pooled, tuning


def _comparisons(pooled: list[dict], folds: list[dict], sample_n: int, conn) -> tuple[list[dict], list[dict]]:
    old_pooled = pd.read_csv(OUT / "phase09/model_performance.csv")
    old_folds = pd.read_csv(OUT / "phase09/fold_performance.csv")
    old = {(r.cv_scheme, r.model, r.feature_set): r for r in old_pooled.itertuples(index=False)}
    new = {(r["cv_scheme"], r["model"], r["feature_set"]): r for r in pooled}
    comparable = sample_n == 12412
    rows = []
    for scheme in ("random_5", "geographic_11"):
        for model in ("OLS", "XGBoost"):
            base_old = old[(scheme, model, "M0")]
            base_new = new[(scheme, model, "M0")]
            for metric, field in (("RMSE", "rmse_log"), ("MAE", "mae_log"), ("R2", "r2_log")):
                direction = -1.0 if metric == "R2" else 1.0
                row = {"estimator": model, "validation": scheme, "metric": metric,
                       "sample_N": sample_n, "same_sample_as_phase9": comparable,
                       "delta_definition": "access minus M0 (higher is better)" if metric == "R2"
                                           else "M0 minus access (higher is better)"}
                for name in ("M0", "ME", "MW"):
                    row[f"primary_buffered_{name}"] = float(getattr(old[(scheme, model, name)], field)) if comparable else None
                    row[f"boundary_sensitivity_{name}"] = float(new[(scheme, model, name)][field])
                for name in ("ME", "MW"):
                    row[f"primary_Delta_{name}"] = (float(direction * (getattr(base_old, field) -
                        getattr(old[(scheme, model, name)], field))) if comparable else None)
                    row[f"boundary_Delta_{name}"] = float(direction * (
                        base_new[field] - new[(scheme, model, name)][field]))
                row["boundary_MW_minus_ME"] = float(new[(scheme, model, "MW")][field] -
                                                     new[(scheme, model, "ME")][field])
                rows.append(row)
    name_rows = conn.execute(text("SELECT area_id,area_name FROM spatial.official_cv_areas")).all()
    area_names = dict(name_rows)
    clipped = {(r["fold"], r["feature_set"]): r for r in folds
               if r["cv_scheme"] == "geographic_11" and r["model"] == "XGBoost"}
    original = {(r.fold, r.feature_set): r for r in old_folds.itertuples(index=False)
                if r.cv_scheme == "geographic_11" and r.model == "XGBoost"}
    area_rows = []
    for fold in sorted(area_names):
        m0, me, mw = (clipped[(fold, name)] for name in ("M0", "ME", "MW"))
        om0, ome, omw = (original[(fold, name)] for name in ("M0", "ME", "MW"))
        row = {"area": area_names[fold] + (" (municipality)" if fold == "frederiksberg_0147" else ""),
               "heldout_area": fold, "N": m0["n"], "same_fold_sample_as_phase9": comparable,
               "primary_M0_RMSE": float(om0.rmse_log) if comparable else None,
               "primary_ME_RMSE": float(ome.rmse_log) if comparable else None,
               "primary_MW_RMSE": float(omw.rmse_log) if comparable else None,
               "clipped_M0_RMSE": m0["rmse_log"], "clipped_ME_RMSE": me["rmse_log"],
               "clipped_MW_RMSE": mw["rmse_log"],
               "Delta_ME_change": (float((m0["rmse_log"] - me["rmse_log"]) -
                    (om0.rmse_log - ome.rmse_log)) if comparable else None),
               "Delta_MW_change": (float((m0["rmse_log"] - mw["rmse_log"]) -
                    (om0.rmse_log - omw.rmse_log)) if comparable else None)}
        if comparable and m0["n"] != int(om0.n):
            raise RuntimeError("Geographic test-fold membership differs from Phase 9")
        area_rows.append(row)
    return rows, area_rows


def run(audit_only: bool = False) -> dict:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            freeze_check(conn)
        migrate(engine)  # Versioned sensitivity-only views/table; no original table modification.
        with engine.connect() as conn:
            counts = _boundary_and_destination_counts(conn)
            keys = _sample_keys(conn)
            euclidean = _euclidean(conn)
            walking, network_id, route_meta = _walking(conn, keys)
            features = euclidean.merge(walking, on=["snapshot_date", "listing_id"], validate="one_to_one")
            if len(features) != len(keys):
                raise RuntimeError("Clipped features do not cover frozen keys")
            changes = _feature_changes(conn, features)
        # Feature QA and outputs happen before any model fitting.
        _csv("boundary_sensitivity_destination_counts.csv", counts)
        _csv("boundary_sensitivity_feature_changes.csv", changes)
        with engine.begin() as conn:
            _persist(conn, features, network_id)
        with engine.connect() as conn:
            edge = _edge_concentration(conn)
            original, frame = _model_frame(conn)
            if audit_only:
                _csv("boundary_sensitivity_edge_concentration.csv", edge)
                freeze_check(conn)
                return {"phase": VERSION, "destination_counts": counts,
                        "feature_changes": changes, "matched_model_n": len(frame),
                        "routing": route_meta, "models_fitted": False}
            folds, pooled, tuning = _fit(frame)
            comparison, area_rows = _comparisons(pooled, folds, len(frame), conn)
            freeze_check(conn)
        _csv("boundary_sensitivity_performance.csv", pooled)
        _csv("boundary_sensitivity_fold_performance.csv", folds)
        _csv("boundary_sensitivity_comparison.csv", comparison)
        _csv("boundary_sensitivity_geographic_pairs.csv", area_rows)
        _csv("boundary_sensitivity_tuning.csv", tuning)
        _csv("boundary_sensitivity_edge_concentration.csv", edge)
        metadata = {"version": VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "primary_n": len(original), "matched_model_n": len(frame),
                    "sample_removed_n": len(original)-len(frame), "network": route_meta,
                    "endpoint_rule": "ST_Covers official municipality union, EPSG:25832",
                    "network_clipped": False, "district_restriction": False,
                    "walking_speed_kmh": 4.8, "threshold_m": 800,
                    "outer_folds": "saved analysis.cv_assignments random_5 and geographic_11",
                    "inner_folds": "four grouped 1-km blocks on outer training only",
                    "seeds": {"outer": p9.SEED, "inner": p9.INNER_SEED},
                    "xgb_candidates": list(p9.XGB_CANDIDATES)}
        (OUT / "boundary_sensitivity_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return {"phase": VERSION, "destination_counts": counts,
                "feature_changes": changes, "matched_model_n": len(frame),
                "routing": route_meta, "models_fitted": True}
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-only", action="store_true", help="Build/QA endpoint features without fitting models")
    args = parser.parse_args()
    print(json.dumps(run(audit_only=args.audit_only), indent=2, default=str))

"""Assemble thesis-ready, aggregate-only tables/figures from frozen project results.

Post-completion presentation work only. Phase 9 artifacts, CV assignments and
the database are read-only; source results are never recalculated or edited.
"""

from __future__ import annotations

import json
import math
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Patch, Rectangle
from matplotlib.colors import Normalize
import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sqlalchemy import text
from src.pipeline.export_rq2_context_panel import main as export_rq2_context_panel

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline import run_analysis_phase9 as p9
from src.pipeline.run_analysis_phase10 import _freeze
from src.pipeline.run_official_geography_phase4 import _rings


ROOT = PROJECT_ROOT
TABLES = ROOT / "outputs/tables/final"
FIGURES = ROOT / "outputs/figures/final"
PHASE9 = ROOT / "outputs/tables/phase09"
INK = "#25455A"
PALE = "#E8F0EF"
BLUE = "#779DB9"
TEAL = "#5F9F95"
CORAL = "#DCA88E"
CRS = 25832


def freeze(conn):
    expected = json.loads((ROOT / "outputs/tables/phase10/primary_freeze.json").read_text())
    actual = _freeze(conn)
    if actual["cv_assignments_sha256"] != expected["cv_assignments_sha256"]:
        raise RuntimeError("Frozen CV assignments changed")
    changed = [name for name, digest in expected["phase9_file_sha256"].items()
               if not (ROOT / name).is_file() or sha256_file(ROOT / name) != digest]
    if changed:
        raise RuntimeError(f"Frozen Phase 9 artifacts changed: {changed}")


def table(name, rows, note):
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError(f"Empty publication table {name}")
    TABLES.mkdir(parents=True, exist_ok=True)
    frame.to_csv(TABLES / f"{name}.csv", index=False, encoding="utf-8")
    def cell(value):
        if pd.isna(value):
            return "—"
        return str(value).replace("|", "\\|").replace("\n", " ")
    names = list(frame.columns)
    lines = [f"# {name.replace('_', ' ').title()}", "", note, "",
             "| " + " | ".join(names) + " |",
             "| " + " | ".join("---" for _ in names) + " |"]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell(v) for v in row) + " |")
    (TABLES / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return frame


def make_tables(conn, sample):
    source = pd.read_csv(ROOT / "outputs/tables/phase02/sample_construction.csv")
    summary = pd.read_csv(ROOT / "outputs/tables/phase07/sample_summary.csv").iloc[0]
    labels = {
        "raw_listings": "Raw Inside Airbnb listings",
        "in_study_area": "Inside Airbnb Copenhagen/Frederiksberg extract",
        "entire_home_apt": "Entire home/apt",
        "conventional_residential": "Conventional residential property",
        "valid_positive_price": "Observed positive listed price (DKK)",
        "valid_coordinates": "Valid coordinates",
    }
    steps = [(labels[r.stage], int(r.remaining_n)) for r in source.itertuples()]
    steps += [("Assigned official validation area", int(summary.primary_with_official_cv_area)),
              ("Reachable walking station; Phase 9 common sample", int(summary.primary_common_accessibility_cv))]
    previous = None
    rows = []
    for label, n in steps:
        rows.append({"Filter step": label, "N remaining": n,
                     "N removed": 0 if previous is None else previous - n,
                     "% retained from previous": 100 if previous is None else round(100*n/previous, 2)})
        previous = n
    if previous != len(sample) or rows[4]["N removed"] != 8559:
        raise RuntimeError("Sample-construction publication table contradicts frozen source")
    table("table1_sample_construction", rows,
          f"Sequential Phase 2/7 filters, unchanged. The {rows[4]['N removed']:,} price losses are missing/invalid outcomes among otherwise eligible residential entire homes; no price was imputed. Final N is the fixed Phase 9 common comparison sample. Percentage uses the preceding row as denominator.")

    specs = [
        ("Outcome", "price_nightly / log_price", "Positive listed nightly price / its natural log", "DKK; ln(DKK)", "Inside Airbnb listing", "Outcome", "Primary", "Missing/nonpositive excluded; never imputed"),
        ("Dwelling", "property_type", "Six conventional entire-home types", "Categorical", "Inside Airbnb listing", "M0", "Primary", "Observed"),
        ("Capacity", "accommodates", "Maximum guest capacity", "Persons", "Inside Airbnb listing", "M0", "Primary", "Observed"),
        ("Dwelling", "bedrooms", "Reported bedroom count", "Count", "Inside Airbnb listing", "M0", "Primary", "Train-fold median + missing flag; see Table 3 observed N"),
        ("Dwelling", "bathrooms_effective", "Structured bathrooms, source-text fallback", "Count", "Inside Airbnb listing", "M0", "Primary", "Source-supported fallback; no statistical fill"),
        ("Amenities", "8 selected amenity flags", "Wifi, dishwasher, washer, dryer, workspace, free parking, private balcony, self check-in", "Eight binary flags", "Inside Airbnb amenities", "M0", "Primary", "Exact-token parsing; observed"),
        ("Rental rule", "minimum_nights", "Minimum stay", "ln(1+nights)", "Inside Airbnb listing", "M0", "Primary", "Observed"),
        ("Rental rule", "instant_bookable", "Instant booking availability", "Binary", "Inside Airbnb listing", "Not fitted", "Excluded", "Entirely missing in snapshot; not imputed"),
        ("Host", "host_listings_count", "Host portfolio listing count", "ln(1+count)", "Inside Airbnb listing", "M0", "Primary", "Observed"),
        ("Host", "superhost", "Host superhost status", "Binary", "Inside Airbnb listing", "M0", "Primary", "Observed"),
        ("Geography", "official_municipality_code", "Copenhagen vs Frederiksberg", "Categorical", "Official municipalities", "M0", "Primary", "Observed"),
        ("Centrality", "distance_centre_euclidean_km", "City Hall Square straight-line distance", "km; EPSG:25832", "Official reference point + PostGIS", "M0", "Primary", "Observed"),
        ("Area context", "log_population_density", "Gross-polygon population density; mixed district/municipality units", "ln(persons/km²); EPSG:25832", "City StatBank / Statistics Denmark", "CTX", "Area-context-adjusted core; post-Phase-9 implementation", "Area value; provisional boundary/water denominator"),
        ("Area context", "income_100k_dkk", "Mean disposable income; cross-source definitions differ", "100,000 DKK/person", "City StatBank / Statistics Denmark", "CTX", "Area-context-adjusted core; post-Phase-9 implementation", "Area value; not harmonised across municipalities"),
        ("Rail/metro", "nearest_station_euclidean_m", "Stored straight-line distance to closest canonical station", "m; EPSG:25832", "OpenStreetMap", "Source feature", "Primary source", "Converted to km for modelling"),
        ("Rail/metro", "nearest_station_euclidean_km", "Model variable: stored station metres divided by 1,000", "km; EPSG:25832", "OpenStreetMap", "ME/MEW", "Primary", "Common sample complete"),
        ("Rail/metro", "nearest_station_walking_minutes", "Closest reachable canonical station", "Minutes; 4.8 km/h", "OSM walking network", "MW/MEW", "Primary", "Unreachable excluded from common comparison"),
        ("Food/social", "food_social_800m", "Canonical POIs within straight-line radius", "ln(1+count); 800 m", "OpenStreetMap", "ME/MEW", "Primary", "Observed"),
        ("Food/social", "food_social_w_10", "Same POIs reachable walking", "ln(1+count); 10 min", "OSM walking network", "MW/MEW", "Primary", "Observed"),
        ("Cultural/tourist", "cultural_tourist_800m", "Canonical POIs within straight-line radius", "ln(1+count); 800 m", "OpenStreetMap", "ME/MEW", "Primary", "Observed"),
        ("Cultural/tourist", "cultural_tourist_w_10", "Same POIs reachable walking", "ln(1+count); 10 min", "OSM walking network", "MW/MEW", "Primary", "Observed"),
        ("Bus", "bus_stop_proximity / bus_walk_time", "Nearest mapped bus stop, not service accessibility", "m / walking minutes", "OpenStreetMap", "Bus sensitivity", "Robustness", "Not part of frozen M0/ME/MW"),
    ]
    table("table2_variable_specification", [dict(zip(("Concept", "Variable", "Definition", "Transformation/unit", "Source", "Model block", "Primary/robustness", "Missing-data treatment"), row)) for row in specs],
          "M0, ME, MW and MEW are the frozen Phase 9 base specification. CTX is the area-context-adjusted core specification: conceptually planned, but implemented after Phase 9 because context comparability was unresolved at the Phase 7 freeze. Its mixed-resolution fields are not fully harmonised neighbourhood measures. DKK is user-confirmed; the source price string itself lacks an explicit currency code.")

    context = pd.read_sql(text("SELECT analysis_area_code,log_population_density,income_100k_dkk FROM features.analysis_area_context"), conn)
    if len(context) != 11:
        raise RuntimeError("Expected eleven context analysis units")
    enriched = sample.merge(context, left_on="official_cv_area_id", right_on="analysis_area_code", validate="many_to_one")
    if len(enriched) != 12412:
        raise RuntimeError("Context join changed sample N")
    enriched["minimum_nights"] = np.expm1(enriched["log1p_minimum_nights"])
    enriched["host_listings_count"] = np.expm1(enriched["log1p_host_listings_count"])
    continuous = [
        ("Listed nightly price", "price_nightly", "DKK"), ("Log listed price", "log_price", "ln(DKK)"),
        ("Accommodates", "accommodates", "persons"), ("Bedrooms", "bedrooms", "rooms"),
        ("Bathrooms", "bathrooms_effective", "rooms"), ("Minimum nights", "minimum_nights", "nights"),
        ("Host portfolio", "host_listings_count", "listings"),
        ("City Hall distance", "distance_centre_euclidean_km", "km"),
        ("Station straight-line distance", "nearest_station_euclidean_m", "m"),
        ("Station walking time", "nearest_station_walking_minutes", "min"),
        ("Food/social straight-line", "food_social_800m", "POIs / 800 m"),
        ("Food/social walking", "food_social_w_10", "POIs / 10 min"),
        ("Cultural/tourist straight-line", "cultural_tourist_800m", "POIs / 800 m"),
        ("Cultural/tourist walking", "cultural_tourist_w_10", "POIs / 10 min"),
        ("Area log density†", "log_population_density", "ln(persons/km²)"),
        ("Area income†", "income_100k_dkk", "100,000 DKK/person"),
    ]
    stat_rows = []
    for label, field, unit in continuous:
        values = pd.to_numeric(enriched[field], errors="coerce").dropna()
        stat_rows.append({"Variable": label, "Unit": unit, "N": len(values),
                          "Mean": round(values.mean(), 3), "SD": round(values.std(ddof=1), 3),
                          "Median": round(values.median(), 3), "p25": round(values.quantile(.25), 3),
                          "p75": round(values.quantile(.75), 3), "Min": round(values.min(), 3),
                          "Max": round(values.max(), 3), "Percentage": ""})
    categories = [("Property: " + str(k), int(v)) for k, v in enriched.property_type.value_counts().items()]
    categories += [("Frederiksberg municipality", int((enriched.official_municipality_code == "0147").sum())),
                   ("Superhost", int(enriched.superhost.astype(bool).sum()))]
    categories += [(label.replace("amenity_", "Amenity: ").replace("_", " "), int(enriched[label].astype(bool).sum()))
                   for label in p9.AMENITIES]
    for label, n in categories:
        stat_rows.append({"Variable": label, "Unit": "share of common sample", "N": n,
                          "Mean": "", "SD": "", "Median": "", "p25": "", "p75": "",
                          "Min": "", "Max": "", "Percentage": round(100*n/len(enriched), 2)})
    table("table3_descriptive_statistics", stat_rows,
          f"Frozen Phase 9 common N={len(sample):,}. Continuous rows report observed N and sample SD; categorical rows report count and percentage of the full common sample. †Area socioeconomic context enters the later area-context-adjusted core specification, not frozen Phase 9 M0. These are listing-weighted descriptions from {len(context)} area values, not {len(sample):,} independent neighbourhood observations. Frederiksberg is a municipality proxy and income definitions differ by source.")

    definitions = [
        ("Rail/metro/S-train station", "Projected straight-line distance to closest eligible station", "Shortest directed pedestrian route plus endpoint snaps to closest reachable station", "km (ME); minutes (MW)", "Continuous station distance/time; no radius choice", "Same canonical OSM station set; bus excluded"),
        ("Food/social POIs", "Count within 800 m straight-line radius", "Same POIs within 10-minute network route", "ln(1+count); 800 m ↔ 10 min", "1,200/1,600 m ↔ 15/20 min", "Same deduplicated OSM restaurant/cafe/bar/pub set"),
        ("Cultural/tourist POIs", "Count within 800 m straight-line radius", "Same POIs within 10-minute network route", "ln(1+count); 800 m ↔ 10 min", "1,200/1,600 m ↔ 15/20 min", "Same deduplicated OSM cultural/tourist set"),
        ("Bus-stop proximity — robustness only", "Distance to nearest OSM bus stop", "Walking time to nearest canonical bus stop", "m / min; secondary only", "No service frequency or route connectivity", "Separate OSM bus-stop set, not primary rail set"),
    ]
    table("table4_accessibility_definitions", [dict(zip(("Concept", "Euclidean definition", "Network definition", "Primary threshold/unit", "Sensitivity", "Destination source"), row)) for row in definitions],
          "Same deduplicated destination set is used for each primary Euclidean/network pair. Walking speed is fixed at 4.8 km/h (80 m/min); 10 minutes corresponds to 800 m of network travel, not an 800 m circle. All metric spatial operations use EPSG:25832. The primary listing population is bounded by Copenhagen and Frederiksberg, but the primary accessibility opportunity set is buffered and may include nearby destinations outside this administrative union. District boundaries do not constrain accessibility. A study-union endpoint sensitivity is reported separately.")

    ladder = pd.read_csv(PHASE9 / "ols_ladder.csv").set_index("feature_set")
    coeff = pd.read_csv(PHASE9 / "ols_coefficients.csv")
    focal = ["nearest_station_euclidean_km", "log1p_food_e800", "log1p_culture_e800",
             "nearest_station_walking_minutes", "log1p_food_w10", "log1p_culture_w10"]
    wide = []
    for term in focal:
        row = {"Focal term (unit)": term}
        for model in ("M0", "ME", "MW", "MEW"):
            part = coeff[(coeff.feature_set == model) & (coeff.term == term)]
            row[model] = "—" if part.empty else (f"{part.beta_log_price.iloc[0]:+.4f} "
                f"({part.robust_se_hc3.iloc[0]:.4f}); "
                f"[{part.ci95_low.iloc[0]:+.4f}, {part.ci95_high.iloc[0]:+.4f}]")
        wide.append(row)
    for label, values in [
        ("Property controls", ["Yes"]*4), ("Host/rental controls", ["Yes"]*4),
        ("Municipality/centrality", ["Yes"]*4), ("Area context", ["No"]*4),
        ("N", [str(int(ladder.loc[m, "n"])) for m in ("M0", "ME", "MW", "MEW")]),
        ("Adjusted R²", [f"{ladder.loc[m, 'adjusted_r2_in_sample']:.3f}" for m in ("M0", "ME", "MW", "MEW")]),
        ("AIC", [f"{ladder.loc[m, 'aic']:.1f}" for m in ("M0", "ME", "MW", "MEW")]),
        ("BIC", [f"{ladder.loc[m, 'bic']:.1f}" for m in ("M0", "ME", "MW", "MEW")]),
    ]:
        wide.append(dict(zip(("Focal term (unit)", "M0", "ME", "MW", "MEW"), (label, *values))))
    table("table5_hedonic_ladder", wide,
          "Frozen Phase 9 base-specification semilog OLS associations. Focal cells give coefficient (HC3 robust SE); [95% CI]. Opportunity variables are ln(1+count), station Euclidean distance is km, and walking station access is minutes. Other controls are present but omitted here; full frozen coefficients are in outputs/tables/phase09/ols_coefficients.csv. HC3 intervals address heteroskedasticity rather than residual spatial dependence. The later area-context-adjusted core specification is compared separately for RQ2; spatial-error analysis is robustness only. MEW is collinearity-sensitive. AIC/BIC and adjusted R² are in-sample, not cross-validated. No causal interpretation.")
    table("table5_full_coefficients_appendix", coeff.to_dict("records"),
          "Unaltered Phase 9 OLS coefficient export. This is an appendix-only full coefficient table; the compact focal ladder is Table 5.")

    perf = pd.read_csv(PHASE9 / "model_performance.csv")
    perf_rows = [{"Validation": "Random 5-fold" if r.cv_scheme == "random_5" else "Leave-one-area-out",
                  "Estimator": "Training mean" if r.model == "train_mean" else r.model,
                  "Block": "—" if r.feature_set == "none" else r.feature_set,
                  "N": int(r.n), "RMSE (ln price)": round(r.rmse_log, 4),
                  "MAE (ln price)": round(r.mae_log, 4), "R² (OOF)": round(r.r2_log, 3)}
                 for r in perf.itertuples()]
    table("table6_predictive_performance", perf_rows,
          f"Frozen Phase 9 pooled outer out-of-fold metrics; lower RMSE/MAE is better. Random=5 spatially interspersed folds; geographic=11 held-out official areas. Same {int(perf.n.iloc[0]):,} observations in every primary comparison. MEW remains exploratory.")

    indexed = perf.set_index(["cv_scheme", "model", "feature_set"])
    inc_rows = []
    for scheme in ("random_5", "geographic_11"):
        for model in ("OLS", "XGBoost"):
            base = indexed.loc[(scheme, model, "M0")]
            e = indexed.loc[(scheme, model, "ME")]
            for block, ref in (("ME", base), ("MW", base), ("MEW", base),
                               ("MW versus ME", e), ("MEW versus ME", e)):
                candidate = indexed.loc[(scheme, model, block.split()[0])]
                inc_rows.append({"Validation": "Random 5-fold" if scheme == "random_5" else "Leave-one-area-out",
                                 "Estimator": model, "Comparison": block if "versus" in block else block + " versus M0",
                                 "ΔRMSE reduction": round(ref.rmse_log-candidate.rmse_log, 5),
                                 "ΔMAE reduction": round(ref.mae_log-candidate.mae_log, 5),
                                 "Reference RMSE": round(ref.rmse_log, 4), "New RMSE": round(candidate.rmse_log, 4)})
    table("table7_incremental_accessibility", [r for r in inc_rows if r["Comparison"].endswith("versus M0")],
          "Frozen Phase 9 pooled outer out-of-fold changes. Δ is reference error minus new-model error; positive means improvement. Comparisons use identical listings/folds. MEW is exploratory; small E/W differences should not be over-ranked.")
    table("table7_incremental_accessibility_appendix", [r for r in inc_rows if r["Comparison"].endswith("versus ME")],
          "Supplementary frozen Phase 9 pairwise comparisons on identical observations/folds. Δ is reference error minus new-model error; positive means improvement. These comparisons do not replace the main-text M0 reference.")

    robust = pd.read_csv(ROOT / "outputs/tables/phase10/robustness_summary.csv")
    summary = []
    for name in ("apartment_condo", "reviewed_only", "review_count", "threshold_15", "threshold_20",
                 "price_trim_1_99", "buffer_500m", "buffer_1000m", "block_1500m", "bus_walking"):
        part = robust[(robust.analysis == name) & (robust.model == "XGBoost") &
                      (robust.cv_scheme if "cv_scheme" in robust.columns else robust.validation_method).astype(str).str.contains("geographic|block_1500")]
        if part.empty:
            raise RuntimeError(f"No geographic XGBoost robustness for {name}")
        candidates = part[part.accessibility_specification.str.contains("MW", na=False)]
        if candidates.empty:
            raise RuntimeError(f"No walking-access row for {name}")
        r = candidates.iloc[0]
        summary.append({"Analysis": name.replace("_", " "), "Status": "Pre-specified/planned" if name != "bus_walking" else "Post-Phase-9 bus amendment",
                        "N": int(r.sample_N), "Validation": r.validation_method,
                        "Comparison": r.accessibility_specification,
                        "RMSE": round(r.RMSE, 4), "ΔRMSE vs reference": round(r.Delta_RMSE_vs_relevant_baseline, 5),
                        "Interpretation": str(r.main_accessibility_conclusion)})
    context_perf = pd.read_csv(ROOT / "outputs/tables/context_augmented_performance.csv")
    context_row = context_perf[(context_perf.model == "XGBoost") &
                               (context_perf.feature_set == "MW_CTX") &
                               (context_perf.cv_scheme == "geographic_11")].iloc[0]
    context_base = context_perf[(context_perf.model == "XGBoost") &
                                (context_perf.feature_set == "M0_CTX") &
                                (context_perf.cv_scheme == "geographic_11")].iloc[0]
    summary.append({"Analysis": "Area context (mixed resolution)", "Status": "Post-Phase-9 planned context", "N": int(context_row.n),
                    "Validation": "geographic_11", "Comparison": "MW_CTX versus M0_CTX",
                    "RMSE": round(context_row.rmse_log, 4),
                    "ΔRMSE vs reference": round(context_base.rmse_log-context_row.rmse_log, 5),
                    "Interpretation": "Core RQ2 adjusted comparison; mixed-resolution context provisional"})
    cph = pd.read_csv(ROOT / "outputs/tables/copenhagen_only_context_sensitivity.csv")
    cph_base = cph.loc[cph.feature_set == "M0_CTX"].iloc[0]
    cph_walk = cph.loc[cph.feature_set == "MW_CTX"].iloc[0]
    cph_folds = pd.read_csv(ROOT / "outputs/tables/context_augmented_fold_performance.csv")
    cph_folds = cph_folds[(cph_folds["sample"] == "copenhagen_10_districts") &
                          (cph_folds.cv_scheme == "geographic_11") &
                          (cph_folds.model == "XGBoost") &
                          (cph_folds.feature_set.isin(["M0_CTX", "MW_CTX"]))]
    cph_pairs = cph_folds.pivot(index="fold", columns="feature_set", values="rmse_log")
    if len(cph_pairs) != 10 or int(cph_walk.n) != 11108:
        raise RuntimeError("Copenhagen-only robustness source changed")
    improved = int((cph_pairs["MW_CTX"] < cph_pairs["M0_CTX"]).sum())
    summary.append({"Analysis": "Area context (Copenhagen only)", "Status": "Post-Phase-9 planned context",
                    "N": int(cph_walk.n), "Validation": "geographic_10", "Comparison": "MW_CTX versus M0_CTX",
                    "RMSE": round(cph_walk.geographic_xgb_rmse_log, 4),
                    "ΔRMSE vs reference": round(cph_base.geographic_xgb_rmse_log-cph_walk.geographic_xgb_rmse_log, 5),
                    "Interpretation": f"Improves {improved}/{len(cph_pairs)} districts; same Copenhagen-only context baseline"})
    boundary = pd.read_csv(ROOT / "outputs/tables/boundary_sensitivity_performance.csv")
    boundary = boundary[(boundary.cv_scheme == "geographic_11") & (boundary.model == "XGBoost")]
    bound_base = boundary.loc[boundary.feature_set == "M0"].iloc[0]
    bound_walk = boundary.loc[boundary.feature_set == "MW"].iloc[0]
    if int(bound_walk.n) != 12412:
        raise RuntimeError("Boundary-sensitivity robustness sample changed")
    summary.append({"Analysis": "Study-boundary destinations", "Status": "Pre-freeze endpoint sensitivity",
                    "N": int(bound_walk.n), "Validation": "geographic_11", "Comparison": "MW_BOUND versus M0_BOUND",
                    "RMSE": round(bound_walk.rmse_log, 4),
                    "ΔRMSE vs reference": round(bound_base.rmse_log-bound_walk.rmse_log, 5),
                    "Interpretation": "Destinations clipped to study union; walking graph unchanged; matched baseline"})
    obs = pd.read_csv(ROOT / "outputs/tables/price_observability_comparison.csv")
    obs_row = obs[(obs.model == "XGBoost") & (obs.feature_set == "MW") &
                  (obs.validation == "geographic_11")].iloc[0]
    summary.append({"Analysis": "High-price-completeness batches", "Status": "Post-completion outcome robustness", "N": int(obs_row.n_high_completeness),
                    "Validation": "geographic_11", "Comparison": "MW versus M0; dates ≥90% observed price",
                    "RMSE": round(obs_row.rmse_high_completeness, 4),
                    "ΔRMSE vs reference": round(obs_row.delta_access_high_completeness, 5),
                    "Interpretation": "Different sample; compare its own M0/MW increment, not raw Phase 9 RMSE"})
    for name, label in (("area_fixed_effects", "Area fixed effects"), ("spatial_error_8nn", "Spatial error")):
        r = robust.loc[robust.analysis == name].iloc[0]
        summary.append({"Analysis": label, "Status": "Planned association robustness", "N": int(r.sample_N),
                        "Validation": "In-sample association", "Comparison": str(r.accessibility_specification),
                        "RMSE": "—", "ΔRMSE vs reference": "—",
                        "Interpretation": str(r.main_accessibility_conclusion)})
    table("table8_robustness_summary", summary,
          "Selected Phase 10 and later checks. Geographic XGBoost walking comparison shown where predictive metrics apply. Area socioeconomic context is a planned specification implemented after Phase 9 and reported as a core RQ2 comparison in its own panel. For 15-/20-minute rows, ΔRMSE is versus the matching no-access baseline, NOT Euclidean accessibility. Fixed effects/spatial-error analyses are association-only and must not be ranked by CV RMSE. Samples, feature definitions and estimands differ. The Phase 9 base result remains frozen.")


def base_map(conn):
    areas = [(r.area_id, r.area_name, r.municipality_code, json.loads(r.geo)) for r in conn.execute(text(
        "SELECT area_id,area_name,municipality_code,ST_AsGeoJSON(geom_25832) geo FROM spatial.official_cv_areas ORDER BY area_id"))]
    municipalities = [(r.municipality_code, json.loads(r.geo)) for r in conn.execute(text(
        "SELECT municipality_code,ST_AsGeoJSON(geom_25832) geo FROM spatial.official_municipalities"))]
    neighbours = [json.loads(r.geo) for r in conn.execute(text(
        "SELECT ST_AsGeoJSON(c.geom_25832) geo FROM spatial.map_context_municipalities c "
        "JOIN spatial.study_area s ON s.area_kind='official_study_area' "
        "WHERE c.municipality_code NOT IN ('0101','0147') AND ST_DWithin(c.geom_25832,s.geom_25832,3500)"))]
    if len(areas) != 11 or len(municipalities) != 2:
        raise RuntimeError("Official map geography incomplete")
    return areas, municipalities, neighbours


def map_extent(ax, areas):
    # Study extent only, with nearby official municipalities as context.
    polygons = [point for _, _, _, g in areas for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]) for ring in poly[:1] for point in ring]
    points = np.asarray(polygons)
    xmin, ymin = points.min(axis=0)
    xmax, ymax = points.max(axis=0)
    ax.set_xlim(xmin-1750, xmax+1750)
    ax.set_ylim(ymin-1100, ymax+1100)
    ax.set_aspect("equal")
    ax.set_axis_off()


def study_map(conn, sample, geo):
    areas, municipalities, neighbours = geo
    # Private points are used only to calculate suppressed and clipped 500 m cells.
    frame = sample[["metric_x", "metric_y"]].copy()
    frame["gx"] = np.floor(frame.metric_x/500).astype(int)
    frame["gy"] = np.floor(frame.metric_y/500).astype(int)
    cells = frame.groupby(["gx", "gy"]).size().reset_index(name="n")
    cells = cells[cells.n >= 5]
    grid = ",".join(f"({int(r.gx)},{int(r.gy)})" for r in cells.itertuples())
    polygons = {(r.gx, r.gy): json.loads(r.geo) for r in conn.execute(text(
        "WITH grid(gx,gy) AS (VALUES " + grid + ") "
        "SELECT gx,gy,ST_AsGeoJSON(ST_CollectionExtract(ST_Intersection(" 
        "ST_MakeEnvelope(gx*500,gy*500,(gx+1)*500,(gy+1)*500,25832),s.geom_25832),3)) geo "
        "FROM grid CROSS JOIN spatial.study_area s WHERE s.area_kind='official_study_area'"))}
    stations = pd.read_sql(text(
        "SELECT station_mode,ST_X(geom_25832) x,ST_Y(geom_25832) y FROM spatial.transit_stations p "
        "WHERE EXISTS (SELECT 1 FROM spatial.study_area s WHERE s.area_kind='official_study_area' "
        "AND ST_DWithin(p.geom_25832,s.geom_25832,1000))"), conn)
    centre = conn.execute(text("SELECT ST_X(geom_25832),ST_Y(geom_25832) FROM spatial.reference_points WHERE reference_id='city_hall_square'")).one()
    fig, ax = plt.subplots(figsize=(10, 8), dpi=200)
    for g in neighbours:
        _rings(ax, g, fill="#EDF1EF", edge="#BAC8C5", linewidth=.5)
    for _, _, _, g in areas:
        _rings(ax, g, fill="#F5F9F8", edge="none", linewidth=0)
    norm = matplotlib.colors.PowerNorm(gamma=.6, vmin=20, vmax=max(20, 4*cells.n.quantile(.95)))
    cmap = plt.get_cmap("YlGnBu")
    for r in cells.itertuples():
        g = polygons.get((r.gx, r.gy))
        if g and g["coordinates"]:
            _rings(ax, g, fill=cmap(norm(4*r.n)), edge="white", linewidth=.15)
    for _, _, code, g in areas:
        if code == "0101":
            _rings(ax, g, fill="none", edge="#8198A4", linewidth=.45, outline_only=True)
    for code, g in municipalities:
        _rings(ax, g, fill="none", edge=INK if code == "0101" else "#A26962", linewidth=1.5, outline_only=True)
    markers = {"metro": ("o", "#B56F73"), "urban_rail": ("s", "#806FA4"), "rail": ("^", "#C28B5A")}
    for mode, (marker, color) in markers.items():
        points = stations[stations.station_mode == mode]
        ax.scatter(points.x, points.y, marker=marker, s=22, color=color, edgecolor="white", linewidth=.35, zorder=8)
    ax.scatter([centre[0]], [centre[1]], marker="*", s=135, color="#D0A447", edgecolor=INK, linewidth=.6, zorder=10)
    map_extent(ax, areas)
    ax.set_title("Study area and retained listing density", fontsize=15, color=INK, loc="left", pad=14)
    ax.text(.01, -.04, f"500 m squares; cells with <5 listings suppressed. Density shown for the frozen {len(sample):,}-listing model sample.\nOfficial Copenhagen districts and Frederiksberg municipality; OSM station points, not Airbnb points. EPSG:25832.",
            transform=ax.transAxes, va="top", fontsize=8.5, color=INK)
    handles = [Patch(facecolor="none", edgecolor=INK, label="Copenhagen boundary"),
               Patch(facecolor="none", edgecolor="#8198A4", linewidth=.7, label="Copenhagen district boundaries"),
               Patch(facecolor="none", edgecolor="#A26962", label="Frederiksberg boundary"),
               Line2D([], [], marker="*", linestyle="", color="#D0A447", markersize=11, label="City Hall Square")]
    handles += [Line2D([], [], marker=marker, linestyle="", color=color, markersize=6,
                       label={"metro":"Metro", "urban_rail":"Urban/light rail", "rail":"Other rail"}[mode])
                for mode, (marker,color) in markers.items()]
    ax.legend(handles=handles, loc="upper right", frameon=True, facecolor="white", fontsize=8)
    bar = fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, shrink=.43, pad=.015)
    bar.set_label("Listings / km²", fontsize=9)
    fig.text(.08, .02, "Sources: Inside Airbnb (2026 snapshot); official DAGI/City boundaries; OSM extract 26 Sep 2026. © OpenStreetMap contributors.", fontsize=7.5, color=INK)
    fig.savefig(FIGURES / "figure2_study_area.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def workflow_figure():
    fig, ax = plt.subplots(figsize=(8.8, 8.8), dpi=200)
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
    steps = [
        ("Inside Airbnb + OpenStreetMap + official geography", 9.2),
        ("PostgreSQL / PostGIS + spatial features", 8.15),
        ("Copenhagen–Frederiksberg urban core", 7.1),
        ("Euclidean  ↔  walking-network accessibility", 6.05),
        ("M0  /  ME  /  MW  /  exploratory MEW", 5),
        ("Semilog OLS  +  XGBoost", 3.95),
        ("Random 5-fold + leave-one-area-out (11 areas)", 2.9),
    ]
    for i, (label, y) in enumerate(steps):
        color = PALE if i % 2 == 0 else "#E7EAF1"
        ax.add_patch(Rectangle((.7, y-.34), 8.6, .68, facecolor=color, edgecolor="#BBCAC9", linewidth=.8))
        ax.text(5, y, label, va="center", ha="center", color=INK, fontsize=11.2, fontweight="medium")
        if i < len(steps)-1:
            ax.annotate("", xy=(5, y-.68), xytext=(5, y-.36), arrowprops={"arrowstyle":"-|>", "color":TEAL, "lw":1.7})
    for x, color, heading, detail in ((.7, PALE, "BASE SPECIFICATION", "Frozen Phase 9 results"),
                                       (5.15, "#EDF4EA", "AREA-CONTEXT CORE", "Implemented after Phase 9")):
        ax.add_patch(Rectangle((x, 1.32), 4.15, .85, facecolor=color, edgecolor="#BBCAC9", linewidth=.8))
        ax.text(x+2.075, 1.82, heading, ha="center", va="center", fontsize=9.2, fontweight="bold", color=INK)
        ax.text(x+2.075, 1.53, detail, ha="center", va="center", fontsize=9.1, color=INK)
    for x in (2.775, 7.225):
        ax.annotate("", xy=(x,2.19), xytext=(5,2.52),
                    arrowprops={"arrowstyle":"-|>", "color":TEAL, "lw":1.5})
    ax.set_title("Research workflow", fontsize=16, color=INK, pad=12)
    fig.text(.5, .055, "One listing snapshot · matched OSM destinations · fixed outer folds\nArea density/income were planned conceptually, but not frozen Phase 9 M0 controls.", ha="center", fontsize=8.5, color=INK)
    fig.savefig(FIGURES / "figure1_workflow.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def composite_and_reuse():
    # These figures are generated by the phase runners. Copy, never alter them.
    reuse = {
        "figure6_accessibility_coefficients.png": ROOT / "outputs/figures/phase09/ols_mw_coefficients.png",
        "figure7_validation_performance.png": ROOT / "outputs/figures/phase10/primary_validation_context.png",
        "figure9_residual_diagnostics.png": ROOT / "outputs/figures/phase09/oof_residual_moran.png",
    }
    for name, source in reuse.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copyfile(source, FIGURES / name)


def comparison_figure(conn, sample):
    """Same frozen listing sample and paired destinations; no row-level export."""
    network = pd.read_sql(text(
        "SELECT snapshot_date,listing_id,nearest_station_network_distance_m "
        "FROM analysis.analysis_dataset_v1 WHERE primary_sample_candidate "
        "AND official_cv_area_id IS NOT NULL AND nearest_station_walking_minutes IS NOT NULL"),conn)
    frame=sample.merge(network,on=["snapshot_date","listing_id"],validate="one_to_one")
    if len(frame)!=12412 or frame.nearest_station_network_distance_m.isna().any():
        raise RuntimeError("Matched-measure figure has inconsistent Phase 9 sample")
    pairs=[("Food/social opportunities","food_social_800m","food_social_w_10","POIs"),
           ("Cultural/tourist opportunities","cultural_tourist_800m","cultural_tourist_w_10","POIs"),
           ("Nearest rail/metro station","nearest_station_euclidean_m","nearest_station_network_distance_m","metres")]
    fig,axes=plt.subplots(1,3,figsize=(15,5),dpi=200,sharex=True,sharey=True)
    norm=matplotlib.colors.LogNorm(vmin=5,vmax=1000)
    for ax,(title,xname,yname,unit) in zip(axes,pairs):
        x=frame[xname].to_numpy(dtype=float); y=frame[yname].to_numpy(dtype=float)
        ax.hexbin(np.log1p(x),np.log1p(y),gridsize=42,extent=(0,9,0,9),
                  mincnt=5,norm=norm,cmap="YlGnBu",linewidths=0)
        ax.plot([0,9],[0,9],ls="--",color="#8095A2",lw=.9)
        ax.set_xlim(0,9);ax.set_ylim(0,9)
        ax.set_aspect("equal")
        ax.set_title(title,loc="left",fontsize=10.5,color=INK)
        ax.set_xlabel(f"ln(1 + straight-line {unit})",fontsize=9)
        ax.set_ylabel(f"ln(1 + walking-network {unit})",fontsize=9)
        ax.grid(color="#E8EDEF",lw=.5)
        ax.text(.04,.96,f"Pearson r = {pearsonr(x,y).statistic:.3f}\nSpearman ρ = {spearmanr(x,y).statistic:.3f}",
                transform=ax.transAxes,va="top",ha="left",fontsize=8,color=INK,
                bbox={"facecolor":"white","edgecolor":"#D5E0E0","boxstyle":"round,pad=.3","alpha":.93})
    bar=fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm,cmap="YlGnBu"),ax=axes,
                     shrink=.65,pad=.018)
    bar.set_label("Listings per hexagon (shared log scale)",fontsize=8)
    fig.suptitle(f"Matched Euclidean and network measures (N={len(frame):,})",fontsize=15,color=INK,y=.97)
    fig.text(.08,.015,"Same canonical OSM destinations in each pair; 800 m straight-line versus 10-minute walking POI counts. Station compares nearest straight-line with network metres. Bins with <5 listings hidden. EPSG:25832.",fontsize=8,color=INK)
    fig.savefig(FIGURES/"figure5_matched_accessibility.png",dpi=200,bbox_inches="tight")
    plt.close(fig)


def price_figure(conn, sample, geo):
    """Price distribution and 500 m spatial medians for exactly the same N."""
    areas, _, neighbours = geo
    p99 = float(sample.price_nightly.quantile(.99))
    source = sample[["metric_x", "metric_y", "price_nightly"]].copy()
    source["gx"] = np.floor(source.metric_x/500).astype(int)
    source["gy"] = np.floor(source.metric_y/500).astype(int)
    cells = source.groupby(["gx", "gy"]).price_nightly.agg(["size", "median"]).reset_index()
    cells = cells[cells["size"] >= 5]
    values = ",".join(f"({int(r.gx)},{int(r.gy)})" for r in cells.itertuples())
    clipped = {(r.gx,r.gy):json.loads(r.geo) for r in conn.execute(text(
        "WITH grid(gx,gy) AS (VALUES " + values + ") "
        "SELECT gx,gy,ST_AsGeoJSON(ST_CollectionExtract(ST_Intersection(" 
        "ST_MakeEnvelope(gx*500,gy*500,(gx+1)*500,(gy+1)*500,25832),s.geom_25832),3)) geo "
        "FROM grid CROSS JOIN spatial.study_area s WHERE s.area_kind='official_study_area'"))}
    fig = plt.figure(figsize=(16, 6), dpi=190)
    grid = fig.add_gridspec(1,3,width_ratios=[1,1,1.35],left=.055,right=.95,top=.86,bottom=.18,wspace=.25)
    ax_price,ax_log,ax_map=(fig.add_subplot(grid[0,i]) for i in range(3))
    detail=sample.loc[sample.price_nightly <= p99, "price_nightly"]
    ax_price.hist(detail,bins=50,color=BLUE,edgecolor="white",linewidth=.3)
    ax_price.set(xlabel="Listed nightly price (DKK)",ylabel="Listings per price bin")
    ax_price.set_title("A · Price (≤99th percentile)",color=INK,loc="left",fontsize=11)
    ax_log.hist(sample.log_price,bins=50,color=TEAL,edgecolor="white",linewidth=.3)
    ax_log.set(xlabel="ln(listed nightly price in DKK)",ylabel="Listings per log-price bin")
    ax_log.set_title("B · Log price (full sample)",color=INK,loc="left",fontsize=11)
    for ax in (ax_price,ax_log):
        ax.grid(axis="y",color="#E9EFF0",linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[["top","right"]].set_visible(False)
    for g in neighbours:
        _rings(ax_map,g,fill="#EDF1EF",edge="#C6D1CE",linewidth=.3)
    for _,_,_,g in areas:
        _rings(ax_map,g,fill="#F2F7F5",edge="white",linewidth=.3)
    norm=matplotlib.colors.Normalize(vmin=float(cells["median"].quantile(.05)),
                                      vmax=float(cells["median"].quantile(.95)))
    cmap=plt.get_cmap("YlGnBu")
    for r in cells.itertuples():
        g=clipped.get((r.gx,r.gy))
        if g and g["coordinates"]:
            _rings(ax_map,g,fill=cmap(norm(r.median)),edge="white",linewidth=.15)
    for _,_,_,g in areas:
        _rings(ax_map,g,fill="none",edge="#648392",linewidth=.45,outline_only=True)
    map_extent(ax_map,areas)
    ax_map.set_title("C · 500 m grid median",color=INK,loc="left",fontsize=11)
    bar=fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm,cmap=cmap),ax=ax_map,
                     fraction=.039,pad=.015,shrink=.8)
    bar.set_label("Median listed price (DKK)",fontsize=8.5)
    fig.suptitle(f"Listed nightly prices in the frozen model sample (N={len(sample):,})",color=INK,fontsize=15,y=.965)
    fig.text(.5,.055,f"Panels A–C use the identical Phase 9 common sample. A omits only the {len(sample)-len(detail)} prices above P99 ({p99:,.0f} DKK) from display, not modelling. "
             "C suppresses cells with <5 listings; EPSG:25832. Source: Inside Airbnb 2026 snapshot; official DAGI/City boundaries.",
             ha="center",fontsize=8,color=INK)
    fig.savefig(FIGURES/"figure3_price_pattern.png",dpi=190,bbox_inches="tight")
    plt.close(fig)


def cv_geography(conn, geo):
    areas, _, neighbours = geo
    source = pd.read_csv(PHASE9 / "fold_performance.csv")
    source = source[(source.cv_scheme == "geographic_11") & (source.model == "XGBoost") & (source.feature_set == "MW")]
    values = source.set_index("fold")
    if len(values) != 11:
        raise RuntimeError("Geographic CV fold coverage changed")
    fig, ax = plt.subplots(figsize=(10.4, 8), dpi=200)
    for g in neighbours:
        _rings(ax, g, fill="#EDF1EF", edge="#BBC8C5", linewidth=.5)
    norm = Normalize(vmin=source.rmse_log.min(), vmax=source.rmse_log.max())
    cmap = plt.get_cmap("YlGnBu")
    labels = []
    for area_id, name, code, geom in areas:
        value = values.loc[area_id]
        _rings(ax, geom, fill=cmap(norm(value.rmse_log)), edge="white", linewidth=.8)
        # PointOnSurface is guaranteed inside the official unit, even for concave polygons.
        labels.append((area_id, name, conn.execute(text("SELECT ST_X(ST_PointOnSurface(geom_25832)),ST_Y(ST_PointOnSurface(geom_25832)) FROM spatial.official_cv_areas WHERE area_id=:id"), {"id":area_id}).one(), int(value.n)))
    offsets = {"cph_02":(10,13), "cph_03":(-8,-12), "cph_05":(-15,5),
               "cph_04":(22,-10), "cph_01":(3,-5)}
    for area_id, name, (x,y), n in labels:
        short = {"Vesterbro-Kongens Enghave":"Vesterbro / K. Enghave", "Frederiksberg":"Frederiksberg†"}.get(name, name)
        ax.annotate(f"{short}\nN={n:,}", (x,y), xytext=offsets.get(area_id,(0,0)),
                    textcoords="offset points",ha="center",va="center",fontsize=6.8,color=INK,
                    path_effects=[matplotlib.patheffects.withStroke(linewidth=2.2, foreground="white")])
    map_extent(ax, areas)
    ax.set_title("Geographic CV: one official area held out per fold", loc="left", fontsize=14, color=INK)
    bar = fig.colorbar(matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, shrink=.48, pad=.02)
    bar.set_label("XGBoost MW held-out RMSE (ln price)", fontsize=9)
    ax.text(.01,-.04,"Official Copenhagen districts plus Frederiksberg municipality†. Colour is fold-level out-of-area error, not price.\nUnseen-area errors are not comparable without considering different N and predictor support. EPSG:25832.",
            transform=ax.transAxes, va="top", fontsize=8.5, color=INK)
    fig.savefig(FIGURES / "figure8_cv_geography.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def catchment_figure(conn):
    """Public network-node origin near harbour; no Airbnb coordinate is used."""
    centre = conn.execute(text("SELECT ST_X(geom_25832),ST_Y(geom_25832) FROM spatial.reference_points WHERE reference_id='city_hall_square'")).one()
    network_id = conn.scalar(text("SELECT network_id FROM spatial.walking_networks ORDER BY built_at DESC LIMIT 1"))
    if not network_id:
        raise RuntimeError("No saved walking network")
    # Fixed cartographic point: closest public OSM walking node to a displaced
    # City Hall reference. This is illustrative, not a sampled Airbnb listing.
    target_x, target_y = centre[0]+1500, centre[1]-1050
    largest_component = conn.scalar(text(
        "SELECT component_id FROM spatial.walking_nodes WHERE network_id=:id "
        "GROUP BY component_id ORDER BY count(*) DESC LIMIT 1"), {"id": network_id})
    origin = conn.execute(text(
        "SELECT osm_node_id,ST_X(geom_25832),ST_Y(geom_25832) FROM spatial.walking_nodes "
        "WHERE network_id=:id AND component_id=:component "
        "ORDER BY geom_25832 <-> ST_SetSRID(ST_MakePoint(:x,:y),25832) LIMIT 1"),
        {"id": network_id,"component":largest_component,"x":target_x,"y":target_y}).one()
    ox, oy = float(origin[1]), float(origin[2])
    nodes = pd.read_sql(text(
        "SELECT osm_node_id AS id,ST_X(geom_25832) x,ST_Y(geom_25832) y FROM spatial.walking_nodes "
        "WHERE network_id=:id AND ST_DWithin(geom_25832,ST_SetSRID(ST_MakePoint(:x,:y),25832),1100)"),
        conn, params={"id":network_id,"x":ox,"y":oy})
    edges = pd.read_sql(text(
        "SELECT e.from_node_id u,e.to_node_id v,e.length_m length,e.forward_allowed forward,e.reverse_allowed reverse "
        "FROM spatial.walking_edges e JOIN spatial.walking_nodes a ON a.network_id=e.network_id AND a.osm_node_id=e.from_node_id "
        "JOIN spatial.walking_nodes b ON b.network_id=e.network_id AND b.osm_node_id=e.to_node_id "
        "WHERE e.network_id=:id AND ST_DWithin(a.geom_25832,ST_SetSRID(ST_MakePoint(:x,:y),25832),1100) "
        "AND ST_DWithin(b.geom_25832,ST_SetSRID(ST_MakePoint(:x,:y),25832),1100)"),
        conn, params={"id":network_id,"x":ox,"y":oy})
    if nodes.empty or edges.empty:
        raise RuntimeError("Illustrative network neighbourhood is empty")
    xy = {int(r.id):(float(r.x),float(r.y)) for r in nodes.itertuples()}
    graph = nx.DiGraph()
    graph.add_nodes_from(xy)
    for r in edges.itertuples():
        if r.forward:
            u,v=int(r.u),int(r.v)
            if not graph.has_edge(u,v) or float(r.length)<graph[u][v]["weight"]:
                graph.add_edge(u,v,weight=float(r.length))
        if r.reverse:
            u,v=int(r.v),int(r.u)
            if not graph.has_edge(u,v) or float(r.length)<graph[u][v]["weight"]:
                graph.add_edge(u,v,weight=float(r.length))
    lengths = nx.single_source_dijkstra_path_length(graph, int(origin[0]), cutoff=800, weight="weight")
    destinations = pd.read_sql(text(
        "SELECT p.category,p.destination_key,ST_X(p.geom_25832) x,ST_Y(p.geom_25832) y,"
        "s.snapped_node_id,s.snap_distance_m FROM spatial.osm_pois p "
        "JOIN spatial.walking_destination_snaps s ON s.destination_kind='poi' AND s.destination_key=p.destination_key AND s.network_id=:id "
        "WHERE ST_DWithin(p.geom_25832,ST_SetSRID(ST_MakePoint(:x,:y),25832),800)"),
        conn, params={"id":network_id,"x":ox,"y":oy})
    # A destination may be inside the circle but not reachable within the
    # 800 m walk budget once its snap connector is accounted for.
    destinations["reachable"] = [lengths.get(int(r.snapped_node_id), math.inf) + float(r.snap_distance_m) <= 800
                                  for r in destinations.itertuples()]
    if destinations.reachable.sum() < 5 or len(lengths) < 25:
        raise RuntimeError("Illustrative node does not show a meaningful connected walking catchment")
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=200, sharex=True, sharey=True)
    cat = {"food_social": ("o", CORAL, "Food/social"), "cultural_tourist": ("^", BLUE, "Cultural/tourist")}
    for ax, title in zip(axes, (f"A · 800 m straight-line circle ({len(destinations)} POIs)",
                                f"B · 10-minute walking-network reach ({int(destinations.reachable.sum())} of {len(destinations)} POIs reachable)")):
        for r in edges.itertuples():
            a, b = xy[int(r.u)], xy[int(r.v)]
            ax.plot((a[0],b[0]),(a[1],b[1]), color="#D8E1E1", linewidth=.5, zorder=1)
        if ax is axes[0]:
            ax.add_patch(Circle((ox,oy),800,facecolor="#B9D7D0",edgecolor=TEAL,alpha=.3,lw=1.5,zorder=2))
        else:
            for r in edges.itertuples():
                a, b = xy[int(r.u)], xy[int(r.v)]
                # Draw directional reachability; partial edge ends at budget.
                for u,v,allowed in ((int(r.u),int(r.v),r.forward),(int(r.v),int(r.u),r.reverse)):
                    if (not allowed or u not in lengths or
                            float(r.length)>graph[u][v]["weight"]+1e-8):
                        continue
                    reach = min(1.0, max(0.0, (800-lengths[u])/float(r.length)))
                    if reach <= 0:
                        continue
                    start, end = xy[u], xy[v]
                    ax.plot((start[0],start[0]+reach*(end[0]-start[0])),
                            (start[1],start[1]+reach*(end[1]-start[1])),
                            color=TEAL, linewidth=2.1, alpha=.88, zorder=3)
        for category, (marker,color,_) in cat.items():
            points=destinations[destinations.category==category]
            ax.scatter(points.x,points.y,s=24,marker=marker,color=color,edgecolor="white",linewidth=.4,zorder=5,
                       alpha=.95 if ax is axes[0] else .4)
            if ax is axes[1]:
                reached=points[points.reachable]
                ax.scatter(reached.x,reached.y,s=29,marker=marker,color=color,edgecolor=INK,linewidth=.35,zorder=6)
        ax.scatter([ox],[oy],marker="*",s=175,color="#D5A349",edgecolor=INK,linewidth=.5,zorder=6)
        ax.set_title(title,fontsize=11,color=INK,loc="left")
        ax.set_xlim(ox-900,ox+900); ax.set_ylim(oy-900,oy+900)
        ax.set_aspect("equal");ax.set_xticks([]);ax.set_yticks([])
        for spine in ax.spines.values(): spine.set_color("#BDCECB")
    handles=[Line2D([],[],marker="*",linestyle="",color="#D5A349",markersize=10,label="Illustrative OSM-node origin"),
             Line2D([],[],color=TEAL,lw=2,label="Reachable street segment")]
    handles += [Line2D([],[],marker=m,linestyle="",color=c,markersize=6,label=label) for m,c,label in cat.values()]
    fig.legend(handles=handles,ncol=4,loc="lower center",bbox_to_anchor=(.5,.02),frameon=False,fontsize=8.5)
    fig.suptitle("Same destinations, different access geometry",fontsize=15,color=INK,y=.97)
    fig.text(.5,.075,"Origin is an illustrative public walking-network node, not an Airbnb listing. Both panels show the same mapped POIs within 800 m straight-line.\nWalking budget = 800 m network travel at 4.8 km/h, including POI snap connectors; lines show reachability, not a service area polygon. EPSG:25832.",
             ha="center",fontsize=8,color=INK)
    fig.savefig(FIGURES / "figure4_catchment_example.png",dpi=200,bbox_inches="tight")
    plt.close(fig)
    return {"network_id": network_id, "illustrative_osm_node": int(origin[0]),
            "candidate_pois_in_circle": len(destinations), "walk_reachable_pois": int(destinations.reachable.sum()),
            "origin_definition": "Nearest node on largest public walking-network component to City Hall Square +1500 m east, -1050 m northing",
            "crs_epsg": CRS, "walking_budget_m": 800}


def make_manifest(catchment_meta):
    planned_tables = [
        ("Table 1", "Sample construction", "table1_sample_construction.csv"),
        ("Table 2", "Variable specification", "table2_variable_specification.csv"),
        ("Table 3", "Descriptive statistics", "table3_descriptive_statistics.csv"),
        ("Table 4", "Accessibility definitions", "table4_accessibility_definitions.csv"),
        ("Table 5", "Compact hedonic ladder", "table5_hedonic_ladder.csv"),
        ("Table 6", "Predictive performance", "table6_predictive_performance.csv"),
        ("Table 7", "Incremental accessibility value", "table7_incremental_accessibility.csv"),
        ("Core RQ2 panel", "Base versus area-context-adjusted prediction", "table_rq2_area_context.csv"),
        ("Table 8", "Robustness summary", "table8_robustness_summary.csv"),
    ]
    planned_figures = [
        ("Figure 1", "Research workflow", "figure1_workflow.png"),
        ("Figure 2", "Study area overview", "figure2_study_area.png"),
        ("Figure 3", "Price distribution and spatial pattern", "figure3_price_pattern.png"),
        ("Figure 4", "Euclidean versus network catchment", "figure4_catchment_example.png"),
        ("Figure 5", "Matched accessibility measures", "figure5_matched_accessibility.png"),
        ("Figure 6", "Accessibility–price association", "figure6_accessibility_coefficients.png"),
        ("Figure 7", "Random versus geographic performance", "figure7_validation_performance.png"),
        ("Figure 8", "Outer CV geography", "figure8_cv_geography.png"),
        ("Methods figure", "Validation designs", "figure_validation_designs.png"),
    ]
    rows=[]
    format_needed={"Table 2","Table 3","Table 5","Table 8"}
    for title, concept, name in planned_tables:
        path=TABLES/name
        status=("READY BUT NEEDS FORMATTING" if title in format_needed else "READY") if path.exists() else "MISSING"
        rows.append((title,concept,status,path.relative_to(ROOT).as_posix(),"MAIN TEXT"))
    for title, concept, name in planned_figures:
        path=FIGURES/name
        rows.append((title,concept,"READY" if path.exists() else "MISSING",path.relative_to(ROOT).as_posix(),"MAIN TEXT"))
    context_path=ROOT/"outputs/figures/context_incremental_accessibility.png"
    rows.append(("Core RQ2 context figure", "Accessibility before/after area socioeconomic context",
                 "READY" if context_path.exists() else "MISSING",context_path.relative_to(ROOT).as_posix(),"MAIN TEXT"))
    # Audit every extant exported file, including post-completion amendments.
    all_files=sorted(p for base in (ROOT/"outputs/tables",ROOT/"outputs/figures")
                     for p in base.rglob("*") if p.is_file() and p.name not in (".gitkeep",".DS_Store"))
    main={path for _,_,_,path,_ in rows}
    main.update(path.removesuffix(".csv")+".md" for _,_,_,path,_ in rows if path.endswith(".csv"))
    inventory=[]
    for path in all_files:
        rel=path.relative_to(ROOT).as_posix()
        if rel in main:
            status=("READY BUT NEEDS FORMATTING" if any(rel.startswith(f"outputs/tables/final/table{number}_") for number in (2,3,5,8)) else "READY")
            place="MAIN TEXT"
        elif path.name == "figure9_residual_diagnostics.png":
            status,place="APPENDIX ONLY","APPENDIX"
        elif path.name == "appendix_boundary_catchment_metadata.json":
            status,place="APPENDIX ONLY","REPOSITORY ONLY"
        elif path.name in ("table_validation_designs.csv", "table_validation_designs.md"):
            status,place="APPENDIX ONLY","APPENDIX"
        elif path.parent == ROOT / "outputs/tables/supplementary":
            status,place="SUPPLEMENTARY","REPOSITORY ONLY"
        elif path.parent == TABLES and path.name.startswith("appendix_destination_"):
            status,place="APPENDIX ONLY","APPENDIX"
        elif "_revision_sources" in path.parts:
            status,place="APPENDIX ONLY","REPOSITORY ONLY"
        elif path.parent in (TABLES,FIGURES):
            status,place="APPENDIX ONLY","APPENDIX" if "appendix" in path.name else "REPOSITORY ONLY"
        elif "phase11" in path.parts or path.suffix==".json":
            status,place="APPENDIX ONLY","REPOSITORY ONLY"
        elif any(x in path.name for x in ("source_coverage","metadata","tuning","snap_diagnostics","map_coverage","destination_counts")):
            status,place="APPENDIX ONLY","REPOSITORY ONLY"
        elif path.name in ("price_distributions.png","median_price_grid.png","euclidean_network_hexbin.png",
                                "ols_mw_coefficients.png","primary_validation_context.png","oof_residual_moran.png"):
            status,place="SUPERSEDED","APPENDIX"
        else:
            status,place="APPENDIX ONLY","APPENDIX"
        inventory.append((rel,status,place))
    manifest=["# Final output manifest", "", "Generated from the v2 proposal and v2 end-to-end plan, matched against all current `outputs/tables/` and `outputs/figures/` files. Status refers to **presentation completeness**, not statistical endorsement. Phase 9 M0/ME/MW/MEW remain the frozen **base specification**. The conceptually planned area socioeconomic-context adjustment was implemented after Phase 9, once sources were audited, and is presented as an **area-context-adjusted core specification**, not the original frozen Phase 7 model or a fully harmonised neighbourhood measure. `READY` means the file exists and passed this assembly audit; manuscript placement still needs final typesetting. `SUPERSEDED` means a final composite/copy is preferred for the main text; the source file remains intact. Placement is one of MAIN TEXT, APPENDIX, or REPOSITORY ONLY. Thesis-ready captions are in `docs/final_figure_captions.md`.", "", "## Planned main-text items", "", "| Item | Planned content | Status | Publication file | Placement |", "|---|---|---|---|---|"]
    manifest += [f"| {a} | {b} | {c} | `{d}` | {e} |" for a,b,c,d,e in rows]
    destination_appendix = ["taxonomy", "counts", "examples", "rail_metro"]
    destination_supplement = ["food_social", "cultural_tourist", "rail_metro"]
    manifest += ["", "## Frozen OSM destination appendix and supplementary inventories", "",
                 "Documentation-only export from the unchanged Phase 5 `phase05_v2` canonical tables. No destination set, accessibility feature, or model was changed. The four compact tables belong in the appendix; full canonical POI and rail inventories remain supplementary CSVs.", "",
                 "| Item | File | Placement |", "|---|---|---|"]
    manifest += [f"| Destination {stem.replace('_', ' ')} | `outputs/tables/final/appendix_destination_{stem}.csv` / `outputs/tables/final/appendix_destination_{stem}.md` | APPENDIX |"
                 for stem in destination_appendix]
    manifest += [f"| Full canonical {stem.replace('_', ' ')} inventory | `outputs/tables/supplementary/destination_inventory_{stem}.csv` | SUPPLEMENTARY / REPOSITORY |"
                 for stem in destination_supplement]
    manifest += ["", "LaTeX appendix files: `outputs/latex/appendix/destination_taxonomy.tex`, `destination_counts.tex`, `destination_examples.tex`, and `destination_rail_metro_full.tex`. [Inventory QA and manuscript note](../reports/appendix_destination_inventory.md)."]
    boundary_figure = "outputs/figures/final/appendix_boundary_catchment_example.png"
    manifest += ["", "## Boundary-endpoint illustration", "",
                 "Separate appendix-only public-OSM catchment example; the main-text Figure 4 remains unchanged. The paired panels show eligible canonical destination endpoints under the buffered primary and study-union-restricted sensitivity definitions. This is not a walking-route or model-result figure.", "",
                 f"| Boundary catchment example | `{boundary_figure}` | APPENDIX |",
                 "", "[Illustration provenance and QA](../reports/appendix_boundary_catchment_figure.md)."]
    manifest += ["", "## Complete exported-file inventory", "", "All non-placeholder files present at audit time are classified below, including source phase outputs and post-completion amendments.", "", "| Path | Status | Placement |", "|---|---|---|"]
    manifest += [f"| `{a}` | {b} | {c} |" for a,b,c in inventory]
    (ROOT/"docs/final_output_manifest.md").write_text("\n".join(manifest)+"\n",encoding="utf-8")
    placement=["# Output placement plan", "", "Copenhagen–Frederiksberg urban core means Copenhagen Municipality plus Frederiksberg Municipality. Keep eight numbered main tables plus a compact core RQ2 comparison panel. Phase 9 is the frozen base specification; the area-context-adjusted core specification was conceptually planned but implemented after Phase 9 because context comparability was unresolved at the Phase 7 freeze. Place the saved context-comparison figure and panel together in the main RQ2 results, not only in the generic robustness table. Use the validation-design schematic in Methods and retain the residual Moran diagnostic, actual 1.5 km block map and validation-designs table in the appendix. Original phase figures remain in place; no model result is replaced. Caption text is in `docs/final_figure_captions.md`.", "", "| Item | Main text file |", "|---|---|"]
    placement += [f"| {a} — {b} | `{d}`" + (f" / `{d.removesuffix('.csv')}.md`" if d.endswith(".csv") else "") + " |"
                  for a,b,_,d,_ in rows]
    placement += ["", "## Frozen OSM destination appendix", "",
                  "These are documentation of the unchanged `phase05_v2` canonical destination universe, not new analytical results. No OSM inventory belongs in the main text. The appendix uses compact taxonomy, count and deterministic-example tables plus the complete 143-station list; thousands of POIs remain supplementary CSVs. The source is the 26 September 2026 OSM snapshot, about three months after the Airbnb snapshot. [Provenance and QA](../reports/appendix_destination_inventory.md).", "",
                  "| Item | Appendix / supplementary file |", "|---|---|"]
    placement += [f"| {stem.replace('_', ' ').title()} appendix | `outputs/tables/final/appendix_destination_{stem}.csv` / `outputs/tables/final/appendix_destination_{stem}.md` |"
                  for stem in destination_appendix]
    placement += [f"| Full {stem.replace('_', ' ')} inventory | `outputs/tables/supplementary/destination_inventory_{stem}.csv` (SUPPLEMENTARY / REPOSITORY) |"
                  for stem in destination_supplement]
    placement += ["", "Thesis-ready LaTeX: `outputs/latex/appendix/destination_taxonomy.tex`, `destination_counts.tex`, `destination_examples.tex`, and `destination_rail_metro_full.tex`."]
    placement += ["", "## Boundary-endpoint illustration", "",
                  f"Keep the original main-text Figure 4 unchanged. Place the separate [public-OSM boundary catchment](../{boundary_figure}) in the appendix, cited alongside the boundary-sensitivity table. It illustrates which canonical endpoints are excluded when the official municipal union is applied; it is not a rerouted network catchment or a model-performance graphic. [Reproducible figure report](../reports/appendix_boundary_catchment_figure.md)."]
    placement += ["", "## Spatial-validation methods placement", "", "The [validation-design schematic](../outputs/figures/final/figure_validation_designs.png) belongs in the Methods spatial-validation section (MAIN TEXT). Reference the actual [1.5 km geometric-block map](../outputs/figures/final/appendix_geometric_block_cv.png) there; the map is APPENDIX. The saved [validation-designs table](../outputs/tables/final/table_validation_designs.md) is APPENDIX supporting Methods. Random CV is interspersed, the block design is a non-administrative robustness split, and leave-one-area-out across 11 analysis areas is the primary unseen-area test."]
    placement += ["", "## Appendix and repository-only outputs", "", "The table below covers every exported file. `APPENDIX` means substantively useful but too detailed/redundant for the main narrative; `REPOSITORY ONLY` means QA, source coverage, tuning or machine-readable lineage rather than a manuscript figure/table.", "", "| File | Placement | Reason |", "|---|---|---|"]
    for rel,status,place in inventory:
        if place=="MAIN TEXT": continue
        reason=("Boundary endpoint inclusion illustration (public OSM only)" if rel==boundary_figure else
                "Full public-OSM canonical inventory (supplementary CSV)" if status=="SUPPLEMENTARY" else
                "Frozen canonical OSM destination appendix documentation" if rel.startswith("outputs/tables/final/appendix_destination_") else
                "Spatial-validation design reference" if place=="METHODS" else
                "Source presentation retained; final main-text composite preferred" if status=="SUPERSEDED" else
                "Diagnostic/provenance detail" if place=="REPOSITORY ONLY" else
                "Supporting robustness, detail or alternative map")
        placement.append(f"| `{rel}` | {place} | {reason} |")
    (ROOT/"docs/output_placement_plan.md").write_text("\n".join(placement)+"\n",encoding="utf-8")
    return rows,inventory


def run():
    TABLES.mkdir(parents=True,exist_ok=True)
    FIGURES.mkdir(parents=True,exist_ok=True)
    engine=get_engine()
    with engine.connect() as conn:
        freeze(conn)
        sample=p9._load(conn)
        make_tables(conn,sample)
        export_rq2_context_panel()
        geo=base_map(conn)
        workflow_figure()
        study_map(conn,sample,geo)
        composite_and_reuse()
        price_figure(conn,sample,geo)
        comparison_figure(conn,sample)
        cv_geography(conn,geo)
        meta=catchment_figure(conn)
        freeze(conn)
    (TABLES/"catchment_example_metadata.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")
    rows,inventory=make_manifest(meta)
    if any(r[2]=="MISSING" for r in rows):
        raise RuntimeError("A planned publication output is still missing")
    print(f"Final output audit assembled {len(rows)} main items; inventoried {len(inventory)} exported files; Phase 9 freeze intact")


if __name__=="__main__":
    run()

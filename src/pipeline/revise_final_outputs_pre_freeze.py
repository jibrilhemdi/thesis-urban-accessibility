"""Presentation-only revision from saved aggregate exports; no database or fitting."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from matplotlib.font_manager import FontProperties, findfont

from src.pipeline.run_context_models_postcompletion02 import figure as context_figure
from src.pipeline.export_rq2_context_panel import main as export_rq2_context_panel
from src.pipeline.run_final_outputs_postcompletion04 import (
    FIGURES, ROOT, TABLES, make_manifest, table, workflow_figure,
)
from src.pipeline.run_validation_visualisation_final import validation_design_rows


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(TABLES / f"{name}.csv", keep_default_na=False)


def _rows(frame: pd.DataFrame) -> list[dict]:
    return frame.to_dict("records")


def revise_tables() -> None:
    sample = _read("table1_sample_construction")
    previous_labels = ("Copenhagen + Frederiksberg study area",
                       "Inside Airbnb Copenhagen/Frederiksberg extract")
    new = "Inside Airbnb Copenhagen–Frederiksberg extract"
    sample.loc[sample["Filter step"].isin(previous_labels), "Filter step"] = new
    assert (sample["Filter step"] == new).sum() == 1
    assert (sample["Filter step"] == "Assigned official validation area").sum() == 1
    table("table1_sample_construction", _rows(sample),
          "Copenhagen–Frederiksberg urban core = Copenhagen Municipality + Frederiksberg Municipality. Sequential Phase 2/7 filters are unchanged. The early geography row denotes the provider extract, not official polygon assignment; the later official-area row requires that assignment. Price losses are missing/invalid outcomes among otherwise eligible residential entire homes; no price was imputed. Percentage uses the preceding row as denominator.")

    variables = _read("table2_variable_specification")
    variables.loc[variables.Variable == "official_municipality_code", "Definition"] = (
        "Copenhagen Municipality versus Frederiksberg Municipality within one urban core")
    variables.loc[variables.Concept == "Area context", "Primary/robustness"] = "Area-context-adjusted core; post-Phase-9 implementation"
    mask = variables.Variable == "nearest_station_euclidean_m"
    assert mask.sum() == 1
    variables.loc[mask, "Definition"] = "Stored straight-line distance to closest canonical station"
    variables.loc[mask, "Transformation/unit"] = "m; EPSG:25832"
    variables.loc[mask, "Model block"] = "Source feature"
    variables.loc[mask, "Missing-data treatment"] = "Converted to km for modelling"
    if not (variables.Variable == "nearest_station_euclidean_km").any():
        model = variables.loc[mask].copy()
        model["Variable"] = "nearest_station_euclidean_km"
        model["Definition"] = "Model variable: stored station metres divided by 1,000"
        model["Transformation/unit"] = "km; EPSG:25832"
        model["Model block"] = "ME/MEW"
        model["Missing-data treatment"] = "Common sample complete"
        index = variables.index[mask][0]
        variables = pd.concat([variables.iloc[:index+1], model, variables.iloc[index+1:]], ignore_index=True)
    table("table2_variable_specification", _rows(variables),
          "M0, ME, MW and MEW are the frozen Phase 9 base specification for the Copenhagen–Frederiksberg urban core. Municipality remains a frozen M0 control. Raw station calculation is in metres; its model input is kilometres. CTX is the area-context-adjusted core specification: conceptually planned, but implemented after Phase 9 because source comparability was unresolved at the Phase 7 freeze. Copenhagen district-level and Frederiksberg municipality-level context are not harmonised neighbourhood controls. DKK is user-confirmed; the source price string lacks an explicit currency code.")

    table("table3_descriptive_statistics", _rows(_read("table3_descriptive_statistics")),
          "Copenhagen–Frederiksberg urban core; frozen Phase 9 common N=12,412. Continuous rows report observed N and sample SD; categorical rows report count and percentage of the common sample. †Area socioeconomic context enters the later area-context-adjusted core specification, not frozen Phase 9 M0. It varies across only 11 area units: ten Copenhagen district-level values and one Frederiksberg municipality-level value. These are listing-weighted descriptions, not 12,412 independent contextual observations. Income definitions differ by source.")

    table("table4_accessibility_definitions", _rows(_read("table4_accessibility_definitions")),
          "Same canonical destinations are used for each matched Euclidean/network pair. Walking speed is 4.8 km/h (80 m/min): 800/1,200/1,600 m network travel corresponds to 10/15/20 minutes; Euclidean comparisons use those straight-line radii. Metric operations use EPSG:25832; bus proximity is robustness only. The listing population is bounded by the Copenhagen–Frederiksberg urban core (Copenhagen Municipality + Frederiksberg Municipality), while the primary opportunity universe is buffered and can include nearby destinations beyond its outer administrative boundary. District boundaries and the internal municipality boundary do not constrain accessibility. A separate sensitivity restricts destination endpoints to the combined municipal union while leaving the walking network unclipped.")

    table("table5_hedonic_ladder", _rows(_read("table5_hedonic_ladder")),
          "Frozen Phase 9 base-specification M0/ME/MW/MEW semilog OLS associations, not causal effects. Focal cells give coefficient (HC3 robust SE); [95% CI]. Opportunity counts use ln(1+count), Euclidean station distance km, and walking station access minutes. Other controls are omitted here; see frozen full coefficients. HC3 addresses heteroskedasticity, not residual spatial dependence. MEW is collinearity-sensitive because Euclidean and walking representations are strongly correlated. The later area-context-adjusted core specification substantially attenuates several focal associations and is reported in the RQ2 panel; spatial-error analysis is a separate check. Adjusted R²/AIC/BIC are in-sample.")

    performance = _read("table6_predictive_performance")
    performance.loc[performance.Validation == "Leave-one-area-out", "Validation"] = (
        "Leave-one-area-out (11 analysis areas)")
    table("table6_predictive_performance", _rows(performance),
          "Frozen Phase 9 pooled outer out-of-fold metrics for the same 12,412 observations; lower RMSE/MAE is better. Random 5-fold is a spatially interspersed benchmark, not geographic validation. Leave-one-area-out holds each of 11 analysis areas out once (10 official Copenhagen districts + Frederiksberg). Geographic transfer also changes predictor support; the error gap alone does not prove leakage. Tiny ME/MW/MEW differences are not statistically established rankings; MEW is exploratory.")

    full = _read("table7_incremental_accessibility")
    appendix_path = TABLES / "table7_incremental_accessibility_appendix.csv"
    if appendix_path.exists():
        appendix = pd.read_csv(appendix_path, keep_default_na=False)
        full = pd.concat([full, appendix], ignore_index=True)
    assert len(full) == 20 and full.Comparison.nunique() == 5
    main = full.loc[full.Comparison.str.endswith("versus M0")]
    supplement = full.loc[full.Comparison.str.endswith("versus ME")]
    assert len(main) == 12 and len(supplement) == 8
    main = main.copy()
    supplement = supplement.copy()
    for frame in (main, supplement):
        frame.rename(columns={"ΔRMSE reduction": "Delta RMSE reduction",
                              "ΔMAE reduction": "Delta MAE reduction"}, inplace=True)
        frame.loc[frame.Validation == "Leave-one-area-out", "Validation"] = (
            "Leave-one-area-out (11 analysis areas)")
    table("table7_incremental_accessibility", _rows(main),
          "Frozen Phase 9 pooled outer out-of-fold changes. Δ is reference error minus new-model error; positive means improvement. Comparisons use identical listings/folds. MEW is exploratory; small E/W differences should not be over-ranked.")
    table("table7_incremental_accessibility_appendix", _rows(supplement),
          "Supplementary frozen Phase 9 pairwise comparisons on identical observations/folds. Δ is reference error minus new-model error; positive means improvement. These comparisons do not replace the main-text M0 reference.")

    robust = _read("table8_robustness_summary")
    robust = robust.loc[~robust.Analysis.isin(["Area context (Copenhagen only)", "Study-boundary destinations"])].copy()
    robust.loc[robust.Analysis.isin(["threshold 15", "threshold 20"]), "Interpretation"] = (
        "ΔRMSE versus matching no-access baseline, not Euclidean access")
    cph = pd.read_csv(ROOT / "outputs/tables/copenhagen_only_context_sensitivity.csv")
    baseline = cph.loc[cph.feature_set == "M0_CTX"].iloc[0]
    walk = cph.loc[cph.feature_set == "MW_CTX"].iloc[0]
    folds = pd.read_csv(ROOT / "outputs/tables/context_augmented_fold_performance.csv")
    folds = folds[(folds["sample"] == "copenhagen_10_districts") & (folds.cv_scheme == "geographic_11") &
                  (folds.model == "XGBoost") & (folds.feature_set.isin(["M0_CTX", "MW_CTX"]))]
    paired = folds.pivot(index="fold", columns="feature_set", values="rmse_log")
    assert int(walk.n) == 11108 and len(paired) == 10
    better = int((paired.MW_CTX < paired.M0_CTX).sum())
    boundary = pd.read_csv(ROOT / "outputs/tables/boundary_sensitivity_performance.csv")
    boundary = boundary[(boundary.cv_scheme == "geographic_11") & (boundary.model == "XGBoost")]
    bound_base = boundary.loc[boundary.feature_set == "M0"].iloc[0]
    bound_walk = boundary.loc[boundary.feature_set == "MW"].iloc[0]
    assert int(bound_walk.n) == 12412
    additions = [
        {"Analysis": "Area context (Copenhagen only)", "Status": "Post-Phase-9 planned context", "N": int(walk.n),
         "Validation": "geographic_10", "Comparison": "MW_CTX versus M0_CTX",
         "RMSE": round(walk.geographic_xgb_rmse_log, 4),
         "ΔRMSE vs reference": round(baseline.geographic_xgb_rmse_log-walk.geographic_xgb_rmse_log, 5),
         "Interpretation": f"Improves {better}/{len(paired)} districts; Copenhagen-only context baseline"},
        {"Analysis": "Study-boundary destinations", "Status": "Pre-freeze endpoint sensitivity", "N": int(bound_walk.n),
         "Validation": "geographic_11", "Comparison": "MW_BOUND versus M0_BOUND",
         "RMSE": round(bound_walk.rmse_log, 4),
         "ΔRMSE vs reference": round(bound_base.rmse_log-bound_walk.rmse_log, 5),
         "Interpretation": "Study-union endpoint restriction does not materially change the primary access conclusion; walking graph unchanged"},
    ]
    robust = pd.concat([robust, pd.DataFrame(additions)], ignore_index=True)
    robust.loc[robust.Analysis == "Area context (mixed resolution)", "Status"] = "Post-Phase-9 planned context"
    robust.loc[robust.Analysis == "Area context (mixed resolution)", "Interpretation"] = "Core RQ2 adjusted comparison; mixed-resolution context provisional"
    table("table8_robustness_summary", _rows(robust),
          "Selected Phase 10 and later checks for the Copenhagen–Frederiksberg urban core; geographic XGBoost walking comparisons shown where predictive metrics apply. Area context is a planned contextual specification implemented after Phase 9 and evaluated as a core RQ2 comparison in the separate panel, not merely a generic robustness exercise. For 15-/20-minute rows, ΔRMSE is versus the matching no-access baseline, NOT Euclidean access. Fixed-effects/spatial-error analyses are association-only with no comparable predictive RMSE. Samples, feature definitions and estimands differ. The Phase 9 base specification remains frozen; study-union endpoints are sensitivity only.")

    table("table_validation_designs", validation_design_rows(),
          "Methods comparison of saved validation assignments for the Copenhagen–Frederiksberg urban core. There are 11 analysis areas: ten official Copenhagen city districts and Frederiksberg. Random folds are spatially interspersed; 1.5 km blocks remain whole and are grouped into five folds; buffered leave-one-area-out retains the same eleven test areas and removes nearby training listings. Distances use EPSG:25832. No assignments were regenerated or models fitted.")


def revise_figures() -> None:
    workflow_figure()
    context_figure(pd.read_csv(ROOT / "outputs/tables/context_comparison.csv").to_dict("records"))
    _validation_performance_figure()
    source_dir = FIGURES / "_revision_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    font_path = findfont(FontProperties(family="DejaVu Sans"))

    def source(name: str) -> Path:
        original = source_dir / name
        if not original.exists():
            shutil.copyfile(FIGURES / name, original)
        return original

    # Add the saved district-boundary symbol to the existing map key. The map
    # itself is an already-aggregated, privacy-safe raster and is not recomputed.
    map_image = Image.open(source("figure2_study_area.png")).convert("RGB")
    draw = ImageDraw.Draw(map_image)
    draw.rectangle((1048, 341, 1394, 386), fill="white", outline="#D4D4D4", width=2)
    draw.line((1060, 364, 1104, 364), fill="#8198A4", width=2)
    draw.text((1118, 347), "Copenhagen district lines", fill="#111111",
              font=ImageFont.truetype(font_path, 20))
    map_image.save(FIGURES / "figure2_study_area.png", dpi=(200, 200))

    meta = json.loads((TABLES / "catchment_example_metadata.json").read_text())
    example = Image.open(source("figure4_catchment_example.png")).convert("RGB")
    draw = ImageDraw.Draw(example)
    label = (f"B · 10-minute walking-network reach "
             f"({meta['walk_reachable_pois']} of {meta['candidate_pois_in_circle']} POIs reachable)")
    draw.rectangle((1034, 105, example.width-15, 164), fill="white")
    font = ImageFont.truetype(font_path, 27)
    if draw.textbbox((0, 0), label, font=font)[2] > example.width-1049:
        font = ImageFont.truetype(font_path, 24)
    draw.text((1038, 121), label, fill="#25455A", font=font)
    example.save(FIGURES / "figure4_catchment_example.png", dpi=(200, 200))

    # Terminology-only correction on the saved aggregate block map; geometry,
    # fold colours and the no-listing neutral block remain untouched.
    blocks = Image.open(source("appendix_geometric_block_cv.png")).convert("RGB")
    draw = ImageDraw.Draw(blocks)
    draw.rectangle((105, 130, 1190, 210), fill="white")
    draw.text((110, 151),
              "Copenhagen–Frederiksberg urban core · five outcome-blind folds · EPSG:25832",
              fill="#667F89", font=ImageFont.truetype(font_path, 25))
    blocks.save(FIGURES / "appendix_geometric_block_cv.png", dpi=(190, 190))


def _validation_performance_figure() -> None:
    """Redraw only the final chart, using frozen aggregate Phase 9 metrics."""
    source = pd.read_csv(ROOT / "outputs/tables/phase09/model_performance.csv")
    subset = source[(source.model == "XGBoost") & (source.feature_set.isin(["M0", "ME", "MW"]))]
    if len(subset) != 6 or subset.n.nunique() != 1:
        raise RuntimeError("Saved XGBoost performance comparison is incomplete")
    blocks = ("M0", "ME", "MW")
    x = np.arange(len(blocks))
    fig, ax = plt.subplots(figsize=(10.3, 5.7), dpi=190)
    for offset, scheme, label, color in (
        (-.18, "random_5", "Random 5-fold", "#C9D9E7"),
        (.18, "geographic_11", "Leave-one-area-out (11 analysis areas)", "#91BFB2"),
    ):
        values = subset.loc[subset.cv_scheme == scheme].set_index("feature_set")
        bars = ax.bar(x + offset, [values.loc[b, "rmse_log"] for b in blocks],
                      width=.35, color=color, edgecolor="#587181", linewidth=.8, label=label)
        for bar in bars:
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+.003,
                    f"{bar.get_height():.3f}", ha="center", va="bottom", fontsize=9, color="#25455A")
    ax.set_xticks(x, ("M0 baseline", "ME Euclidean", "MW walking"))
    ax.set_ylim(0, .395)
    ax.set_ylabel("Pooled out-of-fold RMSE · ln(listed price)")
    ax.set_title("Frozen primary XGBoost comparison", loc="left", color="#25455A", pad=12)
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    ax.grid(axis="y", color="#E8EFED", linewidth=.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(.5, .01,
             "Random folds are spatially interspersed; unseen-area transfer also changes predictor support. The gap alone is not proof of spatial leakage.",
             ha="center", fontsize=8, color="#25455A")
    fig.subplots_adjust(bottom=.16, left=.11, right=.96, top=.91)
    fig.savefig(FIGURES / "figure7_validation_performance.png", dpi=190, bbox_inches="tight")
    plt.close(fig)


def write_figure_captions() -> None:
    meta = json.loads((TABLES / "catchment_example_metadata.json").read_text())
    boundary_meta_path = TABLES / "appendix_boundary_catchment_metadata.json"
    boundary_meta = json.loads(boundary_meta_path.read_text()) if boundary_meta_path.is_file() else None
    summary = pd.read_csv(TABLES / "table6_predictive_performance.csv")
    sample_n = int(summary.N.iloc[0])
    if summary.N.nunique() != 1:
        raise RuntimeError("Final common-sample N is not constant in Table 6")
    captions = [
        "# Final thesis figure captions",
        "",
        "Copenhagen–Frederiksberg urban core means Copenhagen Municipality plus Frederiksberg Municipality. The shorter ‘Copenhagen study area’ refers to this same joint region. These are caption drafts for later LaTeX export, not new analysis.",
        "",
        "## Main text",
        "",
        "1. **Workflow.** The Phase 9 base specification uses Inside Airbnb, OpenStreetMap and official geography. The planned area-context-adjusted core specification was implemented after Phase 9, when source comparability had been audited; it was never an unreported frozen M0 input.",
        "2. **Study area and listing density.** The Copenhagen–Frederiksberg urban core comprises two municipalities. Thin internal lines mark the ten official Copenhagen city districts; Frederiksberg is a separate municipality and one of the 11 analysis areas. Density uses privacy-safe 500 m squares from the eligible common sample, suppressing cells with fewer than five listings. Symbols show eligible rail/metro/S-train stations and the City Hall reference, not individual Airbnb points. EPSG:25832.",
        "3. **Price distribution and spatial pattern.** Frozen common sample; the raw-price histogram's upper-tail display cutoff is visual only, and the mapped 500 m median-price cells suppress groups with fewer than five listings.",
        f"4. **Euclidean versus walking-network catchment.** The illustrative public network-node origin is not an Airbnb listing. Panel A contains {meta['candidate_pois_in_circle']} canonical POIs inside 800 m straight-line; panel B shows {meta['walk_reachable_pois']} of those {meta['candidate_pois_in_circle']} POIs reachable within ten walking-network minutes at 4.8 km/h, including destination snap connectors. The network is not clipped to district or municipal boundaries. EPSG:{meta['crs_epsg']}.",
        f"5. **Matched accessibility representations.** The same {sample_n:,}-listing Phase 9 common sample and canonical destinations are used for all displayed pairs. Axes show ln(1+x) of final-sample counts or nearest-station metres; panel correlations are descriptive, not earlier phase-specific correlations. Hexagons with fewer than five listings are hidden.",
        "6. **Walking-accessibility associations.** Frozen Phase 9 base-specification semilog OLS MW coefficients are conditional associations, not causal effects. HC3 intervals address heteroskedasticity but not residual spatial dependence. The later area-context-adjusted core specification substantially attenuates several focal associations; those estimates are reported separately for RQ2.",
        "7. **Random versus geographic prediction.** Saved Phase 9 XGBoost pooled out-of-fold RMSE under Random 5-fold and Leave-one-area-out (11 analysis areas). Every analysis area is test data once. The geographically separated test also changes predictor support and area composition; its error gap relative to random CV does not prove spatial leakage alone. Small ME/MW differences are not established winners.",
        "8. **Leave-one-area-out geography.** The 11 analysis areas are ten official Copenhagen city districts plus Frederiksberg (administratively a municipality, not a Copenhagen district). Each whole area is held out once; no single district was selected as the test district. Colour is XGBoost MW out-of-area log-price RMSE when that entire area is held out, not price. Different test N and predictor support matter. EPSG:25832.",
        "9. **Core RQ2 comparison: accessibility after area socioeconomic context.** Blue-grey bars show the frozen Phase 9 base specification; green bars show the area-context-adjusted core specification, conceptually planned but implemented after Phase 9. Each bar is the reduction in leave-one-area-out log-price RMSE from adding the named accessibility block to its matching no-access M0; positive means lower error. Context adds log gross-polygon population density and disposable income, with mixed Copenhagen district/Frederiksberg municipality resolution, unverified boundary/area vintage, and cross-source income-definition caveats. These were not frozen Phase 9 controls.",
        "",
        "## Methods and appendix",
        "",
        "- **Validation-design schematic (Methods).** Random five-fold assignment is interspersed; 1.5 km geometric blocks keep whole cells together across five saved folds; leave-one-area-out holds one complete official analysis area at a time. Buffered variants remove training listings near, but do not change, each held-out area. Schematic symbols are not Airbnb coordinates.",
        "- **Actual 1.5 km geometric-block map (Appendix).** Colours are the saved five outcome-blind fold assignments. All listings within one block stay in the same fold. Multiple blocks belong to each fold; blocks themselves are not folds. One saved block with no common-sample listing is neutral; no Airbnb point locations are displayed. EPSG:25832.",
        "- **Residual Moran diagnostic (Appendix).** Frozen Phase 9 out-of-fold residual spatial-autocorrelation diagnostic; retained as evidence that HC3 intervals alone do not resolve spatial dependence.",
    ]
    if boundary_meta:
        captions.append(
            f"- **Destination-boundary catchment (Appendix).** The same public Phase 6 OSM-node origin beside Hellerup station and the same 800 m straight-line circle appear in both panels. The buffered primary universe includes {boundary_meta['poi_within_circle']} canonical POIs, of which {boundary_meta['poi_excluded_outside_union']} are outside Copenhagen–Frederiksberg; the union-endpoint sensitivity retains {boundary_meta['poi_retained_inside_union']}. Grey crosses show outside endpoints for comparison but are not counted in the sensitivity. The official outer municipal-union line is an endpoint filter, not a barrier to walking: no route is shown or clipped. The example is illustrative, contains no Airbnb point, and is not a model-performance result. EPSG:{boundary_meta['crs_epsg']}."
        )
    else:
        captions.append("- **Boundary sensitivity.** Aggregate endpoint/feature-change and matched-model tables remain the evidence; any later public-OSM illustration must keep the walking graph unclipped and must not replace Figure 4.")
    (ROOT / "docs/final_figure_captions.md").write_text("\n".join(captions)+"\n", encoding="utf-8")


def run() -> None:
    for required in ("reports/pre_freeze_boundary_sensitivity.md",
                     "reports/pre_freeze_validation_visualisation.md"):
        if not (ROOT / required).is_file():
            raise FileNotFoundError(f"Required pre-freeze report missing: {required}")
    revise_tables()
    export_rq2_context_panel()
    revise_figures()
    write_figure_captions()
    rows, inventory = make_manifest(json.loads((TABLES / "catchment_example_metadata.json").read_text()))
    if any(row[2] == "MISSING" for row in rows):
        raise RuntimeError("A planned final output is missing")
    print(f"Presentation revision complete: {len(rows)} main items; {len(inventory)} files classified; no model or DB access")


if __name__ == "__main__":
    run()

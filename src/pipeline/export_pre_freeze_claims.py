"""Synthesize final claims from saved aggregates; never fit or modify models.

Qualitative statuses are explicit scientific judgements. The numeric evidence is
read from existing machine-readable outputs each time this script is run.
"""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "outputs/tables"
FIGURES = ROOT / "outputs/figures"
DEST = TABLES / "conclusion_stability.csv"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def one(data: list[dict[str, str]], **conditions: str) -> dict[str, str]:
    matches = [row for row in data if all(row.get(key) == value for key, value in conditions.items())]
    if len(matches) != 1:
        raise ValueError(f"Expected one saved row for {conditions}; found {len(matches)}")
    return matches[0]


def f(value: str, digits: int = 5) -> str:
    return f"{float(value):+.{digits}f}"


def verify_outputs() -> None:
    """Fail closed if a claimed manuscript source is missing."""
    required = [
        *(TABLES / "final" / f"table{i}_{suffix}.csv" for i, suffix in [
            (1, "sample_construction"), (2, "variable_specification"),
            (3, "descriptive_statistics"), (4, "accessibility_definitions"),
            (5, "hedonic_ladder"), (6, "predictive_performance"),
            (7, "incremental_accessibility"), (8, "robustness_summary"),
        ]),
        TABLES / "final/table_validation_designs.csv",
        TABLES / "final/table_validation_performance.csv",
        TABLES / "final/table_rq2_area_context.csv",
        TABLES / "final/table_rq2_area_context.md",
        *(FIGURES / "final" / f"figure{i}_{suffix}.png" for i, suffix in [
            (1, "workflow"), (2, "study_area"), (3, "price_pattern"),
            (4, "catchment_example"), (5, "matched_accessibility"),
            (6, "accessibility_coefficients"), (7, "validation_performance"),
            (8, "cv_geography"),
        ]),
        FIGURES / "final/figure9_residual_diagnostics.png",
        FIGURES / "final/figure_validation_designs.png",
        FIGURES / "final/appendix_geometric_block_cv.png",
        FIGURES / "context_incremental_accessibility.png",
        ROOT / "outputs/latex/main_tables.tex",
        ROOT / "outputs/latex/appendix_tables.tex",
        ROOT / "outputs/latex/table_preamble.tex",
        ROOT / "outputs/latex/table_test_document.tex",
        *(ROOT / "outputs/latex/tables" / f"table{i}_{suffix}.tex" for i, suffix in [
            (1, "sample_construction"), (2, "variable_specification"),
            (3, "descriptive_statistics"), (4, "accessibility_definitions"),
            (5, "hedonic_ladder"), (6, "predictive_performance"),
            (7, "incremental_accessibility"), (8, "robustness_summary"),
        ]),
        ROOT / "outputs/latex/tables/table_validation_designs.tex",
        ROOT / "outputs/latex/tables/table_rq2_area_context.tex",
        *(ROOT / "outputs/latex/appendix" / f"{stem}.tex" for stem in [
            "table5_full_coefficients", "table7_incremental_accessibility_full",
            "context_comparison", "copenhagen_only_context",
            "price_observability_comparison", "boundary_definition_sensitivity",
            "geographic_fold_performance", "block_buffer_validation_summary",
        ]),
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError("Missing/empty final outputs: " + ", ".join(missing))


def build() -> list[dict[str, str]]:
    verify_outputs()
    representation = read(TABLES / "phase10/accessibility_representation.csv")
    primary = read(TABLES / "phase09/model_performance.csv")
    context = read(TABLES / "context_comparison.csv")
    copenhagen = read(TABLES / "copenhagen_only_context_sensitivity.csv")
    observability = read(TABLES / "price_observability_comparison.csv")
    boundary = read(TABLES / "boundary_sensitivity_comparison.csv")
    designs = read(TABLES / "final/table_validation_performance.csv")
    folds = [row for row in read(TABLES / "phase09/fold_performance.csv")
             if row["cv_scheme"] == "geographic_11" and row["model"] == "XGBoost" and row["feature_set"] == "MW"]
    if len(folds) != 11 or len({row["fold"] for row in folds}) != 11 or sum(int(row["n"]) for row in folds) != 12412:
        raise ValueError("Saved Phase 9 LOAO folds do not cover the common sample exactly once")
    p = lambda scheme, block: one(primary, cv_scheme=scheme, model="XGBoost", feature_set=block)
    c = lambda block: one(context, cv_scheme="geographic_11", model="XGBoost", accessibility=block)
    o = lambda block: one(observability, validation="geographic_11", model="XGBoost", feature_set=block)
    b = lambda: one(boundary, validation="geographic_11", estimator="XGBoost", metric="RMSE")
    v = lambda scheme: one(designs, **{"Validation scheme": scheme})
    food = one(representation, category="food_social", walking_minutes="10")
    culture = one(representation, category="cultural_tourist", walking_minutes="10")
    cp = one(copenhagen, feature_set="MW_CTX")
    rows = [
        ("C1", "Euclidean and walking accessibility are empirically different", "SUPPORTED",
         f"At 800 m/10 min, matched food and cultural counts differ for {float(food['different_share'])*100:.1f}% and {float(culture['different_share'])*100:.1f}% of listings, respectively; this does not establish predictive superiority.",
         "outputs/tables/phase10/accessibility_representation.csv"),
        ("C2", "Accessibility modestly improves the original baseline", "SUPPORTED",
         f"Frozen geographic XGBoost M0-to-ME/MW RMSE reductions are {f(c('ME')['delta_rmse_phase9'])} and {f(c('MW')['delta_rmse_phase9'])} log-price units; buffered checks qualify transfer stability.",
         "outputs/tables/phase09/model_performance.csv; outputs/tables/context_comparison.csv; outputs/tables/final/table_validation_performance.csv"),
        ("C3", "Walking-network accessibility meaningfully outperforms Euclidean accessibility", "NOT SUPPORTED",
         f"Frozen geographic XGBoost MW RMSE {float(p('geographic_11','MW')['rmse_log']):.5f} exceeds ME {float(p('geographic_11','ME')['rmse_log']):.5f}; threshold and boundary sensitivities do not establish a stable walking advantage.",
         "outputs/tables/phase09/model_performance.csv; outputs/tables/phase10/model_performance.csv; outputs/tables/boundary_sensitivity_comparison.csv"),
        ("C4", "Accessibility adds stable information beyond area socioeconomic context", "NOT SUPPORTED",
         f"On the identical mixed-area sample, geographic XGBoost context-adjusted ME/MW gains are {f(c('ME')['delta_rmse_ctx'])}/{f(c('MW')['delta_rmse_ctx'])}; Copenhagen-only MW_CTX gains only {f(cp['xgb_delta_rmse_vs_m0_ctx'])} and improves five of ten districts.",
         "outputs/tables/context_comparison.csv; outputs/tables/copenhagen_only_context_sensitivity.csv; reports/postcompletion_02_context_models.md"),
        ("C5", "Geographic validation produces different/higher error than random validation", "SUPPORTED",
         f"Frozen XGBoost MW RMSE is {float(p('random_5','MW')['rmse_log']):.5f} random versus {float(p('geographic_11','MW')['rmse_log']):.5f} LOAO; 1.5-km blocks {float(v('1.5 km block 5-fold')['XGBoost MW RMSE(log price)']):.5f}, buffered LOAO 500/1000 m {float(v('Buffered LOAO 500 m')['XGBoost MW RMSE(log price)']):.5f}/{float(v('Buffered LOAO 1000 m')['XGBoost MW RMSE(log price)']):.5f}; separation also changes training support.",
         "outputs/tables/final/table_validation_performance.csv; reports/pre_freeze_validation_visualisation.md"),
        ("C6", "Main Phase 9 patterns survive high-price-observability sample restriction", "SUPPORTED",
         f"The restricted sample retains {int(o('MW')['n_high_completeness']):,} listings and geographic XGBoost ME/MW gains of {f(o('ME')['delta_access_high_completeness'])}/{f(o('MW')['delta_access_high_completeness'])}; missing-price selection still limits generalisation.",
         "outputs/tables/price_observability_comparison.csv; reports/postcompletion_03_price_observability.md"),
        ("C7", "Main findings are robust to study-boundary destination definition", "SUPPORTED",
         f"Restricting only endpoints to the study union changes geographic XGBoost ME/MW gains from {f(b()['primary_Delta_ME'])}/{f(b()['primary_Delta_MW'])} to {f(b()['boundary_Delta_ME'])}/{f(b()['boundary_Delta_MW'])}; the ordering does not reverse.",
         "outputs/tables/boundary_sensitivity_comparison.csv; reports/pre_freeze_boundary_sensitivity.md"),
    ]
    return [dict(claim_id=claim_id, claim=claim, status=status, evidence=evidence, source_paths=source)
            for claim_id, claim, status, evidence, source in rows]


def main() -> None:
    claims = build()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["claim_id", "claim", "status", "evidence", "source_paths"])
        writer.writeheader()
        writer.writerows(claims)
    print(f"Wrote {len(claims)} audited claims to {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

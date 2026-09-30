"""Export frozen thesis CSV tables to manuscript LaTeX; never fit models.

Run from any working directory: python -m src.pipeline.export_final_latex_tables
All numbers are read from the listed CSV inputs. Formatting changes display
precision only; the source files are never written.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "outputs/tables/final"
OUT = ROOT / "outputs/latex"
TABLES = OUT / "tables"
APP = OUT / "appendix"
DASH = r"\textemdash{}"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def tex(value: object) -> str:
    """Escape source text, including Unicode symbols used in exported labels."""
    if value is None or str(value).strip() in {"", "—", "–"}:
        return DASH
    special = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
        "_": r"\_\allowbreak{}", "%": r"\%", "&": r"\&", "#": r"\#",
        "$": r"\$", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}",
        "—": DASH, "–": "--", "²": r"\textsuperscript{2}",
        "³": r"\textsuperscript{3}", "×": r"$\times$", "†": r"\textdagger{}",
        "Δ": r"$\Delta$", "≥": r"$\geq$", "≤": r"$\leq$",
        "↔": r"$\leftrightarrow$", "≈": r"$\approx$", "−": "-",
    }
    return "".join(special.get(char, char) for char in str(value))


def num(value: object, digits: int = 4, *, count: bool = False) -> str:
    if value is None or str(value).strip() in {"", "—", "–", "nan", "None"}:
        return DASH
    number = float(value)
    if count:
        return f"{int(number):,}"
    if abs(number) < 0.5 * 10 ** -digits:
        number = 0.0
    return f"{number:,.{digits}f}"


def line(values: list[str]) -> str:
    return " & ".join(values) + r" \\" + "\n"


def ragged(colspec: str) -> str:
    return colspec.replace("p{", r">{\raggedright\arraybackslash}p{")


def table(
    caption: str, label: str, headers: list[str], body: list[str],
    colspec: str, note: str, *, landscape: bool = False, size: str = r"\small",
    tabcolsep: int | None = None, arraystretch: float | None = None,
) -> str:
    begin = "\\begin{landscape}\n" if landscape else ""
    end = "\\end{landscape}\n" if landscape else ""
    return (
        begin + "\\begin{table}[p]\n\\centering\n" + size + "\n"
        + (f"\\setlength{{\\tabcolsep}}{{{tabcolsep}pt}}\n" if tabcolsep is not None else "")
        + (f"\\renewcommand{{\\arraystretch}}{{{arraystretch}}}\n" if arraystretch is not None else "")
        + "\\begin{threeparttable}\n"
        + f"\\caption{{{caption}}}\\label{{{label}}}\n"
        + f"\\begin{{tabular}}{{{ragged(colspec)}}}\n\\toprule\n"
        + line(headers) + "\\midrule\n" + "".join(body)
        + "\\bottomrule\n\\end{tabular}\n"
        + "\\begin{tablenotes}[flushleft]\\footnotesize\n"
        + f"\\item {note}\n\\end{{tablenotes}}\n"
        + "\\end{threeparttable}\n\\end{table}\n" + end
    )


def longtable(
    caption: str, label: str, headers: list[str], body: list[str],
    colspec: str, note: str, *, landscape: bool = True,
) -> str:
    begin = "\\begin{landscape}\n" if landscape else ""
    end = "\\end{landscape}\n" if landscape else ""
    head = "\\toprule\n" + line(headers) + "\\midrule\n"
    return (
        begin + "\\small\n" + f"\\begin{{longtable}}{{{ragged(colspec)}}}\n"
        + f"\\caption{{{caption}}}\\label{{{label}}}\\\\\n"
        + head + "\\endfirsthead\n" + head + "\\endhead\n"
        + "".join(body) + "\\bottomrule\n\\end{longtable}\n"
        + f"{{\\footnotesize\\noindent\\emph{{Notes.}} {note}\\par}}\n" + end
    )


def save(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def simple_body(data: list[dict[str, str]], keys: list[str], formats: dict[str, tuple[int, bool]] | None = None) -> list[str]:
    formats = formats or {}
    return [line([num(row[k], *formats[k][:1], count=formats[k][1]) if k in formats else tex(row[k]) for k in keys]) for row in data]


def export_main() -> dict[str, Path]:
    sources: dict[str, Path] = {}

    def output(name: str, source: Path, content: str) -> None:
        save(TABLES / name, content)
        sources[f"tables/{name}"] = source

    data = rows(FINAL / "table1_sample_construction.csv")
    output("table1_sample_construction.tex", FINAL / "table1_sample_construction.csv",
           table("Sample construction", "tab:sample-construction",
                 ["Filter step", "$N$ remaining", "$N$ removed", "Retained (\\%)"],
                 [line([tex(r["Filter step"]), num(r["N remaining"], count=True),
                        num(r["N removed"], count=True), num(r["% retained from previous"], 1)]) for r in data],
                 "p{8cm}rrr", "Sequential inclusion rules; percentage retained is relative to the preceding stage. Listed price is not imputed."))

    data = rows(FINAL / "table2_variable_specification.csv")
    body = [line([tex(r["Concept"]), tex(r["Variable"]), tex(r["Definition"]),
                  tex(r["Transformation/unit"]), tex(r["Source"]),
                  tex(r["Model block"] + "; " + r["Primary/robustness"]),
                  tex(r["Missing-data treatment"])]) for r in data]
    output("table2_variable_specification.tex", FINAL / "table2_variable_specification.csv",
           longtable("Variable specification and model roles", "tab:variables",
                     ["Concept", "Variable", "Definition", "Unit / transform", "Source", "Role", "Missing-data rule"],
                     body, "p{2.5cm}p{3.0cm}p{5.0cm}p{2.7cm}p{2.5cm}p{3.1cm}p{3.7cm}",
                     "M0, ME, MW, and MEW are the frozen Phase 9 base blocks. CTX is the area-context-adjusted core specification, conceptually planned but implemented after Phase 9 because source comparability was unresolved at the Phase 7 freeze. Copenhagen district and Frederiksberg municipality context have different resolutions. Source price is treated as DKK; its string lacks a currency code. Outcome values are never imputed."))

    data = rows(FINAL / "table3_descriptive_statistics.csv")
    continuous = [r for r in data if r["Mean"]]
    categorical = [r for r in data if not r["Mean"]]
    a = [line([tex(r["Variable"]), tex(r["Unit"]), num(r["N"], count=True)]
              + [num(r[k], 2 if r["Unit"] == "DKK" else 3) for k in ("Mean", "SD", "Median", "p25", "p75", "Min", "Max")]) for r in continuous]
    b = [line([tex(r["Variable"]), num(r["N"], count=True), num(r["Percentage"], 2)]) for r in categorical]
    content = (
        "\\begin{landscape}\n\\begin{table}[p]\\centering\\footnotesize\n"
        "\\setlength{\\tabcolsep}{4pt}\\renewcommand{\\arraystretch}{0.9}\n"
        "\\begin{threeparttable}\n"
        "\\caption{Descriptive statistics and sample composition}\\label{tab:descriptives}\n"
        "\\textit{Panel A. Continuous variables}\\par\\smallskip\n"
        "\\begin{tabular}{>{\\raggedright\\arraybackslash}p{5.5cm}>{\\raggedright\\arraybackslash}p{3.2cm}rrrrrrrr}\n\\toprule\n"
        + line(["Variable", "Unit", "$N$", "Mean", "SD", "Median", "P25", "P75", "Min", "Max"])
        + "\\midrule\n" + "".join(a) + "\\bottomrule\n\\end{tabular}\n\\medskip\n"
        + "\\textit{Panel B. Categorical composition}\\par\\smallskip\n"
        + "\\begin{tabular*}{\\linewidth}{@{\\extracolsep{\\fill}}lrr}\n\\toprule\n"
        + line(["Category", "$N$", "Percent (\\%)"]) + "\\midrule\n"
        + "".join(b) + "\\bottomrule\n\\end{tabular*}\n"
        + "\\begin{tablenotes}[flushleft]\\footnotesize\n"
        + "\\item Common frozen Phase 9 sample; continuous rows report observed $N$ and sample SD. Categorical percentages use the common sample denominator. Area density and income enter the later area-context-adjusted core specification, not frozen Phase 9 M0: ten Copenhagen district values and one Frederiksberg municipality value are repeated at listing level. Income definitions differ by source.\n"
        + "\\end{tablenotes}\\end{threeparttable}\\end{table}\\end{landscape}\n"
    )
    output("table3_descriptive_statistics.tex", FINAL / "table3_descriptive_statistics.csv", content)

    data = rows(FINAL / "table4_accessibility_definitions.csv")
    body = simple_body(data, ["Concept", "Euclidean definition", "Network definition", "Primary threshold/unit", "Sensitivity", "Destination source"])
    # tabularx keeps the full scientific definitions readable without scaled text.
    content = (
        "\\begin{landscape}\n\\begin{table}[p]\\centering\\small\n\\begin{threeparttable}\n"
        "\\caption{Matched Euclidean and walking-network accessibility measures}\\label{tab:accessibility-definitions}\n"
        "\\begin{tabularx}{\\linewidth}{>{\\raggedright\\arraybackslash}p{2.8cm}XX>{\\raggedright\\arraybackslash}p{2.7cm}>{\\raggedright\\arraybackslash}p{3.0cm}>{\\raggedright\\arraybackslash}p{3.4cm}}\n\\toprule\n"
        + line(["Concept", "Euclidean definition", "Network definition", "Primary unit", "Sensitivity", "Destination source"])
        + "\\midrule\n" + "".join(body) + "\\bottomrule\n\\end{tabularx}\n"
        + "\\begin{tablenotes}[flushleft]\\footnotesize\n"
        + "\\item Matched measures use the same canonical deduplicated destinations. Walking speed is 4.8 km/h: 800 m network travel is 10 minutes, versus an 800 m straight-line radius. Distances use EPSG:25832. Primary destinations may fall within the buffered extraction area beyond the Copenhagen--Frederiksberg boundary; district and municipality borders do not block access. A separate sensitivity restricts endpoints to the municipal union. Bus proximity is robustness only.\n"
        + "\\end{tablenotes}\\end{threeparttable}\\end{table}\\end{landscape}\n"
    )
    output("table4_accessibility_definitions.tex", FINAL / "table4_accessibility_definitions.csv", content)

    data = rows(FINAL / "table5_hedonic_ladder.csv")
    pattern = re.compile(r"^([+-]?\d+\.\d+) \(([+-]?\d+\.\d+)\); \[([+-]?\d+\.\d+), ([+-]?\d+\.\d+)\]$")
    body = []
    for r in data:
        cells = []
        for model in ("M0", "ME", "MW", "MEW"):
            raw = r[model]
            match = pattern.match(raw)
            if match:
                beta, se, low, high = (num(x, 4) for x in match.groups())
                cells.append(rf"\shortstack{{$ {beta} $\\$({se})$\\$[{low},\,{high}]$}}")
            elif r["Focal term (unit)"] == "N":
                cells.append(num(raw, count=True))
            elif r["Focal term (unit)"] in {"Adjusted R²"}:
                cells.append(num(raw, 3))
            elif r["Focal term (unit)"] in {"AIC", "BIC"}:
                cells.append(num(raw, 1))
            else:
                cells.append(tex(raw))
        body.append(line([tex(r["Focal term (unit)"])] + cells))
    output("table5_hedonic_ladder.tex", FINAL / "table5_hedonic_ladder.csv",
           table("Semi-log OLS hedonic model ladder", "tab:hedonic-ladder",
                 ["Focal term / statistic", "M0", "ME", "MW", "MEW"], body,
                 "p{5.7cm}cccc", "Cells show coefficient, HC3 robust SE in parentheses, and 95\\% confidence interval in brackets. Associations are not causal effects. MEW jointly includes correlated Euclidean and walking measures, so its individual coefficients are collinearity-sensitive. Area-context-adjusted core results are reported in the RQ2 table; spatial-error robustness is separate.", tabcolsep=3, arraystretch=1.12))

    data = rows(FINAL / "table6_predictive_performance.csv")
    body = []
    prev = None
    for r in data:
        if prev and r["Validation"] != prev:
            body.append("\\addlinespace[0.4em]\n")
        body.append(line([tex(r["Validation"]), tex(r["Estimator"]), tex(r["Block"]),
                          num(r["N"], count=True), num(r["RMSE (ln price)"], 4),
                          num(r["MAE (ln price)"], 4), num(r["R² (OOF)"], 3)]))
        prev = r["Validation"]
    output("table6_predictive_performance.tex", FINAL / "table6_predictive_performance.csv",
           table("Out-of-fold predictive performance", "tab:predictive-performance",
                 ["Validation", "Estimator", "Block", "$N$", "RMSE", "MAE", "$R^2$"],
                 body, "p{4.2cm}p{2.3cm}crrrr",
                 "Frozen Phase 9 pooled outer out-of-fold metrics on the common sample. RMSE and MAE use log nightly price; lower is better. Random folds are spatially interspersed. Leave-one-area-out (LOAO) holds out each of ten Copenhagen districts and Frederiksberg once. Small differences do not establish a statistically significant ranking; MEW is exploratory.", landscape=True))

    data = rows(FINAL / "table7_incremental_accessibility.csv")
    assert not any(r["Comparison"] == "MW versus ME" for r in data)
    body = [line([tex(r["Validation"]), tex(r["Estimator"]), tex(r["Comparison"]),
                  num(r["Delta RMSE reduction"], 5), num(r["Delta MAE reduction"], 5)]) for r in data]
    output("table7_incremental_accessibility.tex", FINAL / "table7_incremental_accessibility.csv",
           table("Incremental accessibility information", "tab:incremental-accessibility",
                 ["Validation", "Estimator", "Comparison", "$\\Delta$ RMSE", "$\\Delta$ MAE"],
                 body, "p{4cm}p{2.4cm}p{3.5cm}rr",
                 "Positive $\\Delta$ means error reduction versus the named reference model on the same validation assignment. ME adds Euclidean measures; MW adds walking-network measures; MEW includes both. These are descriptive predictive differences, not causal effects."))

    path = FINAL / "table_rq2_area_context.csv"
    data = rows(path)
    body = [line([tex(r["Estimator"]), tex(r["Specification"]), num(r["N"], count=True),
                  num(r["M0 RMSE"], 5), num(r["ME RMSE"], 5), num(r["MW RMSE"], 5),
                  num(r["ME gain"], 5), num(r["MW gain"], 5)]) for r in data]
    output("table_rq2_area_context.tex", path,
           table("RQ2: accessibility before and after area socioeconomic context", "tab:rq2-area-context",
                 ["Estimator", "Specification", "$N$", "M0 RMSE", "ME RMSE", "MW RMSE", "ME gain", "MW gain"],
                 body, "p{2.0cm}p{6.0cm}rrrrrr",
                 "Pooled leave-one-area-out log-price RMSE on the same listings and saved folds. Base = Phase 9 listing, host/rental, municipality and City Hall centrality controls. Area-context-adjusted core = base plus log gross-polygon population density and disposable income; this planned contextual specification was implemented after Phase 9, not frozen at Phase 7. Positive gain means lower error than the matching M0. Mixed Copenhagen district/Frederiksberg municipality context, income definitions and polygon areas remain provisional.",
                 landscape=True))

    data = rows(FINAL / "table8_robustness_summary.csv")
    body = [line([tex(r["Analysis"]), tex(r["Status"]), num(r["N"], count=True),
                  tex(r["Validation"]), tex(r["Comparison"]), num(r["RMSE"], 4),
                  num(r["ΔRMSE vs reference"], 5), tex(r["Interpretation"])]) for r in data]
    output("table8_robustness_summary.tex", FINAL / "table8_robustness_summary.csv",
           longtable("Robustness and post-completion checks", "tab:robustness",
                     ["Analysis", "Status", "$N$", "Validation", "Comparison", "RMSE", "$\\Delta$ RMSE", "Interpretation"],
                     body, "p{3.0cm}p{2.9cm}rp{2.7cm}p{3.1cm}rrp{6.7cm}",
                     "Statuses preserve implementation chronology, not scientific importance. Area-context-adjusted models are a core RQ2 comparison shown in the separate RQ2 table, not merely a generic robustness exercise. Predictive RMSE across different samples/schemes is not directly paired. Association-only models have no comparable predictive RMSE (em dash). Positive $\\Delta$ denotes lower error than the stated reference."))

    data = rows(FINAL / "table_validation_designs.csv")
    body = simple_body(data, ["Validation scheme", "Grouping unit", "Number of folds/groups", "Spatial separation principle", "Prediction question", "Role in thesis"])
    output("table_validation_designs.tex", FINAL / "table_validation_designs.csv",
           longtable("Validation schemes and prediction questions", "tab:validation-designs",
                     ["Validation scheme", "Grouping unit", "Folds / groups", "Separation", "Prediction question", "Thesis role"],
                     body, "p{3.3cm}p{3.4cm}p{2.9cm}p{4.3cm}p{4.7cm}p{4.3cm}",
                     "Assignments are saved, not regenerated. There are 11 official held-out analysis areas (ten Copenhagen districts plus Frederiksberg). All listings in one 1.5 km spatial block share a fold; multiple blocks make up a fold. Buffered LOAO retains the same test areas and removes nearby training listings. Spatial distances use EPSG:25832."))
    return sources


def export_appendix() -> dict[str, Path]:
    sources: dict[str, Path] = {}

    def output(name: str, source: Path | tuple[Path, ...], content: str) -> None:
        save(APP / name, content)
        sources[f"appendix/{name}"] = source if isinstance(source, Path) else Path("; ".join(str(p.relative_to(ROOT)) for p in source))

    path = FINAL / "table5_full_coefficients_appendix.csv"
    data = rows(path)
    body = []
    last = None
    for r in data:
        if r["feature_set"] != last:
            body.append(r"\addlinespace[0.5em]" + "\n")
            body.append(r"\multicolumn{6}{l}{\textbf{" + tex(r["feature_set"]) + r"}} \\" + "\n")
            last = r["feature_set"]
        body.append(line([tex(r["feature_set"]), tex(r["term"]),
                          num(r["beta_log_price"], 4), num(r["robust_se_hc3"], 4),
                          num(r["ci95_low"], 4), num(r["ci95_high"], 4)]))
    output("table5_full_coefficients.tex", path,
           longtable("Full semi-log OLS coefficient ladder", "tab:app-full-coefficients",
                     ["Block", "Term", "Coefficient", "HC3 SE", "95\\% CI low", "95\\% CI high"],
                     body, "p{2cm}p{9cm}rrrr",
                     "Coefficients, heteroskedasticity-robust HC3 SE, and confidence limits come directly from the frozen coefficient CSV. Intercept percentage transformations are omitted because they are not substantively meaningful. Coefficients represent associations, not causal effects."))

    p_main = FINAL / "table7_incremental_accessibility.csv"
    p_more = FINAL / "table7_incremental_accessibility_appendix.csv"
    data = rows(p_main) + rows(p_more)
    body = [line([tex(r["Validation"]), tex(r["Estimator"]), tex(r["Comparison"]),
                  num(r["Delta RMSE reduction"], 5), num(r["Delta MAE reduction"], 5),
                  num(r["Reference RMSE"], 4), num(r["New RMSE"], 4)]) for r in data]
    output("table7_incremental_accessibility_full.tex", (p_main, p_more),
           longtable("Full incremental accessibility comparisons", "tab:app-incremental-full",
                     ["Validation", "Estimator", "Comparison", "$\\Delta$ RMSE", "$\\Delta$ MAE", "Reference RMSE", "New RMSE"],
                     body, "p{4cm}p{2.6cm}p{3.8cm}rrrr",
                     "Positive $\\Delta$ denotes reduced out-of-fold error. MW-versus-ME rows are appendix-only; small differences do not establish a firm ranking. All numbers come from frozen final CSV exports."))

    path = ROOT / "outputs/tables/context_comparison.csv"
    data = rows(path)
    body = [line([tex(r["cv_scheme"]), tex(r["model"]), tex(r["accessibility"]),
                  num(r["n"], count=True), num(r["delta_rmse_phase9"], 5),
                  num(r["delta_rmse_ctx"], 5), num(r["change_in_access_gain"], 5),
                  num(r["rmse_access_ctx"], 4)]) for r in data]
    output("context_comparison.tex", path,
           longtable("Full area-context-adjusted accessibility comparison", "tab:app-context-comparison",
                     ["Validation", "Estimator", "Access", "$N$", "Primary $\\Delta$", "CTX $\\Delta$", "Gain change", "CTX RMSE"],
                     body, "p{3.5cm}p{2.3cm}p{2.3cm}rrrrr",
                     "Base and CTX columns compare accessibility gains against their respective M0 baselines on the same sample. CTX is a planned contextual specification implemented after Phase 9; it mixes Copenhagen district-level and Frederiksberg municipality-level context and was not frozen as Phase 7 M0."))

    path = ROOT / "outputs/tables/copenhagen_only_context_sensitivity.csv"
    data = rows(path)
    body = [line([tex(r["feature_set"]), num(r["n"], count=True),
                  num(r["geographic_xgb_rmse_log"], 4), num(r["geographic_xgb_mae_log"], 4),
                  num(r["geographic_xgb_r2_log"], 3), num(r["xgb_delta_rmse_vs_m0_ctx"], 5),
                  num(r["ols_adjusted_r2_in_sample"], 3)]) for r in data]
    output("copenhagen_only_context.tex", path,
           table("Copenhagen-only context sensitivity", "tab:app-copenhagen-context",
                 ["Block", "$N$", "XGB RMSE", "XGB MAE", "XGB $R^2$", "$\\Delta$ RMSE", "OLS adj. $R^2$"],
                 body, "p{3cm}rrrrrr",
                 "Copenhagen-only sample with ten official district holdouts. $\\Delta$ compares XGBoost with the context-augmented M0 on this sample; OLS adjusted $R^2$ is in-sample and is not a cross-validated predictive metric. District context is exploratory."))

    path = ROOT / "outputs/tables/price_observability_comparison.csv"
    data = rows(path)
    body = [line([tex(r["validation"]), tex(r["model"]), tex(r["feature_set"]),
                  num(r["n_phase9"], count=True), num(r["n_high_completeness"], count=True),
                  num(r["rmse_phase9"], 4), num(r["rmse_high_completeness"], 4),
                  num(r["delta_access_phase9"], 5), num(r["delta_access_high_completeness"], 5)]) for r in data]
    output("price_observability_comparison.tex", path,
           longtable("Price-observability batch sensitivity", "tab:app-price-observability",
                     ["Validation", "Estimator", "Block", "Primary $N$", "High-completeness $N$", "Primary RMSE", "High-comp. RMSE", "Primary gain", "High-comp. gain"],
                     body, "p{2.8cm}p{2cm}p{1.6cm}rrrrrr",
                     "High-completeness scrape dates have at least 90\\% observed valid price among otherwise eligible listings. Samples differ; compare within-sample accessibility gains, not raw RMSE as paired errors. Price is never imputed; saved outer folds are filtered, not reassigned."))

    path = ROOT / "outputs/tables/boundary_sensitivity_comparison.csv"
    data = [r for r in rows(path) if r["metric"] == "RMSE"]
    body = [line([tex(r["estimator"]), tex(r["validation"]), num(r["sample_N"], count=True),
                  num(r["primary_Delta_ME"], 5), num(r["boundary_Delta_ME"], 5),
                  num(r["primary_Delta_MW"], 5), num(r["boundary_Delta_MW"], 5),
                  num(r["boundary_sensitivity_MW"], 4)]) for r in data]
    output("boundary_definition_sensitivity.tex", path,
           table("Study-boundary destination sensitivity", "tab:app-boundary-sensitivity",
                 ["Estimator", "Validation", "$N$", "Buffered $\\Delta$ ME", "Union $\\Delta$ ME", "Buffered $\\Delta$ MW", "Union $\\Delta$ MW", "Union MW RMSE"],
                 body, "p{2cm}p{3cm}rrrrrr",
                 "Buffered is the primary opportunity universe. Union restricts destination endpoints to Copenhagen and Frederiksberg, without clipping the walking graph. Positive gain is RMSE reduction versus the matched M0. This sensitivity does not redefine the primary model.", landscape=True))

    path = ROOT / "outputs/tables/phase09/fold_performance.csv"
    mapping_path = ROOT / "outputs/tables/phase04/cv_area_counts.csv"
    names = {r["area"]: r["area_name"] for r in rows(mapping_path)}
    names["frederiksberg"] = "Frederiksberg"
    data = [r for r in rows(path) if r["cv_scheme"] == "geographic_11" and r["model"] == "XGBoost" and r["feature_set"] in {"M0", "MW"}]
    missing = {r["fold"] for r in data} - set(names)
    if missing:
        raise ValueError(f"Official area names missing for folds: {sorted(missing)}")
    body = [line([tex(names[r["fold"]]), tex(r["feature_set"]), num(r["train_n"], count=True),
                  num(r["n"], count=True), num(r["rmse_log"], 4),
                  num(r["mae_log"], 4), num(r["r2_log"], 3)]) for r in data]
    output("geographic_fold_performance.tex", path,
           longtable("XGBoost M0 and MW by held-out official area", "tab:app-geographic-folds",
                     ["Held-out area", "Block", "Train $N$", "Test $N$", "RMSE", "MAE", "$R^2$"],
                     body, "p{6cm}crrrrr",
                     "Each of ten Copenhagen districts and Frederiksberg is held out once. Fold names are joined to the saved official-area lookup; no fold assignments were regenerated. Fold metrics are not pooled metrics."))
    sources["appendix/geographic_fold_performance.tex"] = Path(str(path.relative_to(ROOT)) + "; " + str(mapping_path.relative_to(ROOT)))

    path = FINAL / "table_validation_performance.csv"
    data = rows(path)
    body = [line([tex(r["Validation scheme"]), num(r["Sample N"], count=True),
                  num(r["XGBoost M0 RMSE(log price)"], 4),
                  num(r["XGBoost MW RMSE(log price)"], 4),
                  num(r["MW RMSE reduction vs M0"], 5)]) for r in data]
    output("block_buffer_validation_summary.tex", path,
           table("XGBoost M0 and MW across validation designs", "tab:app-block-buffer-validation",
                 ["Validation scheme", "$N$", "M0 RMSE", "MW RMSE", "$\\Delta$ RMSE"],
                 body, "p{8cm}rrrr",
                 "All entries are saved existing model outputs. The 1.5 km geometric-block and buffered LOAO analyses are robustness checks; LOAO is the primary unseen-area geographic test. Positive $\\Delta$ indicates MW reduces RMSE relative to M0 on that design."))
    return sources


def main() -> None:
    main_sources = export_main()
    app_sources = export_appendix()
    save(OUT / "table_preamble.tex",
         "% Packages needed by the generated manuscript tables.\n"
         "\\usepackage[T1]{fontenc}\n\\usepackage[utf8]{inputenc}\n"
         "\\usepackage{booktabs}\n\\usepackage{threeparttable}\n"
         "\\usepackage{array}\n\\usepackage{tabularx}\n\\usepackage{longtable}\n"
         "\\usepackage{pdflscape}\n")
    main_order = [
        "table1_sample_construction", "table2_variable_specification",
        "table3_descriptive_statistics", "table4_accessibility_definitions",
        "table5_hedonic_ladder", "table6_predictive_performance",
        "table7_incremental_accessibility", "table_rq2_area_context",
        "table8_robustness_summary",
        "table_validation_designs",
    ]
    app_order = [
        "table5_full_coefficients", "table7_incremental_accessibility_full",
        "context_comparison", "copenhagen_only_context",
        "price_observability_comparison", "boundary_definition_sensitivity",
        "geographic_fold_performance", "block_buffer_validation_summary",
    ]
    destination_order = ["destination_taxonomy", "destination_counts",
                         "destination_examples", "destination_rail_metro_full"]
    if all((APP / f"{stem}.tex").is_file() for stem in destination_order):
        app_order.extend(destination_order)
    save(OUT / "main_tables.tex", "% Compile from repository root.\n" +
         "".join(f"\\input{{outputs/latex/tables/{stem}.tex}}\n" for stem in main_order))
    save(OUT / "appendix_tables.tex", "% Compile from repository root.\n" +
         "".join(f"\\input{{outputs/latex/appendix/{stem}.tex}}\n" for stem in app_order))
    save(OUT / "table_test_document.tex",
         "\\documentclass[a4paper,11pt]{article}\n"
         "\\usepackage[margin=2cm]{geometry}\n"
         "\\input{outputs/latex/table_preamble.tex}\n"
         "\\begin{document}\n\\listoftables\n"
         "\\input{outputs/latex/main_tables.tex}\n"
         "\\appendix\n\\input{outputs/latex/appendix_tables.tex}\n"
         "\\end{document}\n")
    print(f"Exported {len(main_sources)} main and {len(app_order)} appendix tables")
    for target, source in {**main_sources, **app_sources}.items():
        print(f"{target} <- {source}")


if __name__ == "__main__":
    main()

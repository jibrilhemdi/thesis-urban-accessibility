"""Presentation-only RQ2 panel from saved matched context comparisons.

No database access or model fitting. Source CSV values are copied, not
recomputed, and the frozen Phase 9 and context-model aggregate files are read
only. Run before exporting the final LaTeX tables.
"""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/tables/context_comparison.csv"
DEST = ROOT / "outputs/tables/final/table_rq2_area_context.csv"
MARKDOWN = DEST.with_suffix(".md")
FIELDS = ["Estimator", "Specification", "N", "M0 RMSE", "ME RMSE", "MW RMSE", "ME gain", "MW gain"]


def read_rows() -> list[dict[str, str]]:
    with SOURCE.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def build_rows() -> list[dict[str, str]]:
    source = read_rows()
    result = []
    for estimator in ("OLS", "XGBoost"):
        matched = {
            access: [row for row in source if row["cv_scheme"] == "geographic_11"
                     and row["model"] == estimator and row["accessibility"] == access]
            for access in ("ME", "MW")
        }
        if any(len(rows) != 1 for rows in matched.values()):
            raise ValueError(f"Expected one saved geographic ME/MW comparison for {estimator}")
        e, w = matched["ME"][0], matched["MW"][0]
        if e["n"] != w["n"] or e["n"] != "12412":
            raise ValueError("Context comparison sample differs from frozen common sample")
        for suffix, label in (
            ("phase9", "Base specification"),
            ("ctx", "Area-context-adjusted core specification"),
        ):
            base = e[f"rmse_m0_{suffix}"]
            if base != w[f"rmse_m0_{suffix}"]:
                raise ValueError(f"ME/MW {suffix} baseline mismatch for {estimator}")
            result.append({
                "Estimator": estimator,
                "Specification": label,
                "N": e["n"],
                "M0 RMSE": base,
                "ME RMSE": e[f"rmse_access_{suffix}"],
                "MW RMSE": w[f"rmse_access_{suffix}"],
                "ME gain": e[f"delta_rmse_{suffix}"],
                "MW gain": w[f"delta_rmse_{suffix}"],
            })
    return result


def main() -> None:
    result = build_rows()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(result)
    lines = [
        "# Core RQ2: accessibility with and without area socioeconomic context",
        "",
        "Pooled leave-one-area-out out-of-fold RMSE for the same 12,412 listings and saved 11 area holdouts. "
        "Base specification = Phase 9 listing, host/rental, municipality and City Hall centrality controls. "
        "Area-context-adjusted core specification = the same controls plus log gross-polygon population density and disposable income. "
        "ME and MW add their frozen Euclidean and walking accessibility blocks, respectively. "
        "Positive gain = matching M0 RMSE minus access-model RMSE; all errors are in log listed-price units. "
        "This context implementation occurred after Phase 9 because source comparability was unresolved at the Phase 7 freeze; "
        "it was conceptually planned but is not the originally frozen primary model. "
        "Copenhagen district and Frederiksberg municipality context are mixed-resolution; income denominators and polygon vintage/area treatment remain provisional. "
        f"All values come from `{SOURCE.relative_to(ROOT)}`; no model was refitted.",
        "",
        "| " + " | ".join(FIELDS) + " |",
        "| " + " | ".join(["---", "---", "---:", "---:", "---:", "---:", "---:", "---:"]) + " |",
    ]
    for row in result:
        cells = [row["Estimator"], row["Specification"], f"{int(row['N']):,}"]
        cells.extend(f"{float(row[field]):.5f}" for field in FIELDS[3:])
        lines.append("| " + " | ".join(cells) + " |")
    MARKDOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(result)} saved-result rows to {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

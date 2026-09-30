"""Read-only, methods-only visualisations from frozen Phase 8 CV assignments."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box
from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.pipeline.run_context_models_postcompletion02 import freeze_check


FIG = PROJECT_ROOT / "outputs/figures/final"
TAB = PROJECT_ROOT / "outputs/tables/final"
FOLD = {1: "#9FB9D4", 2: "#AED0BD", 3: "#E7C9A8", 4: "#CBBBDD", 5: "#E4B9C4"}
NEUTRAL = "#E8ECEB"
INK = "#263D4B"
MUTED = "#526873"
LINE = "#607785"


def _shape(wkb):
    return shapely.from_wkb(bytes(wkb))


def _polygons(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "Polygon":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _polygons(part)


def _lines(ax, geometry, color: str, width: float, zorder: int):
    if geometry.geom_type == "LineString":
        x, y = geometry.xy
        ax.plot(x, y, color=color, linewidth=width, zorder=zorder,
                solid_capstyle="round")
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            _lines(ax, part, color, width, zorder)


def _csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _markdown(path: Path, rows: list[dict], caption: str) -> None:
    columns = list(rows[0])
    lines = [caption, "", "| " + " | ".join(columns) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    def display(value):
        if isinstance(value, float):
            return f"{value:.5f}"
        if isinstance(value, int):
            return f"{value:,}"
        return str(value).replace("|", "\\|")
    for row in rows:
        lines.append("| " + " | ".join(display(row[column]) for column in columns) + " |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load(conn):
    freeze_check(conn)
    blocks = pd.read_sql(text(
        "SELECT c.block_1500m_id, min(c.block_1500m_fold) fold,"
        "count(*) source_listings,"
        "count(*) FILTER (WHERE a.primary_sample_candidate "
        "AND a.official_cv_area_id IS NOT NULL "
        "AND a.nearest_station_walking_minutes IS NOT NULL) common_listings,"
        "count(DISTINCT c.block_1500m_fold) fold_values "
        "FROM analysis.cv_assignments c JOIN analysis.analysis_dataset_v1 a "
        "USING(snapshot_date,listing_id) WHERE c.block_1500m_id IS NOT NULL "
        "GROUP BY c.block_1500m_id ORDER BY c.block_1500m_id"
    ), conn)
    municipalities = [(row[0], _shape(row[1])) for row in conn.execute(text(
        "SELECT municipality_code,ST_AsBinary(geom_25832) "
        "FROM spatial.official_municipalities "
        "WHERE municipality_code IN ('0101','0147') ORDER BY municipality_code"
    ))]
    areas = conn.execute(text(
        "SELECT area_id,area_name FROM spatial.official_cv_areas ORDER BY area_id"
    )).all()
    assignment = conn.execute(text(
        "SELECT count(*) total, count(DISTINCT random_fold) random_folds,"
        "count(DISTINCT heldout_area) heldout_areas,"
        "count(DISTINCT block_1500m_fold) block_folds,"
        "count(*) FILTER (WHERE block_crs_epsg<>25832 OR block_1500m_seed<>20261034) bad_metadata "
        "FROM analysis.cv_assignments"
    )).one()
    buffers = conn.execute(text(
        "SELECT buffer_m,count(DISTINCT heldout_area) areas,count(*) records "
        "FROM analysis.cv_buffer_exclusions GROUP BY buffer_m ORDER BY buffer_m"
    )).all()
    if (len(blocks) != 53 or blocks.fold_values.max() != 1 or
            set(blocks.fold) != set(FOLD) or int(blocks.source_listings.sum()) != 23066 or
            int(blocks.common_listings.sum()) != 12412 or
            int((blocks.common_listings == 0).sum()) != 1):
        raise RuntimeError("Saved 1.5-km block assignment differs from Phase 8")
    if (len(municipalities) != 2 or len(areas) != 11 or assignment.total != 23144 or
            (assignment.random_folds, assignment.heldout_areas, assignment.block_folds,
             assignment.bad_metadata) != (5, 11, 5, 0)):
        raise RuntimeError("Saved random/geographic/block assignment QA failed")
    if [(row.buffer_m, row.areas) for row in buffers] != [(500, 11), (1000, 11)]:
        raise RuntimeError("Saved buffered LOAO area coverage changed")
    return blocks, municipalities, areas, buffers


def _block_map(blocks: pd.DataFrame, municipalities) -> None:
    study = shapely.union_all([shape for _, shape in municipalities])
    fig, ax = plt.subplots(figsize=(12.4, 8), dpi=190)
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(left=.055, right=.76, bottom=.135, top=.83)
    ax.set_facecolor("#F8FAFA")
    drawn = 0
    for row in blocks.itertuples(index=False):
        ix, iy = (int(value) for value in row.block_1500m_id.split(":"))
        square = box(ix*1500, iy*1500, (ix+1)*1500, (iy+1)*1500)
        clipped = square.intersection(study)
        if clipped.is_empty:
            raise RuntimeError(f"Saved block does not intersect official study union: {row.block_1500m_id}")
        colour = NEUTRAL if row.common_listings == 0 else FOLD[int(row.fold)]
        for polygon in _polygons(clipped):
            x, y = polygon.exterior.xy
            ax.fill(x, y, facecolor=colour, edgecolor="white", linewidth=.95,
                    zorder=2)
            for hole in polygon.interiors:
                hx, hy = hole.xy
                ax.fill(hx, hy, color="#F8FAFA", zorder=3)
        drawn += 1
    for _, geometry in municipalities:
        _lines(ax, geometry.boundary, INK, 1.35, 5)
    _lines(ax, study.boundary, INK, 1.7, 6)
    if drawn != 53:
        raise RuntimeError("The map did not draw every saved block")
    xmin, ymin, xmax, ymax = study.bounds
    pad = 1600
    ax.set_xlim(xmin-pad, xmax+pad)
    ax.set_ylim(ymin-pad, ymax+pad)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(.99, .965, "N ↑", transform=ax.transAxes, ha="right", va="top",
            fontsize=11, color=INK, fontweight="bold")
    # Metric scale bar in the projected EPSG:25832 map plane.
    x0, y0 = xmin+1200, ymin-1050
    ax.plot([x0, x0+2000], [y0, y0], color=INK, linewidth=2.2, zorder=8)
    ax.plot([x0, x0], [y0-100, y0+100], color=INK, linewidth=1.5, zorder=8)
    ax.plot([x0+2000, x0+2000], [y0-100, y0+100], color=INK, linewidth=1.5, zorder=8)
    ax.text(x0+1000, y0-190, "2 km", ha="center", va="top", fontsize=9, color=INK)
    handles = [Patch(facecolor=FOLD[i], edgecolor=LINE, linewidth=.7, label=f"Fold {i}")
               for i in range(1, 6)]
    handles.append(Patch(facecolor=NEUTRAL, edgecolor=LINE, linewidth=.7,
                         label="No common-sample listing (1 block)"))
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(.785, .69),
               frameon=False, title="Saved fold assignment", title_fontsize=11,
               fontsize=9, labelspacing=.9, handlelength=1.5)
    fig.text(.785, .385, "53 saved blocks\n5 folds\n1.5 km × 1.5 km cells",
             fontsize=10, color=INK, linespacing=1.7, va="top")
    fig.text(.785, .245, "Full squares are clipped to the\nmunicipal union for display.\n"
             "The neutral block has saved\nassignment but no listing in\nthe Phase 9 common sample.",
             fontsize=9, color=MUTED, linespacing=1.5, va="top")
    fig.suptitle("Actual saved geometric-block CV assignment", x=.055, ha="left",
                 y=.965, fontsize=19, fontweight="bold", color=INK)
    fig.text(.055, .87, "Copenhagen–Frederiksberg urban core · five outcome-blind folds · EPSG:25832",
             fontsize=10, color=MUTED)
    fig.text(.055, .07, "All listings within one spatial block are assigned to the same fold.  "
             "Blocks are not folds: multiple blocks belong to each fold.",
             fontsize=10, color=INK, fontweight="medium")
    fig.text(.055, .035, "Official municipality polygons: project PostGIS archive. "
             "No individual Airbnb locations shown.", fontsize=8, color=MUTED)
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "appendix_geometric_block_cv.png", dpi=190, facecolor="white")
    plt.close(fig)


def _schematic() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14.6, 5.4), dpi=190)
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(left=.045, right=.975, top=.77, bottom=.27, wspace=.16)
    for ax in axes:
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.add_patch(Rectangle((.02, .02), .96, .96, facecolor="#F9FBFB",
                               edgecolor="#DDE5E7", linewidth=1.2))
    # Only synthetic symbols: never use real Airbnb point coordinates here.
    rng = np.random.default_rng(7281)
    ax = axes[0]
    x = np.repeat(np.linspace(.13, .87, 7), 5) + rng.uniform(-.025, .025, 35)
    y = np.tile(np.linspace(.14, .86, 5), 7) + rng.uniform(-.025, .025, 35)
    assignment = (np.arange(35)*3) % 5 + 1
    rng.shuffle(assignment)
    for fold in range(1, 6):
        choice = assignment == fold
        ax.scatter(x[choice], y[choice], s=105, facecolor=FOLD[fold],
                   edgecolor="white", linewidth=.8, zorder=2)
    axes[0].set_title("A  Random 5-fold", loc="left", color=INK, fontsize=13, fontweight="bold", pad=13)

    ax = axes[1]
    pattern = np.array([[1, 4, 2, 5, 3], [3, 2, 5, 1, 4], [5, 1, 3, 4, 2],
                        [2, 5, 4, 3, 1], [4, 3, 1, 2, 5]])
    for iy in range(5):
        for ix in range(5):
            ax.add_patch(Rectangle((.075+ix*.17, .075+iy*.17), .17, .17,
                                   facecolor=FOLD[int(pattern[iy, ix])],
                                   edgecolor="white", linewidth=1.5))
    axes[1].set_title("B  1.5 km geometric blocks", loc="left", color=INK,
                      fontsize=13, fontweight="bold", pad=13)

    ax = axes[2]
    # Stylised official areas: 11 tiles, one entire area held out.
    for idx in range(11):
        col, row = idx % 4, idx // 4
        xx, yy = .08+col*.215, .69-row*.25
        test = idx == 5
        ax.add_patch(Rectangle((xx, yy), .205, .24,
                               facecolor=FOLD[2] if test else "#DCE5E7",
                               edgecolor="white", linewidth=1.8))
        if test:
            ax.text(xx+.1025, yy+.12, "TEST", ha="center", va="center",
                    fontsize=10, fontweight="bold", color=INK)
    axes[2].set_title("C  Leave one official area out", loc="left", color=INK,
                      fontsize=13, fontweight="bold", pad=13)
    labels = ["Spatially interspersed benchmark", "Non-administrative spatial robustness",
              "Primary unseen-area geographic test"]
    explanations = ["Individual listings can be nearby across folds.",
                    "Whole blocks move together; adjacent blocks can differ.",
                    "One of 11 complete areas is test; repeat for every area."]
    for ax, label, explanation in zip(axes, labels, explanations):
        ax.text(0, -.12, label, transform=ax.transAxes, ha="left", va="top",
                fontsize=10, fontweight="bold", color=INK)
        ax.text(0, -.22, explanation, transform=ax.transAxes, ha="left", va="top",
                fontsize=8.5, color=MUTED)
    fig.suptitle("Three ways to separate training and test listings", x=.045, ha="left",
                 y=.965, fontsize=19, fontweight="bold", color=INK)
    fig.text(.045, .855, "Schematic only · A/B colours show five fold labels; C highlights one held-out area · no real listing points",
             fontsize=10, color=MUTED)
    fig.text(.045, .055, "Buffered LOAO keeps the same held-out area, then also removes nearby "
             "training listings within a saved 500 m or 1,000 m buffer.",
             fontsize=9.5, color=INK)
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "figure_validation_designs.png", dpi=190, facecolor="white")
    plt.close(fig)


def validation_design_rows() -> list[dict[str, str]]:
    """Methods descriptions for the already-saved assignment designs."""
    return [
        {"Validation scheme": "Random 5-fold", "Grouping unit": "Individual listing",
         "Number of folds/groups": "5", "Spatial separation principle": "None; neighbouring train/test listings can occur",
         "Prediction question": "How well does the model predict interspersed listings in a familiar spatial mix?",
         "Role in thesis": "Spatially interspersed benchmark; not a spatial-transfer test"},
        {"Validation scheme": "1.5 km geometric block 5-fold", "Grouping unit": "Saved 1.5 km × 1.5 km grid cell",
         "Number of folds/groups": "5 folds; 53 occupied saved blocks",
         "Spatial separation principle": "Whole blocks stay together; adjacent blocks can differ in fold",
         "Prediction question": "How well does the model predict held-out grid blocks across the study area?",
         "Role in thesis": "Non-administrative spatial robustness"},
        {"Validation scheme": "Leave-one-area-out (11 analysis areas)", "Grouping unit": "Official Copenhagen district or Frederiksberg analysis area",
         "Number of folds/groups": "11 groups: 10 Copenhagen districts + Frederiksberg",
         "Spatial separation principle": "Whole official area held out; neighbours can remain across its border",
         "Prediction question": "How well does the model predict an entirely unseen official area?",
         "Role in thesis": "Primary reported unseen-area geographic test"},
        {"Validation scheme": "Buffered leave-one-area-out 500 m", "Grouping unit": "Same 11 official test areas; nearby training listings excluded",
         "Number of folds/groups": "11 held-out areas", "Spatial separation principle": "Exclude training listings within 500 m of held-out polygon; test area unchanged",
         "Prediction question": "How well does the model predict an unseen area after removing nearby training data?",
         "Role in thesis": "Stronger spatial-separation robustness"},
        {"Validation scheme": "Buffered leave-one-area-out 1000 m", "Grouping unit": "Same 11 official test areas; nearby training listings excluded",
         "Number of folds/groups": "11 held-out areas", "Spatial separation principle": "Exclude training listings within 1,000 m of held-out polygon; test area unchanged",
         "Prediction question": "How well does the model predict an unseen area after removing more nearby training data?",
         "Role in thesis": "Stronger spatial-separation robustness"},
    ]


def _methods() -> None:
    rows = validation_design_rows()
    _csv(TAB / "table_validation_designs.csv", rows)
    _markdown(TAB / "table_validation_designs.md", rows,
              "# Validation designs — methods table\n\nSaved assignments only; no model fitted for this table. "
              "Blocks and buffers use EPSG:25832 metres.")


def _performance() -> None:
    primary = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase09/model_performance.csv")
    robustness = pd.read_csv(PROJECT_ROOT / "outputs/tables/phase10/robustness_summary.csv")
    specs = (
        ("Random 5-fold", "phase9", "random_5", primary),
        ("1.5 km block 5-fold", "block_1500m", "block_1500m_5", robustness),
        ("Leave-one-area-out", "phase9", "geographic_11", primary),
        ("Buffered LOAO 500 m", "buffer_500m", "geographic_11", robustness),
        ("Buffered LOAO 1000 m", "buffer_1000m", "geographic_11", robustness),
    )
    rows = []
    for label, analysis, validation, source in specs:
        chosen = {}
        for model in ("M0", "MW"):
            if analysis == "phase9":
                found = source.loc[(source.cv_scheme == validation) &
                                   (source.model == "XGBoost") & (source.feature_set == model)]
                field, n_field, source_label = "rmse_log", "n", "Phase 9 saved performance"
            else:
                found = source.loc[(source.analysis == analysis) &
                                   (source.validation_method == validation) &
                                   (source.model == "XGBoost") &
                                   (source.accessibility_specification == model)]
                field, n_field, source_label = "RMSE", "sample_N", "Phase 10 saved robustness"
            chosen[model] = (float(found.iloc[0][field]), int(found.iloc[0][n_field])) if len(found) == 1 else None
        if any(value is not None and value[1] != 12412 for value in chosen.values()):
            raise RuntimeError("Existing model output differs from the 12,412-row common sample")
        m0, mw = chosen["M0"], chosen["MW"]
        rows.append({"Validation scheme": label, "XGBoost M0 RMSE(log price)": m0[0] if m0 else "not estimated",
                     "XGBoost MW RMSE(log price)": mw[0] if mw else "not estimated",
                     "MW RMSE reduction vs M0": m0[0]-mw[0] if m0 and mw else "not estimated",
                     "Sample N": 12412 if m0 and mw else "not estimated",
                     "Source": source_label})
    _csv(TAB / "table_validation_performance.csv", rows)
    _markdown(TAB / "table_validation_performance.md", rows,
              "# Existing XGBoost M0/MW performance — appendix table\n\n"
              "Pooled outer out-of-fold RMSE of log listed price; positive reduction favours MW. "
              "These are different validation questions, not a score contest. No model was refitted.")


def run() -> dict:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            blocks, municipalities, areas, buffers = _load(conn)
        _block_map(blocks, municipalities)
        _schematic()
        _methods()
        _performance()
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            freeze_check(conn)
        return {"saved_blocks": len(blocks), "folds": int(blocks.fold.nunique()),
                "blocks_without_common_sample_listings": int((blocks.common_listings == 0).sum()),
                "official_areas": len(areas), "buffer_radii_m": [row.buffer_m for row in buffers],
                "figures": 2, "methods_rows": 4, "existing_performance_rows": 5,
                "models_run": False}
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

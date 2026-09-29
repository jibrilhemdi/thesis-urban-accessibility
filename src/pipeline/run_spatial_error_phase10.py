"""One inferential spatial-error sensitivity justified by Phase 9 residual Moran I.

This is not a spatial-CV predictive model. It uses the frozen common sample,
Phase 9 MW controls and the same directed row-standardised 8-nearest-neighbour
EPSG:25832 weights used by the residual diagnostic.
"""

from __future__ import annotations

import json

import libpysal
import numpy as np
import pandas as pd
import spreg
from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, write_json
from src.pipeline.run_analysis_phase10 import SETS, _freeze, _load, _preprocessor
from src.spatial.spatial_diagnostics import knn_indices


def run() -> dict:
    prior = json.loads((PROJECT_ROOT / "outputs/tables/phase10/primary_freeze.json").read_text())
    engine = get_engine()
    try:
        with engine.connect() as conn:
            if _freeze(conn) != prior:
                raise RuntimeError("Phase 9 freeze changed")
            frame, _ = _load(conn)
        columns = SETS["MW"]
        prep = _preprocessor(columns)
        x = np.asarray(prep.fit_transform(frame[list(columns)]), dtype=float)
        names = list(prep.get_feature_names_out())
        y = frame["log_price"].to_numpy(float).reshape(-1, 1)
        coords = frame[["metric_x", "metric_y"]].to_numpy(float)
        neighbours = knn_indices(coords, k=8)
        weights = libpysal.weights.W({i: list(map(int, neighbours[i]))
                                      for i in range(len(frame))}, silence_warnings=True)
        weights.transform = "r"
        model = spreg.GM_Error_Het(y, x, weights, name_y="log_price",
                                   name_x=names, name_w="directed 8NN EPSG:25832 row-standardised",
                                   max_iter=1, step1c=False)
        betas = np.asarray(model.betas).ravel()
        errors = np.asarray(model.std_err).ravel()
        labels = ["Intercept", *names, "lambda_spatial_error"]
        if len(betas) != len(labels):
            raise RuntimeError(f"Unexpected spatial-error coefficient shape {len(betas)} / {len(labels)}")
        rows = []
        for i, label in enumerate(labels):
            rows.append({"analysis": "spatial_error_8nn", "term": label,
                         "beta_log_price": float(betas[i]),
                         "heteroskedastic_robust_se": float(errors[i]) if i < len(errors) else np.nan,
                         "n": len(frame), "weights": "directed 8NN row-standardised",
                         "crs_epsg": 25832,
                         "method": "PySAL spreg.GM_Error_Het; full-sample association only"})
        destination = PROJECT_ROOT / "outputs/tables/phase10/spatial_error_coefficients.csv"
        pd.DataFrame(rows).to_csv(destination, index=False)
        meta = {"method": "GM_Error_Het", "spreg_version": spreg.__version__,
                "libpysal_version": libpysal.__version__, "n": len(frame),
                "k": 8, "weights": "directed, row-standardised, self excluded",
                "crs_epsg": 25832, "lambda": float(betas[-1]),
                "purpose": "inferential coefficient sensitivity; not comparable with out-of-fold RMSE"}
        write_json(PROJECT_ROOT / "outputs/tables/phase10/spatial_error_metadata.json", meta)
        return meta
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

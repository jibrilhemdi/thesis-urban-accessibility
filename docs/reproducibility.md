# Reproducibility notes

## Collection

Run the ingestion scripts from the project root. They use relative project paths and do not depend on a personal home directory.

```bash
python src/ingestion/download_inside_airbnb.py
python src/ingestion/download_osm_overpass.py
python -m src.ingestion.download_copenhagen_statbank --retrieval-date YYYY-MM-DD
python -m src.ingestion.download_municipality_statbank --retrieval-date YYYY-MM-DD
python src/ingestion/build_manifest.py --verify
python -m src.pipeline.run_minimum_pipeline
```

The source manifest records the URL, local path, retrieval time, size, SHA-256 checksum, and provider metadata. The OSM extraction metadata also records the bbox, endpoint, OSM timestamp, query paths, and response counts. The City Statbank metadata records exact table selections, periods, raw CSV checksums, and district join boundary. The national StatBank metadata records the Frederiksberg source tables and periods for its single proxy analysis area. The historical Frederiksberg-only extract remains superseded.

For the current pooled context, Copenhagen KKHUS1 is deliberately fixed at `2026K1` to align its household reference date with Frederiksberg FAM55N (`2026-01-01`). Population remains `2026K3` in both sources. The older Copenhagen Q3 household extract remains date-stamped and checksummed; do not substitute it into the current analytical table.

The available non-GTFS run is intentionally local and dependency-light. It produces a Parquet and compressed CSV analytical table with listing controls, projected coordinates, nearest OSM network nodes, network degree, nearest-category walking times, and a nearest-category accessibility index. Pooled 11-area analyses use `analysis_area_` fields and `eligible_for_mixed_analysis_area_context`; strict Copenhagen-only district analyses use `eligible_for_district_context_model`. The pipeline metadata records mixed-source field lineage and period/definition caveats. Run with `--force` only when deliberately replacing a processed output.

## Frozen-data principle

Once the analytical dataset is created, copy the source manifest into the analysis run metadata and record the exact snapshot dates. Do not overwrite raw files in place; use a new date-stamped directory for a new collection.

## Environment

The download scripts use the Python standard library. Spatial feature engineering is expected to use the packages in `requirements.txt`; create a project-specific environment before installing them. Record the final `python --version` and package lock/export used for the thesis.

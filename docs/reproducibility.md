# Reproducibility notes

## Collection

Run the ingestion scripts from the project root. They use relative project paths and do not depend on a personal home directory.

```bash
python src/ingestion/download_inside_airbnb.py
python src/ingestion/download_osm_overpass.py
python -m src.ingestion.download_copenhagen_statbank --retrieval-date YYYY-MM-DD
python -m src.ingestion.download_frederiksberg_statbank --retrieval-date YYYY-MM-DD
python src/ingestion/build_manifest.py --verify
python -m src.pipeline.run_minimum_pipeline
```

The source manifest records the URL, local path, retrieval time, size, SHA-256 checksum, and provider metadata. The OSM extraction metadata also records the bbox, endpoint, OSM timestamp, query paths, and response counts. The City Statbank metadata records the exact table selections, periods, raw CSV checksums, and district join boundary. The Frederiksberg StatBank metadata records the municipality code, exact API selections, raw CSV checksums, and the derivations used for the tidy municipality context row.

The available non-GTFS run is intentionally local and dependency-light. It produces a Parquet and compressed CSV analytical table with listing controls, projected coordinates, nearest OSM network nodes, network degree, nearest-category walking times, and a nearest-category accessibility index. Run it with `--force` only when deliberately replacing a processed output.

## Frozen-data principle

Once the analytical dataset is created, copy the source manifest into the analysis run metadata and record the exact snapshot dates. Do not overwrite raw files in place; use a new date-stamped directory for a new collection.

## Environment

The download scripts use the Python standard library. Spatial feature engineering is expected to use the packages in `requirements.txt`; create a project-specific environment before installing them. Record the final `python --version` and package lock/export used for the thesis.

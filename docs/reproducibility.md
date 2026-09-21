# Reproducibility notes

## Collection

Run the ingestion scripts from the project root. They use relative project paths and do not depend on a personal home directory.

```bash
python src/ingestion/download_inside_airbnb.py
python src/ingestion/download_osm_overpass.py
python src/ingestion/build_manifest.py --verify
```

The source manifest records the URL, local path, retrieval time, size, SHA-256 checksum, and provider metadata. The OSM extraction metadata also records the bbox, endpoint, OSM timestamp, query paths, and response counts.

## Frozen-data principle

Once the analytical dataset is created, copy the source manifest into the analysis run metadata and record the exact snapshot dates. Do not overwrite raw files in place; use a new date-stamped directory for a new collection.

## Environment

The download scripts use the Python standard library. Spatial feature engineering is expected to use the packages in `requirements.txt`; create a project-specific environment before installing them. Record the final `python --version` and package lock/export used for the thesis.

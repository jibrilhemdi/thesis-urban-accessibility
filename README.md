# Urban accessibility and short-term rental outcomes — Copenhagen

Reproducible research workspace for the MSc Social Data Science thesis on whether network-based urban accessibility measures add information beyond conventional location variables when modelling Copenhagen short-term-rental listing prices.

The immediate data stage contains a dated Inside Airbnb Copenhagen snapshot and a reproducible OpenStreetMap/Overpass extraction. Raw source files are intentionally ignored by Git because they contain listing-level coordinates and provider-controlled data. The source manifest, download scripts, schemas, and decisions are kept in the repository so the data can be re-obtained.

## Start here

1. Read [`docs/document_requirements.md`](docs/document_requirements.md) for the separation between the user request and requirements extracted from the two supplied planning documents.
2. Read [`docs/data_governance.md`](docs/data_governance.md) before sharing outputs.
3. Inspect [`data/metadata/source_manifest.json`](data/metadata/source_manifest.json) after downloading.

## Download the current data snapshot

The default configuration uses the Copenhagen snapshot dated `2026-06-30`, which is the latest snapshot listed on the Inside Airbnb download page when this workspace was prepared.

```bash
python src/ingestion/download_inside_airbnb.py
python src/ingestion/download_osm_overpass.py
python -m src.ingestion.download_copenhagen_statbank --retrieval-date YYYY-MM-DD
python -m src.ingestion.download_municipality_statbank --retrieval-date YYYY-MM-DD
python src/ingestion/build_manifest.py
python -m src.pipeline.run_minimum_pipeline
```

The OSM script derives the extraction bounding box from the downloaded listing coordinates and adds a 0.02-degree buffer. It saves the exact Overpass queries beside the raw responses.

The minimum pipeline writes a local analytical table to `data/processed/copenhagen/<snapshot>/`. It cleans listing controls, retains source price without currency conversion, builds OSM walking-time features, and defines 11 analysis areas: 10 Copenhagen districts plus Frederiksberg municipality as one explicitly flagged proxy area. Strict City district fields stay separate from pooled `analysis_area_` fields. All listings have mixed-area context; `eligible_for_district_context_model` remains false for Frederiksberg. GTFS and PostGIS remain pending in `data/metadata/pipeline_run.json`.

To use another Inside Airbnb snapshot:

```bash
python src/ingestion/download_inside_airbnb.py --date YYYY-MM-DD
```

## Data layout

```text
data/
├── raw/inside_airbnb/copenhagen/<snapshot>/   # listings, calendar, reviews, neighbourhoods
├── raw/osm/copenhagen/<retrieval-date>/       # Overpass responses and exact queries
├── raw/municipality_statbank/<retrieval-date>/ # national source for Frederiksberg proxy area
├── interim/                                   # cached intermediate tables
├── processed/                                 # frozen analytical data
└── metadata/                                  # manifests and collection metadata
```

The intended feature blocks are property/listing controls (P), basic location (L), OSM network accessibility (A), GTFS transit accessibility (T), and neighbourhood context (N). The pooled context layer has mixed geographic resolution. Copenhagen-only district models remain the cleaner sensitivity check. Copenhagen households now use 2026 Q1, aligned to Frederiksberg's 1 January 2026 reference date; population remains 2026 Q3 for both. Source methods may still differ, and income denominators and dwelling definitions are not fully harmonised, so pooled context measures should be sensitivity covariates, not unqualified equivalents. GTFS remains a modular follow-up source pending approval.

## Sources and attribution

- Inside Airbnb: <https://insideairbnb.com/get-the-data/> and <https://insideairbnb.com/data-assumptions/>. The download page states that the data are licensed under CC BY 4.0.
- OpenStreetMap contributors: <https://www.openstreetmap.org/copyright>. OSM data are available under the Open Database License (ODbL).
- Overpass API: <https://overpass-api.de/>. The raw response includes the OSM data timestamp used by the server.
- City of Copenhagen Statbank: <https://kk.statistikbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1>. The selected tables and periods are recorded in `data/metadata/copenhagen_statbank_run.json`.
- Statistics Denmark StatBank: <https://www.statbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1> and API documentation at <https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api>. The Frederiksberg municipality row supplies its single proxy analysis area; Copenhagen's national row is retained for provenance but not substituted for City district values. Selections are recorded in `data/metadata/municipality_statbank_run.json`.

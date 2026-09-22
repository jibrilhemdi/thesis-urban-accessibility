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
python -m src.ingestion.download_frederiksberg_statbank --retrieval-date YYYY-MM-DD
python src/ingestion/build_manifest.py
python -m src.pipeline.run_minimum_pipeline
python -m src.analysis.run_analysis --force
```

The OSM script derives the extraction bounding box from the downloaded listing coordinates and adds a 0.02-degree buffer. It saves the exact Overpass queries beside the raw responses.

The minimum pipeline writes a local analytical table to `data/processed/copenhagen/<snapshot>/`. It cleans non-identifying listing controls, retains source price without currency conversion, projects coordinates to an EPSG:25832-compatible metric system, builds an undirected pedestrian graph from OSM, snaps listings and OSM opportunities to that graph, computes nearest-category walking times, and joins City of Copenhagen district context plus Frederiksberg municipality context. GTFS and PostGIS remain pending in `data/metadata/pipeline_run.json`.

The analysis runner uses all valid source prices, including the 683 July 3–4 late-batch prices, and records `price_scrape_batch`, `price_from_late_scrape_batch`, and `price_data_status`. It writes model comparisons, descriptive tables, calendar/review summaries, OSM catchment summaries, spatial diagnostics, and privacy-safe figures under `outputs/tables/<snapshot>/` and `outputs/figures/<snapshot>/`. The early June 30–July 1 sample is included as a robustness analysis.

To use another Inside Airbnb snapshot:

```bash
python src/ingestion/download_inside_airbnb.py --date YYYY-MM-DD
```

## Data layout

```text
data/
├── raw/inside_airbnb/copenhagen/<snapshot>/   # listings, calendar, reviews, neighbourhoods
├── raw/osm/copenhagen/<retrieval-date>/       # Overpass responses and exact queries
├── raw/frederiksberg_statbank/<retrieval-date>/ # Statistics Denmark API responses
├── interim/                                   # cached intermediate tables
├── processed/                                 # frozen analytical data
└── metadata/                                  # manifests and collection metadata
```

The intended feature blocks are property/listing controls (P), basic location (L), OSM network accessibility (A), GTFS transit accessibility (T), and neighbourhood context (N). Municipal context is now collected with its source geography retained explicitly; GTFS remains a modular follow-up source pending approval.

## Sources and attribution

- Inside Airbnb: <https://insideairbnb.com/get-the-data/> and <https://insideairbnb.com/data-assumptions/>. The download page states that the data are licensed under CC BY 4.0.
- OpenStreetMap contributors: <https://www.openstreetmap.org/copyright>. OSM data are available under the Open Database License (ODbL).
- Overpass API: <https://overpass-api.de/>. The raw response includes the OSM data timestamp used by the server.
- City of Copenhagen Statbank: <https://kk.statistikbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1>. The selected tables and periods are recorded in `data/metadata/copenhagen_statbank_run.json`.
- Statistics Denmark StatBank: <https://www.statbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1> and API documentation at <https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api>. Frederiksberg municipality code 147 and all selections are recorded in `data/metadata/frederiksberg_statbank_run.json`.

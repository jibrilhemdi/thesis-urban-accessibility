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
python src/ingestion/build_manifest.py
```

The OSM script derives the extraction bounding box from the downloaded listing coordinates and adds a 0.02-degree buffer. It saves the exact Overpass queries beside the raw responses.

To use another Inside Airbnb snapshot:

```bash
python src/ingestion/download_inside_airbnb.py --date YYYY-MM-DD
```

## Data layout

```text
data/
├── raw/inside_airbnb/copenhagen/<snapshot>/   # listings, calendar, reviews, neighbourhoods
├── raw/osm/copenhagen/<retrieval-date>/       # Overpass responses and exact queries
├── interim/                                   # cached intermediate tables
├── processed/                                 # frozen analytical data
└── metadata/                                  # manifests and collection metadata
```

The intended feature blocks are property/listing controls (P), basic location (L), OSM network accessibility (A), GTFS transit accessibility (T), and neighbourhood context (N). GTFS and municipal context remain modular follow-up sources; they are not silently substituted into this initial collection.

## Sources and attribution

- Inside Airbnb: <https://insideairbnb.com/get-the-data/> and <https://insideairbnb.com/data-assumptions/>. The download page states that the data are licensed under CC BY 4.0.
- OpenStreetMap contributors: <https://www.openstreetmap.org/copyright>. OSM data are available under the Open Database License (ODbL).
- Overpass API: <https://overpass-api.de/>. The raw response includes the OSM data timestamp used by the server.

Do not commit raw listing files, row-level listing maps, host-identifying fields, or unaggregated coordinates to a public repository.

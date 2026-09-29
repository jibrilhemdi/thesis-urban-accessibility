# Data governance and sharing rules

## Raw data

Raw Inside Airbnb and OSM/Overpass files are stored under `data/raw/` and ignored by Git. Keep them locally or in an access-controlled research location. Preserve the source manifest and extraction metadata alongside the files.

Do not publish:

- host names, profile text, URLs, or other unnecessary identifying fields;
- row-level listing coordinates or maps that make individual listings easy to locate;
- raw files unless the provider’s current terms explicitly allow redistribution.

## Derived data

Use aggregated grids, neighbourhood summaries, or sufficiently broad spatial units for public figures. Before release, inspect every table and map for accidental row-level coordinates or host identifiers.

## Provider limitations

Inside Airbnb coordinates are anonymised and should not support address-level claims. Listed prices are not realised transaction prices. OSM coverage/tagging is uneven and tag absence is not evidence that an amenity does not exist. These limitations must be carried into the methods and discussion chapters.

## Attribution

- Inside Airbnb: cite the snapshot date and download page; follow CC BY 4.0 attribution.
- OpenStreetMap: credit “© OpenStreetMap contributors” and follow ODbL requirements.
- Overpass: cite the endpoint and preserve the OSM data timestamp recorded in `extraction_metadata.json`.
- Statistics Denmark StatBank: cite the table IDs, Copenhagen code 101 and Frederiksberg code 147, retrieval date, and the API documentation/source page recorded in `data/metadata/municipality_statbank_run.json`.

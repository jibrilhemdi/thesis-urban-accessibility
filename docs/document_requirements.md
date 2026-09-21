# Request versus document-derived requirements

## Authoritative user request

The user asked for two outcomes:

1. prepare this folder for the thesis project; and
2. collect data for Inside Airbnb and OpenStreetMap.

Those are the actions implemented in this workspace.

## Requirements extracted from the supplied documents

The two supplied DOCX files are planning documents, not separate user messages. They were used to inform the project setup as follows:

- study area: Copenhagen;
- primary observational unit: one Inside Airbnb listing in a fixed snapshot;
- primary outcome: cleaned/log listed nightly price, with calendar prices treated as a comparison or sensitivity measure;
- immediate data scope: Inside Airbnb plus OSM walking-network and amenity data;
- planned feature blocks: property/listing controls, basic location, OSM network accessibility, later GTFS transit accessibility, and later neighbourhood context;
- reproducibility: immutable raw inputs, source URLs, retrieval dates, checksums, exact OSM queries, and a documented analytical-data freeze;
- governance: raw data outside version control, no public row-level listing coordinates, no unnecessary host names/free text, and OSM/Inside Airbnb attribution;
- interpretation: observational associations and prediction, not causal effects;
- fallback: the minimum thesis remains viable if GTFS or municipal data are delayed.

The documents also propose later work—GTFS access, municipal context, model ladders, spatial cross-validation, Moran’s I, robustness checks, and writing milestones. Those are preserved as project direction but are not silently treated as completed work in this initial setup.

## Deliberate boundary for this turn

This preparation collects the seven current Copenhagen Inside Airbnb files listed by the provider and two reproducible OSM/Overpass extracts: a walkable highway network and a documented amenity/transport POI layer. It does not request GTFS access, collect municipal statistics, build routing features, or fit models yet.

The live snapshot was inspected after download. Its calendar file does not contain prices, and its listing prices are displayed with a dollar sign. These facts override any unverified currency or calendar-price assumptions in the planning documents until the source convention is confirmed.

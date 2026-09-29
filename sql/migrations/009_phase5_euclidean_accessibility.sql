-- Phase 5: immutable-source OSM element copy, auditable destinations and Euclidean features.
CREATE TABLE IF NOT EXISTS raw.osm_phase5_elements (
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    osm_type text NOT NULL CHECK (osm_type IN ('node','way','relation')),
    osm_id bigint NOT NULL,
    element jsonb NOT NULL,
    PRIMARY KEY (source_file_id,osm_type,osm_id)
);

CREATE TABLE IF NOT EXISTS spatial.osm_destination_candidates (
    candidate_key text PRIMARY KEY,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    taxonomy_version text NOT NULL,
    category text NOT NULL CHECK (category IN ('food_social','cultural_tourist','station')),
    osm_type text NOT NULL CHECK (osm_type IN ('node','way','relation')),
    osm_id bigint NOT NULL,
    name text,
    normalized_name text NOT NULL,
    wikidata text,
    tags jsonb NOT NULL,
    position_method text NOT NULL CHECK (position_method IN ('osm_node','gdal_point_on_surface')),
    geom geometry(Point,4326) NOT NULL,
    geom_25832 geometry(Point,25832) NOT NULL,
    canonical_candidate_key text REFERENCES spatial.osm_destination_candidates(candidate_key),
    dedup_reason text,
    UNIQUE (source_file_id,category,osm_type,osm_id)
);
CREATE INDEX IF NOT EXISTS osm_candidates_metric_gist
    ON spatial.osm_destination_candidates USING gist (geom_25832);
CREATE INDEX IF NOT EXISTS osm_candidates_category_name_idx
    ON spatial.osm_destination_candidates (category,normalized_name);

CREATE TABLE IF NOT EXISTS spatial.osm_pois (
    destination_key text PRIMARY KEY REFERENCES spatial.osm_destination_candidates(candidate_key),
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    taxonomy_version text NOT NULL,
    category text NOT NULL CHECK (category IN ('food_social','cultural_tourist')),
    osm_type text NOT NULL,
    osm_id bigint NOT NULL,
    name text,
    tags jsonb NOT NULL,
    position_method text NOT NULL,
    merged_osm_refs jsonb NOT NULL,
    duplicate_count integer NOT NULL CHECK (duplicate_count >= 0),
    geom geometry(Point,4326) NOT NULL,
    geom_25832 geometry(Point,25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS osm_pois_metric_gist ON spatial.osm_pois USING gist (geom_25832);
CREATE INDEX IF NOT EXISTS osm_pois_category_idx ON spatial.osm_pois (category);

CREATE TABLE IF NOT EXISTS spatial.transit_stations (
    station_key text PRIMARY KEY REFERENCES spatial.osm_destination_candidates(candidate_key),
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    taxonomy_version text NOT NULL,
    station_mode text NOT NULL CHECK (station_mode IN ('metro','urban_rail','rail')),
    osm_type text NOT NULL,
    osm_id bigint NOT NULL,
    name text NOT NULL,
    tags jsonb NOT NULL,
    position_method text NOT NULL,
    merged_osm_refs jsonb NOT NULL,
    duplicate_count integer NOT NULL CHECK (duplicate_count >= 0),
    geom geometry(Point,4326) NOT NULL,
    geom_25832 geometry(Point,25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS transit_stations_metric_gist
    ON spatial.transit_stations USING gist (geom_25832);

CREATE TABLE IF NOT EXISTS features.euclidean_accessibility (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    taxonomy_version text NOT NULL,
    valid_coordinates boolean NOT NULL,
    count_coverage_complete boolean,
    source_edge_distance_m double precision CHECK (source_edge_distance_m >= 0),
    nearest_station_coverage_complete boolean,
    nearest_station_key text REFERENCES spatial.transit_stations(station_key),
    nearest_station_distance_m double precision CHECK (nearest_station_distance_m >= 0),
    food_social_800m integer CHECK (food_social_800m >= 0),
    food_social_1200m integer CHECK (food_social_1200m >= 0),
    food_social_1600m integer CHECK (food_social_1600m >= 0),
    cultural_tourist_800m integer CHECK (cultural_tourist_800m >= 0),
    cultural_tourist_1200m integer CHECK (cultural_tourist_1200m >= 0),
    cultural_tourist_1600m integer CHECK (cultural_tourist_1600m >= 0),
    distance_crs_epsg integer NOT NULL DEFAULT 25832 CHECK (distance_crs_epsg = 25832),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date,listing_id),
    FOREIGN KEY (snapshot_date,listing_id) REFERENCES clean.airbnb_listings(snapshot_date,listing_id)
);
CREATE INDEX IF NOT EXISTS euclidean_accessibility_source_idx
    ON features.euclidean_accessibility (source_file_id,taxonomy_version);

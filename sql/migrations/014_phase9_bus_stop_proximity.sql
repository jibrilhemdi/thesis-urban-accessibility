-- Secondary bus-stop proximity amendment; separate from frozen rail/metro sets.
CREATE TABLE IF NOT EXISTS spatial.bus_stops (
    bus_stop_key text PRIMARY KEY,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    taxonomy_version text NOT NULL CHECK (taxonomy_version='bus_stop_proximity_v1'),
    osm_object_type text NOT NULL CHECK (osm_object_type IN ('node','way')),
    osm_id bigint NOT NULL,
    selection_rule text NOT NULL,
    tags jsonb NOT NULL,
    geom geometry(Point,4326) NOT NULL,
    geom_25832 geometry(Point,25832) NOT NULL,
    UNIQUE(osm_object_type,osm_id)
);
CREATE INDEX IF NOT EXISTS bus_stops_metric_gist ON spatial.bus_stops USING gist(geom_25832);

CREATE TABLE IF NOT EXISTS features.bus_stop_proximity (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    taxonomy_version text NOT NULL CHECK (taxonomy_version='bus_stop_proximity_v1'),
    nearest_bus_stop_key text REFERENCES spatial.bus_stops(bus_stop_key),
    nearest_bus_stop_euclidean_m double precision CHECK (nearest_bus_stop_euclidean_m>=0),
    distance_crs_epsg integer NOT NULL CHECK (distance_crs_epsg=25832),
    PRIMARY KEY(snapshot_date,listing_id),
    FOREIGN KEY(snapshot_date,listing_id) REFERENCES clean.airbnb_listings(snapshot_date,listing_id)
);

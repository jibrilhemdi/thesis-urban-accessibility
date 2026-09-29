-- Phase 10 post-Phase-9 bus-walking sensitivity; never modifies Phase 9 tables.
CREATE TABLE IF NOT EXISTS spatial.bus_stops_canonical (
    bus_stop_key text PRIMARY KEY REFERENCES spatial.bus_stops(bus_stop_key),
    dedup_version text NOT NULL CHECK (dedup_version='bus_walk_v1'),
    duplicate_count integer NOT NULL CHECK (duplicate_count>0),
    geom_25832 geometry(Point,25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS bus_stops_canonical_metric_gist
    ON spatial.bus_stops_canonical USING gist(geom_25832);

CREATE TABLE IF NOT EXISTS features.bus_accessibility (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    network_id text NOT NULL REFERENCES spatial.walking_networks(network_id),
    dedup_version text NOT NULL CHECK (dedup_version='bus_walk_v1'),
    nearest_euclidean_stop_key text REFERENCES spatial.bus_stops_canonical(bus_stop_key),
    bus_distance_euclidean_m double precision CHECK (bus_distance_euclidean_m>=0),
    nearest_walking_stop_key text REFERENCES spatial.bus_stops_canonical(bus_stop_key),
    bus_walk_distance_m double precision CHECK (bus_walk_distance_m>=0),
    bus_walk_time_min double precision CHECK (bus_walk_time_min>=0),
    bus_stop_snap_distance_m double precision CHECK (bus_stop_snap_distance_m>=0),
    routing_status text NOT NULL CHECK (routing_status IN
        ('ok','invalid_coordinates','no_walk_node','no_reachable_bus_stop')),
    distance_crs_epsg integer NOT NULL CHECK (distance_crs_epsg=25832),
    walking_speed_kmh numeric(4,2) NOT NULL CHECK (walking_speed_kmh=4.80),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(snapshot_date,listing_id),
    FOREIGN KEY(snapshot_date,listing_id)
        REFERENCES clean.airbnb_listings(snapshot_date,listing_id)
);
CREATE INDEX IF NOT EXISTS bus_accessibility_status_idx
    ON features.bus_accessibility(network_id,routing_status);

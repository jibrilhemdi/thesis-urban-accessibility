-- Phase 6: versioned pedestrian graph, auditable snaps, and listing-level routes.
CREATE TABLE IF NOT EXISTS spatial.walking_networks (
    network_id text PRIMARY KEY,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    source_sha256 char(64) NOT NULL,
    source_date date,
    network_type text NOT NULL,
    filter_version text NOT NULL,
    filter_spec jsonb NOT NULL,
    source_crs_epsg integer NOT NULL CHECK (source_crs_epsg=4326),
    metric_crs_epsg integer NOT NULL CHECK (metric_crs_epsg=25832),
    node_count integer NOT NULL CHECK (node_count>0),
    source_segment_count integer NOT NULL CHECK (source_segment_count>0),
    directed_arc_count integer NOT NULL CHECK (directed_arc_count>0),
    weak_component_count integer NOT NULL CHECK (weak_component_count>0),
    largest_component_nodes integer NOT NULL CHECK (largest_component_nodes>0),
    built_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_file_id,filter_version)
);

CREATE TABLE IF NOT EXISTS spatial.walking_nodes (
    network_id text NOT NULL REFERENCES spatial.walking_networks(network_id),
    osm_node_id bigint NOT NULL,
    lon double precision NOT NULL,
    lat double precision NOT NULL,
    component_id integer NOT NULL CHECK (component_id>0),
    geom_25832 geometry(Point,25832) NOT NULL,
    PRIMARY KEY (network_id,osm_node_id),
    CHECK (lon BETWEEN 12 AND 13 AND lat BETWEEN 55 AND 56)
);
CREATE INDEX IF NOT EXISTS walking_nodes_metric_gist ON spatial.walking_nodes USING gist(geom_25832);
CREATE INDEX IF NOT EXISTS walking_nodes_component_idx ON spatial.walking_nodes(network_id,component_id);

CREATE TABLE IF NOT EXISTS spatial.walking_edges (
    network_id text NOT NULL REFERENCES spatial.walking_networks(network_id),
    osm_way_id bigint NOT NULL,
    segment_index integer NOT NULL,
    from_node_id bigint NOT NULL,
    to_node_id bigint NOT NULL,
    length_m double precision NOT NULL CHECK (length_m>0),
    highway text NOT NULL,
    forward_allowed boolean NOT NULL,
    reverse_allowed boolean NOT NULL,
    PRIMARY KEY (network_id,osm_way_id,segment_index),
    FOREIGN KEY (network_id,from_node_id) REFERENCES spatial.walking_nodes(network_id,osm_node_id),
    FOREIGN KEY (network_id,to_node_id) REFERENCES spatial.walking_nodes(network_id,osm_node_id),
    CHECK (forward_allowed OR reverse_allowed)
);
CREATE INDEX IF NOT EXISTS walking_edges_from_idx ON spatial.walking_edges(network_id,from_node_id);
CREATE INDEX IF NOT EXISTS walking_edges_to_idx ON spatial.walking_edges(network_id,to_node_id);

CREATE TABLE IF NOT EXISTS spatial.walking_destination_snaps (
    network_id text NOT NULL REFERENCES spatial.walking_networks(network_id),
    destination_kind text NOT NULL CHECK (destination_kind IN ('poi','station')),
    destination_key text NOT NULL,
    category text NOT NULL CHECK (category IN ('food_social','cultural_tourist','station')),
    snapped_node_id bigint NOT NULL,
    component_id integer NOT NULL,
    snap_distance_m double precision NOT NULL CHECK (snap_distance_m>=0),
    large_snap boolean NOT NULL,
    severe_snap boolean NOT NULL,
    PRIMARY KEY (network_id,destination_kind,destination_key),
    FOREIGN KEY (network_id,snapped_node_id) REFERENCES spatial.walking_nodes(network_id,osm_node_id)
);
CREATE INDEX IF NOT EXISTS walking_dest_snaps_node_idx ON spatial.walking_destination_snaps(network_id,snapped_node_id);

CREATE TABLE IF NOT EXISTS features.walking_listing_snaps (
    network_id text NOT NULL REFERENCES spatial.walking_networks(network_id),
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    snapped_node_id bigint,
    component_id integer,
    snap_distance_m double precision CHECK (snap_distance_m>=0),
    large_snap boolean,
    severe_snap boolean,
    PRIMARY KEY (network_id,snapshot_date,listing_id),
    FOREIGN KEY (snapshot_date,listing_id) REFERENCES clean.airbnb_listings(snapshot_date,listing_id),
    FOREIGN KEY (network_id,snapped_node_id) REFERENCES spatial.walking_nodes(network_id,osm_node_id)
);
CREATE INDEX IF NOT EXISTS walking_listing_snaps_node_idx ON features.walking_listing_snaps(network_id,snapped_node_id);

CREATE TABLE IF NOT EXISTS features.walking_accessibility (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    network_id text NOT NULL REFERENCES spatial.walking_networks(network_id),
    destination_taxonomy_version text NOT NULL,
    walking_speed_kmh numeric(4,2) NOT NULL CHECK (walking_speed_kmh=4.80),
    snapped_node_id bigint,
    listing_snap_distance_m double precision CHECK (listing_snap_distance_m>=0),
    nearest_station_key text REFERENCES spatial.transit_stations(station_key),
    nearest_station_network_distance_m double precision CHECK (nearest_station_network_distance_m>=0),
    nearest_station_walking_minutes double precision CHECK (nearest_station_walking_minutes>=0),
    nearest_station_coverage_complete boolean,
    food_social_w_10 integer CHECK (food_social_w_10>=0),
    food_social_w_15 integer CHECK (food_social_w_15>=0),
    food_social_w_20 integer CHECK (food_social_w_20>=0),
    cultural_tourist_w_10 integer CHECK (cultural_tourist_w_10>=0),
    cultural_tourist_w_15 integer CHECK (cultural_tourist_w_15>=0),
    cultural_tourist_w_20 integer CHECK (cultural_tourist_w_20>=0),
    routing_status text NOT NULL CHECK (routing_status IN ('ok','invalid_coordinates','no_walk_node','no_reachable_station')),
    distance_crs_epsg integer NOT NULL CHECK (distance_crs_epsg=25832),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date,listing_id),
    FOREIGN KEY (snapshot_date,listing_id) REFERENCES clean.airbnb_listings(snapshot_date,listing_id),
    FOREIGN KEY (network_id,snapped_node_id) REFERENCES spatial.walking_nodes(network_id,osm_node_id)
);
CREATE INDEX IF NOT EXISTS walking_accessibility_network_idx ON features.walking_accessibility(network_id,routing_status);

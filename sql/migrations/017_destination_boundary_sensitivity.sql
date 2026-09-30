-- Post-completion endpoint-only sensitivity. Original destination tables and graph are untouched.
CREATE VIEW spatial.study_union_boundary_sensitivity AS
SELECT ST_UnaryUnion(ST_Collect(geom_25832)) AS geom_25832
FROM spatial.official_municipalities
WHERE municipality_code IN ('0101', '0147');

CREATE VIEW spatial.osm_pois_study_union_sensitivity AS
SELECT p.destination_key, p.category, p.source_file_id, p.taxonomy_version, p.geom_25832
FROM spatial.osm_pois p CROSS JOIN spatial.study_union_boundary_sensitivity u
WHERE ST_Covers(u.geom_25832, p.geom_25832);

CREATE VIEW spatial.transit_stations_study_union_sensitivity AS
SELECT s.station_key, s.station_mode, s.source_file_id, s.taxonomy_version, s.geom_25832
FROM spatial.transit_stations s CROSS JOIN spatial.study_union_boundary_sensitivity u
WHERE ST_Covers(u.geom_25832, s.geom_25832);

CREATE TABLE features.destination_boundary_sensitivity (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    network_id text NOT NULL REFERENCES spatial.walking_networks(network_id),
    nearest_station_euclidean_m_clip double precision CHECK (nearest_station_euclidean_m_clip >= 0),
    nearest_station_walking_minutes_clip double precision CHECK (nearest_station_walking_minutes_clip >= 0),
    food_social_800m_clip integer NOT NULL CHECK (food_social_800m_clip >= 0),
    cultural_tourist_800m_clip integer NOT NULL CHECK (cultural_tourist_800m_clip >= 0),
    food_social_w_10_clip integer NOT NULL CHECK (food_social_w_10_clip >= 0),
    cultural_tourist_w_10_clip integer NOT NULL CHECK (cultural_tourist_w_10_clip >= 0),
    distance_crs_epsg integer NOT NULL DEFAULT 25832 CHECK (distance_crs_epsg = 25832),
    walking_speed_kmh numeric(4,2) NOT NULL DEFAULT 4.80 CHECK (walking_speed_kmh = 4.80),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, listing_id),
    FOREIGN KEY (snapshot_date, listing_id) REFERENCES clean.airbnb_listings(snapshot_date, listing_id)
);

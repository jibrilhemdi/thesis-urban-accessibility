-- Provider polygons are candidate geography, not official municipality/district boundaries.
CREATE TABLE IF NOT EXISTS spatial.provider_neighbourhoods (
    area_id text PRIMARY KEY,
    provider_label text NOT NULL UNIQUE,
    municipality_proxy text NOT NULL CHECK (municipality_proxy IN ('Copenhagen', 'Frederiksberg')),
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    source_crs_text text NOT NULL,
    source_crs_basis text NOT NULL,
    geom_source geometry(MultiPolygon, 4326) NOT NULL,
    geom_4326 geometry(MultiPolygon, 4326) NOT NULL,
    geom_25832 geometry(MultiPolygon, 25832) NOT NULL,
    boundary_25832 geometry(MultiLineString, 25832) NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS provider_neighbourhoods_geom_4326_gist
    ON spatial.provider_neighbourhoods USING gist (geom_4326);
CREATE INDEX IF NOT EXISTS provider_neighbourhoods_geom_25832_gist
    ON spatial.provider_neighbourhoods USING gist (geom_25832);
CREATE INDEX IF NOT EXISTS provider_neighbourhoods_boundary_25832_gist
    ON spatial.provider_neighbourhoods USING gist (boundary_25832);

CREATE TABLE IF NOT EXISTS spatial.study_area (
    area_kind text PRIMARY KEY,
    description text NOT NULL,
    source_file_id bigint REFERENCES meta.source_files(source_file_id),
    buffer_metres numeric,
    crs_for_operations integer NOT NULL DEFAULT 25832 CHECK (crs_for_operations = 25832),
    geom_4326 geometry(MultiPolygon, 4326) NOT NULL,
    geom_25832 geometry(MultiPolygon, 25832) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS study_area_geom_4326_gist ON spatial.study_area USING gist (geom_4326);
CREATE INDEX IF NOT EXISTS study_area_geom_25832_gist ON spatial.study_area USING gist (geom_25832);

CREATE TABLE IF NOT EXISTS spatial.reference_points (
    reference_id text PRIMARY KEY,
    description text NOT NULL,
    source_url text NOT NULL,
    source_accessed_on date NOT NULL,
    source_crs_text text NOT NULL,
    geom_4326 geometry(Point, 4326) NOT NULL,
    geom_25832 geometry(Point, 25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS reference_points_geom_25832_gist
    ON spatial.reference_points USING gist (geom_25832);

CREATE TABLE IF NOT EXISTS features.listing_spatial_base (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    municipality_proxy text,
    cv_area_id text REFERENCES spatial.provider_neighbourhoods(area_id),
    provider_neighbourhood text,
    polygon_match_count integer NOT NULL CHECK (polygon_match_count >= 0),
    provider_label_matches_polygon boolean,
    assignment_status text NOT NULL,
    context_statistical_unit_id text,
    context_assignment_status text NOT NULL,
    near_provider_border_100m boolean NOT NULL,
    distance_centre_euclidean_km double precision NOT NULL CHECK (distance_centre_euclidean_km >= 0),
    distance_crs_epsg integer NOT NULL DEFAULT 25832 CHECK (distance_crs_epsg = 25832),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, listing_id),
    FOREIGN KEY (snapshot_date, listing_id) REFERENCES clean.airbnb_listings(snapshot_date, listing_id),
    CHECK (context_statistical_unit_id IS NULL OR context_assignment_status = 'verified')
);
CREATE INDEX IF NOT EXISTS listing_spatial_base_cv_area_idx
    ON features.listing_spatial_base (cv_area_id, snapshot_date);

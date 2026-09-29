-- Official municipality boundaries: DAWA/DAGI; district boundaries: Copenhagen municipal WFS.
CREATE TABLE IF NOT EXISTS spatial.official_municipalities (
    municipality_code text PRIMARY KEY,
    municipality_name text NOT NULL,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    source_crs_epsg integer NOT NULL CHECK (source_crs_epsg = 4326),
    source_geo_changed_at timestamptz,
    geom_source geometry(MultiPolygon,4326) NOT NULL,
    geom_4326 geometry(MultiPolygon,4326) NOT NULL,
    geom_25832 geometry(MultiPolygon,25832) NOT NULL,
    boundary_25832 geometry(MultiLineString,25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS official_municipalities_geom_gist ON spatial.official_municipalities USING gist(geom_4326);
CREATE INDEX IF NOT EXISTS official_municipalities_metric_gist ON spatial.official_municipalities USING gist(geom_25832);

CREATE TABLE IF NOT EXISTS spatial.official_copenhagen_districts (
    district_number integer PRIMARY KEY CHECK (district_number BETWEEN 1 AND 10),
    district_name text NOT NULL UNIQUE,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    source_crs_epsg integer NOT NULL CHECK (source_crs_epsg = 4326),
    geom_source geometry(MultiPolygon,4326) NOT NULL,
    geom_4326 geometry(MultiPolygon,4326) NOT NULL,
    geom_25832 geometry(MultiPolygon,25832) NOT NULL,
    boundary_25832 geometry(MultiLineString,25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS official_districts_geom_gist ON spatial.official_copenhagen_districts USING gist(geom_4326);
CREATE INDEX IF NOT EXISTS official_districts_metric_gist ON spatial.official_copenhagen_districts USING gist(geom_25832);

-- Canonical candidate CV units: ten official Copenhagen districts plus Frederiksberg municipality.
CREATE OR REPLACE VIEW spatial.official_cv_areas AS
SELECT 'cph_' || lpad(district_number::text,2,'0') AS area_id, district_name AS area_name,
       '0101'::text AS municipality_code, source_file_id, geom_4326, geom_25832, boundary_25832
FROM spatial.official_copenhagen_districts
UNION ALL
SELECT 'frederiksberg_0147', municipality_name, municipality_code,
       source_file_id, geom_4326, geom_25832, boundary_25832
FROM spatial.official_municipalities WHERE municipality_code='0147';

ALTER TABLE features.listing_spatial_base
    ADD COLUMN IF NOT EXISTS official_municipality_code text,
    ADD COLUMN IF NOT EXISTS official_municipality_match_count integer,
    ADD COLUMN IF NOT EXISTS official_cv_area_id text,
    ADD COLUMN IF NOT EXISTS official_cv_match_count integer,
    ADD COLUMN IF NOT EXISTS official_assignment_status text,
    ADD COLUMN IF NOT EXISTS near_official_border_100m boolean;
CREATE INDEX IF NOT EXISTS listing_spatial_base_official_cv_idx
    ON features.listing_spatial_base (official_cv_area_id,snapshot_date);

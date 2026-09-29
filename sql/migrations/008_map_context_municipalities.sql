-- Official neighbouring municipalities are cartographic context only.
-- Keep them separate from the two-municipality study-area table.
CREATE TABLE IF NOT EXISTS spatial.map_context_municipalities (
    municipality_code text PRIMARY KEY,
    municipality_name text NOT NULL,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    source_crs_epsg integer NOT NULL CHECK (source_crs_epsg = 4326),
    geom_source geometry(MultiPolygon,4326) NOT NULL,
    geom_4326 geometry(MultiPolygon,4326) NOT NULL,
    geom_25832 geometry(MultiPolygon,25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS map_context_municipalities_geom_gist
    ON spatial.map_context_municipalities USING gist(geom_4326);
CREATE INDEX IF NOT EXISTS map_context_municipalities_metric_gist
    ON spatial.map_context_municipalities USING gist(geom_25832);

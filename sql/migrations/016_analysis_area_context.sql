-- Post-completion context amendment. This does not change the frozen Phase 7/9 view.
CREATE TABLE IF NOT EXISTS features.analysis_area_context (
    analysis_area_code text PRIMARY KEY,
    analysis_area_name text NOT NULL,
    analysis_area_geography text NOT NULL CHECK (analysis_area_geography IN ('Copenhagen district','Frederiksberg municipality proxy')),
    analysis_area_source_provider text NOT NULL,
    population_count integer NOT NULL CHECK (population_count > 0),
    population_period text NOT NULL,
    area_m2 double precision NOT NULL CHECK (area_m2 > 0),
    area_km2 double precision NOT NULL CHECK (area_km2 > 0),
    population_density_per_km2 double precision NOT NULL CHECK (population_density_per_km2 > 0),
    log_population_density double precision NOT NULL,
    average_disposable_income_dkk numeric NOT NULL CHECK (average_disposable_income_dkk > 0),
    income_100k_dkk numeric NOT NULL CHECK (income_100k_dkk > 0),
    income_period text NOT NULL,
    analysis_area_is_municipality_proxy boolean NOT NULL,
    analysis_area_income_definition_differs boolean NOT NULL,
    analysis_area_household_definition_unverified boolean NOT NULL,
    analysis_area_dwelling_definition_unverified boolean NOT NULL,
    area_crs_epsg integer NOT NULL CHECK (area_crs_epsg = 25832),
    area_includes_water_status text NOT NULL,
    population_source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    income_source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    boundary_source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    audited_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW analysis.analysis_dataset_context_v1 AS
SELECT a.*,
       c.analysis_area_code,
       c.analysis_area_name,
       c.analysis_area_geography,
       c.analysis_area_source_provider,
       c.population_count AS analysis_area_population_count,
       c.population_period AS analysis_area_population_period,
       c.area_m2 AS analysis_area_area_m2,
       c.area_km2 AS analysis_area_area_km2,
       c.population_density_per_km2 AS analysis_area_population_density_per_km2,
       c.log_population_density AS log_analysis_area_population_density,
       c.average_disposable_income_dkk AS analysis_area_average_disposable_income_dkk,
       c.income_100k_dkk AS analysis_area_income_100k_dkk,
       c.income_period AS analysis_area_income_period,
       c.analysis_area_is_municipality_proxy,
       c.analysis_area_income_definition_differs,
       c.analysis_area_household_definition_unverified,
       c.analysis_area_dwelling_definition_unverified,
       c.area_crs_epsg AS analysis_area_area_crs_epsg,
       c.area_includes_water_status AS analysis_area_area_includes_water_status,
       c.population_source_file_id AS analysis_area_population_source_file_id,
       c.income_source_file_id AS analysis_area_income_source_file_id,
       c.boundary_source_file_id AS analysis_area_boundary_source_file_id
FROM analysis.analysis_dataset_v1 a
LEFT JOIN features.analysis_area_context c
  ON a.official_cv_area_id = c.analysis_area_code;

COMMENT ON VIEW analysis.analysis_dataset_context_v1 IS
'Post-completion, mixed-resolution area context. Phase 9 view untouched; NULL context for unassigned listings. Do not treat Frederiksberg as a neighbourhood or pooled income as harmonised.';

-- Context observations retain their own geography, period, concept and source.
-- Municipality measures are never stored as neighbourhood attributes.
CREATE TABLE IF NOT EXISTS clean.municipality_context_measures (
    municipality_code text NOT NULL CHECK (municipality_code IN ('101', '147')),
    municipality_name text NOT NULL,
    measure_code text NOT NULL,
    reference_period text NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL,
    population_definition text NOT NULL,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    cleaned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (municipality_code, measure_code, reference_period)
);

CREATE TABLE IF NOT EXISTS clean.copenhagen_district_context_measures (
    district_code text NOT NULL CHECK (district_code ~ '^10(0[1-9]|10)$'),
    district_name text NOT NULL,
    measure_code text NOT NULL,
    reference_period text NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL,
    population_definition text NOT NULL,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    cleaned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (district_code, measure_code, reference_period)
);

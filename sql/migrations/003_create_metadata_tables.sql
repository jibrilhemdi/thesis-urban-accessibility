CREATE TABLE IF NOT EXISTS meta.schema_migrations (
    migration_name text PRIMARY KEY,
    file_hash_sha256 char(64) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.source_files (
    source_file_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename text NOT NULL,
    relative_path text NOT NULL UNIQUE,
    source_name text NOT NULL,
    source_url text,
    file_hash_sha256 char(64) NOT NULL CHECK (file_hash_sha256 ~ '^[0-9a-f]{64}$'),
    file_size bigint NOT NULL CHECK (file_size >= 0),
    source_date date,
    snapshot_date date,
    acquisition_date date,
    geographic_extent text,
    imported_at timestamptz,
    row_count bigint CHECK (row_count >= 0),
    notes text,
    registered_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.import_runs (
    import_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    source_hash_sha256 char(64) NOT NULL,
    target_table text NOT NULL,
    import_options jsonb NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    rows_loaded bigint CHECK (rows_loaded >= 0),
    error_message text
);

CREATE UNIQUE INDEX IF NOT EXISTS import_runs_one_success_per_file_table
    ON meta.import_runs (source_file_id, target_table) WHERE status = 'success';

-- Fold assignment is based on projected coordinates and official municipality,
-- never price values or accessibility outcomes. Runner inserts once and refuses
-- to silently change an existing freeze.
CREATE TABLE IF NOT EXISTS analysis.spatial_cv_folds_v1 (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    block_id text NOT NULL,
    fold_id integer NOT NULL CHECK (fold_id BETWEEN 1 AND 5),
    municipality_code text NOT NULL CHECK (municipality_code IN ('0101','0147')),
    crs_epsg integer NOT NULL CHECK (crs_epsg=25832),
    grid_size_m integer NOT NULL CHECK (grid_size_m=1000),
    assignment_method text NOT NULL CHECK (assignment_method='StratifiedGroupKFold'),
    random_seed integer NOT NULL CHECK (random_seed=20260929),
    frozen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date,listing_id),
    FOREIGN KEY (snapshot_date,listing_id) REFERENCES clean.airbnb_listings(snapshot_date,listing_id)
);
CREATE INDEX IF NOT EXISTS spatial_cv_folds_block_idx
    ON analysis.spatial_cv_folds_v1 (block_id,fold_id);

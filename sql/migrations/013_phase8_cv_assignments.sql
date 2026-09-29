-- Phase 8: fixed, outcome-blind random/geographic/block CV identifiers.
-- The Phase 7 one-kilometre folds remain in their original frozen table.
CREATE TABLE IF NOT EXISTS analysis.cv_assignments (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    random_fold smallint NOT NULL CHECK (random_fold BETWEEN 1 AND 5),
    geographic_fold smallint CHECK (geographic_fold BETWEEN 1 AND 11),
    heldout_area text,
    block_1km_id text,
    block_1km_fold smallint CHECK (block_1km_fold BETWEEN 1 AND 5),
    block_1500m_id text,
    block_1500m_fold smallint CHECK (block_1500m_fold BETWEEN 1 AND 5),
    random_seed integer NOT NULL CHECK (random_seed=20260929),
    block_1500m_seed integer NOT NULL CHECK (block_1500m_seed=20261034),
    assignment_version text NOT NULL CHECK (assignment_version='phase08_v1'),
    block_crs_epsg integer NOT NULL CHECK (block_crs_epsg=25832),
    frozen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date,listing_id),
    FOREIGN KEY (snapshot_date,listing_id) REFERENCES clean.airbnb_listings(snapshot_date,listing_id),
    CHECK ((geographic_fold IS NULL) = (heldout_area IS NULL)),
    CHECK ((block_1km_id IS NULL) = (block_1km_fold IS NULL)),
    CHECK ((block_1500m_id IS NULL) = (block_1500m_fold IS NULL))
);
CREATE INDEX IF NOT EXISTS cv_assignments_random_idx ON analysis.cv_assignments(random_fold);
CREATE INDEX IF NOT EXISTS cv_assignments_geographic_idx ON analysis.cv_assignments(heldout_area);
CREATE INDEX IF NOT EXISTS cv_assignments_block1500_idx ON analysis.cv_assignments(block_1500m_fold);

-- Sparse list of records excluded from training in a buffered leave-area-out
-- sensitivity. Same-area records are test observations and are never listed.
CREATE TABLE IF NOT EXISTS analysis.cv_buffer_exclusions (
    heldout_area text NOT NULL,
    buffer_m integer NOT NULL CHECK (buffer_m IN (500,1000)),
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    crs_epsg integer NOT NULL CHECK (crs_epsg=25832),
    assignment_version text NOT NULL CHECK (assignment_version='phase08_v1'),
    frozen_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (heldout_area,buffer_m,snapshot_date,listing_id),
    FOREIGN KEY (snapshot_date,listing_id) REFERENCES analysis.cv_assignments(snapshot_date,listing_id)
);
CREATE INDEX IF NOT EXISTS cv_buffer_listing_idx
    ON analysis.cv_buffer_exclusions(snapshot_date,listing_id);

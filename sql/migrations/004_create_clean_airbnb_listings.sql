CREATE TABLE IF NOT EXISTS clean.airbnb_listings (
    snapshot_date date NOT NULL,
    listing_id bigint NOT NULL,
    source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id),
    last_scraped date,
    neighbourhood_cleansed text,
    room_type text,
    property_type text,
    latitude double precision,
    longitude double precision,
    geom geometry(Point, 4326),
    geom_25832 geometry(Point, 25832),
    price_raw text,
    price_nightly numeric(14, 2),
    log_price double precision,
    accommodates integer,
    bedrooms numeric,
    bathrooms numeric,
    bathrooms_text text,
    amenities_raw text,
    minimum_nights integer,
    instant_bookable text,
    host_is_superhost text,
    host_listings_count integer,
    calculated_host_listings_count integer,
    number_of_reviews integer,
    number_of_reviews_ltm integer,
    review_scores_rating numeric,
    in_study_area boolean NOT NULL,
    entire_home_apt boolean NOT NULL,
    conventional_residential boolean NOT NULL,
    valid_price boolean NOT NULL,
    valid_coordinates boolean NOT NULL,
    primary_sample_candidate boolean NOT NULL,
    cleaned_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, listing_id),
    CHECK (NOT primary_sample_candidate OR
           (in_study_area AND entire_home_apt AND conventional_residential
            AND valid_price AND valid_coordinates))
);

CREATE INDEX IF NOT EXISTS airbnb_listings_geom_gist
    ON clean.airbnb_listings USING gist (geom);
CREATE INDEX IF NOT EXISTS airbnb_listings_geom_25832_gist
    ON clean.airbnb_listings USING gist (geom_25832);
CREATE INDEX IF NOT EXISTS airbnb_listings_primary_candidate_idx
    ON clean.airbnb_listings (snapshot_date, primary_sample_candidate);

CREATE OR REPLACE VIEW analysis.airbnb_primary_sample_candidates AS
SELECT * FROM clean.airbnb_listings WHERE primary_sample_candidate;

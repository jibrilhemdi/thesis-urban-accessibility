WITH source_rows AS (
    SELECT *
    FROM raw.inside_airbnb_listings
    WHERE _source_file_id = :listings_file_id
),
typed AS (
    SELECT
        CAST(:snapshot_date AS date) AS snapshot_date,
        id::bigint AS listing_id,
        CAST(:listings_file_id AS bigint) AS source_file_id,
        CASE WHEN last_scraped ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
             THEN last_scraped::date END AS last_scraped,
        NULLIF(neighbourhood_cleansed, '') AS neighbourhood_cleansed,
        NULLIF(room_type, '') AS room_type,
        NULLIF(property_type, '') AS property_type,
        CASE WHEN latitude ~ '^-?[0-9]+([.][0-9]+)?$'
             THEN latitude::double precision END AS latitude,
        CASE WHEN longitude ~ '^-?[0-9]+([.][0-9]+)?$'
             THEN longitude::double precision END AS longitude,
        price AS price_raw,
        CASE WHEN price ~ '^[$]([0-9]+|[0-9]{1,3}(,[0-9]{3})+)([.][0-9]{2})?$'
             THEN replace(replace(price, '$', ''), ',', '')::numeric(14, 2) END AS price_nightly,
        CASE WHEN accommodates ~ '^[0-9]+$' THEN accommodates::integer END AS accommodates,
        CASE WHEN bedrooms ~ '^[0-9]+([.][0-9]+)?$' THEN bedrooms::numeric END AS bedrooms,
        CASE WHEN bathrooms ~ '^[0-9]+([.][0-9]+)?$' THEN bathrooms::numeric END AS bathrooms,
        NULLIF(bathrooms_text, '') AS bathrooms_text,
        amenities AS amenities_raw,
        CASE WHEN minimum_nights ~ '^[0-9]+$' THEN minimum_nights::integer END AS minimum_nights,
        NULLIF(instant_bookable, '') AS instant_bookable,
        NULLIF(host_is_superhost, '') AS host_is_superhost,
        CASE WHEN host_listings_count ~ '^[0-9]+$' THEN host_listings_count::integer END AS host_listings_count,
        CASE WHEN calculated_host_listings_count ~ '^[0-9]+$'
             THEN calculated_host_listings_count::integer END AS calculated_host_listings_count,
        CASE WHEN number_of_reviews ~ '^[0-9]+$' THEN number_of_reviews::integer END AS number_of_reviews,
        CASE WHEN number_of_reviews_ltm ~ '^[0-9]+$' THEN number_of_reviews_ltm::integer END AS number_of_reviews_ltm,
        CASE WHEN review_scores_rating ~ '^[0-9]+([.][0-9]+)?$'
             THEN review_scores_rating::numeric END AS review_scores_rating
    FROM source_rows
),
flagged AS (
    SELECT
        typed.*,
        EXISTS (
            SELECT 1 FROM raw.inside_airbnb_neighbourhood_lookup AS lookup
            WHERE lookup._source_file_id = :lookup_file_id
              AND lookup.neighbourhood = typed.neighbourhood_cleansed
        ) AS in_study_area,
        room_type = 'Entire home/apt' AS entire_home_apt,
        property_type IN (
            'Entire rental unit', 'Entire condo', 'Entire home',
            'Entire townhouse', 'Entire villa', 'Entire loft'
        ) AS conventional_residential,
        price_nightly > 0 AS valid_price,
        latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180 AS valid_coordinates
    FROM typed
),
with_points AS (
    SELECT flagged.*,
           CASE WHEN valid_coordinates THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                END AS point_4326
    FROM flagged
)
INSERT INTO clean.airbnb_listings (
    snapshot_date, listing_id, source_file_id, last_scraped, neighbourhood_cleansed,
    room_type, property_type, latitude, longitude, geom, geom_25832,
    price_raw, price_nightly, log_price, accommodates, bedrooms, bathrooms,
    bathrooms_text, amenities_raw, minimum_nights, instant_bookable,
    host_is_superhost, host_listings_count, calculated_host_listings_count,
    number_of_reviews, number_of_reviews_ltm, review_scores_rating,
    in_study_area, entire_home_apt, conventional_residential, valid_price,
    valid_coordinates, primary_sample_candidate
)
SELECT
    snapshot_date, listing_id, source_file_id, last_scraped, neighbourhood_cleansed,
    room_type, property_type, latitude, longitude, point_4326,
    CASE WHEN point_4326 IS NOT NULL THEN ST_Transform(point_4326, 25832) END,
    price_raw, price_nightly,
    CASE WHEN price_nightly > 0 THEN ln(price_nightly::double precision) END,
    accommodates, bedrooms, bathrooms, bathrooms_text, amenities_raw,
    minimum_nights, instant_bookable, host_is_superhost, host_listings_count,
    calculated_host_listings_count, number_of_reviews, number_of_reviews_ltm,
    review_scores_rating,
    COALESCE(in_study_area, false), COALESCE(entire_home_apt, false),
    COALESCE(conventional_residential, false), COALESCE(valid_price, false),
    COALESCE(valid_coordinates, false),
    COALESCE(in_study_area, false) AND COALESCE(entire_home_apt, false)
    AND COALESCE(conventional_residential, false) AND COALESCE(valid_price, false)
    AND COALESCE(valid_coordinates, false)
FROM with_points;

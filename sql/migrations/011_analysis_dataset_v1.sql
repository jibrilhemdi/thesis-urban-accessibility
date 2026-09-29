-- Phase 7: one listing row; source-preserving LEFT JOINs on the composite key.
-- District statistics are exploratory only: numeric district/name agree, but the
-- official WFS polygon vintage is not verified against the StatBank vintage.
CREATE OR REPLACE VIEW analysis.analysis_dataset_v1 AS
WITH district_context AS (
    SELECT d.district_code, min(d.district_name) AS district_name,
           max(d.value) FILTER (WHERE d.measure_code='district_population'
               AND d.reference_period='2026Q3') AS district_population_2026q3,
           max(d.value) FILTER (WHERE d.measure_code='district_households'
               AND d.reference_period='2026Q1') AS district_households_2026q1,
           max(d.value) FILTER (WHERE d.measure_code='district_average_disposable_income'
               AND d.reference_period='2024') AS district_income_2024_dkk_person
    FROM clean.copenhagen_district_context_measures d
    GROUP BY d.district_code
), frederiksberg_context AS (
    SELECT max(value) FILTER (WHERE measure_code='total_population'
               AND reference_period='2026Q3') AS municipality_population_2026q3,
           max(value) FILTER (WHERE measure_code='households'
               AND reference_period='2026-01-01') AS municipality_households_2026q1,
           max(value) FILTER (WHERE measure_code='average_personal_disposable_income'
               AND reference_period='2024') AS municipality_income_2024_dkk_person
    FROM clean.municipality_context_measures WHERE municipality_code='147'
), joined AS (
    SELECT l.*, s.official_municipality_code, s.official_cv_area_id,
           s.official_assignment_status, s.near_official_border_100m,
           s.distance_centre_euclidean_km, s.distance_crs_epsg,
           e.taxonomy_version AS euclidean_taxonomy_version,
           e.count_coverage_complete AS euclidean_count_coverage_complete,
           e.nearest_station_distance_m AS nearest_station_euclidean_m,
           e.nearest_station_coverage_complete AS euclidean_station_coverage_complete,
           e.food_social_800m, e.food_social_1200m, e.food_social_1600m,
           e.cultural_tourist_800m, e.cultural_tourist_1200m, e.cultural_tourist_1600m,
           w.network_id, w.destination_taxonomy_version,
           w.walking_speed_kmh, w.routing_status,
           w.listing_snap_distance_m, w.nearest_station_walking_minutes,
           w.nearest_station_network_distance_m,
           w.nearest_station_coverage_complete AS walking_station_coverage_complete,
           w.food_social_w_10, w.food_social_w_15, w.food_social_w_20,
           w.cultural_tourist_w_10, w.cultural_tourist_w_15, w.cultural_tourist_w_20,
           d.district_code AS context_district_code, d.district_name AS context_district_name,
           d.district_population_2026q3, d.district_households_2026q1,
           d.district_income_2024_dkk_person,
           CASE WHEN s.official_cv_area_id='frederiksberg_0147'
                THEN f.municipality_population_2026q3 END AS frb_municipality_population_2026q3,
           CASE WHEN s.official_cv_area_id='frederiksberg_0147'
                THEN f.municipality_households_2026q1 END AS frb_municipality_households_2026q1,
           CASE WHEN s.official_cv_area_id='frederiksberg_0147'
                THEN f.municipality_income_2024_dkk_person END AS frb_municipality_income_2024_dkk_person,
           CASE WHEN s.official_cv_area_id='frederiksberg_0147'
                THEN 'municipality_proxy_different_source_definition'
                WHEN s.official_cv_area_id IS NULL THEN 'unassigned_official_area'
                WHEN d.district_code IS NULL THEN 'district_code_or_name_mismatch'
                ELSE 'district_code_name_match_vintage_unverified' END AS context_join_status
    FROM clean.airbnb_listings l
    LEFT JOIN features.listing_spatial_base s USING (snapshot_date,listing_id)
    LEFT JOIN features.euclidean_accessibility e USING (snapshot_date,listing_id)
    LEFT JOIN features.walking_accessibility w USING (snapshot_date,listing_id)
    LEFT JOIN spatial.official_copenhagen_districts od
        ON s.official_cv_area_id=('cph_' || lpad(od.district_number::text,2,'0'))
    LEFT JOIN district_context d
        ON d.district_code=('10' || lpad(od.district_number::text,2,'0'))
       AND replace(d.district_name,'/','-')=od.district_name
    CROSS JOIN frederiksberg_context f
)
SELECT snapshot_date, listing_id, source_file_id, last_scraped,
       price_nightly, (valid_price AND price_nightly > 0) AS observed_positive_price,
       CASE WHEN price_nightly > 0 THEN ln(price_nightly::double precision) END AS log_price,
       NOT (valid_price AND price_nightly > 0) AS missing_or_invalid_price,
       in_study_area, entire_home_apt, conventional_residential,
       valid_price, valid_coordinates, primary_sample_candidate,
       property_type, room_type, accommodates, bedrooms, bathrooms AS bathrooms_structured,
       bathrooms_text,
       CASE WHEN bathrooms IS NOT NULL THEN bathrooms
            WHEN bathrooms_text ~* '^[0-9]+([.][0-9]+)? baths?$'
                THEN substring(bathrooms_text from '^([0-9]+([.][0-9]+)?)')::numeric
            WHEN bathrooms_text='Half-bath' THEN 0.5::numeric
       END AS bathrooms_effective,
       CASE WHEN bathrooms IS NOT NULL THEN 'structured'
            WHEN bathrooms_text ~* '^[0-9]+([.][0-9]+)? baths?$'
                OR bathrooms_text='Half-bath' THEN 'source_text'
            ELSE 'missing' END AS bathrooms_source,
       CASE WHEN bathrooms IS NOT NULL AND bathrooms_text ~* '^[0-9]+([.][0-9]+)? baths?$'
                 THEN bathrooms <> substring(bathrooms_text from '^([0-9]+([.][0-9]+)?)')::numeric
            WHEN bathrooms IS NOT NULL AND bathrooms_text='Half-bath' THEN bathrooms <> 0.5
            ELSE false END AS bathrooms_source_disagreement,
       minimum_nights,
       CASE WHEN minimum_nights >= 0 THEN ln(1+minimum_nights::double precision) END AS log1p_minimum_nights,
       CASE WHEN lower(instant_bookable) IN ('t','true','yes') THEN true
            WHEN lower(instant_bookable) IN ('f','false','no') THEN false END AS instant_bookable,
       CASE WHEN lower(host_is_superhost) IN ('t','true','yes') THEN true
            WHEN lower(host_is_superhost) IN ('f','false','no') THEN false END AS superhost,
       host_listings_count,
       CASE WHEN host_listings_count >= 0 THEN ln(1+host_listings_count::double precision) END AS log1p_host_listings_count,
       calculated_host_listings_count, number_of_reviews, number_of_reviews_ltm,
       review_scores_rating,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Wifi' END AS amenity_wifi,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Dishwasher' END AS amenity_dishwasher,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Washer' END AS amenity_washer,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Dryer' END AS amenity_dryer,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Dedicated workspace' END AS amenity_workspace,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Free parking on premises' END AS amenity_free_parking,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Private patio or balcony' END AS amenity_private_balcony,
       CASE WHEN amenities_raw IS NULL THEN NULL ELSE amenities_raw::jsonb ? 'Self check-in' END AS amenity_self_checkin,
       official_municipality_code, official_cv_area_id, official_assignment_status,
       near_official_border_100m, distance_centre_euclidean_km, distance_crs_epsg,
       euclidean_taxonomy_version, euclidean_count_coverage_complete,
       euclidean_station_coverage_complete, nearest_station_euclidean_m,
       food_social_800m, food_social_1200m, food_social_1600m,
       cultural_tourist_800m, cultural_tourist_1200m, cultural_tourist_1600m,
       network_id, destination_taxonomy_version, walking_speed_kmh, routing_status,
       listing_snap_distance_m, walking_station_coverage_complete,
       nearest_station_network_distance_m, nearest_station_walking_minutes,
       food_social_w_10, food_social_w_15, food_social_w_20,
       cultural_tourist_w_10, cultural_tourist_w_15, cultural_tourist_w_20,
       context_join_status, context_district_code, context_district_name,
       district_population_2026q3, district_households_2026q1,
       district_income_2024_dkk_person,
       frb_municipality_population_2026q3, frb_municipality_households_2026q1,
       frb_municipality_income_2024_dkk_person
FROM joined;

COMMENT ON VIEW analysis.analysis_dataset_v1 IS
'Phase 7 one-row-per-listing view. Context is exploratory with source/resolution-specific columns; official district polygon vintage versus StatBank geography is unverified. No outcome/predictor imputation.';

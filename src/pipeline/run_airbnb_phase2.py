"""Import the Airbnb snapshot, build clean listings, and export Phase 2 QA."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.db.raw_csv import ingest_csv
from src.db.sources import prepare_all_sources, register_records
from src.ingestion.common import PROJECT_ROOT


CONVENTIONAL_PROPERTY_TYPES = frozenset({
    "Entire rental unit", "Entire condo", "Entire home",
    "Entire townhouse", "Entire villa", "Entire loft",
})
CANONICAL_AMENITIES = (
    "Wifi", "Kitchen", "Dishwasher", "Washer", "Dryer",
    "Dedicated workspace", "Air conditioning", "Free parking on premises",
    "Private patio or balcony", "Self check-in",
)
EXPECTED_ROOM_TYPES = {"Entire home/apt", "Private room", "Shared room"}
SNAPSHOT_ROOT = Path("data/raw/inside_airbnb/copenhagen")
SAMPLE_STAGES = (
    ("raw_listings", "true"),
    ("in_study_area", "in_study_area"),
    ("entire_home_apt", "in_study_area AND entire_home_apt"),
    ("conventional_residential", "in_study_area AND entire_home_apt AND conventional_residential"),
    ("valid_positive_price", "in_study_area AND entire_home_apt AND conventional_residential AND valid_price"),
    ("valid_coordinates", "primary_sample_candidate"),
)


def property_type_reason(value: str) -> tuple[bool, str]:
    if value in CONVENTIONAL_PROPERTY_TYPES:
        return True, "Clearly self-contained conventional urban dwelling form"
    if value.startswith(("Private room", "Shared room")):
        return False, "Room-level accommodation, not a self-contained entire dwelling"
    if "hotel" in value.lower() or "serviced" in value.lower() or "hostel" in value.lower():
        return False, "Hotel, hostel, or serviced/commercial accommodation"
    if value in {"Entire place", "Casa particular"}:
        return False, "Ambiguous residential type; not verifiably conventional"
    return False, "Nonstandard, accessory, or holiday accommodation form"


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _source_id(conn, relative_path: Path, expected_snapshot: date) -> int:
    result = conn.execute(text(
        "SELECT source_file_id, snapshot_date FROM meta.source_files WHERE relative_path = :path "
        "AND imported_at IS NOT NULL"
    ), {"path": relative_path.as_posix()}).one_or_none()
    if result is None:
        raise RuntimeError(f"Raw file is not imported: {relative_path}")
    if result.snapshot_date != expected_snapshot:
        raise ValueError(f"Source snapshot metadata differs from requested date: {relative_path}")
    return result.source_file_id


def _preflight(conn, listings_id: int, lookup_id: int) -> int:
    listing_checks = conn.execute(text(
        "SELECT count(*) AS n, count(DISTINCT id) AS unique_ids, "
        "count(*) FILTER (WHERE id !~ '^[0-9]+$' OR id IS NULL) AS bad_ids, "
        "count(*) FILTER (WHERE price IS NOT NULL AND price <> '' "
        "AND price !~ '^[$]([0-9]+|[0-9]{1,3}(,[0-9]{3})+)([.][0-9]{2})?$') AS bad_prices "
        "FROM raw.inside_airbnb_listings WHERE _source_file_id = :id"
    ), {"id": listings_id}).mappings().one()
    if listing_checks["n"] == 0 or listing_checks["n"] != listing_checks["unique_ids"] or listing_checks["bad_ids"]:
        raise ValueError("Listing source has missing/duplicate/non-numeric IDs")
    if listing_checks["bad_prices"]:
        raise ValueError(f"Investigate {listing_checks['bad_prices']} unparsed nonempty source prices")
    numeric_patterns = {
        "accommodates": "^[0-9]+$", "bedrooms": "^[0-9]+([.][0-9]+)?$",
        "bathrooms": "^[0-9]+([.][0-9]+)?$", "minimum_nights": "^[0-9]+$",
        "host_listings_count": "^[0-9]+$", "calculated_host_listings_count": "^[0-9]+$",
        "number_of_reviews": "^[0-9]+$", "number_of_reviews_ltm": "^[0-9]+$",
        "review_scores_rating": "^[0-9]+([.][0-9]+)?$",
    }
    for field, pattern in numeric_patterns.items():
        invalid = conn.scalar(text(
            f"SELECT count(*) FROM raw.inside_airbnb_listings WHERE _source_file_id = :id "
            f"AND {field} IS NOT NULL AND {field} <> '' AND {field} !~ :pattern"
        ), {"id": listings_id, "pattern": pattern})
        if invalid:
            raise ValueError(f"Investigate {invalid} nonnumeric source values in {field}")
    room_types = set(conn.execute(text(
        "SELECT DISTINCT room_type FROM raw.inside_airbnb_listings WHERE _source_file_id = :id"
    ), {"id": listings_id}).scalars())
    if not room_types.issubset(EXPECTED_ROOM_TYPES):
        raise ValueError(f"Unexpected room types need review: {sorted(str(v) for v in room_types - EXPECTED_ROOM_TYPES)}")
    lookup = conn.execute(text(
        "SELECT count(*) AS n, count(DISTINCT neighbourhood) AS unique_names "
        "FROM raw.inside_airbnb_neighbourhood_lookup WHERE _source_file_id = :id"
    ), {"id": lookup_id}).mappings().one()
    if lookup["n"] == 0 or lookup["n"] != lookup["unique_names"]:
        raise ValueError("Neighbourhood lookup has missing or duplicate labels")
    return listing_checks["n"]


def build_clean_listings(engine: Engine, snapshot: date, snapshot_root: Path) -> int:
    listings_path = snapshot_root / "data/listings.csv.gz"
    lookup_path = snapshot_root / "visualisations/neighbourhoods.csv"
    sql_path = PROJECT_ROOT / "sql/queries/build_clean_airbnb_listings.sql"
    with engine.begin() as conn:
        listings_id = _source_id(conn, listings_path, snapshot)
        lookup_id = _source_id(conn, lookup_path, snapshot)
        expected = _preflight(conn, listings_id, lookup_id)
        existing = set(conn.execute(text(
            "SELECT DISTINCT source_file_id FROM clean.airbnb_listings WHERE snapshot_date = :snapshot"
        ), {"snapshot": snapshot}).scalars())
        if existing and existing != {listings_id}:
            raise ValueError("Snapshot already has clean listings from another source file")
        conn.execute(text("DELETE FROM clean.airbnb_listings WHERE snapshot_date = :snapshot"),
                     {"snapshot": snapshot})
        conn.execute(text(sql_path.read_text(encoding="utf-8")), {
            "snapshot_date": snapshot,
            "listings_file_id": listings_id,
            "lookup_file_id": lookup_id,
        })
        checks = conn.execute(text(
            "SELECT count(*) AS n, count(DISTINCT listing_id) AS unique_ids, "
            "count(*) FILTER (WHERE valid_coordinates AND (geom IS NULL OR geom_25832 IS NULL)) AS missing_geom, "
            "count(*) FILTER (WHERE geom IS NOT NULL AND ST_SRID(geom) <> 4326) AS wrong_geom_srid, "
            "count(*) FILTER (WHERE geom_25832 IS NOT NULL AND ST_SRID(geom_25832) <> 25832) AS wrong_metric_srid, "
            "count(*) FILTER (WHERE primary_sample_candidate AND (price_nightly <= 0 OR log_price IS NULL)) AS bad_primary_price, "
            "count(*) FILTER (WHERE primary_sample_candidate AND room_type <> 'Entire home/apt') AS bad_primary_room "
            "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot"
        ), {"snapshot": snapshot}).mappings().one()
        if checks["n"] != expected or checks["unique_ids"] != expected or any(
            checks[key] for key in ("missing_geom", "wrong_geom_srid", "wrong_metric_srid",
                                    "bad_primary_price", "bad_primary_room")
        ):
            raise RuntimeError(f"Clean listing QA failed: {dict(checks)}")
    return expected


def _sample_flow(engine: Engine, snapshot: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous: int | None = None
    with engine.connect() as conn:
        for stage, condition in SAMPLE_STAGES:
            count = conn.scalar(text(
                f"SELECT count(*) FROM clean.airbnb_listings WHERE snapshot_date = :snapshot AND {condition}"
            ), {"snapshot": snapshot})
            rows.append({"stage": stage, "remaining_n": count,
                         "excluded_at_stage_n": 0 if previous is None else previous - count})
            previous = count
    return rows


def _property_decisions(engine: Engine, snapshot: date) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        raw_rows = conn.execute(text(
            "SELECT property_type, count(*) AS all_listings_n, "
            "count(*) FILTER (WHERE entire_home_apt) AS entire_home_apt_n, "
            "count(*) FILTER (WHERE entire_home_apt AND valid_price) AS entire_home_apt_priced_n "
            "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot "
            "GROUP BY property_type ORDER BY property_type"
        ), {"snapshot": snapshot}).mappings().all()
    rows = []
    for source in raw_rows:
        value = source["property_type"] or "[missing]"
        include, reason = property_type_reason(value)
        rows.append({"property_type": value, "all_listings_n": source["all_listings_n"],
                     "entire_home_apt_n": source["entire_home_apt_n"],
                     "entire_home_apt_priced_n": source["entire_home_apt_priced_n"],
                     "include_as_conventional": include, "reason": reason})
    return rows


def _amenity_prevalence(engine: Engine, snapshot: date) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts: Counter[str] = Counter()
    listing_scope_n = 0
    parsed_n = 0
    invalid = 0
    all_tokens: set[str] = set()
    with engine.connect() as conn:
        result = conn.execution_options(stream_results=True).execute(text(
            "SELECT amenities_raw FROM clean.airbnb_listings "
            "WHERE snapshot_date = :snapshot AND entire_home_apt AND conventional_residential"
        ), {"snapshot": snapshot})
        for (raw_value,) in result:
            listing_scope_n += 1
            try:
                amenities = json.loads(raw_value)
            except (TypeError, ValueError):
                invalid += 1
                continue
            if not isinstance(amenities, list) or any(not isinstance(item, str) for item in amenities):
                invalid += 1
                continue
            parsed_n += 1
            unique = set(amenities)
            all_tokens.update(unique)
            counts.update(unique.intersection(CANONICAL_AMENITIES))
    rows = []
    for amenity in CANONICAL_AMENITIES:
        n = counts[amenity]
        prevalence = n / parsed_n if parsed_n else None
        rows.append({"amenity": amenity, "present_n": n, "denominator_n": parsed_n,
                     "prevalence": round(prevalence, 6) if prevalence is not None else None,
                     "internal_candidate": bool(prevalence is not None and 0.05 < prevalence < 0.95)})
    return rows, {"listing_scope_n": listing_scope_n, "parsed_n": parsed_n,
                  "invalid_json": invalid, "distinct_source_tokens": len(all_tokens)}


def _profile(engine: Engine, snapshot: date) -> dict[str, Any]:
    with engine.connect() as conn:
        price = [dict(row) for row in conn.execute(text(
            "SELECT primary_sample_candidate AS primary_only, count(*) AS n, "
            "min(price_nightly)::double precision AS price_min, "
            "percentile_cont(0.25) WITHIN GROUP (ORDER BY price_nightly::double precision) AS price_q1, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY price_nightly::double precision) AS price_median, "
            "percentile_cont(0.75) WITHIN GROUP (ORDER BY price_nightly::double precision) AS price_q3, "
            "max(price_nightly)::double precision AS price_max, "
            "percentile_cont(0.25) WITHIN GROUP (ORDER BY log_price) AS log_price_q1, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY log_price) AS log_price_median, "
            "percentile_cont(0.75) WITHIN GROUP (ORDER BY log_price) AS log_price_q3, "
            "min(log_price) AS log_price_min, max(log_price) AS log_price_max "
            "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot AND valid_price "
            "GROUP BY primary_sample_candidate ORDER BY primary_sample_candidate"
        ), {"snapshot": snapshot}).mappings()]
        price_all = dict(conn.execute(text(
            "SELECT count(*) AS n, min(price_nightly)::double precision AS price_min, "
            "percentile_cont(0.25) WITHIN GROUP (ORDER BY price_nightly::double precision) AS price_q1, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY price_nightly::double precision) AS price_median, "
            "percentile_cont(0.75) WITHIN GROUP (ORDER BY price_nightly::double precision) AS price_q3, "
            "max(price_nightly)::double precision AS price_max, "
            "min(log_price) AS log_price_min, "
            "percentile_cont(0.25) WITHIN GROUP (ORDER BY log_price) AS log_price_q1, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY log_price) AS log_price_median, "
            "percentile_cont(0.75) WITHIN GROUP (ORDER BY log_price) AS log_price_q3, "
            "max(log_price) AS log_price_max "
            "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot AND valid_price"
        ), {"snapshot": snapshot}).mappings().one())
        review = dict(conn.execute(text(
            "SELECT count(*) AS n, min(number_of_reviews) AS min_reviews, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY number_of_reviews) AS median_reviews, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY number_of_reviews) AS p95_reviews, "
            "max(number_of_reviews) AS max_reviews, "
            "count(*) FILTER (WHERE number_of_reviews = 0) AS zero_reviews "
            "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot"
        ), {"snapshot": snapshot}).mappings().one())
        coordinates = dict(conn.execute(text(
            "SELECT count(*) AS n, count(*) FILTER (WHERE valid_coordinates) AS valid_n, "
            "count(*) FILTER (WHERE geom IS NOT NULL AND geom_25832 IS NOT NULL) AS both_geom_n, "
            "min(latitude) AS latitude_min, max(latitude) AS latitude_max, "
            "min(longitude) AS longitude_min, max(longitude) AS longitude_max "
            "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot"
        ), {"snapshot": snapshot}).mappings().one())
        scrape = [dict(row) for row in conn.execute(text(
            "SELECT last_scraped, count(*) AS listings_n, "
            "count(*) FILTER (WHERE valid_price) AS priced_n "
            "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot "
            "GROUP BY last_scraped ORDER BY last_scraped"
        ), {"snapshot": snapshot}).mappings()]
        controls = ("accommodates", "bedrooms", "bathrooms", "bathrooms_text", "amenities_raw",
                    "minimum_nights", "instant_bookable", "host_is_superhost", "host_listings_count",
                    "calculated_host_listings_count", "number_of_reviews", "number_of_reviews_ltm",
                    "review_scores_rating")
        missingness = []
        for field in controls:
            result = conn.execute(text(
                f"SELECT count(*) AS n, count(*) FILTER (WHERE {field} IS NULL) AS missing_n "
                "FROM clean.airbnb_listings WHERE snapshot_date = :snapshot"
            ), {"snapshot": snapshot}).mappings().one()
            missingness.append({"field": field, "listings_n": result["n"],
                                "missing_n": result["missing_n"]})
    return {"price_all": price_all, "price_by_primary": price, "review": review,
            "coordinates": coordinates, "scrape": scrape, "missingness": missingness}


def _format_number(value: Any) -> str:
    return "NA" if value is None else f"{float(value):,.2f}"


def export_phase2(engine: Engine, snapshot: date) -> dict[str, Any]:
    flow = _sample_flow(engine, snapshot)
    properties = _property_decisions(engine, snapshot)
    amenities, amenity_qa = _amenity_prevalence(engine, snapshot)
    profile = _profile(engine, snapshot)
    with engine.connect() as conn:
        imported_rows = dict(conn.execute(text(
            "SELECT target_table, rows_loaded FROM meta.import_runs "
            "WHERE status = 'success' AND target_table IN "
            "('raw.inside_airbnb_listings', 'raw.inside_airbnb_calendar', "
            "'raw.inside_airbnb_reviews', 'raw.inside_airbnb_neighbourhood_lookup')"
        )).all())
    if len(imported_rows) != 4:
        raise RuntimeError("All four Airbnb raw imports must succeed before Phase 2 export")
    output_root = PROJECT_ROOT / "outputs/tables"
    _write_csv(output_root / "sample_construction.csv", flow,
               ["stage", "remaining_n", "excluded_at_stage_n"])
    _write_csv(output_root / "property_type_decisions.csv", properties,
               ["property_type", "all_listings_n", "entire_home_apt_n",
                "entire_home_apt_priced_n", "include_as_conventional", "reason"])
    _write_csv(output_root / "amenities_prevalence.csv", amenities,
               ["amenity", "present_n", "denominator_n", "prevalence", "internal_candidate"])
    _write_csv(output_root / "control_missingness.csv", profile["missingness"],
               ["field", "listings_n", "missing_n"])
    primary_price = next((row for row in profile["price_by_primary"] if row["primary_only"]), None)
    price_rows = [dict(sample="all_valid_prices", **profile["price_all"])]
    if primary_price:
        price_rows.append({"sample": "primary_candidate", **{key: value for key, value in primary_price.items()
                                                       if key != "primary_only"}})
    price_columns = ["sample", "n", "price_min", "price_q1", "price_median", "price_q3",
                     "price_max", "log_price_min", "log_price_q1", "log_price_median",
                     "log_price_q3", "log_price_max"]
    _write_csv(output_root / "price_distribution.csv", price_rows, price_columns)

    property_lines = "\n".join(
        f"| {row['property_type']} | {row['all_listings_n']:,} | "
        f"{'Include' if row['include_as_conventional'] else 'Exclude'} | {row['reason']} |"
        for row in properties
    )
    flow_lines = "\n".join(
        f"| {row['stage']} | {row['remaining_n']:,} | {row['excluded_at_stage_n']:,} |"
        for row in flow
    )
    amenity_lines = "\n".join(
        f"| {row['amenity']} | {row['present_n']:,}/{row['denominator_n']:,} | "
        f"{row['prevalence']:.1%} | {'Yes' if row['internal_candidate'] else 'No'} |"
        for row in amenities
    )
    missing_lines = "\n".join(
        f"| {row['field']} | {row['missing_n']:,}/{row['listings_n']:,} |"
        for row in profile["missingness"]
    )
    price_lines = "\n".join(
        f"| {row['sample']} | {row['n']:,} | {_format_number(row['price_min'])} | "
        f"{_format_number(row['price_q1'])} | {_format_number(row['price_median'])} | "
        f"{_format_number(row['price_q3'])} | {_format_number(row['price_max'])} | "
        f"{_format_number(row['log_price_min'])} | {_format_number(row['log_price_q1'])} | "
        f"{_format_number(row['log_price_median'])} | {_format_number(row['log_price_q3'])} | "
        f"{_format_number(row['log_price_max'])} |"
        for row in price_rows
    )
    scrape_lines = "\n".join(
        f"| {row['last_scraped']} | {row['listings_n']:,} | {row['priced_n']:,} |"
        for row in profile["scrape"]
    )
    report = f"""# Phase 2 — Airbnb cleaning and primary sample candidate

Snapshot: {snapshot.isoformat()}. Generated from PostgreSQL `raw` and `clean` tables by `python -m src.pipeline.run_airbnb_phase2`; no local Parquet/CSV was used as input. Source CSV values are kept in versioned raw tables. The primary candidate remains a *listed-price* sample, not bookings or realised prices.

## Raw ingestion and sample funnel

Raw imports: {imported_rows['raw.inside_airbnb_listings']:,} detailed listings, {imported_rows['raw.inside_airbnb_calendar']:,} calendar rows, {imported_rows['raw.inside_airbnb_reviews']:,} detailed reviews, and {imported_rows['raw.inside_airbnb_neighbourhood_lookup']:,} provider neighbourhood labels. The listings have {flow[0]['remaining_n']:,} distinct IDs. Calendar and reviews are **not joined** to the listing table in Phase 2.

| Stage | Remaining N | Excluded at stage |
|---|---:|---:|
{flow_lines}

No review-count or availability restriction is used. Source `last_scraped` is provenance, not a replacement-price or model-control rule.

## Price and log-price

The numeric source `price` is treated as DKK per user confirmation; the file displays `$` and has no explicit currency code. No conversion or statistical outcome imputation is performed. Nonmatching or missing price strings remain NULL; non-positive numeric prices have NULL log-price and fail `valid_price`. Values below are listed nightly prices, not transactions.

| Sample | N | Price min | Price Q1 | Price median | Price Q3 | Price max | Log min | Log Q1 | Log median | Log Q3 | Log max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{price_lines}

The same aggregates are exported to `outputs/tables/price_distribution.csv`.

Price completeness by scrape date (diagnostic only):

| Scrape date | Listings | Valid prices |
|---|---:|---:|
{scrape_lines}

## Property-type decisions

The inclusion rule is based on clearly residential, self-contained urban dwelling forms, not predictive performance. Excluded rows remain in `clean.airbnb_listings` with flags. The table below covers every source category; `outputs/tables/property_type_decisions.csv` also gives entire-home and priced counts.

| Property type | All listings | Decision | Reason |
|---|---:|---|---|
{property_lines}

## Candidate controls and amenities

No predictor imputation is applied. Missingness from the clean listing table:

| Field | Missing / all listings |
|---|---:|
{missing_lines}

`instant_bookable` is empty for every archived listing and is unavailable as a Phase 2 control; no value is inferred from other fields.

Amenities were parsed as source JSON arrays for the {amenity_qa['listing_scope_n']:,} entire-home conventional listings, before price selection. {amenity_qa['parsed_n']:,} arrays parsed; {amenity_qa['invalid_json']:,} are invalid/missing and are not silently treated as amenity absence. {amenity_qa['distinct_source_tokens']:,} distinct raw tokens were observed; only controlled, accommodation-relevant labels are published below. Internal candidates require strict 5% < prevalence < 95% among parsed arrays, independent of price.

| Amenity | Present / parsed listings | Prevalence | Internal candidate |
|---|---:|---:|---|
{amenity_lines}

## Coordinates, reviews, and limitations

Coordinates: {profile['coordinates']['valid_n']:,}/{profile['coordinates']['n']:,} valid global longitude/latitude pairs; {profile['coordinates']['both_geom_n']:,} have both 4326 and 25832 point geometries. Longitude range {_format_number(profile['coordinates']['longitude_min'])}–{_format_number(profile['coordinates']['longitude_max'])}; latitude range {_format_number(profile['coordinates']['latitude_min'])}–{_format_number(profile['coordinates']['latitude_max'])}. PostGIS applies `ST_Transform` from source WGS84 (EPSG:4326) to ETRS89 / UTM 32N (EPSG:25832), a projection used for Denmark by [the Danish national mapping authority](https://www.sdfe.dk/media/2919769/001-etrs89-utm.pdf). Both geometry columns have GiST indexes. Airbnb coordinates are provider-anonymised; no address-level precision is claimed.

Review counts: median {_format_number(profile['review']['median_reviews'])}; 95th percentile {_format_number(profile['review']['p95_reviews'])}; max {profile['review']['max_reviews']:,}; zero-review listings {profile['review']['zero_reviews']:,}. Reviews are an activity proxy, not bookings.

`in_study_area` uses provider neighbourhood labels in the imported lookup. It is not an independently validated official municipality boundary; polygon containment remains future spatial QA. The conventional-type rule is intentionally conservative and may exclude some residential but atypical/holiday forms. Calendar availability is not occupancy. Detailed reviews contain personal/free text and are kept only in access-controlled `raw`; none is copied to this report or the clean listing table. No accessibility measures are calculated in Phase 2.
"""
    report_path = PROJECT_ROOT / "reports/phase02_airbnb_cleaning.md"
    report_path.write_text(report, encoding="utf-8")
    return {"raw_listings": flow[0]["remaining_n"], "primary_sample_candidate": flow[-1]["remaining_n"],
            "report": report_path.relative_to(PROJECT_ROOT).as_posix()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="2026-06-30", help="Local Inside Airbnb snapshot date")
    args = parser.parse_args()
    snapshot = date.fromisoformat(args.snapshot)
    snapshot_root = SNAPSHOT_ROOT / snapshot.isoformat()
    sources = (
        ("data/listings.csv.gz", "inside_airbnb_listings"),
        ("data/calendar.csv.gz", "inside_airbnb_calendar"),
        ("data/reviews.csv.gz", "inside_airbnb_reviews"),
        ("visualisations/neighbourhoods.csv", "inside_airbnb_neighbourhood_lookup"),
    )
    if any(not (PROJECT_ROOT / snapshot_root / relative).is_file() for relative, _ in sources):
        raise FileNotFoundError("One or more required Airbnb snapshot files are absent; inspect the snapshot before running")
    engine = get_engine()
    try:
        migrate(engine)
        registered = register_records(engine, prepare_all_sources())
        print(f"Verified and registered {len(registered):,} immutable raw files")
        for relative, table in sources:
            result = ingest_csv(engine, snapshot_root / relative, table)
            print(json.dumps(result, default=str))
        count = build_clean_listings(engine, snapshot, snapshot_root)
        print(f"Cleaned {count:,} listing rows")
        print(json.dumps(export_phase2(engine, snapshot), indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

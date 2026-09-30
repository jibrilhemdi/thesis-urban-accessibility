"""Audit archived 11-area context and publish a separate, non-primary view.

No price model or frozen Phase 9 artifact is read or rewritten here.
"""

from __future__ import annotations

import csv
import json
import math
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.ingestion.common import PROJECT_ROOT, sha256_file

RAW = PROJECT_ROOT / "data/raw"
OUTPUT = PROJECT_ROOT / "outputs/tables/analysis_area_context.csv"
AUDIT_OUTPUT = PROJECT_ROOT / "outputs/tables/context_district_source_audit.csv"
CITY = RAW / "copenhagen_statbank/2026-09-29"
NATIONAL = RAW / "municipality_statbank/2026-09-29"
SOURCE_FILES = {
    "city_population": "data/raw/copenhagen_statbank/2026-09-29/tables/KKBEF1.csv",
    "city_income": "data/raw/copenhagen_statbank/2026-09-29/tables/KKIND3.csv",
    "national_population": "data/raw/municipality_statbank/2026-09-29/tables/FOLK1A.csv",
    "national_income": "data/raw/municipality_statbank/2026-09-29/tables/INDKP106.csv",
}
FIELDS = (
    "analysis_area_code", "analysis_area_name", "analysis_area_geography",
    "analysis_area_source_provider", "population_count", "population_period",
    "area_m2", "area_km2", "population_density_per_km2", "log_population_density",
    "average_disposable_income_dkk", "income_100k_dkk", "income_period",
    "analysis_area_is_municipality_proxy", "analysis_area_income_definition_differs",
    "analysis_area_household_definition_unverified", "analysis_area_dwelling_definition_unverified",
    "area_crs_epsg", "area_includes_water_status", "population_source_file_id",
    "income_source_file_id", "boundary_source_file_id",
)


def _metadata(table: str) -> dict:
    return json.loads((CITY / "metadata" / f"{table}.json").read_text(encoding="utf-8"))


def verify_city_metadata() -> dict[str, tuple[str, int, Decimal, Decimal]]:
    """Tie wide CSV cells to explicit ordered codes/labels in each response metadata."""
    out = {}
    expected = {"KKBEF1": ("2026K3", "2026Q3"), "KKIND3": ("2024", "2024")}
    for table, (period_code, period_label) in expected.items():
        meta = _metadata(table)
        codes, names = meta["selected_codes"]["var1"], meta["selected_labels"]["var1"]
        if codes != [f"10{i:02}" for i in range(1, 11)] or len(set(names)) != 10:
            raise ValueError(f"{table}: district codes/names are not ten unique official districts")
        if meta["selected_codes"]["var5"] != [period_code] or meta["selected_labels"]["var5"] != [period_label]:
            raise ValueError(f"{table}: unexpected statistical reference period")
        if table == "KKBEF1" and [meta["selected_codes"][f"var{i}"] for i in (2, 3, 4)] != [["TOT"], ["TOT"], ["TOT"]]:
            raise ValueError("KKBEF1: expected all-sex, all-age, all-marital-status population")
        if table == "KKIND3" and [meta["selected_codes"][f"var{i}"] for i in (2, 3, 4)] != [["003"], ["TOT"], ["02"]]:
            raise ValueError("KKIND3: expected average income, all sex, disposable income")
        with (CITY / "tables" / f"{table}.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if len(rows) != 1 or len(rows[0]) != 14:
            raise ValueError(f"{table}: unexpected wide CSV shape")
        if rows[0][:4] != [meta["selected_labels"][f"var{i}"][0] for i in (4, 3, 2, 5)]:
            raise ValueError(f"{table}: dimension-label order changed")
        for code, label, value in zip(codes, names, rows[0][4:], strict=True):
            key = code
            name = label.removeprefix("District - ")
            number = Decimal(value)
            if not number.is_finite() or number <= 0:
                raise ValueError(f"{table}: nonpositive/nonfinite value")
            if table == "KKBEF1" and number != number.to_integral_value():
                raise ValueError("Population is not an integer")
            if table == "KKBEF1":
                out[key] = (name, int(number), Decimal(0), Decimal(0))
            else:
                if key not in out or out[key][0] != name:
                    raise ValueError("KKBEF1 and KKIND3 district codes/names disagree")
                out[key] = (name, out[key][1], number, Decimal(0))
    return out


def verify_national_metadata() -> dict[tuple[str, str], Decimal]:
    expected = {
        "FOLK1A": {"KØN": "TOT", "ALDER": "IALT", "CIVILSTAND": "TOT", "Tid": "2026K3"},
        "INDKP106": {"ENHED": "118", "KOEN": "MOK", "ALDER1": "00", "INDKINTB": "000", "Tid": "2024"},
    }
    values = {}
    for table, dimensions in expected.items():
        metadata = json.loads((NATIONAL / "tableinfo" / f"{table}.json").read_text(encoding="utf-8"))
        variables = {item["id"]: item for item in metadata["variables"]}
        if metadata["id"] != table or not all(
            code in {v["id"] for v in variables[dimension]["values"]}
            for dimension, code in dimensions.items()
        ):
            raise ValueError(f"{table}: selected codes absent from archived tableinfo")
        with (NATIONAL / "tables" / f"{table}.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=";"))
        if len(rows) != 2 or {row["OMRÅDE"].split()[0] for row in rows} != {"101", "147"}:
            raise ValueError(f"{table}: expected the two municipality rows")
        for row in rows:
            if any(row["TID" if dimension == "Tid" else dimension].split()[0] != code
                   for dimension, code in dimensions.items()):
                raise ValueError(f"{table}: row selection differs from metadata")
            municipality = row["OMRÅDE"].split()[0]
            number = Decimal(row["INDHOLD"])
            if not number.is_finite() or number <= 0 or (table == "FOLK1A" and number != number.to_integral_value()):
                raise ValueError(f"{table}: invalid source value")
            values[(table, municipality)] = number
    for table in expected:
        with (RAW / "frederiksberg_statbank/2026-09-22/tables" / f"{table}.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            older = list(csv.DictReader(handle, delimiter=";"))
        if len(older) != 1 or older[0]["OMRÅDE"].split()[0] != "147" or \
                Decimal(older[0]["INDHOLD"]) != values[(table, "147")]:
            raise ValueError(f"{table}: older Frederiksberg archive disagrees with selected national extract")
    return values


def _source_ids(conn) -> dict[str, int]:
    found = {}
    for role, relative_path in SOURCE_FILES.items():
        row = conn.execute(text("SELECT source_file_id, file_hash_sha256, imported_at "
                                "FROM meta.source_files WHERE relative_path=:path"),
                           {"path": relative_path}).mappings().one()
        if row["imported_at"] is None or row["file_hash_sha256"].strip() != sha256_file(PROJECT_ROOT / relative_path):
            raise ValueError(f"Unregistered or changed source: {relative_path}")
        found[role] = row["source_file_id"]
    return found


def build_rows(conn, city: dict, national: dict, ids: dict) -> list[dict]:
    measures = conn.execute(text("""
        SELECT 'city' AS family, district_code AS code, district_name AS name,
               measure_code, reference_period, value, source_file_id
        FROM clean.copenhagen_district_context_measures
        WHERE measure_code IN ('district_population','district_average_disposable_income')
        UNION ALL
        SELECT 'national', municipality_code, municipality_name,
               measure_code, reference_period, value, source_file_id
        FROM clean.municipality_context_measures
        WHERE measure_code IN ('total_population','average_personal_disposable_income')
    """)).mappings().all()
    by_key = {(m["family"], m["code"], m["measure_code"]): m for m in measures}
    if len(by_key) != len(measures):
        raise ValueError("Duplicate clean context measure")
    polygons = conn.execute(text("""
        SELECT area_id, area_name, municipality_code, source_file_id,
               ST_SRID(geom_25832) AS epsg, ST_IsValid(geom_25832) AS valid,
               ST_Area(geom_25832) AS area_m2
        FROM spatial.official_cv_areas ORDER BY area_id
    """)).mappings().all()
    if len(polygons) != 11 or {p["area_id"] for p in polygons} != {
        *(f"cph_{i:02}" for i in range(1, 11)), "frederiksberg_0147"
    }:
        raise ValueError("Expected exactly ten City districts and one Frederiksberg municipality")
    rows = []
    for polygon in polygons:
        code = polygon["area_id"]
        proxy = code == "frederiksberg_0147"
        district_code = "10" + code[-2:] if not proxy else "147"
        family = "national" if proxy else "city"
        pop_type = "total_population" if proxy else "district_population"
        income_type = "average_personal_disposable_income" if proxy else "district_average_disposable_income"
        population = by_key[(family, district_code, pop_type)]
        income = by_key[(family, district_code, income_type)]
        if proxy:
            if polygon["municipality_code"] != "0147" or polygon["area_name"] != "Frederiksberg":
                raise ValueError("Frederiksberg municipality geometry/name mismatch")
        elif (polygon["municipality_code"] != "0101" or
              polygon["area_name"] != city[district_code][0].replace("/", "-")):
            raise ValueError(f"District code/name differs from official polygon: {code}")
        if population["reference_period"] != "2026Q3" or income["reference_period"] != "2024":
            raise ValueError("Unexpected statistical reference period")
        if population["source_file_id"] != ids["national_population" if proxy else "city_population"] or \
                income["source_file_id"] != ids["national_income" if proxy else "city_income"]:
            raise ValueError("Clean context lineage differs from archived selected source")
        if not proxy and (population["value"] != city[district_code][1] or income["value"] != city[district_code][2]):
            raise ValueError("Clean district value differs from metadata-mapped CSV")
        if proxy and (population["value"] != national[("FOLK1A", "147")] or
                      income["value"] != national[("INDKP106", "147")]):
            raise ValueError("Clean Frederiksberg value differs from selected national CSV")
        area_m2 = float(polygon["area_m2"])
        pop = int(population["value"])
        income_dkk = Decimal(income["value"])
        if polygon["epsg"] != 25832 or not polygon["valid"] or not math.isfinite(area_m2) or area_m2 <= 0 or pop <= 0 or income_dkk <= 0:
            raise ValueError("Invalid area, CRS, population or income")
        area_km2 = area_m2 / 1_000_000
        density = pop / area_km2
        if not math.isfinite(density) or density <= 0:
            raise ValueError("Invalid population density")
        rows.append({
            "analysis_area_code": code, "analysis_area_name": polygon["area_name"],
            "analysis_area_geography": "Frederiksberg municipality proxy" if proxy else "Copenhagen district",
            "analysis_area_source_provider": "Statistics Denmark StatBank" if proxy else "City of Copenhagen Statbank",
            "population_count": pop, "population_period": population["reference_period"],
            "area_m2": area_m2, "area_km2": area_km2,
            "population_density_per_km2": density, "log_population_density": math.log(density),
            "average_disposable_income_dkk": income_dkk, "income_100k_dkk": income_dkk / 100000,
            "income_period": income["reference_period"],
            "analysis_area_is_municipality_proxy": proxy,
            "analysis_area_income_definition_differs": proxy,
            "analysis_area_household_definition_unverified": True,
            "analysis_area_dwelling_definition_unverified": True,
            "area_crs_epsg": 25832,
            "area_includes_water_status": "polygon area; water inclusion not independently verified",
            "population_source_file_id": population["source_file_id"],
            "income_source_file_id": income["source_file_id"],
            "boundary_source_file_id": polygon["source_file_id"],
        })
    return rows


def run() -> list[dict]:
    city = verify_city_metadata()
    national = verify_national_metadata()
    engine = get_engine()
    migrate(engine)
    with engine.begin() as conn:
        ids = _source_ids(conn)
        rows = build_rows(conn, city, national, ids)
        # The table is derived; replace it atomically while retaining immutable sources.
        conn.execute(text("DELETE FROM features.analysis_area_context"))
        conn.execute(text("""INSERT INTO features.analysis_area_context (
            analysis_area_code, analysis_area_name, analysis_area_geography, analysis_area_source_provider,
            population_count, population_period, area_m2, area_km2, population_density_per_km2,
            log_population_density, average_disposable_income_dkk, income_100k_dkk, income_period,
            analysis_area_is_municipality_proxy, analysis_area_income_definition_differs,
            analysis_area_household_definition_unverified, analysis_area_dwelling_definition_unverified,
            area_crs_epsg, area_includes_water_status, population_source_file_id,
            income_source_file_id, boundary_source_file_id
        ) VALUES (
            :analysis_area_code, :analysis_area_name, :analysis_area_geography, :analysis_area_source_provider,
            :population_count, :population_period, :area_m2, :area_km2, :population_density_per_km2,
            :log_population_density, :average_disposable_income_dkk, :income_100k_dkk, :income_period,
            :analysis_area_is_municipality_proxy, :analysis_area_income_definition_differs,
            :analysis_area_household_definition_unverified, :analysis_area_dwelling_definition_unverified,
            :area_crs_epsg, :area_includes_water_status, :population_source_file_id,
            :income_source_file_id, :boundary_source_file_id
        )"""), rows)
        base = conn.scalar(text("SELECT count(*) FROM analysis.analysis_dataset_v1"))
        combined, distinct_keys = conn.execute(text("""
            SELECT count(*), count(DISTINCT (snapshot_date, listing_id))
            FROM analysis.analysis_dataset_context_v1
        """)).one()
        if combined != base or distinct_keys != base or base != 23144:
            raise ValueError("New context view changed listing cardinality")
        incomplete = conn.scalar(text("""
            SELECT count(*) FROM analysis.analysis_dataset_context_v1
            WHERE official_cv_area_id IS NOT NULL AND analysis_area_code IS NULL
        """))
        if incomplete:
            raise ValueError(f"Context missing for {incomplete} officially assigned listings")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k: row[k] for k in FIELDS} for row in rows)
    with AUDIT_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        fields = ("district_code", "district_name", "population", "population_period",
                  "average_disposable_income_dkk", "income_period", "population_source_table",
                  "income_source_table", "population_source_provider", "income_source_provider",
                  "population_source_file_id", "income_source_file_id")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if row["analysis_area_is_municipality_proxy"]:
                continue
            writer.writerow({
                "district_code": "10" + row["analysis_area_code"][-2:],
                "district_name": city["10" + row["analysis_area_code"][-2:]][0],
                "population": row["population_count"], "population_period": row["population_period"],
                "average_disposable_income_dkk": row["average_disposable_income_dkk"],
                "income_period": row["income_period"], "population_source_table": "KKBEF1",
                "income_source_table": "KKIND3", "population_source_provider": "City of Copenhagen Statbank",
                "income_source_provider": "City of Copenhagen Statbank",
                "population_source_file_id": row["population_source_file_id"],
                "income_source_file_id": row["income_source_file_id"],
            })
    print(f"Audited {len(rows)} areas; base/view listings {base}; export {OUTPUT}")
    return rows


if __name__ == "__main__":
    run()

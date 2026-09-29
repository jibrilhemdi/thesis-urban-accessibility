"""Ingest archived context extracts and build geography/period-explicit measures."""

from __future__ import annotations

import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import text

from src.db.connection import get_engine
from src.db.migrations import migrate
from src.db.raw_csv import ingest_csv
from src.db.sources import prepare_all_sources, register_records
from src.ingestion.common import PROJECT_ROOT


NATIONAL_TABLES = ("BOL101", "BOL106", "FAM55N", "FOLK1A", "INDKP106")
CITY_TABLES = ("KKBEF1", "KKHUS1", "KKIND3", "KKBOL3")
VERSIONS = (
    ("frederiksberg_statbank", "2026-09-22", "dst_frb", NATIONAL_TABLES),
    ("municipality_statbank", "2026-09-29", "dst_municipal", NATIONAL_TABLES),
    ("copenhagen_statbank", "2026-09-22", "kk_district", CITY_TABLES),
    ("copenhagen_statbank", "2026-09-29", "kk_district", CITY_TABLES),
)
LATEST_NATIONAL = ("municipality_statbank", "2026-09-29", "dst_municipal")
LATEST_CITY = ("copenhagen_statbank", "2026-09-29", "kk_district")
MUNICIPALITIES = {"101": "Copenhagen", "147": "Frederiksberg"}
NATIONAL_DEFINITIONS = {
    "FOLK1A": ("Total registered population at start of quarter", "persons", "2026Q3", "municipality-level descriptive/context"),
    "FAM55N": ("Households across mutually exclusive type/size/child cells", "households", "2026-01-01", "municipality-level descriptive/context"),
    "INDKP106": ("Average personal disposable income, persons aged 14+", "DKK per person", "2024", "robustness-only"),
    "BOL101": ("Dwellings by resident status, use, tenure, owner and build year", "dwellings", "2026", "municipality-level descriptive/context"),
    "BOL106": ("Average persons per dwelling with registered population", "persons per dwelling", "2026", "municipality-level descriptive/context"),
}
CITY_DEFINITIONS = {
    "KKBEF1": ("Total registered population", "persons", "2026Q3", "robustness-only: Copenhagen districts"),
    "KKHUS1": ("Total households", "households", "2026Q1 (1 January)", "robustness-only: Copenhagen districts"),
    "KKIND3": ("Average disposable income for people with the income type", "DKK per person", "2024", "robustness-only: Copenhagen districts"),
    "KKBOL3": ("Dwellings, occupied dwellings, housing residents and average residents", "mixed; see clean measure", "2026", "robustness-only: Copenhagen districts"),
}
POPULATION_DEFINITIONS = {
    "FOLK1A": "All-age registered population at first day of quarter; total sex and marital status",
    "FAM55N": "Households at 1 January, classified by type, size and children; not persons",
    "INDKP106": "Persons aged 14+ in selected total income group; mean personal disposable income",
    "BOL101": "BBR dwellings by registered-population status; counts dwellings, not people",
    "BOL106": "Average persons in dwellings with registered population; not area population",
    "KKBEF1": "District total registered population, all sexes, ages and marital statuses",
    "KKHUS1": "District total households, not people",
    "KKIND3": "People with the selected disposable-income type; City denominator differs from INDKP106",
    "KKBOL3": "District dwelling and housing-resident measures; housing residents differ from total population",
}


def raw_table(prefix: str, version: str, table: str) -> str:
    return f"{prefix}_{version.replace('-', '')}_{table.lower()}"


def raw_path(provider: str, version: str, table: str) -> Path:
    return Path("data/raw") / provider / version / "tables" / f"{table}.csv"


def _code(value: str) -> str:
    return value.split(" ", 1)[0]


def _number(value: str, *, integer: bool = False) -> Decimal:
    try:
        number = Decimal(value.replace(",", "."))
    except (InvalidOperation, AttributeError) as error:
        raise ValueError("Non-numeric context source cell; investigate raw file") from error
    if not number.is_finite() or number < 0 or (integer and number != number.to_integral_value()):
        raise ValueError("Invalid negative, nonfinite or noninteger context source cell")
    return number


def _rows(conn, table: str) -> list[dict]:
    # Table names are generated solely from fixed module constants.
    return [dict(row) for row in conn.execute(text(f"SELECT * FROM raw.{table} ORDER BY _source_row_number")).mappings()]


def _source_id(conn, path: Path) -> int:
    result = conn.execute(text(
        "SELECT source_file_id FROM meta.source_files WHERE relative_path = :path AND imported_at IS NOT NULL"
    ), {"path": path.as_posix()}).scalar_one()
    return result


def _measure(code: str, period: str, value: Decimal, unit: str, definition: str, source_id: int) -> dict:
    return {"measure_code": code, "reference_period": period, "value": value, "unit": unit,
            "population_definition": definition, "source_file_id": source_id}


def _national_measures(conn) -> list[dict]:
    provider, version, prefix = LATEST_NATIONAL
    selected: dict[str, list[dict]] = {}
    source_ids: dict[str, int] = {}
    for table in NATIONAL_TABLES:
        selected[table] = _rows(conn, raw_table(prefix, version, table))
        source_ids[table] = _source_id(conn, raw_path(provider, version, table))
    if {len(selected[t]) for t in ("FOLK1A", "INDKP106", "BOL106")} != {2}:
        raise ValueError("Expected one direct national population/income/average cell per municipality")
    if len(selected["FAM55N"]) != 576 or len(selected["BOL101"]) != 33264:
        raise ValueError("National household/dwelling source row count changed")
    result: list[dict] = []
    for municipality, name in MUNICIPALITIES.items():
        def add(table: str, code: str, period: str, value: Decimal, unit: str, definition: str) -> None:
            result.append({"municipality_code": municipality, "municipality_name": name,
                           **_measure(code, period, value, unit, definition, source_ids[table])})

        population = [row for row in selected["FOLK1A"] if _code(row["OMRÅDE"]) == municipality]
        if len(population) != 1 or tuple(_code(population[0][key]) for key in ("KØN", "ALDER", "CIVILSTAND", "TID")) != ("TOT", "IALT", "TOT", "2026K3"):
            raise ValueError("FOLK1A selection/municipality differs from specification")
        add("FOLK1A", "total_population", "2026Q3", _number(population[0]["INDHOLD"], integer=True),
            "persons", "Total population, all ages/sexes/marital statuses at first day of quarter")

        households = [row for row in selected["FAM55N"] if _code(row["OMRÅDE"]) == municipality]
        household_keys = [tuple(row[key] for key in ("HUSTYP", "HUSSTØR", "ANTBORNH")) for row in households]
        if len(households) != 288 or len(set(household_keys)) != len(household_keys) or any(_code(row["TID"]) != "2026" for row in households):
            raise ValueError("FAM55N household cells not the expected exclusive 2026 selection")
        add("FAM55N", "households", "2026-01-01",
            sum((_number(row["INDHOLD"], integer=True) for row in households), Decimal(0)),
            "households", "Households at 1 January; sum of selected household-type/size/children cells")

        income = [row for row in selected["INDKP106"] if _code(row["OMRÅDE"]) == municipality]
        if len(income) != 1 or tuple(_code(income[0][key]) for key in ("ENHED", "KOEN", "ALDER1", "INDKINTB", "TID")) != ("118", "MOK", "00", "000", "2024"):
            raise ValueError("INDKP106 income selection differs from specification")
        add("INDKP106", "average_personal_disposable_income", "2024",
            _number(income[0]["INDHOLD"]), "DKK per person",
            "Mean disposable income for persons aged 14+ in selected total group; not household income")

        dwellings = [row for row in selected["BOL101"] if _code(row["OMRÅDE"]) == municipality]
        dwelling_keys = [tuple(row[key] for key in ("BEBO", "ANVENDELSE", "UDLFORH", "EJER", "OPFØRELSESÅR")) for row in dwellings]
        if len(dwellings) != 16632 or len(set(dwelling_keys)) != len(dwelling_keys) or any(_code(row["TID"]) != "2026" for row in dwellings):
            raise ValueError("BOL101 dwelling cells not the expected exclusive 2026 selection")
        total = sum((_number(row["INDHOLD"], integer=True) for row in dwellings), Decimal(0))
        occupied = sum((_number(row["INDHOLD"], integer=True) for row in dwellings if _code(row["BEBO"]) == "1000"), Decimal(0))
        add("BOL101", "dwellings_all_selected_statuses", "2026", total, "dwellings",
            "Sum across BOL101 resident-status/use/tenure/owner/build-year cells; includes non-registered statuses")
        add("BOL101", "dwellings_with_registered_population", "2026", occupied, "dwellings",
            "BOL101 BEBO=1000 subset; registered population in dwelling, not a resident count")

        average = [row for row in selected["BOL106"] if _code(row["OMRÅDE"]) == municipality]
        if len(average) != 1 or tuple(_code(average[0][key]) for key in ("ENHED", "ANVENDELSE", "TID")) != ("GNSPB", "TOT", "2026"):
            raise ValueError("BOL106 selection differs from specification")
        add("BOL106", "persons_per_registered_dwelling", "2026", _number(average[0]["INDHOLD"]),
            "persons per dwelling", "Average persons per dwelling with registered population; rounded source average")
    return result


def _city_measures(conn) -> list[dict]:
    provider, version, prefix = LATEST_CITY
    result: list[dict] = []
    expected = {"KKBEF1": ("district_population", "2026Q3", "persons", "Total population across sexes, ages and marital statuses"),
                "KKHUS1": ("district_households", "2026Q1", "households", "Total households across household types, sizes and children; 1 January 2026"),
                "KKIND3": ("district_average_disposable_income", "2024", "DKK per person", "Mean disposable income for people with this income type; not identical to national INDKP106 denominator")}
    district_keys: set[tuple[str, str]] = set()
    for table in CITY_TABLES:
        metadata_path = PROJECT_ROOT / "data/raw" / provider / version / "metadata" / f"{table}.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        codes = metadata["selected_codes"]["var1"]
        labels = metadata["selected_labels"]["var1"]
        if len(codes) != 10 or len(set(codes)) != 10 or len(labels) != 10:
            raise ValueError("City district code/label metadata is not ten unique districts")
        keys = {(code, label.removeprefix("District - ")) for code, label in zip(codes, labels)}
        if district_keys and keys != district_keys:
            raise ValueError("City district selections differ between source tables")
        district_keys = keys
        source_id = _source_id(conn, raw_path(provider, version, table))
        rows = _rows(conn, raw_table(prefix, version, table))
        if table != "KKBOL3":
            if len(rows) != 1 or len(rows[0]) != 16:
                raise ValueError(f"Unexpected wide City source shape for {table}")
            row = rows[0]
            values = [row[f"field_{index}"] for index in range(5, 15)]
            if set(row[f"field_{index}"] for index in range(1, 5)) != set(metadata["selected_labels"][f"var{index}"][0] for index in range(2, 6)):
                raise ValueError(f"Unexpected City dimension labels in {table}")
            measure_code, period, unit, definition = expected[table]
            for code, label, value in zip(codes, labels, values):
                result.append({"district_code": code, "district_name": label.removeprefix("District - "),
                               **_measure(measure_code, period, _number(value, integer=table != "KKIND3"), unit, definition, source_id)})
        else:
            if len(rows) != 10 or metadata["selected_codes"]["var5"] != ["01", "04", "06", "08"]:
                raise ValueError("Unexpected City housing source shape/measure selection")
            by_label = {row["field_5"]: row for row in rows}
            if set(by_label) != set(labels):
                raise ValueError("City housing district labels differ from selection metadata")
            housing_measures = (
                ("district_dwelling_count", "dwellings", "Total dwellings in City KKBOL3"),
                ("district_occupied_dwelling_count", "dwellings", "Occupied dwellings in City KKBOL3"),
                ("district_housing_resident_count", "persons", "Residents in City KKBOL3 housing statistic; not identical to KKBEF1 total population"),
                ("district_residents_per_occupied_dwelling", "persons per dwelling", "City KKBOL3 average residents per occupied dwelling"),
            )
            for code, label in zip(codes, labels):
                row = by_label[label]
                if row["field_4"] != "2026":
                    raise ValueError("Unexpected City housing period")
                for index, (measure_code, unit, definition) in enumerate(housing_measures, 6):
                    result.append({"district_code": code, "district_name": label.removeprefix("District - "),
                                   **_measure(measure_code, "2026", _number(row[f"field_{index}"], integer=index != 9), unit, definition, source_id)})
    if len(result) != 70:
        raise RuntimeError("Expected seven selected City measures for ten districts")
    return result


def build_clean_context(engine) -> tuple[int, int]:
    with engine.begin() as conn:
        national = _national_measures(conn)
        city = _city_measures(conn)
        conn.execute(text("DELETE FROM clean.municipality_context_measures"))
        conn.execute(text("DELETE FROM clean.copenhagen_district_context_measures"))
        conn.execute(text("INSERT INTO clean.municipality_context_measures "
                          "(municipality_code, municipality_name, measure_code, reference_period, value, unit, population_definition, source_file_id) "
                          "VALUES (:municipality_code, :municipality_name, :measure_code, :reference_period, :value, :unit, :population_definition, :source_file_id)"), national)
        conn.execute(text("INSERT INTO clean.copenhagen_district_context_measures "
                          "(district_code, district_name, measure_code, reference_period, value, unit, population_definition, source_file_id) "
                          "VALUES (:district_code, :district_name, :measure_code, :reference_period, :value, :unit, :population_definition, :source_file_id)"), city)
    return len(national), len(city)


def export_assessment(engine) -> int:
    records = []
    with engine.connect() as conn:
        for provider, version, prefix, tables in VERSIONS:
            for table in tables:
                path = raw_path(provider, version, table)
                source = conn.execute(text(
                    "SELECT s.file_hash_sha256, s.source_url, r.rows_loaded FROM meta.source_files s "
                    "JOIN meta.import_runs r USING (source_file_id) "
                    "WHERE s.relative_path = :path AND r.target_table = :target AND r.status = 'success'"
                ), {"path": path.as_posix(), "target": "raw." + raw_table(prefix, version, table)}).one()
                national = table in NATIONAL_TABLES
                concept, unit, period, use = (NATIONAL_DEFINITIONS if national else CITY_DEFINITIONS)[table]
                if not national:
                    city_meta = json.loads((PROJECT_ROOT / "data/raw" / provider / version / "metadata" /
                                            f"{table}.json").read_text(encoding="utf-8"))
                    period = city_meta["selected_labels"]["var6" if table == "KKBOL3" else "var5"][0]
                    if table == "KKHUS1" and period == "2026Q1":
                        period += " (1 January)"
                latest = (provider, version) in ((LATEST_NATIONAL[0], LATEST_NATIONAL[1]), (LATEST_CITY[0], LATEST_CITY[1]))
                records.append({
                    "source_table": table, "archive_version": version, "source_path": path.as_posix(),
                    "raw_table": "raw." + raw_table(prefix, version, table), "source_url": source.source_url or "",
                    "source_sha256": source.file_hash_sha256.strip(),
                    "raw_rows": source.rows_loaded, "concept": concept, "unit": unit,
                    "geography": "municipality" if national else "Copenhagen district",
                    "geographic_units": "Frederiksberg only" if provider == "frederiksberg_statbank" else
                    ("Copenhagen and Frederiksberg" if national else "10 Copenhagen districts"),
                    "reference_period": period,
                    "population_definition": POPULATION_DEFINITIONS[table],
                    "varies_below_municipality": not national,
                    "selected_for_clean": latest,
                    "model_use": (use if latest else "archive only: superseded extract"),
                    "reason": ("National selection has only municipality codes 101 and 147; no within-municipality variation" if national else
                               "City source has ten district observations; Frederiksberg absent"),
                })
    path = PROJECT_ROOT / "outputs/tables/phase03/context_source_assessment.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    return len(records)


def main() -> None:
    engine = get_engine()
    try:
        print("Applied migrations:", migrate(engine), flush=True)
        print("Registered raw files:", len(register_records(engine, prepare_all_sources())), flush=True)
        for provider, version, prefix, tables in VERSIONS:
            for table in tables:
                path = raw_path(provider, version, table)
                if not (PROJECT_ROOT / path).is_file():
                    raise FileNotFoundError(path)
                kwargs = ({"delimiter": ";"} if table in NATIONAL_TABLES else
                          {"encoding": "iso-8859-1", "header": False})
                result = ingest_csv(engine, path, raw_table(prefix, version, table), **kwargs)
                print(result["target_table"], result["status"], result.get("rows_loaded", ""), flush=True)
        national_n, city_n = build_clean_context(engine)
        assessed = export_assessment(engine)
        print(f"Clean measures: {national_n} municipality, {city_n} City district; {assessed} source assessments", flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

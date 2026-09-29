"""Collect comparable Copenhagen and Frederiksberg municipality context.

Both municipalities are queried from the same Statistics Denmark tables with
identical selections and periods. This is a separate geographic layer from
the City of Copenhagen's district statistics.
"""

from __future__ import annotations

import argparse
import copy
import io
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

from src.ingestion.common import PROJECT_ROOT, read_manifest, sha256_bytes, update_manifest, utc_now, write_json


API_BASE = "https://api.statbank.dk/v1"
MUNICIPALITIES = {"101": "Copenhagen", "147": "Frederiksberg"}
USER_AGENT = "copenhagen-urban-accessibility-thesis/0.1 (academic research)"

TABLE_SPECS: list[dict[str, Any]] = [
    {
        "table": "FOLK1A",
        "description": "Population at the first day of the quarter",
        "period": "2026Q3",
        "selections": {"OMRÅDE": ["101", "147"], "KØN": ["TOT"], "ALDER": ["IALT"], "CIVILSTAND": ["TOT"], "Tid": ["2026K3"]},
    },
    {
        "table": "FAM55N",
        "description": "Households 1 January",
        "period": "2026-01-01",
        "selections": {"OMRÅDE": ["101", "147"], "HUSTYP": ["*"], "HUSSTØR": ["*"], "ANTBORNH": ["*"], "Tid": ["2026"]},
    },
    {
        "table": "INDKP106",
        "description": "Average disposable income for persons aged 14+",
        "period": "2024",
        "selections": {"OMRÅDE": ["101", "147"], "ENHED": ["118"], "KOEN": ["MOK"], "ALDER1": ["00"], "INDKINTB": ["000"], "Tid": ["2024"]},
    },
    {
        "table": "BOL101",
        "description": "Dwellings by resident status, use, tenure, ownership and construction year",
        "period": "2026",
        "selections": {"OMRÅDE": ["101", "147"], "BEBO": ["*"], "ANVENDELSE": ["*"], "UDLFORH": ["*"], "EJER": ["*"], "OPFØRELSESÅR": ["*"], "Tid": ["2026"]},
    },
    {
        "table": "BOL106",
        "description": "Average persons per dwelling with registered population",
        "period": "2026",
        "selections": {"OMRÅDE": ["101", "147"], "ENHED": ["GNSPB"], "ANVENDELSE": ["TOT"], "Tid": ["2026"]},
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-date", default=None, help="Date stamp for new raw and tidy files; defaults to today (UTC).")
    parser.add_argument("--force", action="store_true", help="Replace a collection at the same retrieval date.")
    return parser.parse_args()


def data_url(spec: dict[str, Any]) -> str:
    parameters: list[tuple[str, str]] = [("lang", "en"), ("valuePresentation", "CodeAndValue")]
    parameters.extend((variable, ",".join(values)) for variable, values in spec["selections"].items())
    return f"{API_BASE}/data/{spec['table']}/CSV?{urlencode(parameters)}"


def read_csv(payload: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(payload), sep=";", encoding="utf-8-sig", dtype="string")


def numeric_values(frame: pd.DataFrame) -> pd.Series:
    values = pd.to_numeric(frame["INDHOLD"].str.replace(",", ".", regex=False), errors="coerce")
    if values.isna().any():
        raise ValueError("StatBank response contains missing or nonnumeric values in the selected cells")
    return values


def municipality_rows(frame: pd.DataFrame, code: str) -> pd.DataFrame:
    rows = frame.loc[frame["OMRÅDE"].str.startswith(code + " ")].copy()
    if rows.empty:
        raise ValueError(f"No StatBank data for municipality {code}")
    return rows


def derive_context(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for code, name in MUNICIPALITIES.items():
        population = numeric_values(municipality_rows(frames["FOLK1A"], code))
        income = numeric_values(municipality_rows(frames["INDKP106"], code))
        average = numeric_values(municipality_rows(frames["BOL106"], code))
        if len(population) != 1 or len(income) != 1 or len(average) != 1:
            raise ValueError(f"Expected one direct value per selected table for {name}")

        households = numeric_values(municipality_rows(frames["FAM55N"], code))
        dwellings = municipality_rows(frames["BOL101"], code)
        dwelling_values = numeric_values(dwellings)
        registered_mask = dwellings["BEBO"].str.startswith("1000 ")
        records.append(
            {
                "municipality_code": code,
                "municipality_name": name,
                "municipality_context_provider": "Statistics Denmark StatBank",
                "municipality_context_geography": "municipality",
                "municipality_population_count": int(population.iloc[0]),
                "municipality_household_count": int(households.sum()),
                "municipality_average_disposable_income_dkk": int(income.iloc[0]),
                "municipality_dwelling_count": int(dwelling_values.sum()),
                "municipality_registered_population_dwelling_count": int(dwelling_values.loc[registered_mask].sum()),
                "municipality_average_persons_per_registered_dwelling": float(average.iloc[0]),
            }
        )
    return pd.DataFrame(records)


def validate_tableinfo(info: dict[str, Any], spec: dict[str, Any]) -> None:
    variables = {item["id"]: {value["id"] for value in item["values"]} for item in info["variables"]}
    for variable, requested in spec["selections"].items():
        if variable not in variables:
            raise ValueError(f"{spec['table']} is missing variable {variable}")
        for code in requested:
            if code != "*" and code not in variables[variable]:
                raise ValueError(f"{spec['table']} has no {variable} code {code}")


def manifest_entry(path: Path, *, asset: str, source_url: str, status: str, table: str | None = None) -> dict[str, Any]:
    return {
        "provider": "Statistics Denmark StatBank",
        "asset": asset,
        "source_url": source_url,
        "local_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "downloaded_at_utc": utc_now(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_bytes(path.read_bytes()),
        "status": status,
        **({"table": table} if table else {}),
    }


def main() -> None:
    args = parse_args()
    retrieval_date = args.retrieval_date or pd.Timestamp.now(tz="UTC").date().isoformat()
    raw_root = PROJECT_ROOT / "data" / "raw" / "municipality_statbank" / retrieval_date
    context_path = PROJECT_ROOT / "data" / "interim" / f"municipality_statbank_context_{retrieval_date}.csv"
    metadata_path = PROJECT_ROOT / "data" / "metadata" / "municipality_statbank_run.json"
    if context_path.exists() and not args.force:
        raise FileExistsError(f"{context_path} exists; choose a new retrieval date or use --force")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    downloads: list[tuple[dict[str, Any], bytes, bytes, str]] = []
    frames: dict[str, pd.DataFrame] = {}
    for spec in TABLE_SPECS:
        table = spec["table"]
        info_url = f"{API_BASE}/tableinfo/{table}?lang=en&format=JSON"
        info_response = session.get(info_url, timeout=90)
        info_response.raise_for_status()
        validate_tableinfo(info_response.json(), spec)
        url = data_url(spec)
        data_response = session.get(url, timeout=240)
        data_response.raise_for_status()
        frame = read_csv(data_response.content)
        if set(frame["OMRÅDE"].str.split(" ", n=1).str[0]) != set(MUNICIPALITIES):
            raise ValueError(f"Unexpected municipality coverage for {table}")
        frames[table] = frame
        downloads.append((spec, info_response.content, data_response.content, data_response.url))
        print(f"Validated {table}: {len(frame):,} rows for both municipalities")

    context = derive_context(frames)
    entries: list[dict[str, Any]] = []
    table_metadata: list[dict[str, Any]] = []
    for spec, info_payload, data_payload, url in downloads:
        table = spec["table"]
        table_path = raw_root / "tables" / f"{table}.csv"
        info_path = raw_root / "tableinfo" / f"{table}.json"
        table_path.parent.mkdir(parents=True, exist_ok=True)
        info_path.parent.mkdir(parents=True, exist_ok=True)
        table_path.write_bytes(data_payload)
        info_path.write_bytes(info_payload)
        entries.append(manifest_entry(table_path, asset=table, source_url=url, status="downloaded", table=table))
        entries.append(
            manifest_entry(
                info_path,
                asset=f"{table}_tableinfo",
                source_url=f"{API_BASE}/tableinfo/{table}?lang=en&format=JSON",
                status="downloaded",
                table=table,
            )
        )
        table_metadata.append(
            {
                "table": table,
                "description": spec["description"],
                "period": spec["period"],
                "selected_codes": spec["selections"],
                "data_url": url,
                "raw_file": table_path.relative_to(PROJECT_ROOT).as_posix(),
                "tableinfo_file": info_path.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context.to_csv(context_path, index=False)
    entries.append(
        manifest_entry(
            context_path,
            asset="two_municipality_context_tidy",
            source_url="https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api",
            status="created",
        )
    )

    # Preserve the old collection for provenance, but mark its tidy row as
    # superseded so it is not mistaken for a district-comparable observation.
    legacy_path = "data/interim/frederiksberg_statbank_municipality_context_2026-09-22.csv"
    legacy = next((item for item in read_manifest()["files"] if item["local_path"] == legacy_path), None)
    if legacy is not None:
        legacy = copy.deepcopy(legacy)
        legacy["status"] = "superseded"
        legacy["superseded_by"] = context_path.relative_to(PROJECT_ROOT).as_posix()
        entries.append(legacy)
    update_manifest(entries)

    run_metadata = {
        "provider": "Statistics Denmark StatBank",
        "retrieved_at_utc": utc_now(),
        "retrieval_date": retrieval_date,
        "api_documentation": "https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api",
        "geography": "Copenhagen municipality (101) and Frederiksberg municipality (147)",
        "tables": table_metadata,
        "tidy_context": context_path.relative_to(PROJECT_ROOT).as_posix(),
        "tidy_rows": int(len(context)),
        "columns": context.columns.tolist(),
        "derivation": {
            "municipality_population_count": "FOLK1A total population, 2026Q3",
            "municipality_household_count": "FAM55N sum across mutually exclusive household cells, 2026-01-01",
            "municipality_average_disposable_income_dkk": "INDKP106 average for the total group of persons aged 14+, 2024",
            "municipality_dwelling_count": "BOL101 sum of all dwelling classifications, 2026",
            "municipality_registered_population_dwelling_count": "BOL101 BEBO=1000 dwelling subset, 2026",
            "municipality_average_persons_per_registered_dwelling": "BOL106 GNSPB for total use, 2026",
        },
        "comparability_note": "Both rows use identical national tables, selections and periods. Copenhagen district statistics remain a separate geographic layer; district totals should not be compared directly to these municipality totals.",
        "excluded_measure": "A separate housing resident count is not available in the selected national tables. No FOLK1A population value is relabelled as a housing resident count.",
        "supersedes": legacy_path,
    }
    write_json(metadata_path, run_metadata)
    print(f"Saved {context_path.relative_to(PROJECT_ROOT)}")
    print(context.to_string(index=False))


if __name__ == "__main__":
    main()

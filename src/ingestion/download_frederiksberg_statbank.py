"""Collect municipality-level context for Frederiksberg from StatBank Denmark.

Frederiksberg is an independent municipality and is therefore not included in
the City of Copenhagen's 10-district Statbank geography. This collector uses
the official national StatBank API for municipality code 147 and preserves the
raw API responses, selections, derivations, and a tidy context row suitable for
joining to the Inside Airbnb neighbourhood label ``Frederiksberg``.
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

from src.ingestion.common import PROJECT_ROOT, sha256_bytes, update_manifest, utc_now, write_json


API_BASE = "https://api.statbank.dk/v1/data"
TABLEINFO_BASE = "https://api.statbank.dk/v1/tableinfo"
MUNICIPALITY_CODE = "147"
MUNICIPALITY_NAME = "Frederiksberg"
USER_AGENT = "copenhagen-urban-accessibility-thesis/0.1 (academic research)"

TABLE_SPECS: list[dict[str, Any]] = [
    {
        "table": "FOLK1A",
        "description": "Population at the first day of the quarter",
        "selections": {
            "OMRÅDE": [MUNICIPALITY_CODE],
            "KØN": ["TOT"],
            "ALDER": ["IALT"],
            "CIVILSTAND": ["TOT"],
            "Tid": ["2026K3"],
        },
        "output_column": "population_count",
        "period": "2026Q3",
        "derivation": "Direct value for total sex, age, and marital status.",
    },
    {
        "table": "FAM55N",
        "description": "Households 1 January",
        "selections": {
            "OMRÅDE": [MUNICIPALITY_CODE],
            "HUSTYP": ["*"],
            "HUSSTØR": ["*"],
            "ANTBORNH": ["*"],
            "Tid": ["2026"],
        },
        "output_column": "household_count",
        "period": "2026",
        "derivation": "Sum of all mutually exclusive household type, size, and child-count cells.",
    },
    {
        "table": "INDKP106",
        "description": "Disposable income for people aged 14+",
        "selections": {
            "OMRÅDE": [MUNICIPALITY_CODE],
            "ENHED": ["118"],
            "KOEN": ["MOK"],
            "ALDER1": ["00"],
            "INDKINTB": ["000"],
            "Tid": ["2024"],
        },
        "output_column": "average_disposable_income_dkk",
        "period": "2024",
        "derivation": "Direct average income for persons in the total group, all income intervals.",
    },
    {
        "table": "BOL101",
        "description": "Dwellings by region, resident status, use, tenure, ownership and construction year",
        "selections": {
            "OMRÅDE": [MUNICIPALITY_CODE],
            "BEBO": ["*"],
            "ANVENDELSE": ["*"],
            "UDLFORH": ["*"],
            "EJER": ["*"],
            "OPFØRELSESÅR": ["*"],
            "Tid": ["2026"],
        },
        "output_column": "dwelling_count",
        "period": "2026",
        "derivation": "Sum across all dwelling classifications; occupied count is the BEBO=1000 subset (dwellings with registered population).",
    },
    {
        "table": "BOL106",
        "description": "Dwellings with registered population (average) by region, unit and use",
        "selections": {
            "OMRÅDE": [MUNICIPALITY_CODE],
            "ENHED": ["GNSPB"],
            "ANVENDELSE": ["TOT"],
            "Tid": ["2026"],
        },
        "output_column": "average_residents_per_occupied_dwelling",
        "period": "2026",
        "derivation": "Direct average persons per dwelling for total use; retained under the common context field name.",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-date", default=None, help="Date-stamp for local files; defaults to today.")
    parser.add_argument("--force", action="store_true", help="Recollect tables and replace local outputs.")
    return parser.parse_args()


def api_query_url(table: str, selections: dict[str, list[str]]) -> str:
    params: list[tuple[str, str]] = [
        ("lang", "en"),
        ("valuePresentation", "CodeAndValue"),
        ("timeOrder", "Ascending"),
    ]
    for variable, values in selections.items():
        params.append((variable, ",".join(values)))
    return f"{API_BASE}/{table}/CSV?{urlencode(params)}"


def fetch_table(session: requests.Session, spec: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    url = api_query_url(spec["table"], spec["selections"])
    response = session.get(url, timeout=240)
    response.raise_for_status()
    metadata = {
        "table": spec["table"],
        "description": spec["description"],
        "tableinfo_url": f"{TABLEINFO_BASE}/{spec['table']}?lang=en&format=JSON",
        "api_url": response.url,
        "api_endpoint": API_BASE,
        "download_format": "CSV with semicolon delimiter and code+label values",
        "retrieved_at_utc": utc_now(),
        "selected_codes": spec["selections"],
        "period": spec["period"],
        "derivation": spec["derivation"],
        "municipality_code": MUNICIPALITY_CODE,
        "municipality_name": MUNICIPALITY_NAME,
    }
    return response.content, metadata


def read_api_csv(payload: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(payload), sep=";", encoding="utf-8-sig")


def numeric_values(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(
        df["INDHOLD"].astype("string").str.replace(r"[^0-9.\-]", "", regex=True),
        errors="coerce",
    )


def derive_context(table_frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    population = numeric_values(table_frames["FOLK1A"]).iloc[0]
    households = numeric_values(table_frames["FAM55N"]).sum(min_count=1)
    income = numeric_values(table_frames["INDKP106"]).iloc[0]

    dwellings = table_frames["BOL101"].copy()
    dwellings["value_numeric"] = numeric_values(dwellings)
    dwelling_count = dwellings["value_numeric"].sum(min_count=1)
    registered_mask = dwellings["BEBO"].astype("string").str.startswith("1000 ")
    occupied_dwelling_count = dwellings.loc[registered_mask, "value_numeric"].sum(min_count=1)

    average_residents = numeric_values(table_frames["BOL106"]).iloc[0]
    context = pd.DataFrame(
        [
            {
                "statbank_area_code": MUNICIPALITY_CODE,
                "district_name_statbank": MUNICIPALITY_NAME,
                "statbank_context_provider": "Statistics Denmark StatBank",
                "statbank_context_geography": "municipality",
                "population_count": population,
                "household_count": households,
                "average_disposable_income_dkk": income,
                "dwelling_count": dwelling_count,
                "occupied_dwelling_count": occupied_dwelling_count,
                "resident_count_statbank": population,
                "average_residents_per_occupied_dwelling": average_residents,
            }
        ]
    )
    derivation = {
        "population_count": "FOLK1A total population at the first day of 2026Q3.",
        "household_count": "FAM55N sum across all household dimensions for 2026-01-01.",
        "average_disposable_income_dkk": "INDKP106 average disposable income for persons aged 14+, total sex, total age, all income intervals, 2024.",
        "dwelling_count": "BOL101 sum across all dwelling classifications for 2026.",
        "occupied_dwelling_count": "BOL101 sum of dwellings with registered population (BEBO=1000) for 2026.",
        "resident_count_statbank": "Set equal to FOLK1A total population; BOL101 is a dwelling-count table without a resident-count measure.",
        "average_residents_per_occupied_dwelling": "BOL106 total-use average persons per dwelling for dwellings with registered population, 2026.",
    }
    return context, derivation


def main() -> None:
    args = parse_args()
    retrieval_date = args.retrieval_date or pd.Timestamp.now(tz="UTC").date().isoformat()
    raw_root = PROJECT_ROOT / "data" / "raw" / "frederiksberg_statbank" / retrieval_date
    table_root = raw_root / "tables"
    metadata_root = raw_root / "metadata"
    context_path = PROJECT_ROOT / "data" / "interim" / f"frederiksberg_statbank_municipality_context_{retrieval_date}.csv"
    run_metadata_path = PROJECT_ROOT / "data" / "metadata" / "frederiksberg_statbank_run.json"
    if context_path.exists() and not args.force:
        raise FileExistsError(f"{context_path} already exists; use --force to replace it.")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    manifest_entries: list[dict[str, Any]] = []
    table_frames: dict[str, pd.DataFrame] = {}
    table_metadata: list[dict[str, Any]] = []

    for spec in TABLE_SPECS:
        table = spec["table"]
        print(f"Collecting {table}: {spec['description']}")
        payload, metadata = fetch_table(session, spec)
        raw_path = table_root / f"{table}.csv"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(payload)
        metadata_path = metadata_root / f"{table}.json"
        write_json(metadata_path, metadata)
        frame = read_api_csv(payload)
        table_frames[table] = frame
        metadata.update(
            {
                "raw_file": raw_path.relative_to(PROJECT_ROOT).as_posix(),
                "raw_sha256": sha256_bytes(payload),
                "raw_bytes": len(payload),
                "raw_rows": int(len(frame)),
                "raw_columns": frame.columns.tolist(),
                "selection_metadata_file": metadata_path.relative_to(PROJECT_ROOT).as_posix(),
            }
        )
        write_json(metadata_path, metadata)
        table_metadata.append(metadata)
        manifest_entries.extend(
            [
                {
                    "provider": "Statistics Denmark StatBank",
                    "asset": table,
                    "source_url": metadata["api_url"],
                    "local_path": raw_path.relative_to(PROJECT_ROOT).as_posix(),
                    "downloaded_at_utc": metadata["retrieved_at_utc"],
                    "size_bytes": len(payload),
                    "sha256": sha256_bytes(payload),
                    "status": "downloaded",
                    "table": table,
                    "period": metadata["period"],
                },
                {
                    "provider": "Statistics Denmark StatBank",
                    "asset": f"{table}_selection_metadata",
                    "source_url": metadata["tableinfo_url"],
                    "local_path": metadata_path.relative_to(PROJECT_ROOT).as_posix(),
                    "downloaded_at_utc": metadata["retrieved_at_utc"],
                    "size_bytes": metadata_path.stat().st_size,
                    "sha256": sha256_bytes(metadata_path.read_bytes()),
                    "status": "created",
                    "table": table,
                },
            ]
        )
        print(f"  -> {len(frame):,} raw rows")

    context, derivation = derive_context(table_frames)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context.to_csv(context_path, index=False)
    manifest_entries.append(
        {
            "provider": "Statistics Denmark StatBank",
            "asset": "frederiksberg_municipality_context_tidy",
            "source_url": "https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api",
            "local_path": context_path.relative_to(PROJECT_ROOT).as_posix(),
            "downloaded_at_utc": utc_now(),
            "size_bytes": context_path.stat().st_size,
            "sha256": sha256_bytes(context_path.read_bytes()),
            "status": "created",
        }
    )
    update_manifest(manifest_entries)

    run_metadata = {
        "provider": "Statistics Denmark StatBank",
        "retrieved_at_utc": utc_now(),
        "retrieval_date": retrieval_date,
        "landing_page": "https://www.statbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1",
        "api_documentation": "https://www.dst.dk/en/Statistik/hjaelp-til-statistikbanken/api",
        "api_endpoint": API_BASE,
        "license_note": "Statistics Denmark makes StatBank data available under its published reuse terms; retain source attribution and table references.",
        "geography": "Frederiksberg municipality, code 147; independent municipality adjacent to the City of Copenhagen.",
        "tables": table_metadata,
        "tidy_context": context_path.relative_to(PROJECT_ROOT).as_posix(),
        "tidy_rows": int(len(context)),
        "columns": context.columns.tolist(),
        "derivation": derivation,
        "comparability_warning": "This municipality-level source is not a district-level continuation of the City of Copenhagen Statbank. Provider and geographic level are retained in the tidy output so models can account for the mixed context geography.",
    }
    write_json(run_metadata_path, run_metadata)
    print(f"Saved tidy context to {context_path.relative_to(PROJECT_ROOT)}")
    print(context.to_string(index=False))


if __name__ == "__main__":
    main()

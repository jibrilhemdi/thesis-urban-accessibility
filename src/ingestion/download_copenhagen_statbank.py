"""Collect district-level context from the City of Copenhagen Statbank.

The City Statbank exposes an interactive table-selection interface rather than
the national StatBank API. This script submits documented selections to that
interface and saves the exact returned CSV files, selection metadata, and a
tidy district context table.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.ingestion.common import PROJECT_ROOT, sha256_bytes, update_manifest, utc_now, write_json


STATBANK_ROOT = "https://kk.statistikbank.dk/statbank5a/"
SELECTION_URL = STATBANK_ROOT + "SelectVarVal/Define.asp?Maintable={table}&PLanguage=1"
DISTRICT_CODES = [str(code) for code in range(1001, 1011)]
USER_AGENT = "copenhagen-urban-accessibility-thesis/0.1 (academic research)"

TABLE_SPECS: list[dict[str, Any]] = [
    {
        "table": "KKBEF1",
        "subject_code": "301",
        "subject_area": "Population and projections",
        "description": "Population by district, sex, age and marital status",
        "selections": {"var1": DISTRICT_CODES, "var2": ["TOT"], "var3": ["TOT"], "var4": ["TOT"], "var5": ["__LATEST_QUARTER__"]},
        "output_columns": {"value": "population_count"},
    },
    {
        "table": "KKHUS1",
        "subject_code": "301",
        "subject_area": "Population and projections",
        "description": "Households by district, household type, children and household size",
        "selections": {"var1": DISTRICT_CODES, "var2": ["TOT"], "var3": ["TOT"], "var4": ["TOT"], "var5": ["__LATEST_QUARTER__"]},
        "output_columns": {"value": "household_count"},
    },
    {
        "table": "KKIND3",
        "subject_code": "305",
        "subject_area": "Income, wealth and income distribution",
        "description": "Income for persons aged 14+ by district, unit, sex and type of income",
        "selections": {"var1": DISTRICT_CODES, "var2": ["003"], "var3": ["TOT"], "var4": ["02"], "var5": ["__LATEST_YEAR__"]},
        "output_columns": {"value": "average_disposable_income_dkk"},
    },
    {
        "table": "KKBOL3",
        "subject_code": "302",
        "subject_area": "Homes, buildings and areas",
        "description": "Dwellings, square meters and residents by district",
        "selections": {"var1": DISTRICT_CODES, "var2": ["TOT"], "var3": ["TOT"], "var4": ["TOT"], "var5": ["01", "04", "06", "08"], "var6": ["__LATEST_YEAR__"]},
        "unit_columns": {
            "Number of dwellings": "dwelling_count",
            "Number of occupied dwellings": "occupied_dwelling_count",
            "Number of residents": "resident_count_statbank",
            "Average number of residents per occupied dwelling": "average_residents_per_occupied_dwelling",
        },
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-date", default=None, help="Date-stamp for local files; defaults to today.")
    parser.add_argument("--force", action="store_true", help="Recollect tables and replace the local context output.")
    return parser.parse_args()


def clean_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def post_form(session: requests.Session, url: str, data: list[tuple[str, str]], timeout: int) -> requests.Response:
    """Submit the legacy Statbank form using its ISO-8859-1 page encoding."""
    encoded = urlencode(data, doseq=True, encoding="iso-8859-1", errors="strict").encode("ascii")
    return session.post(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )


def parse_options(page_text: str) -> dict[str, list[tuple[str, str]]]:
    options: dict[str, list[tuple[str, str]]] = {}
    for match in re.finditer(r'<SELECT[^>]*NAME="(var\d+)"[^>]*>(.*?)</SELECT>', page_text, re.I | re.S):
        name, body = match.groups()
        found = []
        for option in re.finditer(r'<OPTION\s+VALUE="([^"]*)"[^>]*>(.*?)</option>', body, re.I | re.S):
            code, label = option.groups()
            label = clean_label(re.sub(r"<.*?>", "", label))
            found.append((code, label))
        options[name] = found
    return options


def parse_main_form(page_text: str) -> tuple[str, list[tuple[str, str]], str]:
    form_match = re.search(r'<FORM[^>]*name=["\']main["\'][^>]*>', page_text, re.I)
    if form_match is None:
        raise RuntimeError("Could not find the City Statbank selection form")
    form_tag = form_match.group(0)
    form_end = re.search(r"</FORM>", page_text[form_match.end() :], re.I)
    if form_end is None:
        raise RuntimeError("Could not find the end of the City Statbank selection form")
    form_fragment = page_text[form_match.start() : form_match.end() + form_end.end()]

    def attr(tag: str, name: str) -> str:
        found = re.search(rf'{re.escape(name)}\s*=\s*["\']([^"\']*)["\']', tag, re.I)
        return found.group(1) if found else ""

    hidden: list[tuple[str, str]] = []
    for input_match in re.finditer(r"<INPUT\b[^>]*>", form_fragment, re.I):
        tag = input_match.group(0)
        name = attr(tag, "name")
        if not name or attr(tag, "type").lower() in {"image", "submit"}:
            continue
        hidden.append((name, attr(tag, "value")))
    soup = BeautifulSoup(page_text, "html.parser")
    title = clean_label(soup.title.get_text(" ", strip=True) if soup.title else "")
    return attr(form_tag, "action"), hidden, title


def option_label(options: dict[str, list[tuple[str, str]]], variable: str, code: str) -> str:
    for option_code, label in options.get(variable, []):
        if option_code == code:
            return label
    return code


def latest_code(options: dict[str, list[tuple[str, str]]], variable: str, kind: str) -> str:
    pattern = r"^\d{4}K\d$" if kind == "quarter" else r"^\d{4}$"
    for code, _ in options.get(variable, []):
        if re.match(pattern, code):
            return code
    raise RuntimeError(f"Could not find a current {kind} in {variable}")


def build_selection(
    session: requests.Session, spec: dict[str, Any]
) -> tuple[bytes, dict[str, Any], str]:
    table = spec["table"]
    page_url = SELECTION_URL.format(table=table)
    page_response = session.get(page_url, timeout=60)
    page_response.raise_for_status()
    page_text = page_response.content.decode("iso-8859-1", "replace")
    action, hidden, title = parse_main_form(page_text)
    options = parse_options(page_text)
    selections: dict[str, list[str]] = {}
    selected_labels: dict[str, list[str]] = {}
    for variable, requested in spec["selections"].items():
        resolved: list[str] = []
        for code in requested:
            if code == "__LATEST_QUARTER__":
                code = latest_code(options, variable, "quarter")
            elif code == "__LATEST_YEAR__":
                code = latest_code(options, variable, "year")
            resolved.append(code)
        selections[variable] = resolved
        selected_labels[variable] = [option_label(options, variable, code) for code in resolved]

    hidden_map = {name: value for name, value in hidden}
    hidden_map["TS"] = (
        f"ShowTable&OldTab={hidden_map.get('OldTab', 'SELECT')}&SubjectCode={hidden_map.get('SubjectCode', spec['subject_code'])}"
        f"&AntVar={hidden_map.get('antvar', len(selections))}&Contents={hidden_map.get('Contents', 'Indhold')}"
        f"&tidrubr={hidden_map.get('tidrubr', 'rubrik5')}"
    )
    hidden_map["PLanguage"] = "1"
    hidden_map["MainTable"] = table
    form_data: list[tuple[str, str]] = [(name, value) for name, value in hidden_map.items() if not name.startswith("var")]
    for variable, codes in selections.items():
        form_data.extend((variable, code) for code in codes)

    result_url = urljoin(page_response.url, action)
    result = post_form(session, result_url, form_data, timeout=90)
    result.raise_for_status()
    soup = BeautifulSoup(result.text, "html.parser")
    ready_form = soup.find("form", attrs={"name": "ready"})
    if ready_form is None:
        raise RuntimeError(f"No output form returned for {table}: {clean_label(soup.get_text(' ', strip=True))[:500]}")
    ready_action = urljoin(result.url, ready_form.get("action", ""))
    output_data: list[tuple[str, str]] = []
    for tag in ready_form.find_all("input"):
        name = tag.get("name")
        if not name or tag.get("type", "").lower() in {"image", "submit"}:
            continue
        output_data.append((name, tag.get("value", "")))
    output_data = [(name, value) for name, value in output_data if name.lower() != "fileformatid"]
    output_data.extend([("fileformatid", "8"), ("run.x", "1"), ("run.y", "1")])
    output = post_form(session, ready_action, output_data, timeout=90)
    output.raise_for_status()
    if b"<html" in output.content[:200].lower() and b"Internal server error" in output.content:
        raise RuntimeError(f"City Statbank returned an error while downloading {table}")

    metadata = {
        "table": table,
        "title": title,
        "description": spec["description"],
        "selection_page": page_url,
        "download_format": "comma-separated CSV (Statbank FileformatId 8)",
        "retrieved_at_utc": utc_now(),
        "selected_codes": selections,
        "selected_labels": selected_labels,
        "available_option_counts": {variable: len(values) for variable, values in options.items()},
        "response_url": output.url,
    }
    return output.content, metadata, title


def decode_csv(payload: bytes) -> list[list[str]]:
    for encoding in ("utf-8-sig", "iso-8859-1"):
        try:
            text = payload.decode(encoding)
            return [[clean_label(cell) for cell in row] for row in csv.reader(io.StringIO(text))]
        except UnicodeDecodeError:
            continue
    raise UnicodeError("Could not decode Statbank CSV")


def as_number(value: str) -> float:
    value = clean_label(value)
    if value in {"", ".", "..", "-"} or value.startswith("<"):
        return math.nan
    value = value.replace(" ", "").replace(",", "")
    try:
        return float(value)
    except ValueError:
        return math.nan


def rows_to_context(
    table: str, rows: list[list[str]], spec: dict[str, Any], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    """Turn Statbank's default wide CSV into one row per selected district.

    The provider places the selected district dimension in columns, so the
    exported CSV has dimension labels followed by one value per district.
    """
    records: list[dict[str, Any]] = []
    district_codes = metadata["selected_codes"]["var1"]
    district_labels = metadata["selected_labels"]["var1"]
    for row in rows:
        if table == "KKBOL3" and any(cell.startswith("District - ") for cell in row):
            district_cell = next(cell for cell in row if cell.startswith("District - "))
            district = district_cell.removeprefix("District - ").strip()
            unit_labels = metadata["selected_labels"]["var5"]
            values = row[-len(unit_labels) :]
            record: dict[str, Any] = {"district_name_statbank": district}
            for unit, raw_value in zip(unit_labels, values):
                if unit in spec["unit_columns"]:
                    record[spec["unit_columns"][unit]] = as_number(raw_value)
            records.append(record)
            continue
        if len(row) < len(district_codes) + 1:
            continue
        dimension_cells = row[: -len(district_codes)]
        values = row[-len(district_codes) :]
        for code, label, raw_value in zip(district_codes, district_labels, values):
            district = label.removeprefix("District - ").strip()
            value = as_number(raw_value)
            record: dict[str, Any] = {"district_name_statbank": district}
            if table == "KKBOL3":
                unit_columns = spec["unit_columns"]
                unit = next((cell for cell in dimension_cells if cell in unit_columns), None)
                if unit is None:
                    continue
                record[unit_columns[unit]] = value
            else:
                value_column = spec["output_columns"]["value"]
                record[value_column] = value
            records.append(record)
    return records


def district_code_map() -> dict[str, str]:
    return {
        "Indre By": "1001",
        "Østerbro": "1002",
        "Nørrebro": "1003",
        "Vesterbro/Kongens Enghave": "1004",
        "Valby": "1005",
        "Vanløse": "1006",
        "Brønshøj-Husum": "1007",
        "Bispebjerg": "1008",
        "Amager Øst": "1009",
        "Amager Vest": "1010",
    }


def main() -> None:
    args = parse_args()
    retrieval_date = args.retrieval_date or pd.Timestamp.now(tz="UTC").date().isoformat()
    raw_root = PROJECT_ROOT / "data" / "raw" / "copenhagen_statbank" / retrieval_date
    table_root = raw_root / "tables"
    metadata_root = raw_root / "metadata"
    context_path = PROJECT_ROOT / "data" / "interim" / f"copenhagen_statbank_district_context_{retrieval_date}.csv"
    if context_path.exists() and not args.force:
        raise FileExistsError(f"{context_path} already exists; use --force to replace it.")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    manifest_entries: list[dict[str, Any]] = []
    context_parts: list[pd.DataFrame] = []
    table_metadata: list[dict[str, Any]] = []

    for spec in TABLE_SPECS:
        table = spec["table"]
        print(f"Collecting {table}: {spec['description']}")
        payload, metadata, _ = build_selection(session, spec)
        raw_path = table_root / f"{table}.csv"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(payload)
        metadata_path = metadata_root / f"{table}.json"
        write_json(metadata_path, metadata)
        manifest_entries.extend(
            [
                {
                    "provider": "City of Copenhagen Statbank",
                    "asset": table,
                    "source_url": metadata["selection_page"],
                    "local_path": raw_path.relative_to(PROJECT_ROOT).as_posix(),
                    "downloaded_at_utc": metadata["retrieved_at_utc"],
                    "size_bytes": len(payload),
                    "sha256": sha256_bytes(payload),
                    "status": "downloaded",
                    "table": table,
                    "periods": metadata["selected_labels"].get("var5", metadata["selected_labels"].get("var6", [])),
                },
                {
                    "provider": "City of Copenhagen Statbank",
                    "asset": f"{table}_selection_metadata",
                    "source_url": metadata["selection_page"],
                    "local_path": metadata_path.relative_to(PROJECT_ROOT).as_posix(),
                    "downloaded_at_utc": metadata["retrieved_at_utc"],
                    "size_bytes": metadata_path.stat().st_size,
                    "sha256": sha256_bytes(metadata_path.read_bytes()),
                    "status": "created",
                    "table": table,
                },
            ]
        )
        rows = decode_csv(payload)
        records = rows_to_context(table, rows, spec, metadata)
        context_parts.append(pd.DataFrame(records))
        metadata["raw_file"] = raw_path.relative_to(PROJECT_ROOT).as_posix()
        metadata["raw_sha256"] = sha256_bytes(payload)
        metadata["raw_rows"] = len(rows)
        table_metadata.append(metadata)
        print(f"  -> {len(rows):,} raw rows; {len(records):,} district records")

    context = context_parts[0]
    for part in context_parts[1:]:
        context = context.merge(part, on="district_name_statbank", how="outer")
    code_map = district_code_map()
    context["statbank_district_code"] = context["district_name_statbank"].map(code_map)
    context = context[["statbank_district_code", "district_name_statbank"] + [c for c in context.columns if c not in {"statbank_district_code", "district_name_statbank"}]]
    context = context.sort_values("statbank_district_code").reset_index(drop=True)
    context_path.parent.mkdir(parents=True, exist_ok=True)
    context.to_csv(context_path, index=False)
    manifest_entries.append(
        {
            "provider": "City of Copenhagen Statbank",
            "asset": "district_context_tidy",
            "source_url": "https://kk.statistikbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1",
            "local_path": context_path.relative_to(PROJECT_ROOT).as_posix(),
            "downloaded_at_utc": utc_now(),
            "size_bytes": context_path.stat().st_size,
            "sha256": sha256_bytes(context_path.read_bytes()),
            "status": "created",
        }
    )
    update_manifest(manifest_entries)
    run_metadata = {
        "provider": "City of Copenhagen Statbank",
        "retrieved_at_utc": utc_now(),
        "retrieval_date": retrieval_date,
        "landing_page": "https://kk.statistikbank.dk/statbank5a/SelectTable/Omrade0.asp?PLanguage=1",
        "documentation": "https://www.kk.dk/sites/default/files/2021-11/KK%20Statistikbank%20dokumentation_04112021.pdf",
        "license_note": "The City Statbank is an official public statistical source; retain source attribution and table references.",
        "geography": "10 City of Copenhagen districts; Frederiksberg is not part of this district system.",
        "tables": table_metadata,
        "tidy_context": context_path.relative_to(PROJECT_ROOT).as_posix(),
        "tidy_rows": int(len(context)),
        "columns": context.columns.tolist(),
        "join_warning": "Airbnb listings labelled Frederiksberg cannot be joined to City of Copenhagen district statistics and must remain missing or be excluded from district-context models.",
    }
    write_json(PROJECT_ROOT / "data" / "metadata" / "copenhagen_statbank_run.json", run_metadata)
    print(f"Saved tidy context to {context_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

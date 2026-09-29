"""Run Phase 1 database setup, checks, registration, and raw CSV ingestion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from src.db.connection import database_settings, get_engine
from src.db.migrations import database_check, migrate
from src.db.raw_csv import ingest_csv
from src.db.sources import prepare_all_sources, register_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("connect", help="Test basic connection without changing the database")
    commands.add_parser("migrate", help="Apply versioned, checksum-verified SQL migrations")
    commands.add_parser("check", help="Check PostGIS, schemas, and applied migrations")
    commands.add_parser("postgis-version", help="Print the installed PostGIS version")
    commands.add_parser("register-sources", help="Hash and register every immutable file under data/raw")
    ingest = commands.add_parser("ingest-csv", help="Load a CSV/CSV.gz as text into raw.<table>")
    ingest.add_argument("--path", required=True, type=Path, help="Path inside data/raw")
    ingest.add_argument("--table", required=True, help="Lower-case destination name in raw schema")
    ingest.add_argument("--encoding", default="utf-8-sig", help="Explicit source encoding")
    ingest.add_argument("--delimiter", default=",", help="Single-character CSV delimiter")
    ingest.add_argument("--no-header", action="store_true", help="Preserve first row as data; generate field_1... headers")
    ingest.add_argument("--batch-rows", type=int, default=5000, help="Rows per COPY batch")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = database_settings()
    engine = get_engine()
    try:
        if args.command == "connect":
            with engine.connect() as conn:
                name = conn.scalar(text("SELECT current_database()"))
                if name != settings["DB_NAME"]:
                    raise RuntimeError("Connected database name does not match DB_NAME")
            result = {"connection": "ok", "database": name}
        elif args.command == "migrate":
            result = {"applied_now": migrate(engine)}
        elif args.command == "check":
            result = database_check(engine, settings["DB_NAME"])
        elif args.command == "postgis-version":
            with engine.connect() as conn:
                result = {"postgis_version": conn.scalar(text("SELECT postgis_version()"))}
        elif args.command == "register-sources":
            records = prepare_all_sources()
            ids = register_records(engine, records)
            result = {"raw_files_verified_and_registered": len(ids), "unique_source_ids": len(set(ids))}
        else:
            result = ingest_csv(engine, args.path, args.table, encoding=args.encoding,
                                delimiter=args.delimiter, header=not args.no_header,
                                batch_rows=args.batch_rows)
        print(json.dumps(result, indent=2, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

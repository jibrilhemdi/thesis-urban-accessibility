"""Stream CSV/CSV.gz source values into versioned, all-text raw tables."""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
from itertools import chain
from pathlib import Path
from typing import Iterator

from psycopg2 import sql
from sqlalchemy import Engine, text

from src.ingestion.common import sha256_file
from src.db.sources import MANIFEST_PATH, PROJECT_ROOT, _manifest_entries, prepare_source, register_records


TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
RESERVED_COLUMNS = {"_source_file_id", "_source_row_number"}


def _open_csv(path: Path, encoding: str):
    if path.name.endswith(".csv.gz"):
        return gzip.open(path, "rt", encoding=encoding, newline="")
    if path.suffix == ".csv":
        return path.open("r", encoding=encoding, newline="")
    raise ValueError("Raw importer accepts only .csv or .csv.gz")


def _csv_rows(path: Path, *, encoding: str, delimiter: str, header: bool) -> tuple[list[str], Iterator[list[str]], object]:
    handle = _open_csv(path, encoding)
    try:
        csv.field_size_limit(10_000_000)
        reader = csv.reader(handle, delimiter=delimiter, strict=True)
        first = next(reader, None)
        if first is None:
            raise ValueError("CSV source is empty")
        columns = first if header else [f"field_{index}" for index in range(1, len(first) + 1)]
        if not columns or any(not value or "\x00" in value or len(value.encode("utf-8")) > 63 for value in columns):
            raise ValueError("CSV has empty, NUL-containing, or overlong column names")
        if len(set(columns)) != len(columns) or RESERVED_COLUMNS.intersection(columns):
            raise ValueError("CSV has duplicate or reserved column names")
        rows = reader if header else chain([first], reader)
        return columns, rows, handle
    except Exception:
        handle.close()
        raise


def _copy_rows(cursor, path: Path, table: str, source_file_id: int, *,
               encoding: str, delimiter: str, header: bool, batch_rows: int) -> int:
    columns, rows, handle = _csv_rows(path, encoding=encoding, delimiter=delimiter, header=header)
    all_columns = ["_source_file_id", "_source_row_number", *columns]
    create = sql.SQL(
        "CREATE TABLE IF NOT EXISTS raw.{} ("
        "_source_file_id bigint NOT NULL REFERENCES meta.source_files(source_file_id), "
        "_source_row_number bigint NOT NULL, {}, "
        "PRIMARY KEY (_source_file_id, _source_row_number))"
    ).format(sql.Identifier(table), sql.SQL(", ").join(
        sql.SQL("{} text").format(sql.Identifier(column)) for column in columns
    ))
    copy = sql.SQL("COPY raw.{} ({}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')").format(
        sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(column) for column in all_columns)
    )
    try:
        cursor.execute(create)
        cursor.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = %s ORDER BY ordinal_position", (table,)
        )
        actual = cursor.fetchall()
        expected = [("_source_file_id", "bigint"), ("_source_row_number", "bigint")]
        expected.extend((column, "text") for column in columns)
        if actual != expected:
            raise ValueError(f"Existing raw.{table} schema differs from CSV header")
        cursor.execute(sql.SQL("SELECT count(*) FROM raw.{} WHERE _source_file_id = %s").format(
            sql.Identifier(table)), (source_file_id,))
        if cursor.fetchone()[0]:
            raise ValueError(f"raw.{table} already contains rows for this source without a successful import log")

        copy_statement = copy.as_string(cursor)
        count = 0
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\n")
        for count, row in enumerate(rows, start=1):
            if len(row) != len(columns):
                raise ValueError(f"CSV record {count} has {len(row)} fields; expected {len(columns)}")
            writer.writerow([source_file_id, count, *row])
            if count % batch_rows == 0:
                buffer.seek(0)
                cursor.copy_expert(copy_statement, buffer)
                buffer.seek(0)
                buffer.truncate(0)
        if buffer.tell():
            buffer.seek(0)
            cursor.copy_expert(copy_statement, buffer)
        cursor.execute(sql.SQL("SELECT count(*) FROM raw.{} WHERE _source_file_id = %s").format(
            sql.Identifier(table)), (source_file_id,))
        loaded = cursor.fetchone()[0]
        if loaded != count:
            raise RuntimeError(f"Row-count check failed for raw.{table}: copied {count}, found {loaded}")
        return count
    finally:
        handle.close()


def ingest_csv(
    engine: Engine, path: Path, table: str, *, encoding: str = "utf-8-sig",
    delimiter: str = ",", header: bool = True, batch_rows: int = 5000,
    project_root: Path = PROJECT_ROOT, manifest_path: Path = MANIFEST_PATH,
) -> dict[str, object]:
    if not TABLE_NAME_RE.fullmatch(table):
        raise ValueError("Table name must be lower-case SQL identifier of at most 63 characters")
    if len(delimiter) != 1 or batch_rows < 1:
        raise ValueError("Delimiter must be one character and batch_rows must be positive")
    path = path if path.is_absolute() else project_root / path
    manifest = _manifest_entries(manifest_path)
    record = prepare_source(path, project_root=project_root, manifest=manifest)
    source_file_id = register_records(engine, [record])[0]
    target = f"raw.{table}"
    import_options = {"encoding": encoding, "delimiter": delimiter, "header": header}
    with engine.begin() as conn:
        successful = conn.execute(text(
            "SELECT import_options FROM meta.import_runs WHERE source_file_id = :id "
            "AND target_table = :target AND status = 'success'"
        ), {"id": source_file_id, "target": target})
        prior_options = successful.scalar_one_or_none()
        if prior_options is not None:
            if prior_options != import_options:
                raise ValueError("Source/table already imported with different CSV options")
            return {"status": "already_imported", "source_file_id": source_file_id, "target_table": target}
        run_id = conn.execute(text(
            "INSERT INTO meta.import_runs (source_file_id, source_hash_sha256, target_table, import_options, status) "
            "VALUES (:id, :digest, :target, CAST(:options AS jsonb), 'running') RETURNING import_run_id"
        ), {"id": source_file_id, "digest": record["file_hash_sha256"], "target": target,
            "options": json.dumps(import_options)}).scalar_one()
    try:
        with engine.begin() as conn:
            cursor = conn.connection.driver_connection.cursor()
            try:
                loaded = _copy_rows(cursor, path, table, source_file_id, encoding=encoding,
                                    delimiter=delimiter, header=header, batch_rows=batch_rows)
            finally:
                cursor.close()
            if sha256_file(path) != record["file_hash_sha256"]:
                raise ValueError("Raw source changed during import")
            conn.execute(text(
                "UPDATE meta.source_files SET imported_at = now(), row_count = :rows "
                "WHERE source_file_id = :id"
            ), {"rows": loaded, "id": source_file_id})
            conn.execute(text(
                "UPDATE meta.import_runs SET status = 'success', finished_at = now(), "
                "rows_loaded = :rows WHERE import_run_id = :run_id"
            ), {"rows": loaded, "run_id": run_id})
    except Exception as error:
        # The COPY/table transaction rolls back; never log raw cell values.
        safe_message = str(error) if type(error) is ValueError else type(error).__name__
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE meta.import_runs SET status = 'failed', finished_at = now(), "
                "error_message = :message WHERE import_run_id = :run_id"
            ), {"message": safe_message[:500], "run_id": run_id})
        raise
    return {"status": "success", "source_file_id": source_file_id,
            "target_table": target, "rows_loaded": loaded, "import_run_id": run_id}

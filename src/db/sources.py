"""Verify immutable raw files and register their provenance in PostgreSQL."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from src.ingestion.common import MANIFEST_PATH, PROJECT_ROOT, sha256_file


RAW_ROOT = PROJECT_ROOT / "data" / "raw"
PROVIDERS = {
    "inside_airbnb": "Inside Airbnb",
    "osm": "OpenStreetMap via Overpass",
    "copenhagen_statbank": "City of Copenhagen Statbank",
    "frederiksberg_statbank": "Statistics Denmark StatBank",
    "municipality_statbank": "Statistics Denmark StatBank",
    "official_boundaries": "Danish national geography API / Copenhagen Municipality WFS",
    "official_map_context": "Danish national geography API",
}
EXTENTS = {
    "inside_airbnb": "Copenhagen and Frederiksberg listing area",
    "osm": "Buffered Copenhagen/Frederiksberg listing extent",
    "copenhagen_statbank": "Copenhagen Municipality districts",
    "frederiksberg_statbank": "Frederiksberg Municipality",
    "municipality_statbank": "Copenhagen and Frederiksberg municipalities",
    "official_boundaries": "Copenhagen and Frederiksberg municipalities; Copenhagen districts",
    "official_map_context": "Capital Region of Denmark municipalities (cartographic context only)",
}


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _manifest_entries(manifest_path: Path = MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Source manifest is missing: {manifest_path}")
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
    raw = [entry for entry in entries if entry["local_path"].startswith("data/raw/")]
    by_path = {entry["local_path"]: entry for entry in raw}
    if len(by_path) != len(raw):
        raise ValueError("Duplicate raw-file paths in source manifest")
    return by_path


def prepare_source(
    path: Path, *, project_root: Path = PROJECT_ROOT, manifest: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    raw_root = project_root / "data" / "raw"
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(raw_root.resolve()):
        raise ValueError("Source must be a regular file inside data/raw, not a symlink")
    relative_path = path.resolve().relative_to(project_root.resolve()).as_posix()
    parts = Path(relative_path).parts
    provider_key = parts[2]
    if provider_key not in PROVIDERS:
        raise ValueError(f"Unrecognized raw source directory: {provider_key}")
    manifest_entry = (manifest or {}).get(relative_path, {})
    actual_hash = sha256_file(path)
    actual_size = path.stat().st_size
    if manifest_entry:
        if actual_hash != manifest_entry.get("sha256") or actual_size != manifest_entry.get("size_bytes"):
            raise ValueError(f"Raw source differs from manifest: {relative_path}")
    sidecar = {}
    if not manifest_entry and path.name in {"snapshot_metadata.json", "extraction_metadata.json"}:
        sidecar = json.loads(path.read_text(encoding="utf-8"))
    if provider_key in {"official_boundaries", "official_map_context"} and path.name != "acquisition_metadata.json":
        metadata_path = path.parent / "acquisition_metadata.json"
        if metadata_path.is_file():
            sidecar = json.loads(metadata_path.read_text(encoding="utf-8")).get("files", {}).get(path.name, {})
    elif provider_key in {"official_boundaries", "official_map_context"} and path.name == "acquisition_metadata.json":
        sidecar = json.loads(path.read_text(encoding="utf-8"))
    elif provider_key == "osm" and "phase05" in parts:
        metadata_path = path.parent / "acquisition_metadata.json"
        if path.name == "acquisition_metadata.json":
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        elif metadata_path.is_file():
            sidecar = json.loads(metadata_path.read_text(encoding="utf-8")).get("files", {}).get(path.name, {})
    snapshot_date = _iso_date(manifest_entry.get("snapshot_date"))
    if snapshot_date is None and provider_key == "inside_airbnb":
        snapshot_date = _iso_date(parts[4])
    source_date = _iso_date(
        manifest_entry.get("source_date") or manifest_entry.get("osm_timestamp")
        or sidecar.get("source_date") or sidecar.get("retrieval_date")
    )
    notes = {key: manifest_entry[key] for key in ("asset", "table", "period", "periods", "status", "superseded_by")
             if key in manifest_entry}
    if not manifest_entry:
        notes["manifest"] = "No source-manifest entry; SHA-256 computed directly from immutable raw file"
    if sidecar.get("source_crs"):
        notes["source_crs"] = sidecar["source_crs"]
    return {
        "filename": path.name,
        "relative_path": relative_path,
        "source_name": manifest_entry.get("provider") or (
            "OpenStreetMap via BBBike" if provider_key == "osm" and "phase05" in parts else PROVIDERS[provider_key]
        ),
        "source_url": manifest_entry.get("source_url") or sidecar.get("source_url") or sidecar.get("landing_page") or sidecar.get("source_page"),
        "file_hash_sha256": actual_hash,
        "file_size": actual_size,
        "source_date": source_date,
        "snapshot_date": snapshot_date,
        "acquisition_date": _iso_date(manifest_entry.get("downloaded_at_utc") or sidecar.get("retrieved_at_utc") or sidecar.get("acquired_at_utc")),
        "geographic_extent": sidecar.get("geographic_extent") or EXTENTS[provider_key],
        "notes": json.dumps(notes, ensure_ascii=False) if notes else None,
    }


def prepare_all_sources(
    *, project_root: Path = PROJECT_ROOT, manifest_path: Path = MANIFEST_PATH
) -> list[dict[str, Any]]:
    manifest = _manifest_entries(manifest_path)
    raw_root = project_root / "data" / "raw"
    paths = sorted(path for path in raw_root.rglob("*") if path.is_file() and path.name != ".gitkeep")
    present = {path.resolve().relative_to(project_root.resolve()).as_posix() for path in paths}
    missing = sorted(set(manifest) - present)
    if missing:
        raise FileNotFoundError(f"Manifest-listed raw file is missing: {missing[0]}")
    return [prepare_source(path, project_root=project_root, manifest=manifest) for path in paths]


def register_records(engine: Engine, records: list[dict[str, Any]]) -> list[int]:
    """Reject path/hash drift; repeat registration returns the same IDs."""
    ids: list[int] = []
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(2026092902)"))
        for record in records:
            existing = conn.execute(text(
                "SELECT source_file_id, file_hash_sha256, file_size FROM meta.source_files "
                "WHERE relative_path = :path"
            ), {"path": record["relative_path"]}).first()
            if existing:
                if existing.file_hash_sha256.strip() != record["file_hash_sha256"] or existing.file_size != record["file_size"]:
                    raise ValueError(f"Previously registered raw file changed: {record['relative_path']}")
                ids.append(existing.source_file_id)
                continue
            source_file_id = conn.execute(text(
                "INSERT INTO meta.source_files (filename, relative_path, source_name, source_url, "
                "file_hash_sha256, file_size, source_date, snapshot_date, acquisition_date, "
                "geographic_extent, notes) VALUES (:filename, :relative_path, :source_name, :source_url, "
                ":file_hash_sha256, :file_size, :source_date, :snapshot_date, :acquisition_date, "
                ":geographic_extent, :notes) RETURNING source_file_id"
            ), record).scalar_one()
            ids.append(source_file_id)
    return ids

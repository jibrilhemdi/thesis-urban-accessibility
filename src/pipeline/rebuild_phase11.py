"""Guarded, offline rebuild from an empty PostGIS database and archived raw files.

Run only in a fresh working copy: phase runners write fixed report/output paths.
This command never deletes a database, volume, raw file, or existing result.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT
from src.db.sources import prepare_all_sources


STEPS: tuple[tuple[str, ...], ...] = (
    ("src.db.cli", "migrate"),
    ("src.pipeline.run_airbnb_phase2",),
    ("src.pipeline.run_context_phase3",),
    ("src.pipeline.run_spatial_phase4",),
    ("src.pipeline.run_euclidean_phase5",),
    ("src.pipeline.run_walking_phase6",),
    ("src.pipeline.export_walking_phase6",),
    ("src.pipeline.run_analysis_phase7",),
    ("src.pipeline.run_analysis_phase8",),
    ("src.pipeline.run_bus_proximity_phase9",),
    ("src.pipeline.audit_destination_boundary_phase9",),
    ("src.pipeline.run_analysis_phase9",),
    ("src.pipeline.run_bus_walking_phase10",),
    ("src.pipeline.run_analysis_phase10",),
    ("src.pipeline.run_spatial_error_phase10",),
    ("src.pipeline.run_analysis_phase10", "--synthesis-only"),
    ("src.pipeline.run_analysis_phase10", "--buffer-qa"),
    ("src.pipeline.audit_reproducibility_phase11",),
)


def require_fresh_destination() -> None:
    """Fail closed before any runner can overwrite the existing thesis outputs."""
    outputs = PROJECT_ROOT / "outputs"
    existing = [path for folder in ("tables", "figures")
                for path in (outputs / folder).iterdir() if path.name != ".gitkeep"]
    if existing:
        raise RuntimeError("Rebuild requires a fresh checkout with empty outputs/; existing results were not touched")
    engine = get_engine()
    try:
        with engine.connect() as conn:
            if conn.scalar(text("SELECT to_regclass('meta.schema_migrations') IS NOT NULL")):
                raise RuntimeError("Rebuild requires an unmigrated, empty database; migration history already exists")
            if conn.scalar(text("SELECT to_regclass('meta.source_files') IS NOT NULL")):
                n = conn.scalar(text("SELECT count(*) FROM meta.source_files"))
                if n:
                    raise RuntimeError("Rebuild requires an empty database: meta.source_files already contains rows")
            if conn.scalar(text("SELECT to_regclass('clean.airbnb_listings') IS NOT NULL")):
                n = conn.scalar(text("SELECT count(*) FROM clean.airbnb_listings"))
                if n:
                    raise RuntimeError("Rebuild requires an empty database: clean.airbnb_listings already contains rows")
    finally:
        engine.dispose()


def main() -> None:
    if PROJECT_ROOT != Path.cwd().resolve():
        raise RuntimeError("Run from the fresh project checkout root")
    require_fresh_destination()
    sources = prepare_all_sources()  # SHA-256/manifest check before any import.
    if not sources:
        raise RuntimeError("No archived raw sources; obtain the documented snapshots first")
    env = os.environ.copy()
    for step in STEPS:
        command = [sys.executable, "-m", *step]
        print("Running", " ".join(command), flush=True)
        subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


if __name__ == "__main__":
    main()

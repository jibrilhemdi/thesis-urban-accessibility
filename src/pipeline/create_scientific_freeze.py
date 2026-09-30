"""Freeze already-estimated scientific artifacts without running any producer.

This command is deliberately read-only with respect to PostgreSQL and existing
results. It creates a new, non-overwriting local release directory containing
public provenance, scientific tables, and an explicitly editable presentation
snapshot. Private raw data and credentials are never copied.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zoneinfo import ZoneInfo

from sqlalchemy import text

from src.db.connection import get_engine
from src.ingestion.common import PROJECT_ROOT, sha256_file
from src.pipeline.release_snapshot import release_files
from src.pipeline.run_analysis_phase10 import _freeze


ROOT = PROJECT_ROOT
RELEASES = ROOT / "outputs/releases"
LOCAL_TZ = ZoneInfo("Europe/Copenhagen")
FREEZE_GUARD = ROOT / "outputs/tables/phase10/primary_freeze.json"
INVENTORIES = {
    "food_social": ROOT / "outputs/tables/supplementary/destination_inventory_food_social.csv",
    "cultural_tourist": ROOT / "outputs/tables/supplementary/destination_inventory_cultural_tourist.csv",
    "station": ROOT / "outputs/tables/supplementary/destination_inventory_rail_metro.csv",
}


def _run_git(*args: str) -> str:
    return subprocess.run(("git", *args), cwd=ROOT, text=True,
                          check=True, capture_output=True).stdout.strip()


def _science_path(path: Path) -> bool:
    """Select immutable result sources, not formatted main tables or pixels."""
    rel = path.relative_to(ROOT).as_posix()
    if rel in {"outputs/tables/final/appendix_destination_counts.csv",
               "outputs/tables/final/appendix_destination_taxonomy.csv",
               "outputs/tables/final/appendix_destination_examples.csv",
               "outputs/tables/final/appendix_destination_rail_metro.csv"}:
        return True
    if rel.startswith("outputs/tables/supplementary/destination_inventory_"):
        return path.suffix == ".csv"
    if not rel.startswith("outputs/tables/") or path.suffix not in {".csv", ".json"}:
        return False
    if rel.startswith(("outputs/tables/final/", "outputs/tables/phase11/")):
        return False
    return True


def _inventory_rows(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    key_column = "canonical_station_id" if path == INVENTORIES["station"] else "canonical_destination_id"
    keys = [row[key_column] for row in rows]
    if len(keys) != len(set(keys)) or any(row["taxonomy_version"] != "phase05_v2" for row in rows):
        raise RuntimeError(f"Noncanonical or duplicate destination inventory: {path}")
    return set(keys)


def _database_state() -> dict:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            expected = json.loads(FREEZE_GUARD.read_text(encoding="utf-8"))
            current = _freeze(conn)
            if current != expected:
                raise RuntimeError("Frozen Phase 9 artifacts or saved CV assignments changed")
            if current["cv_assignment_rows"] != 23144 or len(current["phase9_file_sha256"]) != 27:
                raise RuntimeError("Phase 9/CV freeze manifest has unexpected scope")

            sample = conn.execute(text(
                "SELECT count(*) n,count(DISTINCT (snapshot_date,listing_id)) unique_n,"
                "count(DISTINCT official_cv_area_id) areas,"
                "count(*) FILTER (WHERE price_nightly<=0 OR log_price IS NULL OR "
                "abs(log_price-ln(price_nightly::double precision))>1e-10) bad_price "
                "FROM analysis.analysis_dataset_v1 WHERE primary_sample_candidate "
                "AND official_cv_area_id IS NOT NULL "
                "AND nearest_station_walking_minutes IS NOT NULL"
            )).one()
            phase9_meta = json.loads((ROOT / "outputs/tables/phase09/run_metadata.json").read_text())
            if (sample.n != phase9_meta["common_sample_n"] or sample.n != sample.unique_n or
                    sample.areas != 11 or sample.bad_price):
                raise RuntimeError("Authoritative Phase 9 common sample differs from saved metadata")

            areas = conn.execute(text(
                "SELECT area_id,municipality_code,ST_AsEWKB(geom_25832) "
                "FROM spatial.official_cv_areas ORDER BY area_id"
            )).all()
            if len(areas) != 11 or sum(row[1] == "0147" for row in areas) != 1:
                raise RuntimeError("Official 10+1 analysis-area geography changed")
            boundary_hash = hashlib.sha256()
            for area_id, municipality_code, geom in areas:
                boundary_hash.update(f"{area_id}|{municipality_code}|".encode())
                boundary_hash.update(bytes(geom))
                boundary_hash.update(b"\n")

            db_pois = {category: set() for category in ("food_social", "cultural_tourist")}
            for category, key, taxonomy in conn.execute(text(
                "SELECT category,destination_key,taxonomy_version "
                "FROM spatial.osm_pois ORDER BY category,destination_key"
            )):
                if taxonomy != "phase05_v2" or category not in db_pois:
                    raise RuntimeError("Canonical POI taxonomy differs from Phase 5")
                db_pois[category].add(key)
            db_stations = set()
            for key, taxonomy in conn.execute(text(
                "SELECT station_key,taxonomy_version FROM spatial.transit_stations ORDER BY station_key"
            )):
                if taxonomy != "phase05_v2":
                    raise RuntimeError("Canonical station taxonomy differs from Phase 5")
                db_stations.add(key)
            db_pois["station"] = db_stations
            counts = {category: len(keys) for category, keys in db_pois.items()}
            if counts != {"food_social": 3006, "cultural_tourist": 463, "station": 143}:
                raise RuntimeError(f"Canonical destination totals changed: {counts}")
            for category, path in INVENTORIES.items():
                if _inventory_rows(path) != db_pois[category]:
                    raise RuntimeError(f"Exported canonical IDs differ from PostGIS: {category}")

            folds = conn.execute(text(
                "SELECT count(DISTINCT heldout_area) areas,count(DISTINCT random_fold) random_folds,"
                "count(DISTINCT block_1500m_id) blocks,count(DISTINCT block_1500m_fold) block_folds "
                "FROM analysis.cv_assignments"
            )).one()
            split_blocks = conn.scalar(text(
                "SELECT count(*) FROM (SELECT block_1500m_id FROM analysis.cv_assignments "
                "WHERE block_1500m_id IS NOT NULL GROUP BY block_1500m_id "
                "HAVING count(DISTINCT block_1500m_fold)<>1) x"
            ))
            buffers = dict(conn.execute(text(
                "SELECT buffer_m,count(DISTINCT heldout_area) "
                "FROM analysis.cv_buffer_exclusions GROUP BY buffer_m"
            )).all())
            if tuple(folds) != (11, 5, 53, 5) or split_blocks or buffers != {500: 11, 1000: 11}:
                raise RuntimeError("Saved validation geometry/assignment structure changed")

            migrations = conn.execute(text(
                "SELECT migration_name,trim(file_hash_sha256) FROM meta.schema_migrations "
                "ORDER BY migration_name"
            )).all()
            source_rows = conn.execute(text(
                "SELECT source_file_id,relative_path,source_name,source_url,"
                "trim(file_hash_sha256),file_size,source_date,snapshot_date,acquisition_date "
                "FROM meta.source_files ORDER BY source_file_id"
            )).all()
            if len(migrations) != 17 or len(source_rows) != 58:
                raise RuntimeError("Registered source/migration count changed")
            for name, digest in migrations:
                path = ROOT / "sql/migrations" / name
                if not path.is_file() or sha256_file(path) != digest:
                    raise RuntimeError(f"Migration checksum mismatch: {name}")
            sources = []
            for row in source_rows:
                source_id, relative, name, url, digest, size, source_date, snapshot_date, acquired = row
                path = ROOT / relative
                if not path.is_file() or path.stat().st_size != size or sha256_file(path) != digest:
                    raise RuntimeError(f"Registered immutable source changed: {relative}")
                sources.append({"source_file_id": source_id, "relative_path": relative,
                                "source_name": name, "source_url": url, "sha256": digest,
                                "file_size": size, "source_date": str(source_date) if source_date else None,
                                "snapshot_date": str(snapshot_date) if snapshot_date else None,
                                "acquisition_date": str(acquired) if acquired else None})

            dbname, pg_version, postgis_version = conn.execute(text(
                "SELECT current_database(),version(),postgis_full_version()"
            )).one()
            return {
                "authoritative_database": dbname,
                "database_host": engine.url.host,
                "database_port": engine.url.port,
                "postgresql_version": pg_version,
                "postgis_version": postgis_version,
                "schema_migration_count": len(migrations),
                "migration_sha256": {name: digest for name, digest in migrations},
                "registered_source_count": len(sources),
                "source_file_registry": sources,
                "official_cv_area_geometry_sha256": boundary_hash.hexdigest(),
                "primary_dataset_view": "analysis.analysis_dataset_v1",
                "primary_sample_n": sample.n,
                "analysis_area_count": sample.areas,
                "cv_assignment_rows": current["cv_assignment_rows"],
                "cv_assignments_sha256": current["cv_assignments_sha256"],
                "phase9_freeze_sha256": sha256_file(FREEZE_GUARD),
                "phase9_recorded_artifact_count": len(current["phase9_file_sha256"]),
                "canonical_destination_counts": counts,
                "canonical_destination_taxonomy_version": "phase05_v2",
                "validation_designs": {"random_folds": 5, "block_side_m": 1500,
                                       "block_count": 53, "block_folds": 5,
                                       "heldout_areas": 11, "buffer_m": [500, 1000]},
            }
    finally:
        engine.dispose()


def _freeze_record(manifest: dict) -> str:
    release_id = manifest["release_id"]
    return f"""# Scientific freeze {release_id}

Created {manifest['created_at_local']} from Git commit `{manifest['git_commit']}`. This is the **empirical science v1** for thesis writing. The authoritative persistent layer is Docker PostgreSQL/PostGIS `{manifest['authoritative_database']}`; private raw data and credentials are **not** included. Source paths/hashes, 17 migrations, frozen scientific artifact hashes, the 23,144-row CV digest and the official area-geometry digest are in `scientific_manifest.json`.

## Frozen study and specifications

The **Copenhagen–Frederiksberg urban core** comprises Copenhagen Municipality and the administratively separate Frederiksberg Municipality. The common comparison has **{manifest['primary_sample_n']:,}** unique conventional entire-home listings with valid coordinates, official-area assignment, reachable walking station and observed positive listed nightly price; the outcome is `ln(price_nightly)` in user-confirmed DKK. Missing prices are never imputed. The 11 analysis areas are ten official Copenhagen districts plus Frederiksberg municipality.

Phase 9 **Base specification** M0/ME/MW/MEW uses property/listing and host/rental controls, municipality and City Hall centrality; ME and MW add matched Euclidean or network accessibility, while combined MEW is collinearity-sensitive exploratory. The **Area-context-adjusted core specification** M0_CTX/ME_CTX/MW_CTX/MEW_CTX adds log area population density and disposable income. It is chronologically a **Post-Phase-9 implementation of a planned contextual specification**, not the original Phase 9 baseline. Copenhagen context is district-level, Frederiksberg context municipality-level; income/area definitions are not perfectly harmonised.

Canonical `phase05_v2` food/social ({manifest['canonical_destination_counts']['food_social']:,}), cultural/tourist ({manifest['canonical_destination_counts']['cultural_tourist']:,}) and rail/metro/S-train ({manifest['canonical_destination_counts']['station']:,}) destinations and deduplication are frozen. Memorial-only objects and bus/tram-only primary stations remain excluded. Euclidean and walking features use the same destination IDs. The primary buffered endpoint universe, 800 m straight-line/10-minute network opportunity measures, continuous nearest-station measures, 4.8 km/h (80 m/min) walking speed, snap connectors and routing are frozen. Matched 1,200/1,600 m and 15/20-minute alternatives remain sensitivities. An official two-municipality-union endpoint restriction is a completed secondary sensitivity only; walking routes and district/internal municipal crossings are not clipped.

Saved random five-fold is a spatially interspersed benchmark. The 53 whole 1.5 km blocks allocated to five folds provide non-administrative robustness; multiple blocks form a fold. Eleven-area leave-one-area-out is the primary unseen-area test, holding out every area once. Buffered LOAO at 500/1,000 m is adjacency/separation robustness. Training-mean benchmark, semilog OLS with HC3, XGBoost candidate/tuning design, training-only preprocessing, transformations, seeds, outcome and evaluation metrics are frozen in the archived run metadata and pre-analysis/deviation records.

## Interpretation and completed checks

RQ1: straight-line and network access are empirically different measures, not evidence of network predictive superiority. RQ2: accessibility modestly improves the base specification, but its added geographic prediction is weak/unstable after observed area socioeconomic context; stable added value beyond that context and consistent walking-over-Euclidean superiority are **not supported**. RQ3: random, block, LOAO and buffered LOAO produce different/higher separated errors, but no error gap proves leakage alone. No causal, booking or occupancy claim follows. The frozen seven-row claim matrix and `reports/final_scientific_synthesis.md` give quantitative evidence.

Completed secondary work includes apartment/condo, reviewed, review-count, 15/20-minute, price-trim, area fixed-effect, spatial-error, geometric block/buffer, bus proximity, Copenhagen-only context, high-price-observability and destination-boundary checks. GTFS, TabICLv2, TabPFN, coordinate-uncertainty and all-room-types extensions remain deferred—not silently counted as results.

## What remains editable

The archived figures, formatted final tables, LaTeX files and captions are a **presentation snapshot at freeze time**, not immutable scientific pixels or formatting. Styling, axes, labels, captions, table layout, display precision and placement may change if they faithfully render the hashed scientific sources and preserve the claim interpretation. `docs/scientific_freeze_policy.md` defines allowed display edits, presentation release IDs and error classes. A new substantive data/sample/feature/fold/model/metric result requires a documented `scientific_freeze_v2`; v1 is never overwritten. The older Phase 10 freeze guard contains historical figure hashes, but the new scientific manifest does not make those figures immutable.
"""


def create() -> Path:
    local_now = datetime.now(LOCAL_TZ)
    utc_now = local_now.astimezone(timezone.utc)
    release_id = f"{local_now.date().isoformat()}_scientific_freeze_v1"
    destination = RELEASES / release_id
    if destination.exists():
        raise FileExistsError(f"Scientific release already exists; refusing overwrite: {destination}")

    db = _database_state()
    paths = release_files()
    science = [path for path in paths if _science_path(path)]
    if not science:
        raise RuntimeError("No machine-readable scientific sources selected")
    required_science = {
        "outputs/tables/phase09/model_performance.csv",
        "outputs/tables/phase09/incremental_accessibility.csv",
        "outputs/tables/phase09/ols_coefficients.csv",
        "outputs/tables/phase09/fold_performance.csv",
        "outputs/tables/context_augmented_performance.csv",
        "outputs/tables/context_comparison.csv",
        "outputs/tables/context_augmented_ols.csv",
        "outputs/tables/copenhagen_only_context_sensitivity.csv",
        "outputs/tables/phase10/robustness_summary.csv",
        "outputs/tables/price_observability_performance.csv",
        "outputs/tables/price_observability_comparison.csv",
        "outputs/tables/boundary_sensitivity_comparison.csv",
        "outputs/tables/phase08/cv_fold_summary.csv",
        "outputs/tables/phase10/buffer_separation.csv",
        "outputs/tables/conclusion_stability.csv",
        "outputs/tables/final/appendix_destination_taxonomy.csv",
        "outputs/tables/final/appendix_destination_counts.csv",
    }
    selected = {path.relative_to(ROOT).as_posix() for path in science}
    if required_science - selected:
        raise RuntimeError(f"Missing scientific freeze source(s): {sorted(required_science - selected)}")
    science_hashes = {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in science}
    figure_paths = [path.relative_to(ROOT).as_posix() for path in paths
                    if path.relative_to(ROOT).as_posix().startswith("outputs/figures/")]
    manifest = {
        "release_id": release_id,
        "created_at_local": local_now.isoformat(timespec="seconds"),
        "created_at_utc": utc_now.isoformat(timespec="seconds"),
        "git_commit": _run_git("rev-parse", "HEAD"),
        "git_dirty_status": _run_git("status", "--short").splitlines(),
        "study_area_definition": "Copenhagen–Frederiksberg urban core = Copenhagen Municipality + Frederiksberg Municipality",
        "scientific_results_mutable": False,
        "presentation_outputs_mutable": True,
        "scientific_file_sha256": science_hashes,
        "scientific_file_count": len(science_hashes),
        "presentation_snapshot_figure_paths": figure_paths,
        "presentation_snapshot_file_count": len(paths) - len(science),
        "osm_snapshot_identifier": "Copenhagen.osm.pbf / BBBike / 2026-09-26",
        **db,
    }

    RELEASES.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.staging-", dir=RELEASES))
    try:
        for path in paths:
            target = staging / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        for rel, digest in science_hashes.items():
            if sha256_file(staging / rel) != digest:
                raise RuntimeError(f"Copied scientific source failed SHA-256 verification: {rel}")
        (staging / "scientific_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8")
        (staging / "SCIENTIFIC_FREEZE.md").write_text(_freeze_record(manifest), encoding="utf-8")
        if destination.exists():
            raise FileExistsError(f"Scientific release appeared during staging: {destination}")
        os.rename(staging, destination)
    except Exception:
        # Preserve a failed staging directory for inspection; never delete data
        # or silently create a v2 release.
        raise
    return destination


if __name__ == "__main__":
    created = create()
    print(f"Scientific release created without model execution: {created}")

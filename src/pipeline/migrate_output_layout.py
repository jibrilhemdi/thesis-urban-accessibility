"""Move existing flat aggregate outputs into phase folders without changing bytes.

Only the Phase 10 freeze/metadata manifests are rewritten to record new paths;
the frozen Phase 9 table and figure bytes and CV assignments are untouched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.ingestion.common import PROJECT_ROOT, sha256_file, write_json
from src.pipeline.output_paths import output_file


PHASE_FOR_BARE_TABLE = {
    "amenities_prevalence.csv": "phase02",
    "control_missingness.csv": "phase02",
    "price_distribution.csv": "phase02",
    "property_type_decisions.csv": "phase02",
    "sample_construction.csv": "phase02",
    "context_source_assessment.csv": "phase03",
    "cv_area_counts.csv": "phase04",
    "context_area_redundancy.csv": "phase07",
    "missingness_report.csv": "phase07",
    "price_missingness_comparison.csv": "phase07",
    "redundancy_pairs.csv": "phase07",
    "vif_diagnostics.csv": "phase07",
    "conclusion_stability.csv": "phase10",
    "robustness_summary.csv": "phase10",
    "robustness_summary.md": "phase10",
}
PREFIX = re.compile(r"^(phase\d{2})_(.+)$")


def destination(kind: str, name: str) -> Path:
    if kind == "tables" and name == "phase10_phase9_freeze.json":
        return output_file("tables", "phase10", "primary_freeze.json")
    match = PREFIX.fullmatch(name)
    if match:
        phase, basename = match.groups()
    elif kind == "tables" and name in PHASE_FOR_BARE_TABLE:
        phase, basename = PHASE_FOR_BARE_TABLE[name], name
    else:
        raise ValueError(f"Unclassified flat aggregate output: {kind}/{name}")
    return output_file(kind, phase, basename)


def migrate() -> dict:
    planned: list[tuple[Path, Path, str]] = []
    for kind in ("tables", "figures"):
        root = PROJECT_ROOT / "outputs" / kind
        for source in sorted(root.iterdir()):
            if not source.is_file() or source.name == ".gitkeep":
                continue
            target = destination(kind, source.name)
            if target.exists():
                raise FileExistsError(f"Refusing to overwrite existing output: {target}")
            planned.append((source, target, sha256_file(source)))
    if not planned:
        return {"moved": 0, "phase9_bytes_preserved": True}

    freeze_source = PROJECT_ROOT / "outputs/tables/phase10_phase9_freeze.json"
    freeze = json.loads(freeze_source.read_text(encoding="utf-8"))
    for old_relative, digest in freeze["phase9_file_sha256"].items():
        old = PROJECT_ROOT / old_relative
        if not old.is_file() or sha256_file(old) != digest:
            raise RuntimeError(f"Frozen Phase 9 artifact differs before layout migration: {old_relative}")

    for source, target, digest in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        if sha256_file(target) != digest:
            raise RuntimeError(f"Output bytes changed during move: {target}")

    freeze_target = destination("tables", freeze_source.name)
    rewritten = {}
    for old_relative, digest in freeze["phase9_file_sha256"].items():
        old = Path(old_relative)
        new = destination(old.parts[1], old.name)
        rewritten[new.relative_to(PROJECT_ROOT).as_posix()] = digest
    freeze["phase9_file_sha256"] = dict(sorted(rewritten.items()))
    write_json(freeze_target, freeze)
    metadata_path = output_file("tables", "phase10", "run_metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["phase9_freeze_sha256"] = sha256_file(freeze_target)
    write_json(metadata_path, metadata)

    ledger = {"migration_version": "phase_output_layout_v1",
              "moved": len(planned), "phase9_bytes_preserved": True,
              "note": "SHA-256 values are from before the Phase 10 manifest rewrite and Phase 11 audit refresh.",
              "files": [{"from": source.relative_to(PROJECT_ROOT).as_posix(),
                         "to": target.relative_to(PROJECT_ROOT).as_posix(),
                         "sha256_before_metadata_update": digest} for source, target, digest in planned]}
    write_json(output_file("tables", "phase11", "layout_migration.json"), ledger)
    return {"moved": len(planned), "phase9_bytes_preserved": True,
            "phase9_artifacts": len(rewritten)}


if __name__ == "__main__":
    print(json.dumps(migrate(), indent=2))

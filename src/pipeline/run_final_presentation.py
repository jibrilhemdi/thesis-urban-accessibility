"""Regenerate final presentation only, guarded by scientific-v1 hashes."""

from __future__ import annotations

import argparse
import json

from src.ingestion.common import PROJECT_ROOT, sha256_file


RELEASE = PROJECT_ROOT / "outputs/releases/2026-09-30_scientific_freeze_v1"


def verify_science() -> int:
    manifest = json.loads((RELEASE / "scientific_manifest.json").read_text(encoding="utf-8"))
    if manifest["scientific_results_mutable"] or not manifest["presentation_outputs_mutable"]:
        raise RuntimeError("Scientific/presentation mutability flags are inconsistent")
    failures = [relative for relative, expected in manifest["scientific_file_sha256"].items()
                if not (PROJECT_ROOT / relative).is_file() or
                sha256_file(PROJECT_ROOT / relative) != expected]
    if failures:
        raise RuntimeError(f"Frozen scientific source changed: {failures[:5]}")
    return len(manifest["scientific_file_sha256"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    n = verify_science()
    if args.check_only:
        print(f"Frozen scientific sources verified: {n}")
        return
    # Imports are kept inside this guarded branch: these functions read frozen
    # aggregate sources and write only formatted final tables, figures and TeX.
    from src.pipeline.revise_final_outputs_pre_freeze import run as revise
    from src.pipeline.export_final_latex_tables import main as export_latex

    revise()
    export_latex()
    if verify_science() != n:
        raise RuntimeError("Scientific source inventory changed during presentation export")
    print(f"Presentation regenerated; {n} scientific source hashes remain unchanged")


if __name__ == "__main__":
    main()

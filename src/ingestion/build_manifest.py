"""Validate downloaded raw files and print a compact collection summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import MANIFEST_PATH, PROJECT_ROOT, sha256_file, utc_now, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Recompute and verify every recorded checksum.")
    args = parser.parse_args()

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError("No source manifest found. Download at least one source first.")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    verified = 0
    missing = 0
    mismatched = 0
    total_bytes = 0
    for entry in manifest.get("files", []):
        path = PROJECT_ROOT / entry["local_path"]
        if not path.exists():
            missing += 1
            print(f"MISSING {entry['local_path']}")
            continue
        total_bytes += path.stat().st_size
        if args.verify:
            actual = sha256_file(path)
            if actual != entry.get("sha256"):
                mismatched += 1
                print(f"MISMATCH {entry['local_path']}: manifest={entry.get('sha256')} actual={actual}")
            else:
                verified += 1

    summary = {
        "generated_at_utc": utc_now(),
        "manifest_path": MANIFEST_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "file_count": len(manifest.get("files", [])),
        "total_bytes": total_bytes,
        "missing_files": missing,
        "checksum_mismatches": mismatched,
        "checksums_verified": verified if args.verify else None,
    }
    write_json(PROJECT_ROOT / "data" / "metadata" / "collection_summary.json", summary)
    print(json.dumps(summary, indent=2))
    if missing or mismatched:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Create or audit a public, data-free scientific snapshot.

Only explicitly allowed repository paths are considered. Raw/interim/processed
Airbnb data, local credentials and operating-system/LaTeX by-products never
enter the archive. This is packaging only; it does not run the analysis.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import zipfile

from src.ingestion.common import PROJECT_ROOT


ROOT_FILES = ("README.md", "AGENTS.md", "Makefile", "compose.yaml",
              ".env.example", "requirements.txt", ".gitignore")
ROOT_DIRS = ("docs", "reports", "src", "sql", "tests", "data/metadata",
             "outputs/tables", "outputs/figures", "outputs/latex")
BAD_NAMES = {".DS_Store", "__MACOSX", ".env", "__pycache__", ".pytest_cache",
             ".ipynb_checkpoints", ".venv", "venv"}
BAD_SUFFIXES = (".aux", ".log", ".out", ".toc", ".lof", ".lot", ".fls",
                ".fdb_latexmk", ".synctex.gz", ".bbl", ".blg", ".pyc")
PRIVATE_COLUMNS = {"listing_id", "host_id", "host_name", "metric_x", "metric_y",
                   "geom", "geom_25832", "price_nightly", "log_price"}
REQUIRED = ("outputs/tables/final/table1_sample_construction.csv",
            "outputs/tables/final/table_rq2_area_context.csv",
            "outputs/figures/final/appendix_geometric_block_cv.png",
            "outputs/figures/final/appendix_boundary_catchment_example.png",
            "outputs/latex/main_tables.tex", "outputs/latex/appendix_tables.tex")


def excluded(path: Path) -> bool:
    return any(part in BAD_NAMES or part.startswith("._") for part in path.parts) or \
        path.name.endswith(BAD_SUFFIXES)


def release_files(root: Path = PROJECT_ROOT) -> list[Path]:
    for name in REQUIRED:
        if not (root / name).is_file():
            raise RuntimeError(f"Required release output is missing: {name}")
    paths = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for name in ROOT_DIRS:
        base = root / name
        if base.is_dir():
            paths.extend(path for path in base.rglob("*") if path.is_file())
    selected = []
    for path in paths:
        relative = path.relative_to(root)
        if excluded(relative):
            continue
        if path.is_symlink():
            raise RuntimeError(f"Release input must not be a symlink: {relative}")
        if relative.parts[:2] == ("outputs", "tables") and path.suffix == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                fields = set(next(csv.reader(handle), []))
            if fields & PRIVATE_COLUMNS:
                raise RuntimeError(f"Private row-level column in release table: {relative}")
            if {"latitude", "longitude"} & fields and "destination_" not in path.name:
                raise RuntimeError(f"Coordinate column in non-OSM release table: {relative}")
        selected.append(path)
    return sorted(set(selected), key=lambda path: path.relative_to(root).as_posix())


def audit_archive(archive: Path) -> tuple[int, list[str]]:
    """Inspect a ZIP without extracting or reading private payloads."""
    with zipfile.ZipFile(archive) as handle:
        names = [info.filename for info in handle.infolist() if not info.is_dir()]
    forbidden = []
    for name in names:
        path = Path(name)
        parts = path.parts
        contains_private_data = any(parts[index:index + 2] in
                                    (("data", "raw"), ("data", "interim"),
                                     ("data", "processed"))
                                    for index in range(len(parts) - 1))
        if excluded(path) or contains_private_data or ".." in parts:
            forbidden.append(name)
    return len(names), forbidden


def create_archive(destination: Path, paths: list[Path], root: Path = PROJECT_ROOT) -> None:
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing snapshot: {destination}")
    manifest = {}
    for path in paths:
        with path.open("rb") as handle:
            manifest[path.relative_to(root).as_posix()] = hashlib.file_digest(
                handle, "sha256").hexdigest()
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as handle:
        for path in paths:
            handle.write(path, arcname=path.relative_to(root).as_posix())
        handle.writestr("release_manifest.json", json.dumps(manifest, indent=2,
                                                               sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate allowlisted inputs only")
    parser.add_argument("--output", type=Path, help="Create a new public ZIP; never overwrite")
    parser.add_argument("--audit-archive", type=Path,
                        help="Inspect an existing ZIP for forbidden packaging/private paths")
    args = parser.parse_args()
    if args.audit_archive:
        count, forbidden = audit_archive(args.audit_archive)
        print(f"Archive entries: {count}; forbidden paths: {len(forbidden)}")
        if forbidden:
            print("Unsafe archive: examples:", ", ".join(forbidden[:5]))
            raise SystemExit(1)
        return
    if not (args.check or args.output):
        parser.error("Specify --check, --output, or --audit-archive")
    paths = release_files()
    print(f"Public release inputs checked: {len(paths)} files")
    if args.output:
        create_archive(args.output, paths)
        print(f"Created {args.output}")


if __name__ == "__main__":
    main()

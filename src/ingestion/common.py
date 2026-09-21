"""Small, dependency-light helpers for reproducible source downloads."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "source_manifest.json"
USER_AGENT = "copenhagen-urban-accessibility-thesis/0.1 (academic research; contact via repository)"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temporary.replace(path)


def read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {"generated_at_utc": utc_now(), "files": []}
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def update_manifest(entries: Iterable[dict[str, Any]]) -> None:
    manifest = read_manifest()
    current = {entry["local_path"]: entry for entry in manifest.get("files", [])}
    for entry in entries:
        current[entry["local_path"]] = entry
    manifest["generated_at_utc"] = utc_now()
    manifest["files"] = sorted(current.values(), key=lambda item: item["local_path"])
    write_json(MANIFEST_PATH, manifest)


def download_url(url: str, destination: Path, *, force: bool = False, timeout: int = 180) -> dict[str, Any]:
    """Stream a URL to a local file and return a manifest record."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    relative_path = destination.relative_to(PROJECT_ROOT).as_posix()
    if destination.exists() and not force:
        return {
            "source_url": url,
            "local_path": relative_path,
            "downloaded_at_utc": utc_now(),
            "size_bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            "status": "already_present",
        }

    request = Request(url, headers={"User-Agent": USER_AGENT})
    fd, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".part", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with urlopen(request, timeout=timeout) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
            content_type = response.headers.get("Content-Type")
            last_modified = response.headers.get("Last-Modified")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return {
        "source_url": url,
        "local_path": relative_path,
        "downloaded_at_utc": utc_now(),
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "content_type": content_type,
        "source_last_modified": last_modified,
        "status": "downloaded",
    }

"""Canonical phase-organised paths for aggregate research outputs.

The optional ``phaseNN_`` prefix is accepted at the call boundary for older
runner/table names, but is never present in an on-disk output basename.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.ingestion.common import PROJECT_ROOT


_PREFIX = re.compile(r"^(phase\d{2})_(.+)$")


def output_file(kind: str, phase: str, name: str) -> Path:
    if kind not in {"tables", "figures"} or not re.fullmatch(r"phase\d{2}", phase):
        raise ValueError("Expected tables/figures and a zero-padded phase number")
    if Path(name).name != name or name in {"", ".", ".."}:
        raise ValueError("Output name must be a basename")
    match = _PREFIX.fullmatch(name)
    if match:
        phase, name = match.groups()
    return PROJECT_ROOT / "outputs" / kind / phase / name


class PhaseDirectory:
    """Small path adapter for existing runners; all returned values are Paths."""

    def __init__(self, kind: str, phase: str) -> None:
        self.kind = kind
        self.phase = phase
        self.path = PROJECT_ROOT / "outputs" / kind / phase

    def __truediv__(self, name: str) -> Path:
        return output_file(self.kind, self.phase, name)

    def mkdir(self, *args, **kwargs) -> None:
        self.path.mkdir(*args, **kwargs)

    def glob(self, pattern: str):
        match = _PREFIX.fullmatch(pattern)
        if match:
            phase, pattern = match.groups()
            return (PROJECT_ROOT / "outputs" / self.kind / phase).glob(pattern)
        return self.path.glob(pattern)

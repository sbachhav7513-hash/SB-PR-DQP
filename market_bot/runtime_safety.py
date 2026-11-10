from __future__ import annotations

import tempfile
from pathlib import Path


def require_temporary_path(path: str | Path, *, purpose: str) -> Path:
    resolved = Path(path).resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved.relative_to(temporary_root)
    except ValueError as exc:
        raise ValueError(f"{purpose} must be inside the system temporary directory") from exc
    return resolved

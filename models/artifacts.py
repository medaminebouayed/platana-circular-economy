"""Local, immutable model artifact versioning.

Each training run writes to ``checkpoints/versions/<version_id>/``. A small
``latest.json`` pointer selects the active version without overwriting the
actual model artifacts. The pointer is intentionally separate from MLflow:
local inference stays reproducible even when the tracking server is offline.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def new_version_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


def create_version_dir(checkpoint_dir: str | Path, prefix: str) -> tuple[str, Path]:
    version_id = new_version_id(prefix)
    version_dir = Path(checkpoint_dir) / "versions" / version_id
    version_dir.mkdir(parents=True, exist_ok=False)
    return version_id, version_dir


def write_manifest(version_dir: str | Path, manifest: dict[str, Any]) -> Path:
    path = Path(version_dir) / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def promote_version(
    checkpoint_dir: str | Path,
    version_id: str,
    artifacts: dict[str, str],
    pointer_name: str = "latest.json",
) -> Path:
    """Atomically update a named active-version pointer after all files are written."""
    checkpoint_dir = Path(checkpoint_dir)
    payload = {
        "version_id": version_id,
        "relative_path": f"versions/{version_id}",
        "artifacts": artifacts,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    destination = checkpoint_dir / pointer_name
    temporary = checkpoint_dir / f".{pointer_name}-{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def resolve_latest_artifact(
    checkpoint_dir: str | Path,
    artifact_name: str,
    pointer_name: str = "latest.json",
) -> tuple[Path | None, str | None]:
    """Resolve an artifact from a named pointer, returning ``(path, version_id)``."""
    checkpoint_dir = Path(checkpoint_dir)
    pointer_path = checkpoint_dir / pointer_name
    if not pointer_path.is_file():
        return None, None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        version_id = str(pointer["version_id"])
        relative_path = Path(pointer["relative_path"])
        candidate = checkpoint_dir / relative_path / artifact_name
        if candidate.is_file():
            return candidate, version_id
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    return None, None


def resolve_version_artifact(
    checkpoint_dir: str | Path, version_id: str, artifact_name: str
) -> Path:
    """Resolve one artifact from an immutable version directory safely."""
    if not version_id or Path(version_id).name != version_id:
        raise ValueError("version_id must be a single version directory name")
    if not artifact_name or Path(artifact_name).name != artifact_name:
        raise ValueError("artifact_name must be a filename, not a path")
    candidate = Path(checkpoint_dir) / "versions" / version_id / artifact_name
    if not candidate.is_file():
        raise FileNotFoundError(f"Artifact not found for version {version_id}: {candidate}")
    return candidate

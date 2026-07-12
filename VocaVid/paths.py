from __future__ import annotations

from pathlib import Path

APP_STORAGE_DIR = ".VocaVid"
LEGACY_STORAGE_DIR = "." + "music" + "video" + "gen"
STORAGE_DIRS = (APP_STORAGE_DIR, LEGACY_STORAGE_DIR)


def slug_folder_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "project"


def storage_relative_path(app_root: Path, value: str | Path | None) -> str:
    if value is None:
        return ""
    raw = str(value)
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    for storage_dir in STORAGE_DIRS:
        marker = f"/{storage_dir}/"
        if marker in normalized:
            return normalized.split(marker, 1)[1].lstrip("/")
        prefix = f"{storage_dir}/"
        if normalized.startswith(prefix):
            return normalized[len(prefix):].lstrip("/")
    app_root = app_root.resolve()
    path = Path(raw)
    try:
        return path.resolve().relative_to(app_root).as_posix()
    except (OSError, ValueError):
        return raw


def resolve_storage_path(app_root: Path, value: str | Path | None) -> Path:
    raw = str(value or "")
    path = Path(raw)
    normalized = raw.replace("\\", "/")
    for storage_dir in STORAGE_DIRS:
        marker = f"/{storage_dir}/"
        if marker in normalized:
            return app_root / normalized.split(marker, 1)[1].lstrip("/")
        prefix = f"{storage_dir}/"
        if normalized.startswith(prefix):
            return app_root / normalized[len(prefix):].lstrip("/")
    if _is_internal_relative_path(normalized):
        return app_root / normalized.lstrip("/")
    return path


def is_internal_storage_path(value: str | Path | None) -> bool:
    normalized = str(value or "").replace("\\", "/")
    return (
        _is_internal_relative_path(normalized)
        or any(
            normalized.startswith(f"{storage_dir}/") or f"/{storage_dir}/" in normalized
            for storage_dir in STORAGE_DIRS
        )
    )


def _is_internal_relative_path(normalized: str) -> bool:
    return normalized.startswith("uploads/") or normalized.startswith("outputs/")

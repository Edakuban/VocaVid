from __future__ import annotations

from pathlib import Path

APP_STORAGE_DIR = ".VocaVid"
LEGACY_STORAGE_DIR = "." + "music" + "video" + "gen"
STORAGE_DIRS = (APP_STORAGE_DIR, LEGACY_STORAGE_DIR)


def slug_folder_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "project"


def project_output_file_stem(value: str) -> str:
    parts = [part.strip() for part in str(value or "").split(" - ") if part.strip()]
    if len(parts) >= 3 and parts[-2].isdigit():
        base = f"{parts[-2]} - {parts[-1]}"
    else:
        base = str(value or "").strip() or "project"
    return _windows_safe_filename(base) or "project"


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


def _windows_safe_filename(value: str, max_length: int = 120) -> str:
    cleaned = "".join("_" if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch for ch in value)
    cleaned = " ".join(cleaned.split()).strip(" .")
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
    if cleaned.upper() in reserved_names:
        cleaned = f"{cleaned}_"
    return cleaned[:max_length].rstrip(" .")

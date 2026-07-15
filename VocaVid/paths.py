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
    raw = _safe_path_text(value)
    if not raw:
        return ""
    normalized = raw.replace("\\", "/")
    for storage_dir in STORAGE_DIRS:
        marker = f"/{storage_dir}/"
        if marker in normalized:
            return _clean_storage_suffix(normalized.split(marker, 1)[1])
        prefix = f"{storage_dir}/"
        if normalized.startswith(prefix):
            return _clean_storage_suffix(normalized[len(prefix):])
    app_root = app_root.resolve()
    path = Path(raw)
    try:
        return path.resolve().relative_to(app_root).as_posix()
    except (OSError, ValueError):
        return raw


def resolve_storage_path(app_root: Path, value: str | Path | None) -> Path:
    raw = _safe_path_text(value or "")
    normalized = raw.replace("\\", "/")
    for storage_dir in STORAGE_DIRS:
        marker = f"/{storage_dir}/"
        if marker in normalized:
            return app_root / _clean_storage_suffix(normalized.split(marker, 1)[1])
        prefix = f"{storage_dir}/"
        if normalized.startswith(prefix):
            return app_root / _clean_storage_suffix(normalized[len(prefix):])
    if _is_internal_relative_path(normalized):
        return app_root / _clean_storage_suffix(normalized)
    return Path(raw)


def is_internal_storage_path(value: str | Path | None) -> bool:
    normalized = _safe_path_text(value or "").replace("\\", "/")
    return (
        _is_internal_relative_path(normalized)
        or any(
            normalized.startswith(f"{storage_dir}/") or f"/{storage_dir}/" in normalized
            for storage_dir in STORAGE_DIRS
        )
    )


def _is_internal_relative_path(normalized: str) -> bool:
    return normalized.startswith("uploads/") or normalized.startswith("outputs/")


def _safe_path_text(value: str | Path) -> str:
    raw = str(value)
    if "\x00" in raw or "\r" in raw or "\n" in raw:
        raise ValueError("Storage path contains unsupported control characters")
    return raw


def _clean_storage_suffix(value: str) -> str:
    parts: list[str] = []
    for part in value.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("Storage path must not escape the app root")
        parts.append(part)
    return "/".join(parts)


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

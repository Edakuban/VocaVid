from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from ..lyrics import is_chorus_section
from ..paths import is_internal_storage_path, resolve_storage_path, storage_relative_path
from ..store import Store
from . import context


def _run_project_action(pipeline, project_id: int, action: str, selected_indices: list[int]) -> object:
    method_names = {
        "prompts": "generate_prompts",
        "video-prompts": "generate_video_prompts",
        "images": "generate_images",
        "avatar-image": "generate_avatar_images",
        "clips": "generate_clips",
    }
    return getattr(pipeline, method_names[action])(project_id, selected_indices)


def _selected_action_indices(project_id: int, item_kind: str, selected: list[int], store: Store) -> list[int]:
    if selected:
        selected_set = {int(index) for index in selected}
    else:
        selected_set = set()
    rows = store.list_segments(project_id) if item_kind == "segments" else store.list_lines(project_id)
    if selected_set:
        rows = [row for row in rows if _row_index(row, item_kind) in selected_set]
    rows = [row for row in rows if not bool(_row_value(row, "video_approved", 0))]
    return [_row_index(row, item_kind) for row in rows]


def _job_name(label: str, project_name: str, selected_indices: list[int] | None = None, item_kind: str | None = None) -> str:
    selected = sorted(int(index) + 1 for index in (selected_indices or []))
    if not selected:
        return f"{label}: {project_name}"
    if item_kind and len(selected) == 1:
        item_label = "segment" if item_kind == "segments" else "line"
        return f"{label}: {project_name} ({item_label} {selected[0]})"
    indices = ", ".join(str(index) for index in selected)
    return f"{label}: {project_name} (segments {indices})"


def _action_item_kind(action: str, has_segments: bool) -> str:
    if action == "align" or action == "segments":
        return "lines"
    return "segments" if has_segments else "lines"


def _locked_indices(active_jobs, item_kind: str, rows) -> dict[int, str]:
    row_indices = [_row_index(row, item_kind) for row in rows]
    locked: dict[int, str] = {}
    for job in active_jobs:
        if job.item_kind != item_kind:
            continue
        selected = list(job.selected_indices or [])
        indices = selected if selected else row_indices
        for index in indices:
            locked[int(index)] = job.status
    return locked


def _row_index(row, item_kind: str) -> int:
    key = "segment_index" if item_kind == "segments" else "line_index"
    return int(row[key])


def _merge_row_class(row_class: str, extra_class: str) -> str:
    if not extra_class:
        return row_class
    if not row_class:
        return f' class="{extra_class}"'
    return row_class[:-1] + f" {extra_class}\""


def _url_for_html_attribute(url: str) -> str:
    return str(url).replace("&amp;", "&")


def _url_for_media_attribute(url: str) -> str:
    return json.dumps(_url_for_html_attribute(url))[1:-1]


def _job_average_seconds(job, average_durations: dict[str, float]) -> float | None:
    action = job.action or _action_from_job_name(job.name)
    if not action:
        return None
    return average_durations.get(action)


def _action_from_job_name(name: str) -> str:
    label = str(name).split(":", 1)[0].strip()
    return {
        "generate prompts": "prompts",
        "generate video prompts": "video-prompts",
        "generate images": "images",
        "generate avatar image": "avatar-image",
        "generate clips": "clips",
        "align": "align",
        "build segments": "segments",
        "generate scene plan": "scene-plan",
        "assemble": "assemble",
    }.get(label, "")


def _duration_html(seconds: float | None) -> str:
    if seconds is None:
        return ""
    return _text(_format_duration(seconds))


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return ""
    total = max(0, int(round(float(seconds))))
    minutes, remaining = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {remaining}s"
    return f"{remaining}s"


def _row_value(row, key: str, default):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _reference_paths_from_text(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _reference_paths_from_json(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return _reference_paths_from_text(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _attr(value) -> str:
    return escape(str(value), quote=True)


def _js_arg(value) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _js_string_arg(value) -> str:
    return json.dumps(str(value))


def _text(value) -> str:
    return escape(str(value), quote=False)


def _multiline_text_html(value: str) -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return '<div class="lyrics-lines">' + "".join(f"<div>{_text(line)}</div>" for line in lines) + "</div>"


def _timing_text(start, end) -> str:
    if start is None or end is None:
        return ""
    return f"{float(start):.1f} - {float(end):.1f}"


def _time_value(value) -> str:
    if value is None:
        return ""
    return f"{float(value):.1f}"


def _comfy_output_url(comfy_base_url: str, output_path: str) -> str:
    path = Path(output_path.replace("\\", "/"))
    filename = path.name
    subfolder = path.parent.as_posix()
    url = f"{comfy_base_url.rstrip('/')}/view?filename={quote(filename)}"
    if subfolder and subfolder != ".":
        url += f"&amp;subfolder={quote(subfolder, safe='')}"
    return f"{url}&amp;type=output"


def _generated_asset_url(project, path: str) -> str:
    if _is_local_project_asset(path):
        return _local_asset_url(path)
    return _comfy_output_url(_row_value(project, "comfy_base_url", "http://127.0.0.1:8188"), path)


def _is_local_project_asset(path: str) -> bool:
    if is_internal_storage_path(path):
        return True
    try:
        Path(path).resolve().relative_to(context.APP_ROOT.resolve())
        return True
    except (OSError, ValueError):
        return False


def _local_asset_url(path: str) -> str:
    candidate = resolve_storage_path(context.APP_ROOT, path)
    normalized = storage_relative_path(context.APP_ROOT, path)
    url = "/assets/" + quote(normalized.lstrip("/"), safe="/")
    version = _local_asset_version(candidate, normalized)
    return f"{url}?v={version}" if version else url


def _local_asset_version(candidate: Path, normalized: str) -> str:
    candidates = [candidate]
    normalized_path = normalized.lstrip("/").replace("/", "\\")
    if normalized_path:
        candidates.append(context.APP_ROOT / normalized_path)
    for item in candidates:
        try:
            stat = item.stat()
        except OSError:
            continue
        return f"{stat.st_mtime_ns}-{stat.st_size}"
    return ""


def _section_class(section: str, is_chorus: bool) -> str:
    section_type = _section_type(section, is_chorus)
    if section_type == "refrain":
        return "section-chorus"
    if section_type == "bridge":
        return "section-bridge"
    if section_type == "verse":
        return "section-verse"
    return "section-gap"


def _section_type(section: str, is_chorus: bool) -> str:
    value = str(section or "").lower()
    if is_chorus or is_chorus_section(value):
        return "refrain"
    if "bridge" in value:
        return "bridge"
    if "verse" in value:
        return "verse"
    if "instrumental" in value or "break" in value or "gap" in value or value == "":
        return "gap"
    return "gap"


def _section_legend_html() -> str:
    return """
<div class="section-legend">
  <span><span class="legend-swatch section-gap"></span>Other</span>
  <span><span class="legend-swatch section-verse"></span>Verse</span>
  <span><span class="legend-swatch section-bridge"></span>Bridge</span>
  <span><span class="legend-swatch section-chorus"></span>Refrain</span>
</div>
"""


def _row_class(section: str, is_chorus: bool, confidence, approved: bool = False) -> str:
    classes = [_section_class(section, is_chorus)]
    if approved:
        classes.append("approved-row")
    if confidence is not None and float(confidence) < 0.45:
        classes.append("low-confidence")
    return f' class="{" ".join(classes)}"'


def _line_confidence_by_index(lines) -> dict[int, float]:
    values: dict[int, float] = {}
    for line in lines:
        confidence = _display_confidence(line)
        if confidence is None:
            continue
        try:
            values[int(line["line_index"])] = float(confidence)
        except (KeyError, TypeError, ValueError):
            continue
    return values


def _display_confidence(row):
    if _is_sparse_fallback_row(row):
        return None
    return _row_value(row, "confidence", None)


def _is_sparse_fallback_row(row) -> bool:
    return str(_row_value(row, "error", "") or "").startswith("Sparse Whisper alignment;")


def _segment_confidence_html(segment, confidence_by_line: dict[int, float]) -> str:
    values = [
        confidence_by_line[index]
        for index in _source_line_indices(segment)
        if index in confidence_by_line
    ]
    if not values:
        return ""
    confidence = min(values)
    return f'<div class="timing-confidence">Confidence {round(confidence * 100)}%</div>'


def _source_line_indices(segment) -> list[int]:
    value = _row_value(segment, "source_line_indices", [])
    if isinstance(value, str):
        try:
            value = json.loads(value or "[]")
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        return []
    indices: list[int] = []
    for item in value:
        try:
            indices.append(int(item))
        except (TypeError, ValueError):
            continue
    return indices


def _status_html(status: str, error: str) -> str:
    error_html = f'<div class="status-error">{_text(error)}</div>' if error else ""
    return f'<div class="status">{_text(status)}</div>{error_html}'


def _all_videos_approved(rows) -> bool:
    return bool(rows) and all(bool(_row_value(row, "video_approved", 0)) for row in rows)

__all__ = [
    "_run_project_action",
    "_selected_action_indices",
    "_job_name",
    "_action_item_kind",
    "_locked_indices",
    "_row_index",
    "_merge_row_class",
    "_url_for_html_attribute",
    "_url_for_media_attribute",
    "_job_average_seconds",
    "_action_from_job_name",
    "_duration_html",
    "_format_duration",
    "_row_value",
    "_reference_paths_from_text",
    "_reference_paths_from_json",
    "_attr",
    "_js_arg",
    "_js_string_arg",
    "_text",
    "_multiline_text_html",
    "_timing_text",
    "_time_value",
    "_comfy_output_url",
    "_generated_asset_url",
    "_is_local_project_asset",
    "_local_asset_url",
    "_local_asset_version",
    "_section_class",
    "_section_type",
    "_section_legend_html",
    "_row_class",
    "_line_confidence_by_index",
    "_display_confidence",
    "_is_sparse_fallback_row",
    "_segment_confidence_html",
    "_source_line_indices",
    "_status_html",
    "_all_videos_approved",
]

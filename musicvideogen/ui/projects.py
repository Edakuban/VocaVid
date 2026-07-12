from __future__ import annotations

import re

from .context import JobOptions
from .formatting import (
    _all_videos_approved,
    _attr,
    _format_duration,
    _generated_asset_url,
    _locked_indices,
    _row_value,
    _section_type,
    _text,
)
from .forms import (
    _action_button,
    _avatar_gender_select_html,
    _clear_project_html,
    _clip_lightbox_html,
    _image_lightbox_html,
    _scroll_top_button_html,
    _segment_settings_html,
    _work_items_html,
)
from .queue import (
    _queue_control_html,
    _queue_estimate_html,
    _queue_estimate_seconds,
    _queue_modal_html,
)
from .storyboard import _storyboard_html


def _projects_html(
    projects,
    jobs,
    average_durations: dict[str, float] | None = None,
    queue_estimate_seconds: float | None = None,
    job_options: JobOptions | None = None,
    project_previews: dict[int, list] | None = None,
) -> str:
    average_durations = average_durations or {}
    job_options = job_options or JobOptions()
    project_previews = project_previews or {}
    active_project_ids = {int(job.project_id) for job in jobs if job.project_id and job.status in {"queued", "running"}}
    rows = "".join(_project_list_item_html(p, project_previews.get(int(p["id"]), []), int(p["id"]) in active_project_ids) for p in projects)
    active_count = len([job for job in jobs if job.status in {"queued", "running"}])
    queue_modal = _queue_modal_html(jobs, average_durations, queue_estimate_seconds, job_options)
    return f"""
<div class="start-dashboard">
{_start_topbar_html(queue_estimate_seconds, active_count)}
{_start_hero_html(projects, jobs, queue_estimate_seconds, active_count)}
<div class="start-layout">
<section class="studio-panel">
  <div class="studio-panel-head project-panel-head">
    <h2>Projects</h2>
    <div class="project-browser-controls">
      <input id="project-search" type="search" placeholder="Search projects" aria-label="Search projects">
      <select id="project-filter" aria-label="Filter projects">
        <option value="all" selected>All</option>
        <option value="in-progress">In progress</option>
        <option value="done">Done</option>
      </select>
      <select id="project-sort" aria-label="Sort projects">
        <option value="newest" selected>Newest</option>
        <option value="oldest">Oldest</option>
        <option value="name-asc">Name asc</option>
        <option value="name-desc">Name desc</option>
      </select>
    </div>
  </div>
  <div id="project-grid" class="project-grid">{rows}</div>
  <div id="project-empty-state" class="project-empty-state">No projects match this view.</div>
</section>
</div>
{queue_modal}
{_new_project_modal_html()}
</div>
<script>setupQueueEstimateCountdown(); pollJobsStatus();</script>
"""


def _start_topbar_html(queue_estimate_seconds: float | None, queue_count: int = 0) -> str:
    return f"""
<div class="studio-topbar">
  <img class="studio-logo" src="/icon/VocaVid_icon.svg" alt="" aria-hidden="true">
  <div class="studio-brand">VocaVid</div>
  <div class="studio-tagline">Local AI music-video studio</div>
  <div class="studio-spacer"></div>
  {_queue_estimate_html(queue_estimate_seconds, queue_count)}
  <button class="studio-button" type="button" onclick="openNewProjectModal()">New Project</button>
</div>
"""


def _new_project_modal_html() -> str:
    return f"""
<div id="new-project-modal" class="modal lightbox" onclick="if (event.target === this) closeNewProjectModal()">
  <div class="modal-content">
    <div class="studio-panel-head">
      <h2>New Project</h2>
      <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeNewProjectModal()">X</button>
    </div>
    <form class="new-project-form" action="/projects" method="post" enctype="multipart/form-data">
      <label>Name</label><input name="name" required>
      <label>WAV</label><input name="audio" type="file" accept=".wav,audio/wav" required>
      <label>Lyrics</label><input name="lyrics" type="file" accept=".txt,.lyrics" required>
      <label>Genre</label><input name="genre" required>
      <label>Avatar</label><input name="avatar" type="file" accept="image/*">
      <label>Male / Female Avatar</label>{_avatar_gender_select_html("")}
      <label>Avatar face description</label><textarea name="avatar_face_description"></textarea>
      <label>Comfy Base URL</label><input name="comfy_base_url" value="http://127.0.0.1:8188">
      <label>Lyrics-Zeilen pro Clip</label><input name="lyric_group_size" type="number" min="1" max="8" value="2">
      <label>Refrain-Zeilen pro Clip</label><input name="chorus_group_size" type="number" min="1" max="8" value="1">
      <input name="output_resolution" type="hidden" value="1280x720">
      <input name="fps" type="hidden" value="24">
      <input name="transition_handle_seconds" type="hidden" value="0.5">
      <input name="whisper_model_size" type="hidden" value="large-v3">
      <p><button>Create Project</button></p>
    </form>
  </div>
</div>
"""


def _start_hero_html(projects, jobs, queue_estimate_seconds: float | None, queue_count: int = 0) -> str:
    open_jobs = len([job for job in jobs if job.status in {"queued", "running"}])
    return f"""
<section class="start-hero">
  <div>
    <h1>Build, review, rerender.</h1>
    <p>Projects are the main act, queue health stays visible, and creating a new video opens as a focused modal.</p>
  </div>
  <div class="production-status">
    <h2>Production status</h2>
    <div class="stat-grid">
      <div class="stat"><strong>{len(projects)}</strong><span>projects</span></div>
      <div class="stat"><strong>{open_jobs}</strong><span>active jobs</span></div>
      <div class="stat"><strong>{_text(_format_duration(queue_estimate_seconds or 0))}</strong><span>queue estimate</span></div>
    </div>
  </div>
</section>
"""


def _project_list_item_html(project, preview_rows=None, has_active_jobs: bool = False) -> str:
    preview_rows = preview_rows or []
    done = _is_kdenlive_project_done(project)
    css_class = "project-card project-card-done" if done else "project-card"
    status = "done" if done else "in-progress"
    done_label = '<span class="project-done-badge" aria-label="Done">&#10003;</span>' if done else ""
    media_html = _project_card_media_html(project, preview_rows)
    approved, total = _project_progress_counts(preview_rows)
    progress = _progress_pill_html(approved, total, css_class="project-progress-badge")
    active_attr = ' data-active="1"' if has_active_jobs else ""
    return f"""
<article class="{css_class}" data-project-id="{_attr(project["id"])}" data-title="{_attr(project["name"])}" data-status="{status}"{active_attr}>
  <a class="project-card-link" href="/projects/{project["id"]}">
    {media_html}
    {progress}
    <div class="project-card-body">
      <h3>{_text(project["name"])}</h3>
    </div>
    {done_label}
  </a>
</article>
"""


def _project_card_media_html(project, rows) -> str:
    row = _project_preview_row(rows)
    if row is None:
        return _project_card_placeholder_html(project)
    clip_path = _row_value(row, "clip_path", "")
    if clip_path:
        url = _generated_asset_url(project, clip_path)
        return f'<div class="project-card-art"><video src="{_attr(url)}" preload="metadata" muted playsinline></video></div>'
    image_path = _row_value(row, "avatar_image_path", "") or _row_value(row, "image_path", "")
    if image_path:
        url = _generated_asset_url(project, image_path)
        return f'<div class="project-card-art"><img src="{_attr(url)}" alt="{_attr(project["name"])} preview"></div>'
    return _project_card_placeholder_html(project)


def _project_card_placeholder_html(project) -> str:
    return '<div class="project-card-art"><span class="project-card-placeholder"><span class="project-card-placeholder-mark" aria-label="No preview yet"></span></span></div>'


def _project_progress_counts(rows) -> tuple[int, int]:
    rows = list(rows or [])
    total = len(rows)
    approved = len([row for row in rows if bool(_row_value(row, "video_approved", 0))])
    return approved, total


def _project_preview_row(rows):
    rows = list(rows or [])
    media_rows = [row for row in rows if _row_value(row, "clip_path", "") or _row_value(row, "avatar_image_path", "") or _row_value(row, "image_path", "")]
    if not media_rows:
        return None
    chorus_rows = [row for row in media_rows if bool(_row_value(row, "is_chorus", 0)) or _section_type(_row_value(row, "section", ""), False) == "refrain"]
    clip_chorus = [row for row in chorus_rows if _row_value(row, "clip_path", "")]
    if clip_chorus:
        return clip_chorus[0]
    clip_rows = [row for row in media_rows if _row_value(row, "clip_path", "")]
    if clip_rows:
        return clip_rows[0]
    if chorus_rows:
        return chorus_rows[0]
    return media_rows[0]


def _is_kdenlive_project_done(project) -> bool:
    final_video_path = str(_row_value(project, "final_video_path", "") or "")
    return final_video_path.lower().endswith(".kdenlive")


def _project_navigation_ids(projects, project_id: int) -> tuple[int | None, int | None]:
    project_ids = [int(project["id"]) for project in projects]
    try:
        index = project_ids.index(int(project_id))
    except ValueError:
        return None, None
    previous_project_id = project_ids[index - 1] if index > 0 else None
    next_project_id = project_ids[index + 1] if index + 1 < len(project_ids) else None
    return previous_project_id, next_project_id


def _project_nav_html(project_id: int | None, direction: str) -> str:
    if direction == "previous":
        symbol = "◀"
        active_title = "Vorhergehendes Projekt"
        disabled_title = "Kein vorhergehendes Projekt"
    else:
        symbol = "▶"
        active_title = "Nachfolgendes Projekt"
        disabled_title = "Kein nachfolgendes Projekt"
    if project_id is None:
        return f'<span class="project-nav-button project-nav-disabled" title="{disabled_title}">{symbol}</span>'
    return f'<a class="project-nav-button" href="/projects/{project_id}" title="{active_title}">{symbol}</a>'


def _project_html(
    project,
    lines,
    segments=None,
    used_actions=None,
    active_jobs=None,
    queue_estimate_seconds: float | None = None,
    queue_count: int = 0,
    queue_jobs=None,
    average_durations: dict[str, float] | None = None,
    job_options: JobOptions | None = None,
    previous_project_id: int | None = None,
    next_project_id: int | None = None,
) -> str:
    segments = segments or []
    used_actions = used_actions or set()
    active_jobs = active_jobs or []
    queue_jobs = queue_jobs or []
    average_durations = average_durations or {}
    job_options = job_options or JobOptions()
    work_items = segments or lines
    item_kind = "segments" if segments else "lines"
    locked = _locked_indices(active_jobs, item_kind, work_items)
    assemble_enabled = _all_videos_approved(work_items)
    action_specs = [
        ("align", "Analyze + Split", False, "align"),
        ("scene-plan", "Scene Plan", False, "scene-plan"),
        ("generate-prompts", "Gen Prompts", False, ("prompts", "video-prompts")),
        ("images", "Gen Images", False, "images"),
        ("avatar-image", "Gen Avatar Images", False, "avatar-image"),
        ("clips", "Gen Clips", False, "clips"),
        ("assemble", "Assemble Final", True, "assemble"),
    ]
    actions = "".join(
        _action_button(
            project["id"],
            number,
            action,
            label,
            is_wip,
            any(used_action in used_actions for used_action in used_key) if isinstance(used_key, tuple) else used_key in used_actions,
            enabled=(action != "assemble" or not work_items or assemble_enabled),
        )
        for number, (action, label, is_wip, used_key) in enumerate(action_specs, start=1)
    )
    progress = _project_progress_html(work_items)
    queue_control = _queue_control_html(queue_jobs, average_durations, queue_estimate_seconds, queue_count, job_options)
    queue_modal = _queue_modal_html(queue_jobs, average_durations, queue_estimate_seconds, job_options)
    previous_project_nav = _project_nav_html(previous_project_id, "previous")
    next_project_nav = _project_nav_html(next_project_id, "next")
    initial_setup_banner = _initial_setup_banner_html(active_jobs)
    storyboard = _storyboard_html(project, work_items, item_kind, locked)
    table = _work_items_html(project, lines, segments, locked, show_generation_columns="scene-plan" in used_actions)
    return f"""
<div class="project-studio">
  <div class="project-topbar">
    <div class="project-title-row">
      <div class="project-title-left">
        <a class="button project-icon-button" href="/" aria-label="Back to projects" title="Back to projects">←</a>
        <button class="project-icon-button" type="button" title="Project Settings" onclick="openProjectSettingsModal()">⚙</button>
        {progress}
      </div>
      <div class="project-title-center">
        {previous_project_nav}
        <h1>{project['name']}</h1>
        {next_project_nav}
      </div>
      <div class="project-title-right">
        {queue_control}
      </div>
    </div>
    <div class="actions">{actions}</div>
  </div>
  {queue_modal}
  {initial_setup_banner}
  {storyboard}
  <section id="project-table-view" class="project-table-view" hidden>
    {table}
  </section>
{_project_settings_modal_html(project)}
</div>
{_clip_lightbox_html()}
{_image_lightbox_html()}
{_scroll_top_button_html()}
<script>rememberProjectRows(); setupQueueEstimateCountdown(); pollProjectStatus({project["id"]}); pollJobsStatus();</script>
"""


def _initial_setup_banner_html(active_jobs) -> str:
    setup_actions = {"global-style-prompt", "align", "segments", "scene-plan"}
    setup_jobs = [job for job in active_jobs if job.action in setup_actions]
    if not setup_jobs:
        return ""
    count = len(setup_jobs)
    label = "job" if count == 1 else "jobs"
    return f"""
  <div class="initial-setup-banner">
    <strong>Initial setup running</strong>
    <span>{count} setup {label} queued or running. You can already inspect the project while the foundation is built.</span>
  </div>
"""


def _project_settings_modal_html(project) -> str:
    return f"""
<div id="project-settings-modal" class="modal lightbox" onclick="if (event.target === this) closeProjectSettingsModal()">
  <div class="modal-content project-modal-content">
    <div class="studio-panel-head">
      <h2>Project Settings</h2>
      <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeProjectSettingsModal()">X</button>
    </div>
    <div class="project-settings-body">
      {_segment_settings_html(project, show_heading=False)}
      {_clear_project_html(project)}
    </div>
  </div>
</div>
"""


def _project_status_payload(
    project,
    lines,
    segments,
    active_jobs,
    average_durations: dict[str, float] | None = None,
    used_actions: set[str] | None = None,
    queue_jobs=None,
) -> dict[str, object]:
    average_durations = average_durations or {}
    used_actions = used_actions or set()
    counted_jobs = active_jobs if queue_jobs is None else queue_jobs
    item_kind = "segments" if segments else "lines"
    rows = segments or lines
    locked = _locked_indices(active_jobs, item_kind, rows)
    html = _work_items_html(project, lines, segments, locked, show_generation_columns="scene-plan" in used_actions)
    return {
        "locked": {
            "segments": sorted(locked) if item_kind == "segments" else [],
            "lines": sorted(locked) if item_kind == "lines" else [],
        },
        "queue_estimate_seconds": _queue_estimate_seconds(counted_jobs, average_durations),
        "queue_count": len(counted_jobs),
        "progress_html": _project_progress_html(rows),
        "rows": _extract_row_snippets(html),
        "storyboard_html": _storyboard_html(project, rows, item_kind, locked),
    }


def _extract_row_snippets(html: str) -> dict[str, str]:
    return {
        match.group(1): match.group(0)
        for match in re.finditer(r'<tr id="([^"]+)"[\s\S]*?</tr>', html)
    }


def _project_progress_html(rows) -> str:
    approved, total = _project_progress_counts(rows)
    return _progress_pill_html(approved, total, element_id="project-progress-pill")


def _progress_pill_html(approved: int, total: int, css_class: str = "", element_id: str = "") -> str:
    total = max(0, int(total or 0))
    approved = max(0, min(int(approved or 0), total)) if total else 0
    percent = 0 if total == 0 else round((approved / total) * 100)
    class_attr = "progress-pill"
    if css_class:
        class_attr += f" {css_class}"
    id_attr = f' id="{_attr(element_id)}"' if element_id else ""
    label = f"{approved}/{total}"
    title = f"{label} finished"
    return (
        f'<span{id_attr} class="{_attr(class_attr)}" title="{_attr(title)}">'
        f'<span class="progress-pill-fill" style="--progress: {percent}%"></span>'
        f'<span class="progress-pill-label">{_text(label)}</span>'
        "</span>"
    )

__all__ = [
    "_projects_html",
    "_start_topbar_html",
    "_new_project_modal_html",
    "_start_hero_html",
    "_project_list_item_html",
    "_project_card_media_html",
    "_project_card_placeholder_html",
    "_project_progress_counts",
    "_project_preview_row",
    "_is_kdenlive_project_done",
    "_project_navigation_ids",
    "_project_nav_html",
    "_project_html",
    "_initial_setup_banner_html",
    "_project_settings_modal_html",
    "_project_status_payload",
    "_extract_row_snippets",
    "_project_progress_html",
    "_progress_pill_html",
]

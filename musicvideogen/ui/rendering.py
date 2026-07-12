from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from ..alignment import WHISPER_MODEL_SIZES, normalize_whisper_model_size
from ..paths import is_internal_storage_path, resolve_storage_path, storage_relative_path
from ..store import Store

APP_ROOT = Path.cwd() / ".musicvideogen"


@dataclass
class JobOptions:
    autodelete_finished: bool = False
    shutdown_after_queue: bool = False


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


def _queue_section_html(
    jobs,
    average_durations: dict[str, float],
    queue_estimate_seconds: float | None,
    job_options: JobOptions,
) -> str:
    return f"""
<section id="jobs-panel" class="panel studio-panel queue-panel">
{_queue_control_body_html(jobs, average_durations, queue_estimate_seconds, job_options, heading="Jobs", description="Live queue, recent results, and cleanup controls.")}
</section>
"""


def _queue_control_html(
    jobs,
    average_durations: dict[str, float],
    queue_estimate_seconds: float | None,
    queue_count: int,
    job_options: JobOptions,
) -> str:
    return f"""
<div class="queue-control">
  {_queue_estimate_html(queue_estimate_seconds, queue_count)}
</div>
"""


def _queue_modal_html(
    jobs,
    average_durations: dict[str, float],
    queue_estimate_seconds: float | None,
    job_options: JobOptions,
) -> str:
    return f"""
<div id="queue-modal" class="modal lightbox queue-modal" onclick="if (event.target === this) closeQueueModal()">
  <div class="modal-content queue-modal-content">
    <div class="studio-panel-head">
      <h2>Queue</h2>
      <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeQueueModal()">X</button>
    </div>
    <div class="queue-modal-body">
{_queue_control_body_html(jobs, average_durations, queue_estimate_seconds, job_options, heading="", description="")}
    </div>
  </div>
</div>
"""


def _queue_control_body_html(
    jobs,
    average_durations: dict[str, float],
    queue_estimate_seconds: float | None,
    job_options: JobOptions,
    heading: str = "Jobs",
    description: str = "",
) -> str:
    job_rows = _jobs_table_body_html(jobs, average_durations)
    heading_html = ""
    if heading or description:
        heading_html = f"""
  <div class="queue-panel-head">
    <div>
      {f'<h2 class="jobs-heading">{_text(heading)}</h2>' if heading else ''}
      {f'<p>{_text(description)}</p>' if description else ''}
    </div>
  </div>"""
    return f"""
  {heading_html}
  {_queue_summary_html(jobs, queue_estimate_seconds)}
  <div class="jobs-table-wrap">
    <table><thead><tr><th>#</th><th>Name</th><th>Status</th><th>Created</th><th>Error</th><th>Avg</th><th></th></tr></thead><tbody id="jobs-table-body">{job_rows}</tbody></table>
  </div>
  {_queue_admin_html(job_options)}
"""


def _queue_summary_html(jobs, queue_estimate_seconds: float | None) -> str:
    return f"""
  <div id="queue-summary" class="queue-summary-grid">
{_queue_summary_cards_html(jobs, queue_estimate_seconds)}
  </div>
"""


def _queue_summary_cards_html(jobs, queue_estimate_seconds: float | None) -> str:
    counts = {status: 0 for status in ("queued", "running", "done", "failed")}
    for job in jobs:
        if job.status in counts:
            counts[job.status] += 1
    estimate = _format_duration(queue_estimate_seconds or 0)
    return f"""
    <div class="queue-summary-card queue-summary-card-active"><strong>{counts["queued"]}</strong><span>queued</span></div>
    <div class="queue-summary-card queue-summary-card-active"><strong>{counts["running"]}</strong><span>running</span></div>
    <div class="queue-summary-card"><strong>{counts["done"]}</strong><span>done</span></div>
    <div class="queue-summary-card"><strong>{counts["failed"]}</strong><span>failed</span></div>
    <div class="queue-summary-card"><strong>{_text(estimate)}</strong><span>estimate</span></div>
"""


def _queue_admin_html(job_options: JobOptions) -> str:
    autodelete_checked = " checked" if job_options.autodelete_finished else ""
    shutdown_checked = " checked" if job_options.shutdown_after_queue else ""
    return f"""
  <div class="queue-admin-controls">
    <div class="queue-cleanup-actions">
      <form class="compact-form" action="/jobs/delete-queued" method="post"><button>Delete queued</button></form>
      <form class="compact-form" action="/jobs/delete-finished" method="post"><button>Delete finished</button></form>
    </div>
    <form class="compact-form queue-settings-line" action="/jobs/options" method="post">
      <label><input type="checkbox" name="autodelete_finished"{autodelete_checked} onchange="this.form.submit()"> Autodelete finished</label>
      <label><input type="checkbox" name="shutdown_after_queue"{shutdown_checked} onchange="this.form.submit()"> Shutdown computer 15mins after last queue</label>
    </form>
  </div>
"""


def _jobs_table_body_html(jobs, average_durations: dict[str, float]) -> str:
    return "".join(_job_table_row_html(job, average_durations) for job in jobs)


def _job_table_row_html(job, average_durations: dict[str, float]) -> str:
    row_attrs = _job_row_attrs(job)
    link_hint = '<div class="queue-job-link-hint">Open target</div>' if row_attrs else ""
    return (
        f"<tr{row_attrs}><td>{job.id}</td><td>{_text(job.name)}{link_hint}</td><td>{_text(job.status)}</td>"
        f"<td>{_text(job.created_at)}</td><td class='error'>{_text(job.error)}</td>"
        f"<td>{_duration_html(_job_average_seconds(job, average_durations))}</td><td>{_job_delete_html(job)}</td></tr>"
    )


def _job_row_attrs(job) -> str:
    if not job.project_id:
        return ""
    href = f"/projects/{int(job.project_id)}"
    template_id = ""
    if job.item_kind and job.selected_indices:
        template_id = f"segment-inspector-template-{job.item_kind}-{int(job.selected_indices[0])}"
    return (
        f' class="queue-job-row" data-href="{_attr(href)}" data-template-id="{_attr(template_id)}" '
        'onclick="if (!event.target.closest(\'button, a, form, input, label\')) openQueueJobRow(this)"'
    )


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


def _storyboard_html(project, work_items, item_kind: str, locked=None) -> str:
    locked = locked or {}
    if not work_items:
        return """
  <section id="project-storyboard" class="project-storyboard">
    <div class="storyboard-rail">
      <article class="storyboard-card storyboard-card-empty">
        <div class="storyboard-card-media">No items yet</div>
        <div class="storyboard-card-body">
          <p class="storyboard-card-text">Run alignment or segment generation to populate the storyboard.</p>
        </div>
      </article>
    </div>
  </section>
"""
    cards = "".join(
        _storyboard_card_html(project, row, item_kind, active=index == 0, locked_status=locked.get(_row_index(row, item_kind)))
        for index, row in enumerate(work_items)
    )
    templates = "".join(
        _storyboard_inspector_template_html(
            project,
            item_kind,
            row,
            _storyboard_neighbor_index(work_items, item_kind, index - 1),
            _storyboard_neighbor_index(work_items, item_kind, index + 1),
        )
        for index, row in enumerate(work_items)
    )
    inspector = _segment_inspector_html(
        project,
        item_kind,
        work_items[0],
        None,
        _storyboard_neighbor_index(work_items, item_kind, 1),
    )
    return f"""
  <section id="project-storyboard" class="project-storyboard">
    <div class="storyboard-workspace">
      <div class="storyboard-rail">{cards}</div>
      {inspector}
    </div>
    {templates}
  </section>
"""


def _storyboard_neighbor_index(work_items, item_kind: str, position: int):
    if position < 0 or position >= len(work_items):
        return None
    index_key = "segment_index" if item_kind == "segments" else "line_index"
    return int(_row_value(work_items[position], index_key, 0))


def _storyboard_inspector_template_html(project, item_kind: str, row, previous_index=None, next_index=None) -> str:
    item_index = _row_index(row, item_kind)
    return f"""
    <template id="segment-inspector-template-{item_kind}-{item_index}">
      {_segment_inspector_html(project, item_kind, row, previous_index, next_index)}
    </template>
"""


def _segment_inspector_html(project, item_kind: str, row, previous_index=None, next_index=None) -> str:
    index_key = "segment_index" if item_kind == "segments" else "line_index"
    label = "Segment" if item_kind == "segments" else "Line"
    item_index = int(_row_value(row, index_key, 0))
    display_label = _storyboard_item_display_label(item_kind, item_index)
    text = _row_value(row, "clean_text", "") or "(empty)"
    timing = _timing_text(_row_value(row, "start_sec", None), _row_value(row, "end_sec", None))
    prompt = _row_value(row, "prompt", "") or ""
    video_prompt = _row_value(row, "video_prompt", "") or ""
    image_choice_html = _image_choice_html(project["id"], item_kind, item_index, row)
    approval_html = _approval_html(project["id"], item_kind, item_index, row, button=True)
    prompt_action = f"/projects/{project['id']}/{item_kind}/{item_index}/prompts"
    image_prompt_modal_id = f"image-prompt-modal-{item_kind}-{item_index}"
    video_prompt_modal_id = f"video-prompt-modal-{item_kind}-{item_index}"
    prompt_preview = _prompt_preview_html(project, row, image_prompt_modal_id, video_prompt_modal_id)
    image_prompt_modal = _prompt_modal_html(
        image_prompt_modal_id,
        "Edit image prompt",
        _image_prompt_editor_html(prompt_action, prompt),
    )
    video_prompt_modal = _prompt_modal_html(
        video_prompt_modal_id,
        "Edit video prompt",
        _video_prompt_editor_html(prompt_action, video_prompt),
    )
    media_html = _storyboard_card_media_html(project, row)
    text_html = _multiline_text_html(text) or _text(text)
    timing_html = f'<div class="segment-inspector-meta">{_text(timing)}</div>' if timing else ""
    image_choice_section = f"""
      <div class="segment-inspector-section">
        <div class="segment-inspector-label">Image source</div>
        {image_choice_html}
      </div>""" if image_choice_html else ""
    quick_actions = _inspector_generation_actions_html(project["id"], item_kind, item_index, row)
    navigation = _segment_inspector_navigation_html(item_kind, label, display_label, previous_index, next_index)
    return f"""
      <aside id="segment-inspector" class="segment-inspector" aria-label="Selected storyboard item">
        {navigation}
        {image_choice_section}
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Preview</div>
          {media_html}
        </div>
        <div class="segment-inspector-section">
          <div class="segment-inspector-label-row"><div class="segment-inspector-label">Text</div>{timing_html}</div>
          <div class="segment-inspector-text">{text_html}</div>
        </div>
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Prompts</div>
          {prompt_preview}
        </div>
        {image_prompt_modal}
        {video_prompt_modal}
        <div class="segment-inspector-actions">
          {quick_actions}
          {approval_html}
        </div>
      </aside>
"""


def _segment_inspector_navigation_html(item_kind: str, label: str, display_label: str, previous_index, next_index) -> str:
    return f"""
        <div class="segment-inspector-nav">
          {_segment_inspector_nav_button(item_kind, label, previous_index, "previous")}
          <h3 class="segment-inspector-title">{_text(display_label)}</h3>
          {_segment_inspector_nav_button(item_kind, label, next_index, "next")}
        </div>
"""


def _segment_inspector_nav_button(item_kind: str, label: str, item_index, direction: str) -> str:
    symbol = "\u25c0" if direction == "previous" else "\u25b6"
    active_title = f"{'Vorhergehendes' if direction == 'previous' else 'Nachfolgendes'} {label}"
    disabled_title = f"Kein {'vorhergehendes' if direction == 'previous' else 'nachfolgendes'} {label}"
    if item_index is None:
        return f'<span class="project-nav-button project-nav-disabled" title="{_attr(disabled_title)}">{symbol}</span>'
    template_id = f"segment-inspector-template-{item_kind}-{item_index}"
    return (
        f'<button class="project-nav-button segment-nav-button" type="button" title="{_attr(active_title)}" '
        f'onclick="selectStoryboardTemplate({_attr(_js_arg(template_id))})">{symbol}</button>'
    )


def _storyboard_card_html(project, row, item_kind: str, active: bool = False, locked_status: str | None = None) -> str:
    index_key = "segment_index" if item_kind == "segments" else "line_index"
    index = _row_value(row, index_key, 0)
    display_label = _storyboard_item_display_label(item_kind, int(index))
    checkbox_class = "segment-select" if item_kind == "segments" else "line-select"
    checkbox_label = "Segment markieren" if item_kind == "segments" else "Zeile markieren"
    text = _row_value(row, "clean_text", "") or "(empty)"
    timing = _timing_text(_row_value(row, "start_sec", None), _row_value(row, "end_sec", None))
    status = _row_value(row, "status", "") or "pending"
    meta_html = _storyboard_card_meta_html(row, timing)
    text_html = _multiline_text_html(text) or _text(text)
    media_html = _storyboard_card_media_html(project, row)
    effective_locked_status = locked_status
    active_class = " storyboard-card-active" if active else ""
    approved_class = " storyboard-card-approved" if bool(_row_value(row, "video_approved", 0)) else ""
    locked_class = " storyboard-card-locked" if effective_locked_status else ""
    locked_attr = "1" if effective_locked_status else "0"
    disabled_attr = " disabled" if effective_locked_status else ""
    lock_overlay = f'<div class="storyboard-lock-overlay"><span>{_text(effective_locked_status)}</span></div>' if effective_locked_status else ""
    progress = _storyboard_progress_strip_html(row)
    return f"""
      <article class="storyboard-card{active_class}{approved_class}{locked_class}" tabindex="0" role="button" data-inspector-template="segment-inspector-template-{item_kind}-{_attr(index)}" data-locked="{locked_attr}" onclick="selectStoryboardItem(event, this)" onkeydown="if ((event.key === 'Enter' || event.key === ' ') && !event.target.closest('.storyboard-select-wrap')) selectStoryboardItem(event, this)">
        <label class="storyboard-select-wrap" title="{_attr(checkbox_label)}" onclick="event.stopPropagation()">
          <input type="checkbox" class="{checkbox_class} storyboard-select" name="selected_lines" value="{_attr(index)}" aria-label="{_attr(checkbox_label)}"{disabled_attr}>
        </label>
        {media_html}
        <div class="storyboard-card-body">
          <div class="storyboard-card-title"><span>{_text(display_label)}</span>{meta_html}</div>
          {progress}
          <div class="storyboard-card-text">{text_html}</div>
        </div>
        {lock_overlay}
      </article>
"""


def _storyboard_card_meta_html(row, timing: str) -> str:
    section_label, section_class = _storyboard_section_badge(row)
    timing_html = f"<span>{_text(timing)}</span>" if timing else ""
    section_html = f'<span class="storyboard-section-badge storyboard-section-badge-{_attr(section_class)}">{_text(section_label)}</span>'
    return f'<span class="storyboard-card-meta">{timing_html}{section_html}</span>'


def _storyboard_section_badge(row) -> tuple[str, str]:
    section = str(_row_value(row, "section", "") or "")
    section_type = _section_type(section, bool(_row_value(row, "is_chorus", 0)))
    if section_type == "refrain":
        return "Refrain", "refrain"
    if section_type == "bridge":
        return "Bridge", "bridge"
    if section_type == "verse":
        return "Verse", "verse"
    normalized = section.strip()
    if normalized:
        return normalized, "other"
    return "Other", "other"


def _storyboard_item_display_label(item_kind: str, item_index: int) -> str:
    return f"# {item_index:02d}"


def _storyboard_progress_strip_html(row) -> str:
    steps = [
        ("Prompt", bool(_row_value(row, "prompt", "") or _row_value(row, "video_prompt", ""))),
        ("Image", bool(_row_value(row, "image_path", ""))),
        ("Avatar", bool(_row_value(row, "avatar_image_path", ""))),
        ("Clip", bool(_row_value(row, "clip_path", ""))),
    ]
    chips = "".join(
        f'<span class="progress-step{" progress-step-done" if done else ""}">{_text(label)}</span>'
        for label, done in steps
    )
    return f'<div class="storyboard-progress-strip">{chips}</div>'


def _inspector_generation_actions_html(project_id: int, item_kind: str, item_index: int, row) -> str:
    if not (_row_value(row, "prompt", "") or _row_value(row, "video_prompt", "")):
        return ""
    return f"""
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Next renders</div>
          <div class="inspector-generation-actions">
            {_inspector_action_form_html(project_id, "images", item_index, "Gen Image")}
            {_inspector_action_form_html(project_id, "avatar-image", item_index, "Gen Avatar")}
            {_inspector_action_form_html(project_id, "clips", item_index, "Gen Clip")}
          </div>
        </div>
"""


def _inspector_action_form_html(project_id: int, action: str, item_index: int, label: str) -> str:
    return f"""
<form class="compact-form" action="/projects/{project_id}/{action}" method="post" onsubmit="rememberScrollPosition()">
  <input type="hidden" name="selected_lines" value="{_attr(item_index)}">
  <button>{_text(label)}</button>
</form>
"""


def _storyboard_card_media_html(project, row) -> str:
    clip_path = _row_value(row, "clip_path", "")
    ok_badge = _storyboard_ok_badge_html(row)
    if clip_path:
        url = _generated_asset_url(project, clip_path)
        return f"""
        <div class="storyboard-card-media storyboard-card-media-clip" onclick="toggleStoryboardVideo(event, this)">
          <video class="storyboard-card-video" src="{_attr(_url_for_media_attribute(url))}" preload="metadata" playsinline></video>
          <button class="storyboard-video-toggle" type="button" aria-label="Play clip" onclick="toggleStoryboardVideo(event, this)">
            <span class="storyboard-play-icon">▶</span>
          </button>
          <button class="storyboard-video-expand" type="button" aria-label="Open clip in lightbox" onclick="event.stopPropagation(); openClipLightbox({_attr(_js_string_arg(_url_for_html_attribute(url)))}, this)">⛶</button>
          {ok_badge}
        </div>"""
        return f"""
        <div class="storyboard-card-media storyboard-card-media-clip">
          <button type="button" title="Play clip" onclick="openClipLightbox({_attr(_js_string_arg(_url_for_html_attribute(url)))})">
            <span class="storyboard-play-button"><span class="storyboard-play-icon">▶</span><span>Play clip</span></span>
          </button>
        </div>"""

    image_path = _storyboard_image_path(row)
    if image_path:
        url = _generated_asset_url(project, image_path)
        return f"""
        <div class="storyboard-card-media storyboard-card-media-image">
          <button type="button" title="Open image" onclick="openImageLightbox({_attr(_js_string_arg(_url_for_html_attribute(url)))})">
            <img class="storyboard-card-image" src="{_attr(_url_for_html_attribute(url))}" alt="Storyboard image">
          </button>
          {ok_badge}
        </div>"""

    return f"""
        <div class="storyboard-card-media storyboard-card-media-empty">
          <span class="storyboard-empty-mark"><strong>Awaiting media</strong><span>Generate an image or clip to preview this item.</span></span>
          {ok_badge}
        </div>"""


def _storyboard_ok_badge_html(row) -> str:
    if not bool(_row_value(row, "video_approved", 0)):
        return ""
    return '<span class="storyboard-ok-badge" aria-label="Finished">&#10003;</span>'


def _storyboard_image_path(row) -> str:
    image_path = _row_value(row, "image_path", "")
    avatar_image_path = _row_value(row, "avatar_image_path", "")
    if image_path and avatar_image_path:
        selected = _row_value(row, "selected_image_source", "avatar")
        return image_path if selected == "image" else avatar_image_path
    return avatar_image_path or image_path


def _url_for_html_attribute(url: str) -> str:
    return str(url).replace("&amp;", "&")


def _url_for_media_attribute(url: str) -> str:
    return json.dumps(_url_for_html_attribute(url))[1:-1]


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


def _segment_settings_html(project, show_heading: bool = True) -> str:
    name = _row_value(project, "name", "")
    audio_path = _row_value(project, "audio_path", "")
    lyrics_path = _row_value(project, "lyrics_path", "")
    global_style_prompt = _row_value(project, "global_style_prompt", "")
    scene_plan = _row_value(project, "scene_plan", "") or ""
    genre = _row_value(project, "genre", "")
    avatar_gender = _normalize_avatar_gender(_row_value(project, "avatar_gender", ""))
    avatar_face_description = _row_value(project, "avatar_face_description", "") or ""
    reference_paths = "\n".join(_reference_paths_from_json(_row_value(project, "reference_image_paths", "[]")))
    comfy_base_url = _row_value(project, "comfy_base_url", "http://127.0.0.1:8188")
    output_resolution = _row_value(project, "output_resolution", "1280x720")
    fps = _row_value(project, "fps", 24)
    lyric_group_size = _row_value(project, "lyric_group_size", 2)
    chorus_group_size = _row_value(project, "chorus_group_size", 1)
    transition_handle_seconds = _row_value(project, "transition_handle_seconds", 0.5)
    whisper_model_size = normalize_whisper_model_size(_row_value(project, "whisper_model_size", "small"))
    heading_html = "<h2>Project Settings</h2>" if show_heading else ""
    return f"""
<form class="hidden-action-form" id="global-style-prompt-form-{project['id']}" action="/projects/{project['id']}/global-style-prompt" method="post"></form>
<form class="hidden-action-form" id="scene-plan-form-{project['id']}" action="/projects/{project['id']}/scene-plan/save" method="post"></form>
<form class="hidden-action-form" id="avatar-description-form-{project['id']}" action="/projects/{project['id']}/avatar-description" method="post"></form>
<form class="hidden-action-form" id="realign-lyrics-form-{project['id']}" action="/projects/{project['id']}/realign-lyrics" method="post"></form>
<form class="hidden-action-form" id="realign-lyrics-cpu-form-{project['id']}" action="/projects/{project['id']}/realign-lyrics-cpu" method="post"></form>
<form action="/projects/{project['id']}/settings" method="post" onsubmit="return confirmProjectSettingsSave(this)" data-original-lyric-group-size="{_attr(lyric_group_size)}" data-original-chorus-group-size="{_attr(chorus_group_size)}">
  {heading_html}
  <label>Name</label><input name="name" value="{_attr(name)}" required>
  <label>WAV Path</label><input name="audio_path" value="{_attr(audio_path)}" required>
  <label>Lyrics Path</label><input name="lyrics_path" value="{_attr(lyrics_path)}" required>
  <label>Global Style Prompt</label><textarea name="global_style_prompt" required>{_text(global_style_prompt)}</textarea>
  <p><button type="submit" form="global-style-prompt-form-{project['id']}">KI-Vorschlag erstellen</button></p>
  <label>Scene Plan</label><textarea name="scene_plan" form="scene-plan-form-{project['id']}">{_text(scene_plan)}</textarea>
  <p><button type="submit" form="scene-plan-form-{project['id']}">Save Scene Plan</button></p>
  <label>Genre</label><input name="genre" value="{_attr(genre)}">
  <label>Male / Female Avatar</label>{_avatar_gender_select_html(avatar_gender)}
  <label>Avatar face description</label><textarea name="avatar_face_description">{_text(avatar_face_description)}</textarea>
  <p><button type="submit" form="avatar-description-form-{project['id']}">AI describe avatar</button></p>
  <label>Reference Image Paths</label><textarea name="reference_image_paths">{_text(reference_paths)}</textarea>
  <label>Comfy Base URL</label><input name="comfy_base_url" value="{_attr(comfy_base_url)}">
  <label>Resolution</label><input name="output_resolution" value="{_attr(output_resolution)}">
  <label>FPS</label><input name="fps" type="number" min="1" value="{_attr(fps)}">
  <label>Lyrics-Zeilen pro Clip</label><input name="lyric_group_size" type="number" min="1" max="8" value="{_attr(lyric_group_size)}">
  <label>Refrain-Zeilen pro Clip</label><input name="chorus_group_size" type="number" min="1" max="8" value="{_attr(chorus_group_size)}">
  <label>Transition Handle hinten (Sek.)</label><input name="transition_handle_seconds" type="number" min="0" step="0.1" value="{_attr(transition_handle_seconds)}">
  <label>Whisper Model</label>{_whisper_model_select_html(whisper_model_size)}
  <p>
    <button>Save Project Settings</button>
    <button type="submit" form="realign-lyrics-form-{project['id']}" onclick="return confirm('Lyrics neu alignen und Segmente neu erstellen? Generierte Dateien, Segmente, Timings, Prompts, OK-Status und Button-Status werden zurueckgesetzt.')">Realign Lyrics</button>
    <button type="submit" form="realign-lyrics-cpu-form-{project['id']}" onclick="return confirm('Lyrics per CPU neu alignen und Segmente neu erstellen? Generierte Dateien, Segmente, Timings, Prompts, OK-Status und Button-Status werden zurueckgesetzt.')">Realign Lyrics (CPU)</button>
  </p>
</form>
"""


def _work_items_html(project, lines, segments, locked=None, show_generation_columns: bool = False) -> str:
    locked = locked or {}
    if segments:
        return _segments_html(project, lines, segments, locked, show_generation_columns=show_generation_columns)
    return _lyrics_html(project, lines, locked, show_generation_columns=show_generation_columns)


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


def _lyrics_html(project, lines, locked=None, show_generation_columns: bool = False) -> str:
    locked = locked or {}
    rows = ""
    for line in lines:
        confidence = _display_confidence(line)
        confidence_value = "" if confidence is None else f"{round(float(confidence) * 100)}%"
        row_class = _row_class(line["section"], bool(line["is_chorus"]), confidence, bool(_row_value(line, "video_approved", 0)))
        generation_cells = ""
        if show_generation_columns:
            image_choice_html = _image_choice_html(project["id"], "lines", line["line_index"], line)
            image_html = _assets_stack_html(
                _image_preview_html(project, line["image_path"]),
                _image_preview_html(project, _row_value(line, "avatar_image_path", "")),
                image_choice_html,
            )
            clip_html = _clip_play_html(project, line["clip_path"])
            approval_html = _approval_html(project["id"], "lines", line["line_index"], line)
            video_prompt = _row_value(line, "video_prompt", "")
            prompt_editor = _prompt_editor_html(
                f"/projects/{project['id']}/lines/{line['line_index']}/prompts",
                line["prompt"] or "",
                video_prompt or "",
            )
            redo_html = _redo_html(project["id"], "lines", line["line_index"], _row_value(line, "last_action", ""))
            generation_cells = f"""
  <td colspan="2">{prompt_editor}</td>
  <td class="assets-column">{image_html}</td>
  <td>{clip_html}</td>
  <td>{redo_html}</td>
  <td>{approval_html}</td>"""
        status_html = _status_html(line["status"], line["error"] or "")
        insert_html = _insert_line_html(project["id"], line["line_index"], line["section"])
        delete_html = _delete_line_html(project["id"], line["line_index"])
        timing = _timing_text(line["start_sec"], line["end_sec"])
        start_value = _time_value(line["start_sec"])
        end_value = _time_value(line["end_sec"])
        approved = "1" if bool(_row_value(line, "video_approved", 0)) else "0"
        locked_status = locked.get(int(line["line_index"]))
        tr_class = _merge_row_class(row_class, "locked-row" if locked_status else "")
        lock_overlay = f'<div class="row-lock-overlay">{_text(locked_status)}</div>' if locked_status else ""
        rows += f"""
<tr id="line-row-{line['line_index']}"{tr_class} data-work-item="1" data-video-approved="{approved}" data-locked="{'1' if locked_status else '0'}" onclick="toggleRowSelection(event, this)">
  <td class="select-cell"><input type="checkbox" class="line-select" name="selected_lines" value="{line['line_index']}"></td>
  <td>{_text(line['clean_text'])}</td>
  <td class="timing-column">
    <form class="compact-form timing-form" action="/projects/{project['id']}/lines/{line['line_index']}/timing" method="post">
      <input name="start_sec" value="{start_value}" placeholder="von">
      <input name="end_sec" value="{end_value}" placeholder="bis">
      <button>Save</button>
    </form>
    <div>{timing}</div>
  </td>
  <td class="confidence">{confidence_value}</td>
{generation_cells}
  <td>{status_html}</td>
  <td><form action="/projects/{project['id']}/lines/{line['line_index']}/retry" method="post"><button>Retry</button></form></td>
  <td>{insert_html}</td>
  <td>{delete_html}</td>
  <td>{lock_overlay}</td>
</tr>"""
    generation_headers = '<th colspan="2">Prompts</th><th>Images</th><th>Clip</th><th>Redo</th><th>OK</th>' if show_generation_columns else ""
    return f"""
<div class="panel"><h2>Lyrics / Timing</h2></div>
<table>
  <thead><tr><th>Select</th><th>Lyrics</th><th class="timing-column">Timing</th><th>Confidence</th>{generation_headers}<th>Status</th><th></th><th>Insert</th><th>Loeschen</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
{_section_legend_html()}
"""


def _segments_html(project, lines, segments, locked=None, show_generation_columns: bool = False) -> str:
    locked = locked or {}
    confidence_by_line = _line_confidence_by_index(lines)
    rows = ""
    for segment in segments:
        generation_cells = ""
        audio_html = _audio_play_html(segment["audio_path"])
        row_class = _row_class(
            segment["section"] if segment["kind"] != "gap" else segment["kind"],
            bool(segment["is_chorus"]),
            None,
            bool(_row_value(segment, "video_approved", 0)),
        )
        timing = _timing_text(segment["start_sec"], segment["end_sec"])
        confidence_html = _segment_confidence_html(segment, confidence_by_line)
        alignment_cells = ""
        if not show_generation_columns:
            timing_editor = _segment_timing_editor_html(project["id"], segment)
            section_editor = _segment_section_editor_html(project["id"], segment)
            alignment_cells = f"""
  <td>{section_editor}</td>
  <td class="timing-column">{timing_editor}<div>{timing}</div>{confidence_html}</td>
  <td>{audio_html}</td>"""
        text_html = _multiline_text_html(segment["clean_text"])
        if show_generation_columns:
            image_choice_html = _image_choice_html(project["id"], "segments", segment["segment_index"], segment)
            image_html = _assets_stack_html(
                _image_preview_html(project, segment["image_path"]),
                _image_preview_html(project, _row_value(segment, "avatar_image_path", "")),
                image_choice_html,
            )
            clip_html = _clip_play_html(project, segment["clip_path"])
            approval_html = _approval_html(project["id"], "segments", segment["segment_index"], segment)
            video_prompt = _row_value(segment, "video_prompt", "")
            prompt_editor = _prompt_editor_html(
                f"/projects/{project['id']}/segments/{segment['segment_index']}/prompts",
                segment["prompt"] or "",
                video_prompt or "",
            )
            redo_html = _redo_html(project["id"], "segments", segment["segment_index"], _row_value(segment, "last_action", ""))
            generation_cells = f"""
  <td colspan="2">{prompt_editor}</td>
  <td class="assets-column">{image_html}</td>
  <td>{clip_html}</td>
  <td>{redo_html}</td>
  <td>{approval_html}</td>"""
        status_html = _status_html(segment["status"], segment["error"] or "")
        approved = "1" if bool(_row_value(segment, "video_approved", 0)) else "0"
        locked_status = locked.get(int(segment["segment_index"]))
        tr_class = _merge_row_class(row_class, "locked-row" if locked_status else "")
        lock_overlay = f'<div class="row-lock-overlay">{_text(locked_status)}</div>' if locked_status else ""
        rows += f"""
<tr id="segment-row-{segment['segment_index']}"{tr_class} data-work-item="1" data-video-approved="{approved}" data-locked="{'1' if locked_status else '0'}" onclick="toggleRowSelection(event, this)">
  <td class="select-cell"><input type="checkbox" class="segment-select" name="selected_lines" value="{segment['segment_index']}"></td>
  <td>{segment['segment_index']}</td>
  <td>{text_html}</td>
{alignment_cells}
{generation_cells}
  <td>{status_html}</td>
  <td>{lock_overlay}</td>
</tr>"""
    alignment_headers = '<th>Typ</th><th class="timing-column">Timing</th><th>Audio</th>' if not show_generation_columns else ""
    generation_headers = '<th colspan="2">Prompts</th><th>Images</th><th>Clip</th><th>Redo</th><th>OK</th>' if show_generation_columns else ""
    return f"""
<div class="panel"><h2>Render Segments</h2></div>
<table>
  <thead><tr><th>Select</th><th>#</th><th>Text</th>{alignment_headers}{generation_headers}<th>Status</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
{_section_legend_html()}
"""


def _action_button(project_id: int, number: int, action: str, label: str, is_wip: bool, is_used: bool, enabled: bool = True) -> str:
    title = ""
    css_class = ""
    if is_used:
        css_class = "used-button"
        title = "Already used; click to run again"
    elif is_wip:
        css_class = "wip-button"
        title = "WIP: not fully clean yet"
    attrs = ""
    if css_class:
        attrs += f' class="{css_class}"'
    if not enabled:
        attrs += ' type="button" title="Alle Videos erst mit OK markieren" onclick="alert(\'Bitte erst alle Videos mit OK freigeben.\')"'
    elif title:
        attrs += f' title="{title}"'
    return f"""<form action="/projects/{project_id}/{action}" method="post" onsubmit="return projectActionSubmitted(this)"><button{attrs}>{number}. {label}</button></form>"""


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


def _queue_estimate_html(seconds: float | None, queue_count: int = 0, open_modal: bool = True, element_id: str = "queue-estimate") -> str:
    value = max(0.0, float(seconds or 0.0))
    count = max(0, int(queue_count or 0))
    label = _queue_estimate_label(value, count)
    onclick = ' onclick="openQueueModal()"' if open_modal else ""
    return (
        f'<button id="{_attr(element_id)}" class="queue-estimate" type="button" data-seconds="{int(round(value))}" '
        f'data-queue-estimate="1" data-count="{count}"{onclick}>{_text(label)}</button>'
    )


def _queue_estimate_label(seconds: float | None, queue_count: int) -> str:
    count = max(0, int(queue_count or 0))
    if count <= 0:
        return "Queue 0"
    value = max(0.0, float(seconds or 0.0))
    if value <= 0:
        return f"{count} ~?s"
    return f"{count} ~{_format_duration(value)}"


def _scroll_top_button_html() -> str:
    return '<button class="scroll-top-button" type="button" onclick="scrollToTop()" title="Nach oben" aria-label="Nach oben">↑</button>'


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


def _queue_estimate_seconds(active_jobs, average_durations: dict[str, float]) -> float:
    total = 0.0
    now = datetime.now()
    for job in active_jobs:
        average = average_durations.get(job.action)
        if average is None:
            continue
        remaining = float(average)
        if job.status == "running" and job.started_at:
            try:
                elapsed = (now - datetime.fromisoformat(job.started_at)).total_seconds()
            except ValueError:
                elapsed = 0.0
            remaining = max(0.0, remaining - elapsed)
        total += remaining
    return total


def _job_delete_html(job) -> str:
    if job.status == "running":
        return ""
    return f"""
<form class="compact-form" action="/jobs/{job.id}/delete" method="post">
  <button>Delete</button>
</form>
"""


def _redo_html(project_id: int, item_kind: str, item_index: int, last_action: str | None) -> str:
    if not last_action:
        return ""
    action = _text(last_action)
    return f"""
<form class="compact-form redo-cell" action="/projects/{project_id}/{item_kind}/{item_index}/redo" method="post">
  <button class="icon-button" type="submit" title="Redo again">&#8635;</button>
  <div class="redo-action">{action}</div>
</form>
"""


def _insert_line_html(project_id: int, line_index: int, section: str) -> str:
    return f"""
<form class="compact-form insert-line-form" action="/projects/{project_id}/lines/{line_index}/insert-after" method="post">
  <input name="text" placeholder="Neue Zeile darunter" required>
  <input name="section" value="{_attr(section)}" placeholder="Section">
  <button>+</button>
</form>
"""


def _delete_line_html(project_id: int, line_index: int) -> str:
    return f"""
<form class="compact-form" action="/projects/{project_id}/lines/{line_index}/delete" method="post" onsubmit="return confirm('Lyrics-Zeile wirklich loeschen? Segmente und generierte Inhalte ab dieser Zeile werden zurueckgesetzt.')">
  <button class="danger-button">Loeschen</button>
</form>
"""


def _clear_project_html(project) -> str:
    return f"""
<details class="danger-panel">
  <summary>Danger Zone</summary>
  <div class="actions">
    <form class="compact-form" action="/projects/{project['id']}/clear" method="post" onsubmit="return confirm('Projekt wirklich leeren? Generierte Dateien, Segmente, Timings, Prompts und Button-Status werden zurueckgesetzt. Uploads und Settings bleiben erhalten.')">
      <button class="danger-button">Clear Project</button>
    </form>
    <form class="compact-form" action="/projects/{project['id']}/delete" method="post" onsubmit="return confirm('Projekt wirklich loeschen? Datenbankeintrag, Upload-Ordner und generierte Dateien werden entfernt.')">
      <button class="danger-button">Delete Project</button>
    </form>
  </div>
</details>
"""


def _image_preview_html(project, image_path: str | None) -> str:
    if not image_path:
        return ""
    url = _generated_asset_url(project, image_path)
    return (
        f'<button class="preview-button" type="button" onclick="openImageLightbox({_js_arg(url)})">'
        f'<img class="preview-image" src="{url}" alt="Generated image"></button>'
    )


def _assets_stack_html(*items: str) -> str:
    visible_items = [item for item in items if item]
    if not visible_items:
        return ""
    preview_items = [item for item in visible_items if 'class="preview-button"' in item]
    other_items = [item for item in visible_items if 'class="preview-button"' not in item]
    previews_html = '<div class="asset-previews">' + "".join(preview_items) + "</div>" if preview_items else ""
    return '<div class="assets-stack">' + previews_html + "".join(other_items) + "</div>"


def _image_choice_html(project_id: int, item_kind: str, item_index: int, row) -> str:
    image_path = _row_value(row, "image_path", "")
    avatar_image_path = _row_value(row, "avatar_image_path", "")
    if not image_path or not avatar_image_path:
        return ""
    selected = _row_value(row, "selected_image_source", "avatar")
    image_checked = " checked" if selected == "image" else ""
    avatar_checked = " checked" if selected != "image" else ""
    return f"""
<form class="compact-form image-choice image-choice-inline" action="/projects/{project_id}/{item_kind}/{item_index}/image-source" method="post">
  <label><input type="radio" name="selected_image_source" value="image"{image_checked} onchange="rememberScrollPosition(); this.form.submit()"> Image</label>
  <label><input type="radio" name="selected_image_source" value="avatar"{avatar_checked} onchange="rememberScrollPosition(); this.form.submit()"> Avatar</label>
</form>
"""


def _approval_html(project_id: int, item_kind: str, item_index: int, row, button: bool = False) -> str:
    approved = bool(_row_value(row, "video_approved", 0))
    if not button:
        checked = " checked" if approved else ""
        return f"""
<form class="compact-form" action="/projects/{project_id}/{item_kind}/{item_index}/approval" method="post">
  <input type="hidden" name="video_approved" value="0">
  <label class="approval-label"><input type="checkbox" name="video_approved" value="1"{checked} onchange="rememberScrollPosition(); this.form.submit()"> OK</label>
</form>
"""
    next_value = "0" if approved else "1"
    button_class = "finish-toggle finish-toggle-active" if approved else "finish-toggle finish-toggle-inactive"
    label = "Mark as unfinished" if approved else "Mark as finished"
    check_icon = '<span class="finish-toggle-check" aria-hidden="true">&#10003;</span>' if approved else ""
    return f"""
<form class="compact-form" action="/projects/{project_id}/{item_kind}/{item_index}/approval" method="post" onsubmit="rememberScrollPosition()">
  <input type="hidden" name="video_approved" value="{next_value}">
  <button class="{button_class}" type="submit"><span>{label}</span>{check_icon}</button>
</form>
"""


def _prompt_preview_html(project, row, image_modal_id: str, video_modal_id: str) -> str:
    image_path = _row_value(row, "image_path", "")
    avatar_image_path = _row_value(row, "avatar_image_path", "")
    media_html = ""
    if image_path:
        media_html += _inspector_prompt_media_html(project, image_path, "Image", "image")
    if avatar_image_path:
        media_html += _inspector_prompt_media_html(project, avatar_image_path, "Avatar", "avatar")
    if media_html:
        media_html = f'<div class="inspector-prompt-media-grid">{media_html}</div>'
    else:
        media_html = '<div class="storyboard-card-media storyboard-card-media-empty"><span class="storyboard-empty-mark"><strong>No image yet</strong><span>Generate an image or avatar to preview this prompt.</span></span></div>'
    return f"""
<div class="inspector-prompt-preview">
  {media_html}
  <div class="inspector-prompt-actions">
    <button type="button" onclick="openPromptModal({_attr(_js_arg(image_modal_id))})">Edit image prompt</button>
    <button type="button" onclick="openPromptModal({_attr(_js_arg(video_modal_id))})">Edit video prompt</button>
  </div>
</div>
"""


def _inspector_prompt_media_html(project, path: str, label: str, kind: str) -> str:
    url = _generated_asset_url(project, path)
    url_attr = _url_for_html_attribute(url)
    return (
        f'<div class="inspector-prompt-media inspector-prompt-media-{_attr(kind)}">'
        f'<button class="preview-button" type="button" onclick="openImageLightbox({_attr(_js_arg(url_attr))})">'
        f'<img class="inspector-prompt-image" src="{_attr(url_attr)}" alt="{_attr(label)} prompt reference">'
        "</button>"
        f"<span>{_text(label)}</span>"
        "</div>"
    )


def _prompt_modal_html(modal_id: str, title: str, editor_html: str) -> str:
    return f"""
<div id="{_attr(modal_id)}" class="modal lightbox prompt-modal" onclick="if (event.target === this) closePromptModal({_attr(_js_arg(modal_id))})">
  <div class="modal-content image-prompt-modal-content">
    <div class="studio-panel-head">
      <h2>{_text(title)}</h2>
      <button class="lightbox-close" type="button" aria-label="Close window" onclick="closePromptModal({_attr(_js_arg(modal_id))})">X</button>
    </div>
    {editor_html}
  </div>
</div>
"""


def _image_prompt_editor_html(action: str, prompt: str) -> str:
    return f"""
<form class="compact-form" action="{action}/image/save" method="post">
  <label>Image</label><textarea class="prompt-textarea" name="prompt">{_text(prompt)}</textarea>
  <p class="prompt-actions"><button>Save</button><button type="submit" formaction="{action}/image/ai-fill">AI fill</button></p>
</form>
"""


def _video_prompt_editor_html(action: str, video_prompt: str) -> str:
    return f"""
<form class="compact-form" action="{action}/video/save" method="post">
  <label>Video</label><textarea class="prompt-textarea" name="video_prompt">{_text(video_prompt)}</textarea>
  <p class="prompt-actions"><button>Save</button><button type="submit" formaction="{action}/video/ai-fill">AI fill</button></p>
</form>
"""


def _prompt_editor_html(action: str, prompt: str, video_prompt: str) -> str:
    return _image_prompt_editor_html(action, prompt) + _video_prompt_editor_html(action, video_prompt)


def _segment_section_editor_html(project_id: int, segment) -> str:
    section_type = _section_type(segment["section"], bool(segment["is_chorus"]))
    if section_type not in {"verse", "bridge", "refrain"}:
        section_type = "verse"
    verse_selected = " selected" if section_type == "verse" else ""
    bridge_selected = " selected" if section_type == "bridge" else ""
    refrain_selected = " selected" if section_type == "refrain" else ""
    return f"""
<form class="compact-form section-form" action="/projects/{project_id}/segments/{segment['segment_index']}/section" method="post">
  <select name="section_type" onchange="rememberScrollPosition(); this.form.submit()">
    <option value="verse"{verse_selected}>Verse</option>
    <option value="bridge"{bridge_selected}>Bridge</option>
    <option value="refrain"{refrain_selected}>Refrain</option>
  </select>
</form>
"""


def _whisper_model_select_html(selected: str) -> str:
    selected = normalize_whisper_model_size(selected)
    options = []
    for model_size in WHISPER_MODEL_SIZES:
        selected_attr = " selected" if model_size == selected else ""
        options.append(f'<option value="{_attr(model_size)}"{selected_attr}>{_text(model_size)}</option>')
    return f'<select name="whisper_model_size">{"".join(options)}</select>'


def _avatar_gender_select_html(selected: str) -> str:
    selected = _normalize_avatar_gender(selected)
    options = [
        ("", "Not specified"),
        ("male", "Male"),
        ("female", "Female"),
    ]
    return '<select name="avatar_gender">' + "".join(
        f'<option value="{_attr(value)}"{" selected" if value == selected else ""}>{_text(label)}</option>'
        for value, label in options
    ) + "</select>"


def _normalize_avatar_gender(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"male", "female"} else ""


def _segment_timing_editor_html(project_id: int, segment) -> str:
    start_value = _time_value(segment["start_sec"])
    end_value = _time_value(segment["end_sec"])
    return f"""
<form class="compact-form timing-form" action="/projects/{project_id}/segments/{segment['segment_index']}/timing" method="post">
  <input name="start_sec" value="{start_value}" placeholder="von">
  <input name="end_sec" value="{end_value}" placeholder="bis">
  <button>Save</button>
</form>
"""


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


def _audio_play_html(audio_path: str | None) -> str:
    if not audio_path:
        return ""
    url = _local_asset_url(audio_path)
    return (
        f'<button class="icon-button" type="button" title="Play audio" data-audio-src="{url}" onclick="toggleAudio(this)">▶</button>'
        f'<audio class="inline-player" preload="none" src="{url}"></audio>'
    )


def _clip_play_html(project, clip_path: str | None) -> str:
    if not clip_path:
        return ""
    url = _generated_asset_url(project, clip_path)
    return f'<button class="icon-button" type="button" title="Play clip" onclick="openClipLightbox(\'{url}\')">▶</button>'


def _clip_lightbox_html() -> str:
    return """
<div id="clip-lightbox" class="lightbox" onclick="if (event.target === this) closeClipLightbox()">
  <div class="lightbox-content">
    <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeClipLightbox()">X</button>
    <video id="clip-lightbox-video" controls></video>
  </div>
</div>
"""


def _image_lightbox_html() -> str:
    return """
<div id="image-lightbox" class="lightbox" onclick="if (event.target === this) closeImageLightbox()">
  <div class="lightbox-content">
    <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeImageLightbox()">X</button>
    <img id="image-lightbox-image" alt="Generated image">
  </div>
</div>
"""


def _row_class(section: str, is_chorus: bool, confidence, approved: bool = False) -> str:
    classes = [_section_class(section, is_chorus)]
    if approved:
        classes.append("approved-row")
    if confidence is not None and float(confidence) < 0.45:
        classes.append("low-confidence")
    return f' class="{" ".join(classes)}"'


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
    if is_chorus or "chorus" in value or "refrain" in value:
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
        Path(path).resolve().relative_to(APP_ROOT.resolve())
        return True
    except (OSError, ValueError):
        return False


def _local_asset_url(path: str) -> str:
    candidate = resolve_storage_path(APP_ROOT, path)
    normalized = storage_relative_path(APP_ROOT, path)
    url = "/assets/" + quote(normalized.lstrip("/"), safe="/")
    version = _local_asset_version(candidate, normalized)
    return f"{url}?v={version}" if version else url


def _local_asset_version(candidate: Path, normalized: str) -> str:
    candidates = [candidate]
    normalized_path = normalized.lstrip("/").replace("/", "\\")
    if normalized_path:
        candidates.append(APP_ROOT / normalized_path)
    for item in candidates:
        try:
            stat = item.stat()
        except OSError:
            continue
        return f"{stat.st_mtime_ns}-{stat.st_size}"
    return ""


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

__all__ = [
    "_run_project_action",
    "_selected_action_indices",
    "_projects_html",
    "_start_topbar_html",
    "_new_project_modal_html",
    "_start_hero_html",
    "_queue_section_html",
    "_queue_control_html",
    "_queue_modal_html",
    "_queue_control_body_html",
    "_queue_summary_html",
    "_queue_summary_cards_html",
    "_queue_admin_html",
    "_jobs_table_body_html",
    "_job_table_row_html",
    "_job_row_attrs",
    "_project_list_item_html",
    "_project_card_media_html",
    "_project_card_placeholder_html",
    "_project_progress_counts",
    "_project_preview_row",
    "_is_kdenlive_project_done",
    "_job_name",
    "_action_item_kind",
    "_locked_indices",
    "_row_index",
    "_merge_row_class",
    "_project_html",
    "_initial_setup_banner_html",
    "_project_settings_modal_html",
    "_storyboard_html",
    "_storyboard_neighbor_index",
    "_storyboard_inspector_template_html",
    "_segment_inspector_html",
    "_segment_inspector_navigation_html",
    "_segment_inspector_nav_button",
    "_storyboard_card_html",
    "_storyboard_card_meta_html",
    "_storyboard_section_badge",
    "_storyboard_item_display_label",
    "_storyboard_progress_strip_html",
    "_inspector_generation_actions_html",
    "_inspector_action_form_html",
    "_storyboard_card_media_html",
    "_storyboard_ok_badge_html",
    "_storyboard_image_path",
    "_url_for_html_attribute",
    "_url_for_media_attribute",
    "_project_navigation_ids",
    "_project_nav_html",
    "_segment_settings_html",
    "_work_items_html",
    "_project_status_payload",
    "_extract_row_snippets",
    "_lyrics_html",
    "_segments_html",
    "_action_button",
    "_project_progress_html",
    "_progress_pill_html",
    "_queue_estimate_html",
    "_queue_estimate_label",
    "_scroll_top_button_html",
    "_job_average_seconds",
    "_action_from_job_name",
    "_duration_html",
    "_format_duration",
    "_queue_estimate_seconds",
    "_job_delete_html",
    "_redo_html",
    "_insert_line_html",
    "_delete_line_html",
    "_clear_project_html",
    "_image_preview_html",
    "_assets_stack_html",
    "_image_choice_html",
    "_approval_html",
    "_prompt_preview_html",
    "_inspector_prompt_media_html",
    "_prompt_modal_html",
    "_image_prompt_editor_html",
    "_video_prompt_editor_html",
    "_prompt_editor_html",
    "_segment_section_editor_html",
    "_whisper_model_select_html",
    "_avatar_gender_select_html",
    "_normalize_avatar_gender",
    "_segment_timing_editor_html",
    "_line_confidence_by_index",
    "_display_confidence",
    "_is_sparse_fallback_row",
    "_segment_confidence_html",
    "_source_line_indices",
    "_status_html",
    "_all_videos_approved",
    "_audio_play_html",
    "_clip_play_html",
    "_clip_lightbox_html",
    "_image_lightbox_html",
    "_row_class",
    "_section_class",
    "_section_type",
    "_section_legend_html",
    "_multiline_text_html",
    "_timing_text",
    "_time_value",
    "_comfy_output_url",
    "_generated_asset_url",
    "_is_local_project_asset",
    "_local_asset_url",
    "_local_asset_version",
    "_row_value",
    "_reference_paths_from_text",
    "_reference_paths_from_json",
    "_attr",
    "_js_arg",
    "_js_string_arg",
    "_text",
]

from __future__ import annotations

from datetime import datetime

from .context import JobOptions
from .formatting import (
    _attr,
    _duration_html,
    _format_duration,
    _job_average_seconds,
    _text,
)


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

__all__ = [
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
    "_queue_estimate_html",
    "_queue_estimate_label",
    "_queue_estimate_seconds",
    "_job_delete_html",
]

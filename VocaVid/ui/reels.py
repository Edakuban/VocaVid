from __future__ import annotations

import json

from .formatting import _attr, _format_duration, _local_asset_url, _row_value, _text
from ..paths import project_output_file_stem, slug_folder_name


def _reels_modal_html(project, analyses=None, candidates_by_analysis=None) -> str:
    analyses = analyses or []
    candidates_by_analysis = candidates_by_analysis or {}
    return f"""
<div id="reels-modal" class="modal lightbox reels-modal" onclick="if (event.target === this) closeReelsModal()">
  <div class="modal-content reels-modal-content">
    <div class="studio-panel-head">
      <div>
        <h2>Make reels</h2>
        <p>Create vertical shorts from this finished music video.</p>
      </div>
      <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeReelsModal()">X</button>
    </div>
    <div id="reels-status" class="reels-body">
      {_reels_status_html(project, analyses, candidates_by_analysis)}
    </div>
  </div>
</div>
"""


def _reels_status_html(project, analyses=None, candidates_by_analysis=None) -> str:
    analyses = analyses or []
    candidates_by_analysis = candidates_by_analysis or {}
    latest = analyses[0] if analyses else None
    candidates = candidates_by_analysis.get(int(latest["id"]), []) if latest else []
    return f"""
<section class="reels-grid">
  {_reels_input_html(project, latest)}
  {_reels_analysis_panel_html(latest)}
  {_reels_candidates_html(project, latest, candidates)}
</section>
"""


def _reels_input_html(project, latest) -> str:
    default_source = f"outputs/{slug_folder_name(str(project['name']))}/{project_output_file_stem(str(project['name']))}.mp4"
    return f"""
<section class="reels-panel reels-input-panel">
  <h3>Source MP4</h3>
  <form class="reels-source-form" data-reels-form="1" action="/projects/{project['id']}/reels/analyze" method="post" enctype="multipart/form-data">
    <div class="reels-source-upload">
      <label>Upload MP4</label>
      <input name="source_video" type="file" accept="video/mp4,.mp4" onchange="updateReelsUploadLabel(this)">
    </div>
    <div class="reels-source-info">
      <p class="reels-upload-name" aria-live="polite">No upload selected</p>
      <p class="reels-help">If empty, VocaVid uses <span class="reels-source-path">{_text(default_source)}</span></p>
    </div>
    <button>Analyze reels</button>
  </form>
</section>
"""


def _reels_analysis_panel_html(analysis) -> str:
    if not analysis:
        return """
<section class="reels-panel">
  <h3>Analysis</h3>
  <p class="muted">Select a finished MP4 to generate candidate shorts.</p>
</section>
"""
    metadata = _json_dict(_row_value(analysis, "metadata_json", "{}"))
    duration = metadata.get("duration", 0)
    size = f"{metadata.get('width', '?')}x{metadata.get('height', '?')}"
    fps = metadata.get("fps", "?")
    error = _row_value(analysis, "error", "")
    error_html = f'<p class="reels-error">{_text(error)}</p>' if error else ""
    return f"""
<section class="reels-panel">
  <h3>Analysis</h3>
  <div class="reels-metrics">
    <span><strong>{_text(_row_value(analysis, "status", "pending"))}</strong><small>status</small></span>
    <span><strong>{_text(_format_duration(float(duration or 0)))}</strong><small>duration</small></span>
    <span><strong>{_text(size)}</strong><small>source</small></span>
    <span><strong>{_text(fps)}</strong><small>fps</small></span>
  </div>
  {error_html}
</section>
"""


def _reels_candidates_html(project, analysis, candidates) -> str:
    if not analysis:
        return """
<section class="reels-panel reels-candidates-panel">
  <h3>Candidates</h3>
  <p class="muted">Candidate reels appear here after analysis.</p>
</section>
"""
    cards = "".join(_reels_candidate_card_html(project, analysis, candidate) for candidate in candidates)
    if not cards:
        cards = '<p class="muted">No candidates yet. Analysis may still be running.</p>'
    return f"""
<section class="reels-panel reels-candidates-panel">
  <h3>Candidates</h3>
  <div class="reels-candidate-list">{cards}</div>
</section>
"""


def _reels_candidate_card_html(project, analysis, candidate) -> str:
    preview_path = _row_value(candidate, "preview_path", "")
    export_path = _row_value(candidate, "export_path", "")
    video_path = export_path or preview_path
    video_label = "Export" if export_path else "Preview"
    video = _reels_video_html(video_path, video_label) if video_path else '<div class="reels-preview-placeholder">9:16 preview</div>'
    reasons = ", ".join(_json_list(_row_value(candidate, "reasons_json", "[]")))
    status = _row_value(candidate, "status", "pending")
    error = _row_value(candidate, "error", "")
    error_html = f'<p class="reels-error">{_text(error)}</p>' if error else ""
    return f"""
<article class="reels-candidate-card">
  <div class="reels-candidate-body">
    <div class="reels-candidate-head">
      <h4>{_text(_row_value(candidate, "label", "Candidate"))}</h4>
      <span class="reels-status-pill reels-status-{_attr(status)}">{_text(status)}</span>
    </div>
    <p>{_text(_format_duration(float(candidate["end_sec"]) - float(candidate["start_sec"])))} &middot; score {_text(round(float(candidate["score"]), 2))}</p>
    <p class="muted">{_text(reasons)}</p>
    {error_html}
  </div>
  <div class="reels-preview-frame">{video}</div>
  <div class="reels-candidate-actions">
    <form data-reels-form="1" action="/projects/{project['id']}/reels/{analysis['id']}/candidates/{candidate['id']}/preview" method="post"><button>Preview</button></form>
    <form data-reels-form="1" action="/projects/{project['id']}/reels/{analysis['id']}/candidates/{candidate['id']}/export" method="post"><button>Export</button></form>
    <form data-reels-form="1" action="/projects/{project['id']}/reels/{analysis['id']}/candidates/{candidate['id']}/clear" method="post"><button>Clear</button></form>
    <form data-reels-form="1" action="/projects/{project['id']}/reels/{analysis['id']}/candidates/{candidate['id']}/delete" method="post"><button class="danger-button">Delete</button></form>
  </div>
</article>
"""


def _reels_video_html(path: str, label: str) -> str:
    url = _local_asset_url(path)
    return f'<video controls preload="metadata" src="{_attr(url)}" aria-label="{_attr(label)}"></video>'


def _json_dict(value: str) -> dict:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_list(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


__all__ = [
    "_reels_modal_html",
    "_reels_status_html",
    "_reels_input_html",
    "_reels_analysis_panel_html",
    "_reels_candidates_html",
    "_reels_candidate_card_html",
]

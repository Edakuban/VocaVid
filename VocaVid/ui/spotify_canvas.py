from __future__ import annotations

from .formatting import _attr, _local_asset_url, _row_value, _text


def _spotify_canvas_modal_html(project, canvas=None, reel_candidates=None, storyboard_rows=None) -> str:
    return f"""
<div id="spotify-canvas-modal" class="modal lightbox spotify-canvas-modal" onclick="if (event.target === this) closeSpotifyCanvasModal()">
  <div class="modal-content spotify-canvas-modal-content">
    <div class="studio-panel-head">
      <div>
        <h2>Spotify Canvas</h2>
        <p>Create a silent, loop-ready 9:16 companion visual between 3 and 8 seconds.</p>
      </div>
      <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeSpotifyCanvasModal()">X</button>
    </div>
    <div id="spotify-canvas-status" class="spotify-canvas-body">
      {_spotify_canvas_status_html(project, canvas, reel_candidates, storyboard_rows)}
    </div>
  </div>
</div>
"""


def _spotify_canvas_status_html(project, canvas=None, reel_candidates=None, storyboard_rows=None) -> str:
    reel_candidates = reel_candidates or []
    storyboard_rows = storyboard_rows or []
    duration = float(_row_value(canvas, "duration_sec", 6.0) or 6.0)
    loop_mode = str(_row_value(canvas, "loop_mode", "pingpong") or "pingpong")
    source_path = str(_row_value(canvas, "source_path", "") or "")
    item_index = _row_value(canvas, "item_index", None)
    prompt = str(_row_value(canvas, "prompt", "") or "")
    export_path = str(_row_value(canvas, "export_path", "") or "")
    status = str(_row_value(canvas, "status", "pending") or "pending")
    error = str(_row_value(canvas, "error", "") or "")
    source_options = []
    selected_source_url = ""
    for candidate in reel_candidates:
        path = str(_row_value(candidate, "export_path", "") or _row_value(candidate, "preview_path", "") or "")
        if not path:
            continue
        label = f"{_row_value(candidate, 'label', 'Reel')} ({'export' if _row_value(candidate, 'export_path', '') else 'preview'})"
        selected = " selected" if path == source_path else ""
        preview_url = _local_asset_url(path)
        if selected or not selected_source_url:
            selected_source_url = preview_url
        source_options.append(f'<option value="{_attr(path)}" data-preview-url="{_attr(preview_url)}"{selected}>{_text(label)}</option>')
    scene_options = []
    for row in storyboard_rows:
        if not (_row_value(row, "image_path", "") or _row_value(row, "avatar_image_path", "")):
            continue
        index = int(_row_value(row, "segment_index", 0))
        selected = " selected" if item_index is not None and int(item_index) == index else ""
        label = f"{index + 1}. {_row_value(row, 'section', 'Scene')} — {_row_value(row, 'clean_text', '')}"
        scene_options.append(f'<option value="{index}"{selected}>{_text(label)}</option>')
    result = ""
    if export_path:
        result = f"""
<section class="spotify-canvas-result">
  <div><h3>Canvas export</h3><p>1080 × 1920 MP4 · {_text(f'{duration:.2f} s')} · {_text(loop_mode)}</p></div>
  <div class="spotify-canvas-preview"><video src="{_attr(_local_asset_url(export_path))}" autoplay muted loop playsinline controls></video></div>
  <a class="button" href="{_attr(_local_asset_url(export_path))}" download>Download MP4</a>
</section>"""
    message = f'<p class="spotify-canvas-error">{_text(error)}</p>' if error else ""
    if status in {"queued", "running"}:
        message = f'<p class="spotify-canvas-working">Canvas job is {status}…</p>' + message
    no_reels = '<p class="muted">Export or preview a reel first; it will appear here as a source.</p>' if not source_options else ""
    no_scenes = '<p class="muted">Generate a storyboard image first to create a new Canvas with AI.</p>' if not scene_options else ""
    disabled_reels = " disabled" if not source_options else ""
    disabled_scenes = " disabled" if not scene_options else ""
    loop_options = _loop_options(loop_mode)
    start_sec = max(0.0, float(_row_value(canvas, "source_start_sec", 0) or 0))
    end_sec = start_sec + duration
    return f"""
{result}
{message}
<div class="spotify-canvas-routes">
  <section class="spotify-canvas-panel">
    <span class="spotify-canvas-kicker">Use existing material</span>
    <h3>Trim a reel</h3>
    <p>Choose an existing reel, set the excerpt, and convert it to a validated Canvas export.</p>
    <form data-canvas-form="1" action="/projects/{project['id']}/spotify-canvas/render" method="post">
      <label>Reel source<select name="source_path" required onchange="changeSpotifyCanvasTrimSource(this)"{disabled_reels}>{''.join(source_options)}</select></label>
      {no_reels}
      <div class="spotify-canvas-trim-editor" data-start="{start_sec:.3f}" data-end="{end_sec:.3f}">
        <div class="spotify-canvas-source-preview">
          <video src="{_attr(selected_source_url)}" muted playsinline controls preload="metadata"></video>
          <span>Loop preview</span>
        </div>
        <div class="spotify-canvas-trim-summary">
          <span>From <strong data-canvas-trim-start-label>{start_sec:.2f}s</strong></span>
          <span>To <strong data-canvas-trim-end-label>{end_sec:.2f}s</strong></span>
          <span>Length <strong data-canvas-trim-duration-label>{duration:.2f}s</strong></span>
        </div>
        <div class="spotify-canvas-selection-track" aria-hidden="true"><i></i></div>
        <label>From<input data-canvas-trim-start type="range" min="0" max="60" step="0.01" value="{start_sec:.2f}"></label>
        <label>To<input data-canvas-trim-end type="range" min="0" max="60" step="0.01" value="{end_sec:.2f}"></label>
        <input name="start_sec" type="hidden" value="{start_sec:.3f}">
        <input name="duration_sec" type="hidden" value="{duration:.3f}">
        <p class="spotify-canvas-trim-help">The preview repeats only the selected section. Selection must be longer than 3 and shorter than 8 seconds.</p>
      </div>
      <label>Loop<select name="loop_mode">{loop_options}</select></label>
      <button{disabled_reels}>Create from reel</button>
    </form>
  </section>
  <section class="spotify-canvas-panel spotify-canvas-generate-panel">
    <span class="spotify-canvas-kicker">Create specifically for Spotify</span>
    <h3>Generate a new loop</h3>
    <p>Use a storyboard image as the visual anchor. The prompt generator is tuned for a continuous vertical loop.</p>
    <form data-canvas-form="1" action="/projects/{project['id']}/spotify-canvas/generate" method="post">
      <input name="item_kind" type="hidden" value="segments">
      <label>Storyboard image<select name="item_index" required{disabled_scenes}>{''.join(scene_options)}</select></label>
      {no_scenes}
      <div class="spotify-canvas-fields">
        <label>Duration<input name="duration_sec" type="number" min="3.01" max="7.99" step="0.01" value="{duration:.2f}"></label>
        <label>Loop<select name="loop_mode">{loop_options}</select></label>
      </div>
      <label>Canvas motion prompt<textarea name="prompt" rows="7" placeholder="Describe cyclical subject, environment, and camera motion…">{_text(prompt)}</textarea></label>
      <div class="spotify-canvas-actions">
        <button type="submit" formaction="/projects/{project['id']}/spotify-canvas/prompt"{disabled_scenes}>Generate prompt</button>
        <button type="submit"{disabled_scenes}>Generate Canvas</button>
      </div>
    </form>
  </section>
</div>
"""


def _loop_options(selected: str) -> str:
    options = (("pingpong", "Ping-pong · seamless"), ("cut", "Straight cut"))
    return "".join(f'<option value="{value}"{" selected" if value == selected else ""}>{label}</option>' for value, label in options)


__all__ = ["_spotify_canvas_modal_html", "_spotify_canvas_status_html"]

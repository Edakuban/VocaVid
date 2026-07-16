from __future__ import annotations

import json
import re

from ..alignment import WHISPER_MODEL_SIZES, normalize_whisper_model_size
from .formatting import (
    _attr,
    _display_confidence,
    _generated_asset_url,
    _js_arg,
    _line_confidence_by_index,
    _local_asset_url,
    _merge_row_class,
    _multiline_text_html,
    _reference_paths_from_json,
    _row_class,
    _row_value,
    _section_legend_html,
    _section_type,
    _segment_confidence_html,
    _status_html,
    _text,
    _time_value,
    _timing_text,
    _url_for_html_attribute,
)


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
  <div class="settings-realign-actions">
    <button type="submit" form="realign-lyrics-form-{project['id']}" onclick="return confirm('Lyrics per GeForce GPU neu alignen und Segmente neu erstellen? Generierte Dateien, Segmente, Timings, Prompts, OK-Status und Button-Status werden zurueckgesetzt.')">Realign Lyrics (GeForce GPU)</button>
    <button type="submit" form="realign-lyrics-cpu-form-{project['id']}" onclick="return confirm('Lyrics per CPU neu alignen und Segmente neu erstellen? Generierte Dateien, Segmente, Timings, Prompts, OK-Status und Button-Status werden zurueckgesetzt.')">Realign Lyrics (CPU)</button>
    <button type="button" onclick="closeProjectSettingsModal(); openManualTimingModal()">Realign Lyrics (manually)</button>
  </div>
  <div class="settings-save-actions">
    <button>Save Project Settings</button>
  </div>
</form>
"""


def _manual_timing_modal_html(project, lines, interludes=None) -> str:
    audio_url = _local_asset_url(_row_value(project, "audio_path", ""))
    interludes_by_line = {}
    for interlude in interludes or []:
        interludes_by_line.setdefault(int(interlude["after_line_index"]), []).append(interlude)
    rows = ""
    for position, line in enumerate(lines):
        line_index = int(line["line_index"])
        checked = " checked" if position == 0 or bool(_row_value(line, "manual_segment_start", 0)) else ""
        disabled = " disabled" if position == 0 else ""
        first_boundary_hidden = f'<input type="hidden" name="manual_segment_starts" value="{line_index}">' if position == 0 else ""
        clean_text = _row_value(line, "clean_text", _row_value(line, "raw_text", ""))
        section = _row_value(line, "section", "Verse")
        rows += f"""
<tr>
  <td class="manual-boundary-cell">
    <input type="checkbox" name="manual_segment_starts" value="{line_index}"{checked}{disabled}>
    {first_boundary_hidden}
  </td>
  <td>
    <input type="hidden" name="line_indices" value="{line_index}">
    <input type="hidden" name="row_types" value="lyric">
    <textarea class="manual-lyric-text" name="clean_texts" required>{_text(clean_text)}</textarea>
  </td>
  <td>{_manual_section_select_html(section)}</td>
  <td><input class="manual-time-input" name="start_secs" value="{_attr(_time_value(_row_value(line, "start_sec", None)))}" placeholder="0.0" required></td>
  <td><input class="manual-time-input" name="end_secs" value="{_attr(_time_value(_row_value(line, "end_sec", None)))}" placeholder="0.0" required></td>
</tr>"""
        for interlude in interludes_by_line.get(line_index, []):
            rows += _manual_interlude_row_html(line_index, interlude)
        rows += f'''<tr class="manual-interlude-insert-row"><td colspan="5"><button type="button" class="manual-interlude-add" onclick="addManualInterlude(this, {line_index})" title="Instrumental- oder Interlude-Segment einfuegen">+</button></td></tr>'''
    return f"""
<div id="manual-timing-modal" class="modal lightbox" onclick="if (event.target === this) closeManualTimingModal()">
  <div class="modal-content manual-timing-modal-content">
    <div class="studio-panel-head">
      <h2>Manual Timing</h2>
      <button class="lightbox-close" type="button" aria-label="Close window" onclick="closeManualTimingModal()">X</button>
    </div>
    <form class="manual-timing-form" action="/projects/{project['id']}/manual-timing" method="post">
      <div class="manual-audio-bar">
        <audio id="manual-timing-audio" controls preload="metadata" src="{_attr(audio_url)}" ontimeupdate="updateManualTimingTimestamp(this)"></audio>
        <output id="manual-timing-current">0.0</output>
        <button class="manual-timestamp-button icon-button" type="button" title="Aktuellen Timestamp in die naechste offene Grenze setzen" onclick="applyManualTimingTimestamp()">&#8594;</button>
      </div>
      <table class="manual-timing-table">
        <thead><tr><th>Segment</th><th>Lyrics</th><th>Bereich</th><th>Von</th><th>Bis</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div class="manual-timing-actions">
        <button type="submit">Save Manual Timing</button>
      </div>
    </form>
  </div>
</div>
"""


def _manual_interlude_row_html(after_line_index, interlude=None) -> str:
    interlude = interlude or {}
    clean_text = _row_value(interlude, "clean_text", "[Instrumental]")
    section = _row_value(interlude, "section", "Instrumental")
    start = _time_value(_row_value(interlude, "start_sec", None))
    end = _time_value(_row_value(interlude, "end_sec", None))
    return f'''<tr class="manual-interlude-row">
  <td class="manual-boundary-cell"><button class="manual-interlude-remove" type="button" title="Interlude entfernen" onclick="this.closest('tr').remove()">&#215;</button></td>
  <td>
    <input type="hidden" name="line_indices" value="">
    <input type="hidden" name="row_types" value="interlude">
    <input type="hidden" name="interlude_after_line_indices" value="{int(after_line_index)}">
    <textarea class="manual-lyric-text" name="clean_texts" required>{_text(clean_text)}</textarea>
  </td>
  <td>{_manual_section_select_html(section)}</td>
  <td><input class="manual-time-input" name="start_secs" value="{_attr(start)}" placeholder="0.0" required></td>
  <td><input class="manual-time-input" name="end_secs" value="{_attr(end)}" placeholder="0.0" required></td>
</tr>'''


_MANUAL_SECTION_OPTIONS = (
    "Intro",
    "Verse",
    "Pre-Chorus",
    "Chorus",
    "Refrain",
    "Bridge",
    "Instrumental",
    "Interlude",
    "Instrumental Fade-Out",
    "Outro",
)


def _manual_section_select_html(selected: str) -> str:
    selected = str(selected or "Verse")
    options = list(_MANUAL_SECTION_OPTIONS)
    if selected not in options:
        options.append(selected)
    return '<select name="sections">' + "".join(
        f'<option value="{_attr(option)}"{" selected" if option == selected else ""}>{_text(option)}</option>'
        for option in options
    ) + "</select>"


def _work_items_html(project, lines, segments, locked=None, show_generation_columns: bool = False) -> str:
    locked = locked or {}
    if segments:
        return _segments_html(project, lines, segments, locked, show_generation_columns=show_generation_columns)
    return _lyrics_html(project, lines, locked, show_generation_columns=show_generation_columns)


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


def _action_button(
    project_id: int,
    number: int,
    action: str,
    label: str,
    is_wip: bool,
    is_used: bool,
    enabled: bool = True,
    preview_url: str = "",
    disabled_title: str = "Alle Videos erst mit OK markieren",
    disabled_alert: str = "Bitte erst alle Videos mit OK freigeben.",
) -> str:
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
        attrs += f' type="button" title="{_attr(disabled_title)}" onclick="alert(\'{disabled_alert}\')"'
    elif preview_url:
        attrs += f' type="button" title="Preview rendered MP4" onclick="openClipLightbox({_attr(_js_arg(preview_url))})"'
    elif title:
        attrs += f' title="{title}"'
    if preview_url and enabled:
        return f"""<button{attrs}>{number}. {label}</button>"""
    return f"""<form action="/projects/{project_id}/{action}" method="post" onsubmit="return projectActionSubmitted(this)"><button{attrs}>{number}. {label}</button></form>"""


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
<form class="compact-form image-choice image-choice-inline" action="/projects/{project_id}/{item_kind}/{item_index}/image-source" method="post" data-project-sidepanel-form="1">
  <label><input type="radio" name="selected_image_source" value="image"{image_checked} onchange="submitProjectSidepanelForm(event, this.form)"> Image</label>
  <label><input type="radio" name="selected_image_source" value="avatar"{avatar_checked} onchange="submitProjectSidepanelForm(event, this.form)"> Avatar</label>
</form>
"""


def _approval_html(project_id: int, item_kind: str, item_index: int, row, button: bool = False) -> str:
    approved = bool(_row_value(row, "video_approved", 0))
    if not button:
        checked = " checked" if approved else ""
        return f"""
<form class="compact-form" action="/projects/{project_id}/{item_kind}/{item_index}/approval" method="post" data-project-sidepanel-form="1">
  <input type="hidden" name="video_approved" value="0">
  <label class="approval-label"><input type="checkbox" name="video_approved" value="1"{checked} onchange="rememberApprovalProgressBeforeSubmit(); submitProjectSidepanelForm(event, this.form)"> OK</label>
</form>
"""
    next_value = "0" if approved else "1"
    button_class = "finish-toggle finish-toggle-active" if approved else "finish-toggle finish-toggle-inactive"
    label = "Mark as unfinished" if approved else "Mark as finished"
    check_icon = '<span class="finish-toggle-check" aria-hidden="true">&#10003;</span>' if approved else ""
    return f"""
<form class="compact-form" action="/projects/{project_id}/{item_kind}/{item_index}/approval" method="post" onsubmit="rememberApprovalProgressBeforeSubmit()" data-project-sidepanel-form="1">
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
<form class="compact-form" action="{action}/image/save" method="post" data-project-sidepanel-form="1">
  <label>Image</label><textarea class="prompt-textarea" name="prompt">{_text(prompt)}</textarea>
  <p class="prompt-actions"><button>Save</button><button type="submit" formaction="{action}/image/ai-fill">AI fill</button></p>
</form>
"""


def _video_prompt_editor_html(action: str, video_prompt: str) -> str:
    return f"""
<form class="compact-form" action="{action}/video/save" method="post" data-project-sidepanel-form="1">
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


__all__ = [
    "_segment_settings_html",
    "_manual_timing_modal_html",
    "_work_items_html",
    "_lyrics_html",
    "_segments_html",
    "_action_button",
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
    "_audio_play_html",
    "_clip_play_html",
    "_clip_lightbox_html",
    "_image_lightbox_html",
]

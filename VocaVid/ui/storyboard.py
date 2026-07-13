from __future__ import annotations

from .formatting import (
    _attr,
    _generated_asset_url,
    _js_arg,
    _js_string_arg,
    _multiline_text_html,
    _row_index,
    _row_value,
    _section_type,
    _text,
    _timing_text,
    _url_for_html_attribute,
    _url_for_media_attribute,
)
from .forms import (
    _approval_html,
    _image_choice_html,
    _image_prompt_editor_html,
    _prompt_modal_html,
    _prompt_preview_html,
    _video_prompt_editor_html,
)


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
    timing_html = _segment_inspector_timing_html(project, row, timing)
    image_choice_section = f"""
      <div class="segment-inspector-section">
        <div class="segment-inspector-label">Image source</div>
        {image_choice_html}
      </div>""" if image_choice_html else ""
    quick_actions = _inspector_generation_actions_html(project["id"], item_kind, item_index, row)
    navigation = _segment_inspector_navigation_html(item_kind, label, display_label, previous_index, next_index)
    return f"""
      <aside id="segment-inspector" class="segment-inspector" aria-label="Selected storyboard item">
        <div class="segment-inspector-resize-handle" role="separator" aria-orientation="vertical" aria-label="Resize side panel" tabindex="0"></div>
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


def _segment_inspector_timing_html(project, row, timing: str) -> str:
    if not timing:
        return ""
    audio_path = _row_value(row, "audio_path", "")
    if not audio_path:
        return f'<div class="segment-inspector-meta">{_text(timing)}</div>'
    url = _generated_asset_url(project, audio_path)
    return (
        '<div class="segment-inspector-meta segment-inspector-audio-meta">'
        f'<button class="segment-audio-button icon-button" type="button" title="Segment audio abspielen" onclick="toggleAudio(this)">▶</button>'
        f'<audio preload="none" src="{_attr(_url_for_html_attribute(url))}"></audio>'
        f'<span>{_text(timing)}</span>'
        "</div>"
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
    locked_class = " storyboard-card-locked" if effective_locked_status else ""
    active_class = " storyboard-card-active" if active else ""
    approved = bool(_row_value(row, "video_approved", 0))
    approved_class = " storyboard-card-approved" if approved else ""
    unfinished_class = " storyboard-card-unfinished" if not approved and not effective_locked_status else ""
    locked_attr = "1" if effective_locked_status else "0"
    disabled_attr = " disabled" if effective_locked_status else ""
    lock_overlay = f'<div class="storyboard-lock-overlay"><span>{_text(effective_locked_status)}</span></div>' if effective_locked_status else ""
    progress = _storyboard_progress_strip_html(row)
    return f"""
      <article class="storyboard-card{active_class}{approved_class}{unfinished_class}{locked_class}" tabindex="0" role="button" data-inspector-template="segment-inspector-template-{item_kind}-{_attr(index)}" data-locked="{locked_attr}" onclick="selectStoryboardItem(event, this)" onkeydown="if ((event.key === 'Enter' || event.key === ' ') && !event.target.closest('.storyboard-select-wrap')) selectStoryboardItem(event, this)">
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

__all__ = [
    "_storyboard_html",
    "_storyboard_neighbor_index",
    "_storyboard_inspector_template_html",
    "_segment_inspector_html",
    "_segment_inspector_navigation_html",
    "_segment_inspector_nav_button",
    "_segment_inspector_timing_html",
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
]

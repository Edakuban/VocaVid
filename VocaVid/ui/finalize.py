from __future__ import annotations

from .formatting import (
    _attr,
    _generated_asset_url,
    _row_index,
    _row_value,
    _section_type,
    _url_for_media_attribute,
)


def _finalize_modal_html(project, work_items, item_kind: str) -> str:
    items = _finalize_items_html(project, work_items, item_kind)
    return f"""
<div id="finalize-modal" class="modal lightbox finalize-modal" onclick="if (event.target === this) closeFinalizeModal()">
  <div class="finalize-modal-content">
    <button class="lightbox-close finalize-close" type="button" aria-label="Close finalize review" onclick="closeFinalizeModal()">X</button>
    <div id="finalize-review-data" hidden>{items}</div>
    <header class="finalize-header">
      <div id="finalize-position" class="finalize-position">Finalize</div>
      <h2 id="finalize-title">Review clips</h2>
    </header>
    <div class="finalize-video-frame">
      <video id="finalize-video" controls playsinline></video>
      <div id="finalize-countdown" class="finalize-countdown" hidden aria-live="polite"></div>
    </div>
    <div id="finalize-review-panel" class="finalize-review-panel">
      <p id="finalize-instruction" class="finalize-instruction">The clip will be marked as finished after playback. Press Space or Enter if it needs work.</p>
      <div id="finalize-actions" class="finalize-actions" hidden>
        <div class="finalize-action-row finalize-action-row-generation">
          <button type="button" onclick="queueFinalizeAction('clips')"><kbd>1</kbd><span>Generate Clip</span></button>
          <button type="button" onclick="queueFinalizeAction('avatar-image')"><kbd>2</kbd><span>Generate Avatar</span></button>
          <button type="button" onclick="queueFinalizeAction('images')"><kbd>3</kbd><span>Generate Image</span></button>
        </div>
        <div class="finalize-action-row finalize-action-row-prompts">
          <button type="button" onclick="openFinalizePromptEditor('image')"><kbd>4</kbd><span>Edit Image Prompt</span></button>
          <button type="button" onclick="openFinalizePromptEditor('video')"><kbd>5</kbd><span>Edit Video Prompt</span></button>
        </div>
      </div>
      <form id="finalize-prompt-editor" class="finalize-prompt-editor" method="post" hidden onsubmit="return submitFinalizePrompt(event, this)">
        <div class="finalize-prompt-head">
          <label id="finalize-prompt-label" for="finalize-prompt-textarea">Edit prompt</label>
          <button type="button" onclick="closeFinalizePromptEditor()">Back to actions</button>
        </div>
        <textarea id="finalize-prompt-textarea" class="prompt-textarea"></textarea>
        <div class="finalize-prompt-actions">
          <button type="submit">Save</button>
          <button type="submit" data-ai-fill="1">AI fill</button>
        </div>
      </form>
    </div>
  </div>
</div>
"""


def _finalize_items_html(project, work_items, item_kind: str) -> str:
    return "".join(
        _finalize_item_html(project, row, item_kind, position, len(work_items))
        for position, row in enumerate(work_items)
        if _row_value(row, "clip_path", "")
    )


def _finalize_item_html(project, row, item_kind: str, position: int, total: int) -> str:
    item_index = _row_index(row, item_kind)
    section = str(_row_value(row, "section", "") or "").strip()
    section_type = _section_type(section, bool(_row_value(row, "is_chorus", 0)))
    section_label = {
        "refrain": "Chorus",
        "bridge": "Bridge",
        "verse": "Verse",
    }.get(section_type, section or ("Segment" if item_kind == "segments" else "Line"))
    clean_text = str(_row_value(row, "clean_text", "") or "").strip()
    title = f"{section_label} — {clean_text}" if clean_text else section_label
    clip_url = _generated_asset_url(project, str(_row_value(row, "clip_path", "")))
    approved = "1" if bool(_row_value(row, "video_approved", 0)) else "0"
    return (
        '<div class="finalize-review-item"'
        f' data-item-kind="{_attr(item_kind)}"'
        f' data-item-index="{_attr(item_index)}"'
        f' data-position="{position + 1}"'
        f' data-total="{total}"'
        f' data-title="{_attr(title)}"'
        f' data-src="{_attr(_url_for_media_attribute(clip_url))}"'
        f' data-approved="{approved}"'
        f' data-image-prompt="{_attr(_row_value(row, "prompt", "") or "")}"'
        f' data-video-prompt="{_attr(_row_value(row, "video_prompt", "") or "")}"'
        '></div>'
    )


__all__ = ["_finalize_modal_html", "_finalize_items_html", "_finalize_item_html"]

import tempfile
import unittest
from html import unescape
from pathlib import Path

from fastapi.testclient import TestClient

import musicvideogen.app as app_module
from musicvideogen.app import (
    APP_ROOT,
    _job_name,
    _local_asset_url,
    _page,
    _project_html,
    _project_status_payload,
    _projects_html,
    _reference_paths_from_text,
)
from musicvideogen.worker import Job


class RowLike:
    def __init__(self, data):
        self.data = data

    def __getitem__(self, key):
        return self.data[key]


class AppHtmlTests(unittest.TestCase):
    def test_page_uses_dark_studio_shell_styles(self):
        html = _page("Projects", "")

        self.assertIn(":root", html)
        self.assertIn("--studio-bg", html)
        self.assertIn("background:", html)
        self.assertIn(".studio-topbar", html)
        self.assertIn(".studio-panel", html)
        self.assertIn(".studio-button", html)
        self.assertIn(".studio-chip", html)
        self.assertIn("form, .panel { background: #fff; border: 1px solid #d8d3c8; color: #1c2526;", html)
        self.assertIn("table { width: 100%; border-collapse: collapse; background: white; color: #1c2526;", html)
        self.assertIn("button, .button { border: 0; border-radius: 12px; background: var(--studio-accent);", html)
        self.assertIn(".danger-panel { border-color: #e2b1b1; background: #fff8f8; color: #1c2526;", html)
        self.assertIn(".queue-estimate { margin-left: auto; padding: 6px 10px; border: 1px solid #b9c0bd; border-radius: 6px; background: #fff; color: #20302d;", html)

    def test_project_form_does_not_ask_for_workflow_json_paths(self):
        html = _projects_html([], [])

        self.assertNotIn("Workflow JSON Path", html)
        self.assertNotIn("Comfy Base URL", html)
        self.assertNotIn("workflows/image.json", html)
        self.assertNotIn("workflows/image_reference.json", html)

    def test_start_page_has_new_project_modal_trigger_and_form(self):
        html = _projects_html([], [])

        self.assertIn('class="start-dashboard"', html)
        self.assertIn('class="studio-button" type="button" onclick="openNewProjectModal()"', html)
        self.assertIn('id="new-project-modal"', html)
        self.assertIn('action="/projects"', html)
        self.assertIn('method="post" enctype="multipart/form-data"', html)
        self.assertIn('<label>Name</label><input name="name" required>', html)
        self.assertIn('<label>WAV</label><input name="audio" type="file" accept=".wav,audio/wav" required>', html)
        self.assertIn('<label>Lyrics</label><input name="lyrics" type="file" accept=".txt,.lyrics" required>', html)
        self.assertIn('name="lyric_group_size" type="number" min="1" max="8" value="2"', html)
        self.assertIn('name="chorus_group_size" type="number" min="1" max="8" value="1"', html)
        self.assertIn('name="transition_handle_seconds" type="number" min="0" step="0.1" value="0.5"', html)
        self.assertIn('name="whisper_model_size"', html)
        self.assertNotIn("SUNO Lyrics", html)
        self.assertNotIn("Global Style Prompt", html)
        self.assertNotIn('name="global_style_prompt"', html)
        self.assertNotIn("Reference Images", html)
        self.assertNotIn('name="references"', html)
        self.assertNotIn("Resolution", html)
        self.assertNotIn('name="fps"', html)

    def test_project_form_includes_clip_group_defaults(self):
        html = _projects_html([], [])

        self.assertIn('name="lyric_group_size" type="number" min="1" max="8" value="2"', html)
        self.assertIn('name="chorus_group_size" type="number" min="1" max="8" value="1"', html)
        self.assertIn('name="transition_handle_seconds" type="number" min="0" step="0.1" value="0.5"', html)
        self.assertIn('name="whisper_model_size"', html)
        self.assertIn('<option value="small" selected>small</option>', html)
        self.assertIn('<option value="medium">medium</option>', html)
        self.assertIn('<option value="large-v3">large-v3</option>', html)
        self.assertLess(html.index('name="lyrics"'), html.index('name="lyric_group_size"'))
        self.assertLess(html.index('name="lyric_group_size"'), html.index('name="chorus_group_size"'))
        self.assertLess(html.index('name="chorus_group_size"'), html.index('name="transition_handle_seconds"'))
        self.assertLess(html.index('name="transition_handle_seconds"'), html.index('name="whisper_model_size"'))
        self.assertLess(html.index('name="whisper_model_size"'), html.index("<p><button>Create Project</button></p>"))

    def test_start_page_renders_project_cards_and_marks_done_projects(self):
        projects = [
            {"id": 2, "name": "Finished Song", "final_video_path": "outputs/finished/final.kdenlive"},
            {"id": 1, "name": "Open Song", "final_video_path": None},
        ]

        body = _projects_html(projects, [])
        html = _page("Projects", body)

        self.assertIn('class="project-card project-card-done"', body)
        self.assertIn('<a class="project-card-link" href="/projects/2">', body)
        self.assertIn("Finished Song", body)
        self.assertIn('<span class="project-done-label">done</span>', body)
        self.assertIn('<a class="project-card-link" href="/projects/1">', body)
        self.assertIn(".project-grid", html)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", html)

    def test_jobs_table_has_delete_actions_except_running_and_clear_queued_button(self):
        jobs = [
            Job(id=4, name="generate prompts: Demo Song", status="queued", created_at="2026-06-27T19:15:24"),
            Job(id=3, name="generate clips: Demo Song", status="running", created_at="2026-06-27T19:03:22"),
            Job(id=2, name="align: Demo Song", status="done", created_at="2026-06-27T18:00:00"),
            Job(id=1, name="old job", status="failed", created_at="2026-06-27T17:00:00", error="boom"),
        ]

        html = _projects_html([], jobs, {"prompts": 12.4, "clips": 126.0})

        self.assertIn('action="/jobs/delete-queued"', html)
        self.assertIn("<button>Delete queued</button>", html)
        self.assertIn('action="/jobs/delete-finished"', html)
        self.assertIn("<button>Delete finished</button>", html)
        self.assertIn('class="queue-summary-grid"', html)
        self.assertIn('class="queue-admin-controls"', html)
        self.assertIn("generate prompts: Demo Song", html)
        self.assertIn("<th>Avg</th>", html)
        self.assertIn("<td>12s</td>", html)
        self.assertIn("<td>2m 6s</td>", html)
        self.assertIn('action="/jobs/4/delete"', html)
        self.assertNotIn('action="/jobs/3/delete"', html)
        self.assertIn('action="/jobs/2/delete"', html)
        self.assertIn('action="/jobs/1/delete"', html)
        self.assertIn("<th></th>", html)
        self.assertGreater(html.index('action="/jobs/delete-finished"'), html.index("</table>"))
        self.assertGreater(html.index('class="queue-admin-controls"'), html.index("</table>"))

    def test_start_page_queue_summary_shows_status_counts_and_estimate(self):
        jobs = [
            Job(id=4, name="queued", status="queued", created_at="2026-06-27T19:15:24"),
            Job(id=3, name="running", status="running", created_at="2026-06-27T19:03:22"),
            Job(id=2, name="done", status="done", created_at="2026-06-27T18:00:00"),
            Job(id=1, name="failed", status="failed", created_at="2026-06-27T17:00:00"),
        ]

        html = _projects_html([], jobs, queue_estimate_seconds=70.0)

        self.assertIn('class="queue-panel-head"', html)
        self.assertIn('class="queue-summary-card queue-summary-card-active"', html)
        self.assertIn("<strong>1</strong><span>queued</span>", html)
        self.assertIn("<strong>1</strong><span>running</span>", html)
        self.assertIn("<strong>1</strong><span>done</span>", html)
        self.assertIn("<strong>1</strong><span>failed</span>", html)
        self.assertIn("<strong>1m 10s</strong><span>estimate</span>", html)

    def test_start_page_has_queue_polling_and_queue_options(self):
        html = _page("Projects", _projects_html([], [], queue_estimate_seconds=70.0), queue_count=2)

        self.assertIn('id="queue-estimate"', html)
        self.assertIn("Queue ca. 1m 10s", html)
        self.assertIn('id="queue-summary"', html)
        self.assertIn('id="jobs-table-body"', html)
        self.assertIn('name="autodelete_finished"', html)
        self.assertIn("Autodelete finished", html)
        self.assertIn('name="shutdown_after_queue"', html)
        self.assertIn("Shutdown computer 15mins after last queue", html)
        self.assertIn("setupQueueEstimateCountdown(); pollJobsStatus();", html)
        self.assertIn("fetch('/jobs/status')", html)
        self.assertIn("data.queue_summary_html", html)
        self.assertIn("queueSummary.innerHTML = data.queue_summary_html", html)

    def test_jobs_status_endpoint_returns_queue_summary_for_polling(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"

                app = app_module.create_app()
                app.state.jobs.submit("queued job", lambda: "ok", action="prompts")
                client = TestClient(app)

                response = client.get("/jobs/status")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("queue_summary_html", payload)
                self.assertIn("<span>queued</span>", payload["queue_summary_html"])
                self.assertIn("<span>running</span>", payload["queue_summary_html"])
                self.assertIn("<span>estimate</span>", payload["queue_summary_html"])
                self.assertNotIn('id="queue-summary"', payload["queue_summary_html"])
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_job_name_includes_one_based_selected_segment_indices(self):
        self.assertEqual(_job_name("generate images", "Demo Song", [0, 2]), "generate images: Demo Song (segments 1, 3)")
        self.assertEqual(_job_name("generate images", "Demo Song", []), "generate images: Demo Song")
        self.assertEqual(_job_name("generate images", "Demo Song", [2], item_kind="segments"), "generate images: Demo Song (segment 3)")
        self.assertEqual(_job_name("generate prompts", "Demo Song", [1], item_kind="lines"), "generate prompts: Demo Song (line 2)")

    def test_unfinished_project_actions_are_pink_wip_buttons(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        html = _page("Demo", _project_html(project, []))

        self.assertIn('class="wip-button"', html)
        self.assertIn('title="WIP: not fully clean yet"', html)
        self.assertEqual(html.count('class="wip-button"'), 1)
        self.assertIn('<button>1. Align</button>', html)
        self.assertIn('<button>4. Gen Image Prompts</button>', html)
        self.assertIn('<button>5. Gen Video Prompts</button>', html)
        self.assertIn('<button>6. Gen Images</button>', html)
        self.assertIn('<button>7. Gen Avatar Image</button>', html)
        self.assertIn('<button>8. Gen Clips</button>', html)
        self.assertNotIn('class="button wip-button"', html)

    def test_project_header_has_previous_and_next_project_triangle_links(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, [], previous_project_id=8, next_project_id=6))

        self.assertIn('<a class="project-nav-button" href="/projects/8" title="Vorhergehendes Projekt">◀</a>', html)
        self.assertIn('<a class="project-nav-button" href="/projects/6" title="Nachfolgendes Projekt">▶</a>', html)
        self.assertLess(html.index('title="Vorhergehendes Projekt"'), html.index("<h1>Demo</h1>"))
        self.assertLess(html.index("<h1>Demo</h1>"), html.index('title="Nachfolgendes Projekt"'))
        self.assertIn(".project-nav-button", html)

    def test_project_page_wraps_storyboard_before_advanced_table(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Storyboard lyric",
                "start_sec": 1.0,
                "end_sec": 2.5,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines, previous_project_id=8, next_project_id=6)

        self.assertIn('class="project-studio"', html)
        self.assertLess(html.index('class="project-topbar"'), html.index('title="Vorhergehendes Projekt"'))
        self.assertLess(html.index('title="Nachfolgendes Projekt"'), html.index('class="actions"'))
        self.assertIn('class="view-switch"', html)
        self.assertIn('data-project-view="storyboard"', html)
        self.assertIn('data-project-view="table"', html)
        self.assertIn('id="project-storyboard"', html)
        self.assertIn('class="storyboard-rail"', html)
        self.assertIn('id="project-table-view"', html)
        self.assertIn('class="project-table-view"', html)
        self.assertIn("Storyboard lyric", html)
        self.assertIn("<table>", html)
        self.assertLess(html.index('id="project-storyboard"'), html.index('id="project-table-view"'))
        self.assertLess(html.index('id="project-table-view"'), html.index("<table>"))

    def test_storyboard_card_media_prefers_clip_over_images(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Clip wins",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "outputs/project-7/images/line-000.png",
                "avatar_image_path": "outputs/project-7/images/avatar-line-000.png",
                "clip_path": "outputs/project-7/clips/line-000.mp4",
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('class="storyboard-card-media storyboard-card-media-clip"', html)
        self.assertIn("openClipLightbox(&quot;/assets/outputs/project-7/clips/line-000.mp4", html)
        self.assertIn('class="storyboard-play-button"', html)
        self.assertNotIn('class="storyboard-card-image"', html)

    def test_storyboard_card_media_prefers_avatar_over_image(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Avatar wins",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "outputs/project-7/images/line-000.png",
                "avatar_image_path": "outputs/project-7/images/avatar-line-000.png",
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('src="/assets/outputs/project-7/images/avatar-line-000.png"', html)
        self.assertIn("openImageLightbox(&quot;/assets/outputs/project-7/images/avatar-line-000.png&quot;)", html)
        self.assertNotIn('src="/assets/outputs/project-7/images/line-000.png"', html)

    def test_storyboard_card_media_uses_selected_image_when_both_images_exist(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Selected image wins",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "outputs/project-7/images/line-000.png",
                "avatar_image_path": "outputs/project-7/images/avatar-line-000.png",
                "selected_image_source": "image",
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('src="/assets/outputs/project-7/images/line-000.png"', html)
        self.assertIn("openImageLightbox(&quot;/assets/outputs/project-7/images/line-000.png&quot;)", html)
        self.assertNotIn('src="/assets/outputs/project-7/images/avatar-line-000.png"', html)

    def test_storyboard_includes_segment_inspector_with_existing_item_controls(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 2,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Inspector lyric",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "prompt": "image prompt",
                "video_prompt": "video prompt",
                "image_path": "outputs/project-7/images/segment-002.png",
                "avatar_image_path": "outputs/project-7/images/avatar-segment-002.png",
                "selected_image_source": "image",
                "clip_path": None,
                "audio_path": None,
                "last_action": "images",
                "scene_plan": "",
                "video_approved": 1,
                "status": "failed",
                "error": "render exploded",
            }
        ]

        html = _project_html(project, [], segments)

        self.assertIn('class="segment-inspector"', html)
        self.assertIn("Selected Segment 2", html)
        self.assertIn("Inspector lyric", html)
        self.assertIn('action="/projects/7/segments/2/prompts/image/save"', html)
        self.assertIn('formaction="/projects/7/segments/2/prompts/image/ai-fill"', html)
        self.assertIn('action="/projects/7/segments/2/prompts/video/save"', html)
        self.assertIn('formaction="/projects/7/segments/2/prompts/video/ai-fill"', html)
        self.assertIn('action="/projects/7/segments/2/image-source"', html)
        self.assertIn('name="selected_image_source" value="image" checked', html)
        self.assertIn('action="/projects/7/segments/2/redo"', html)
        self.assertIn('<div class="redo-action">images</div>', html)
        self.assertIn('action="/projects/7/segments/2/approval"', html)
        self.assertIn('name="video_approved" value="1" checked', html)
        self.assertIn('<div class="status">failed</div>', html)
        self.assertIn('<div class="status-error">render exploded</div>', html)
        self.assertIn('class="storyboard-card-media storyboard-card-media-image"', html)
        self.assertIn(".segment-inspector", _page("Demo", ""))

    def test_storyboard_includes_line_inspector_when_segments_are_absent(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Line inspector lyric",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": "line image prompt",
                "video_prompt": "line video prompt",
                "image_path": None,
                "avatar_image_path": None,
                "clip_path": None,
                "last_action": "",
                "video_approved": 0,
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn("Selected Line 3", html)
        self.assertIn('action="/projects/7/lines/3/prompts/image/save"', html)
        self.assertIn('action="/projects/7/lines/3/approval"', html)
        self.assertIn("Line inspector lyric", html)
        self.assertIn('<div class="status">pending</div>', html)

    def test_storyboard_card_media_escapes_url_attributes(self):
        project = {
            "id": 7,
            "name": "Demo",
            "audio_path": "song.wav",
            "final_video_path": None,
            "comfy_base_url": 'http://example.test/"quoted"',
        }
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Escaped image URL",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "musicvideogen/project-7/line-000.png",
                "avatar_image_path": None,
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('src="http://example.test/&quot;quoted&quot;/view?filename=line-000.png&amp;subfolder=musicvideogen%2Fproject-7&amp;type=output"', html)
        self.assertIn('onclick="openImageLightbox(&quot;http://example.test/\\&quot;quoted\\&quot;/view?filename=line-000.png&amp;subfolder=musicvideogen%2Fproject-7&amp;type=output&quot;)"', html)
        self.assertNotIn('src="http://example.test/"quoted"', html)
        self.assertNotIn('onclick="openImageLightbox(\'http://example.test/"quoted"', html)

    def test_storyboard_card_media_serializes_onclick_urls_with_control_chars(self):
        project = {
            "id": 7,
            "name": "Demo",
            "audio_path": "song.wav",
            "final_video_path": None,
            "comfy_base_url": "http://example.test/'quoted\ncontrol\x01",
        }
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Escaped image URL",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "musicvideogen/project-7/line-000.png",
                "avatar_image_path": None,
                "clip_path": None,
                "status": "done",
                "error": "",
            },
            {
                "line_index": 1,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Escaped clip URL",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "avatar_image_path": None,
                "clip_path": "musicvideogen/project-7/clip-001.mp4",
                "status": "done",
                "error": "",
            },
        ]

        html = _project_html(project, lines)
        image_onclick = html.split('onclick="openImageLightbox(', 1)[1].split(')"', 1)[0]
        clip_onclick = html.split('onclick="openClipLightbox(', 1)[1].split(')"', 1)[0]

        self.assertNotIn("\n", image_onclick)
        self.assertNotIn("\n", clip_onclick)
        self.assertNotIn("\x01", image_onclick)
        self.assertNotIn("\x01", clip_onclick)
        self.assertIn(r"\ncontrol\u0001/view?filename=line-000.png", unescape(image_onclick))
        self.assertIn(r"\ncontrol\u0001/view?filename=clip-001.mp4", unescape(clip_onclick))
        self.assertIn(r"http://example.test/'quoted", unescape(image_onclick))
        self.assertIn(r"http://example.test/'quoted", unescape(clip_onclick))

    def test_storyboard_card_media_uses_image_before_fallback(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Image wins",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "outputs/project-7/images/line-000.png",
                "avatar_image_path": None,
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('src="/assets/outputs/project-7/images/line-000.png"', html)
        self.assertIn("openImageLightbox(&quot;/assets/outputs/project-7/images/line-000.png&quot;)", html)
        self.assertNotIn("Awaiting media", html)

    def test_storyboard_card_media_falls_back_when_empty(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "No media yet",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "avatar_image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('class="storyboard-card-media storyboard-card-media-empty"', html)
        self.assertIn("Awaiting media", html)

    def test_project_header_disables_missing_project_navigation(self):
        project = {"id": 9, "name": "Newest", "audio_path": "song.wav", "final_video_path": None}

        html = _project_html(project, [], previous_project_id=None, next_project_id=8)

        self.assertIn('<span class="project-nav-button project-nav-disabled" title="Kein vorhergehendes Projekt">◀</span>', html)
        self.assertIn('<a class="project-nav-button" href="/projects/8" title="Nachfolgendes Projekt">▶</a>', html)

    def test_low_confidence_alignment_rows_are_marked(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": 0.5,
                "end_sec": 1.2,
                "confidence": 0.2,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn("low-confidence", html)
        self.assertIn("<th>Confidence</th>", html)
        self.assertIn("20%", html)

    def test_sparse_fallback_rows_do_not_show_zero_confidence_as_whisper_quality(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": 0.0,
                "end_sec": 5.0,
                "confidence": 0.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "Sparse Whisper alignment; evenly distributed fallback (1/10 confident lyric lines)",
            }
        ]

        html = _project_html(project, lines)

        self.assertNotIn("low-confidence", html)
        self.assertNotIn(">0%</td>", html)

    def test_project_table_has_line_selection_checkboxes_and_action_scope_script(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines)
        page = _page("Demo", html)

        self.assertIn('<input type="checkbox" class="line-select" name="selected_lines" value="3">', html)
        self.assertIn("<th>Select</th>", html)
        self.assertIn('onsubmit="return projectActionSubmitted(this)"', html)
        self.assertIn('name="selected_lines"', html)
        self.assertIn('onclick="toggleRowSelection(event, this)"', html)
        self.assertIn("function toggleRowSelection", page)
        self.assertIn("Keine Checkbox markiert", page)
        self.assertIn("alle(!)", page)
        self.assertIn("itemLabel = hasSegments ? 'Segmente' : 'Zeilen'", page)
        self.assertIn("button, a, input, textarea, select, label, audio, video, img, form", page)

    def test_page_restores_scroll_position_after_form_redirects(self):
        html = _page("Demo", "")

        self.assertIn("musicvideogen-scroll:", html)
        self.assertIn("function rememberScrollPosition", html)
        self.assertIn("document.addEventListener('submit'", html)
        self.assertIn("window.scrollTo(0, scrollY)", html)

    def test_project_page_has_segment_settings_and_segment_table(self):
        project = {
            "id": 7,
            "name": "Demo",
            "audio_path": "song.wav",
            "final_video_path": None,
            "lyric_group_size": 2,
            "chorus_group_size": 4,
        }
        segments = [
            {
                "segment_index": 0,
                "kind": "gap",
                "section": "Instrumental intro",
                "is_chorus": 0,
                "clean_text": "Instrumental intro",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "prompt": None,
                "image_path": None,
                "clip_path": "musicvideogen/project-1/clip-000.mp4",
                "audio_path": "outputs/segment-000.wav",
                "scene_plan": "Slow establishing shot",
                "video_approved": 0,
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments)
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]

        self.assertIn('name="lyric_group_size"', html)
        self.assertIn('value="2"', html)
        self.assertIn('name="chorus_group_size"', html)
        self.assertIn('value="4"', html)
        self.assertIn('action="/projects/7/settings"', html)
        self.assertIn('action="/projects/7/segments"', html)
        self.assertIn("<h2>Render Segments</h2>", html)
        self.assertNotIn('<th colspan="2">Prompts</th>', html)
        self.assertNotIn("<th>Images</th>", html)
        self.assertNotIn("<th>Use</th>", html)
        self.assertNotIn("<th>Avatar Image</th>", html)
        self.assertIn('<input type="checkbox" class="segment-select" name="selected_lines" value="0">', html)
        self.assertIn('onclick="toggleRowSelection(event, this)"', html)
        self.assertIn('<button class="icon-button" type="button" title="Play audio"', html)
        self.assertIn('data-audio-src="/assets/outputs/segment-000.wav"', html)
        self.assertNotIn("<td>outputs/segment-000.wav</td>", html)
        self.assertNotIn("Slow establishing shot", html)
        self.assertNotIn('<button class="icon-button" type="button" title="Play clip"', table_html)
        self.assertNotIn("openClipLightbox", table_html)
        self.assertNotIn("clip-000.mp4", table_html)
        self.assertIn("<th>#</th>", html)
        self.assertNotIn("<th>Section</th>", html)
        self.assertNotIn("<th>Chorus</th>", html)
        self.assertIn('class="section-gap"', html)
        self.assertIn('<span class="legend-swatch section-gap"></span>Other', html)
        self.assertIn("0.0 - 8.0", html)
        self.assertIn('action="/projects/7/segments/0/timing"', html)
        self.assertIn('name="start_sec"', html)
        self.assertIn('name="end_sec"', html)
        self.assertIn('<td class="timing-column">', html)

    def test_segment_table_hides_generation_columns_before_scene_plan(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Segment row",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "prompt": "image prompt",
                "video_prompt": "video prompt",
                "image_path": "outputs/project-7/images/segment-000.png",
                "clip_path": "outputs/project-7/clips/segment-000.mp4",
                "audio_path": "outputs/project-7/audio-segments/segment-000.wav",
                "scene_plan": "",
                "video_approved": 1,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments, used_actions={"segments"})
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]

        self.assertIn("<th>Typ</th>", table_html)
        self.assertIn('<th class="timing-column">Timing</th>', table_html)
        self.assertIn("<th>Audio</th>", table_html)
        self.assertNotIn('<th colspan="2">Prompts</th>', table_html)
        self.assertNotIn("<th>Images</th>", table_html)
        self.assertNotIn("<th>Clip</th>", table_html)
        self.assertNotIn("<th>Redo</th>", table_html)
        self.assertNotIn("<th>OK</th>", table_html)
        self.assertNotIn("image prompt", table_html)
        self.assertNotIn("openClipLightbox", table_html)

    def test_segment_table_hides_alignment_columns_after_scene_plan(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Segment row",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": "outputs/project-7/audio-segments/segment-000.wav",
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments, used_actions={"scene-plan"})

        self.assertNotIn("<th>Typ</th>", html)
        self.assertNotIn('<th class="timing-column">Timing</th>', html)
        self.assertIn('<th colspan="2">Prompts</th>', html)
        self.assertIn("<th>Images</th>", html)
        self.assertNotIn('action="/projects/7/segments/0/timing"', html)
        self.assertNotIn('name="section_type"', html)

    def test_lyrics_table_hides_generation_columns_before_scene_plan(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": 0.5,
                "end_sec": 1.2,
                "confidence": 0.8,
                "prompt": "image prompt",
                "video_prompt": "video prompt",
                "image_path": "outputs/project-7/images/line-000.png",
                "clip_path": "outputs/project-7/clips/line-000.mp4",
                "video_approved": 1,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines, used_actions={"align"})
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]

        self.assertIn("<th>Lyrics</th>", table_html)
        self.assertIn('<th class="timing-column">Timing</th>', table_html)
        self.assertNotIn('<th colspan="2">Prompts</th>', table_html)
        self.assertNotIn("<th>Images</th>", table_html)
        self.assertNotIn("<th>Clip</th>", table_html)
        self.assertNotIn("<th>Redo</th>", table_html)
        self.assertNotIn("<th>OK</th>", table_html)
        self.assertNotIn("image prompt", table_html)

    def test_segment_scene_plan_is_saved_but_hidden_from_segment_table(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Segment row",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "A long scene plan that should wrap in a narrow column",
                "status": "pending",
                "error": "",
            }
        ]

        html = _page("Demo", _project_html(project, [], segments))

        self.assertIn("<h2>Scene Plan</h2>", html)
        self.assertNotIn('<th class="scene-plan-column">Scene Plan</th>', html)
        self.assertNotIn('<td class="scene-plan-column">A long scene plan that should wrap in a narrow column</td>', html)

    def test_project_table_has_compact_timing_controls(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Segment row",
                "start_sec": 230.5,
                "end_sec": 231.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _page("Demo", _project_html(project, [], segments))

        self.assertIn(".timing-column", html)
        self.assertIn(".timing-form input", html)
        self.assertIn("width: 7ch", html)
        self.assertIn('class="compact-form timing-form"', html)

    def test_segment_timing_shows_source_line_confidence(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {"line_index": 0, "confidence": 0.91},
            {"line_index": 1, "confidence": 0.73},
        ]
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "source_line_indices": "[0, 1]",
                "clean_text": "One line\nSecond line",
                "start_sec": 230.5,
                "end_sec": 231.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines, segments)

        self.assertIn('<div class="timing-confidence">Confidence 73%</div>', html)

    def test_segment_table_shows_segment_index_as_second_column(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 12,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Segment row",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments)

        self.assertIn("<th>Select</th><th>#</th><th>Text</th>", html)
        self.assertIn('<input type="checkbox" class="segment-select" name="selected_lines" value="12"></td>\n  <td>12</td>', html)

    def test_project_page_locks_active_segment_rows_and_includes_polling_script(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Locked row",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "video_approved": 0,
                "status": "pending",
                "error": "",
            },
            {
                "segment_index": 1,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Free row",
                "start_sec": 2.0,
                "end_sec": 3.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "video_approved": 0,
                "status": "pending",
                "error": "",
            },
        ]

        html = _page("Demo", _project_html(project, [], segments, active_jobs=[Job(1, "images", "running", "now", project_id=7, item_kind="segments", selected_indices=[0])]))

        self.assertIn('id="segment-row-0"', html)
        self.assertIn('class="section-verse locked-row"', html)
        self.assertIn('data-locked="1"', html)
        self.assertIn('<div class="row-lock-overlay">running</div>', html)
        self.assertIn("pollProjectStatus(7)", html)
        self.assertIn("fetch('/projects/' + projectId + '/status')", html)
        self.assertIn("function replaceProjectRow", html)
        self.assertIn("replacementCheckbox.checked = checkbox.checked", html)
        self.assertIn("replaceProjectRow(row, html)", html)

    def test_project_status_polling_skips_unchanged_rows(self):
        html = _page("Demo", "")

        self.assertIn("const projectRowServerHtml = new Map()", html)
        self.assertIn("function rememberProjectRows", html)
        self.assertIn("function projectRowChanged", html)
        self.assertIn("projectRowServerHtml.get(row.id) || row.outerHTML", html)
        self.assertIn("return previousHtml !== replacement.outerHTML", html)
        self.assertIn("if (!projectRowChanged(row, replacement)) return", html)
        self.assertIn("projectRowServerHtml.set(replacement.id, replacement.outerHTML)", html)

    def test_project_status_payload_includes_storyboard_html_for_polling(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Fresh storyboard text",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "video_approved": 0,
                "status": "done",
                "error": "",
            }
        ]

        payload = _project_status_payload(project, [], segments, active_jobs=[])

        self.assertIn("storyboard_html", payload)
        self.assertIn('id="project-storyboard"', payload["storyboard_html"])
        self.assertIn("Fresh storyboard text", payload["storyboard_html"])
        self.assertIn("done", payload["storyboard_html"])
        self.assertIn('class="segment-inspector"', payload["storyboard_html"])
        self.assertIn('action="/projects/7/segments/0/approval"', payload["storyboard_html"])
        self.assertIn("rows", payload)
        self.assertIn("segment-row-0", payload["rows"])

    def test_project_status_polling_replaces_visible_storyboard(self):
        html = _page("Demo", "")

        self.assertIn("function replaceProjectStoryboard", html)
        self.assertIn("data.storyboard_html", html)
        self.assertIn("const storyboard = document.getElementById('project-storyboard')", html)
        self.assertIn("replacement.hidden = storyboard.hidden", html)
        self.assertIn("storyboard.replaceWith(replacement)", html)

    def test_project_status_polling_skips_storyboard_when_editor_is_active_or_dirty(self):
        html = _page("Demo", "")

        self.assertIn("const projectStoryboardFieldSelector = 'input, textarea, select'", html)
        self.assertIn("function projectStoryboardHasActiveEdit", html)
        self.assertIn("const active = document.activeElement", html)
        self.assertIn("storyboard.contains(active)", html)
        self.assertIn("active.matches(projectStoryboardFieldSelector)", html)
        self.assertIn("function projectStoryboardFieldDirty", html)
        self.assertIn("field.checked !== field.defaultChecked", html)
        self.assertIn("field.value !== field.defaultValue", html)
        self.assertIn("option.selected !== option.defaultSelected", html)
        self.assertIn("function projectStoryboardHasDirtyFields", html)
        self.assertIn("querySelectorAll(projectStoryboardFieldSelector)", html)
        self.assertIn("function shouldReplaceProjectStoryboard", html)
        self.assertIn("!projectStoryboardHasActiveEdit(storyboard) && !projectStoryboardHasDirtyFields(storyboard)", html)
        self.assertIn("if (!shouldReplaceProjectStoryboard(storyboard)) return", html)
        self.assertLess(html.index("if (!shouldReplaceProjectStoryboard(storyboard)) return"), html.index("storyboard.replaceWith(replacement)"))

    def test_segment_table_has_editable_section_type_after_text(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Refrain",
                "is_chorus": 1,
                "clean_text": "Hook line",
                "start_sec": 0.0,
                "end_sec": 3.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments)

        self.assertIn('<th class="timing-column">Timing</th>', html)
        self.assertIn('action="/projects/7/segments/0/section"', html)
        self.assertIn('name="section_type"', html)
        self.assertIn('<option value="verse">Verse</option>', html)
        self.assertIn('<option value="bridge">Bridge</option>', html)
        self.assertIn('<option value="refrain" selected>Refrain</option>', html)
        self.assertLess(html.index("<th>Text</th>"), html.index("<th>Typ</th>"))
        self.assertLess(html.index("<th>Typ</th>"), html.index('<th class="timing-column">Timing</th>'))

    def test_instrumental_break_segments_have_editable_section_type(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 2,
                "kind": "gap",
                "section": "Instrumental break",
                "is_chorus": 0,
                "clean_text": "Instrumental break",
                "start_sec": 10.0,
                "end_sec": 14.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments)

        self.assertIn('action="/projects/7/segments/2/section"', html)
        self.assertIn('name="section_type"', html)
        self.assertIn('<option value="verse" selected>Verse</option>', html)

    def test_bridge_segments_show_bridge_option_and_color(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Bridge",
                "is_chorus": 0,
                "clean_text": "Bridge line",
                "start_sec": 0.0,
                "end_sec": 3.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments)

        self.assertIn('class="section-bridge"', html)
        self.assertIn('<option value="bridge" selected>Bridge</option>', html)

    def test_rows_show_redo_button_with_last_action_before_status(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "last_action": "images",
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines, used_actions={"scene-plan"})

        self.assertIn("<th>Redo</th><th>OK</th><th>Status</th>", html)
        self.assertIn('action="/projects/7/lines/3/redo"', html)
        self.assertNotIn('action="/projects/7/lines/3/redo" method="post" onsubmit="return projectActionSubmitted(this)"', html)
        self.assertIn('title="Redo again"', html)
        self.assertIn("&#8635;", html)
        self.assertIn('<div class="redo-action">images</div>', html)
        self.assertLess(html.index("<th>Redo</th>"), html.index("<th>OK</th>"))

    def test_grouped_segment_text_renders_multiple_lyrics_lines_in_one_row(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "One line\nSecond line",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments)

        self.assertEqual(html.count('class="segment-select"'), 1)
        self.assertIn('<div class="lyrics-lines">', html)
        self.assertIn('<div>One line</div>', html)
        self.assertIn('<div>Second line</div>', html)
        self.assertNotIn("One line\nSecond line", html)

    def test_project_page_shows_only_segment_list_after_segments_exist(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Old lyric row",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "",
            }
        ]
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Segment row",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines, segments)

        self.assertIn("<h2>Render Segments</h2>", html)
        self.assertIn("Segment row", html)
        self.assertNotIn("Old lyric row", html)
        self.assertIn('<input type="checkbox" class="segment-select" name="selected_lines" value="0">', html)
        self.assertNotIn('class="line-select"', html)
        self.assertNotIn("<th>Lyrics</th>", html)

    def test_section_colors_replace_section_and_chorus_columns(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Verse line",
                "start_sec": 1.04,
                "end_sec": 2.06,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "",
            },
            {
                "line_index": 1,
                "section": "Chorus",
                "is_chorus": 1,
                "clean_text": "Hook line",
                "start_sec": 2.06,
                "end_sec": 5.44,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "status": "pending",
                "error": "",
            },
        ]

        html = _project_html(project, lines, used_actions={"scene-plan"})

        self.assertIn('class="section-verse"', html)
        self.assertIn('class="section-chorus"', html)
        self.assertIn("1.0 - 2.1", html)
        self.assertIn("2.1 - 5.4", html)
        self.assertNotIn("<th>#</th>", html)
        self.assertNotIn("<th>Section</th>", html)
        self.assertNotIn("<th>Chorus</th>", html)
        self.assertIn('<span class="legend-swatch section-verse"></span>Verse', html)
        self.assertIn('<span class="legend-swatch section-chorus"></span>Refrain', html)

    def test_page_includes_clip_lightbox_player(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, []))

        self.assertIn('id="clip-lightbox"', html)
        self.assertIn('id="clip-lightbox-video"', html)
        self.assertIn("function openClipLightbox", html)
        self.assertIn("function closeClipLightbox", html)

    def test_build_segments_button_is_in_top_action_row_after_align(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, []))

        align_index = html.index('<button>1. Align</button>')
        segments_index = html.index('<button>2. Segs + Audio</button>')
        scene_plan_index = html.index('<button>3. Scene Plan</button>')
        prompts_index = html.index('<button>4. Gen Image Prompts</button>')
        video_prompts_index = html.index('<button>5. Gen Video Prompts</button>')
        images_index = html.index('<button>6. Gen Images</button>')
        avatar_index = html.index('<button>7. Gen Avatar Image</button>')
        clips_index = html.index('<button>8. Gen Clips</button>')
        assemble_index = html.index('9. Assemble Final')
        settings_index = html.index('action="/projects/7/settings"')
        self.assertLess(align_index, segments_index)
        self.assertLess(segments_index, scene_plan_index)
        self.assertLess(scene_plan_index, prompts_index)
        self.assertLess(prompts_index, video_prompts_index)
        self.assertLess(video_prompts_index, images_index)
        self.assertLess(images_index, avatar_index)
        self.assertLess(avatar_index, clips_index)
        self.assertLess(clips_index, assemble_index)
        self.assertLess(segments_index, settings_index)

    def test_used_top_actions_are_numbered_and_dark_grey_but_clickable(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _project_html(project, [], used_actions={"align", "prompts"})

        self.assertIn('<button class="used-button" title="Already used; click to run again">1. Align</button>', html)
        self.assertIn('<button class="used-button" title="Already used; click to run again">4. Gen Image Prompts</button>', html)
        self.assertIn('action="/projects/7/align"', html)
        self.assertIn('action="/projects/7/prompts"', html)

    def test_project_settings_are_visible_by_default_without_group_size_reset_warning(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, []))

        self.assertNotIn("<details>", html)
        self.assertNotIn("<summary>Project Settings</summary>", html)
        self.assertIn("<h2>Project Settings</h2>", html)
        self.assertIn('data-original-lyric-group-size="2"', html)
        self.assertIn('data-original-chorus-group-size="1"', html)
        self.assertIn("confirmProjectSettingsSave(this)", html)
        self.assertNotIn("Projekt leeren und Segmente neu erstellen?", html)
        self.assertIn("Lyrics neu alignen und Segmente neu erstellen?", html)
        self.assertIn('class="hidden-action-form" id="global-style-prompt-form-7"', html)
        self.assertIn('class="hidden-action-form" id="realign-lyrics-form-7"', html)
        self.assertIn('class="hidden-action-form" id="realign-lyrics-cpu-form-7"', html)
        self.assertIn(".hidden-action-form { display: none; }", html)

    def test_project_page_shows_editable_scene_plan_after_settings(self):
        project = {
            "id": 7,
            "name": "Demo",
            "audio_path": "song.wav",
            "final_video_path": None,
            "scene_plan": "0: Neon intro\n1: Close chorus",
        }

        html = _project_html(project, [])

        self.assertIn("<h2>Scene Plan</h2>", html)
        self.assertIn('action="/projects/7/scene-plan/save"', html)
        self.assertIn('name="scene_plan"', html)
        self.assertIn("0: Neon intro", html)
        self.assertIn("1: Close chorus", html)
        self.assertIn("<button>Save Scene Plan</button>", html)
        self.assertLess(html.index("<h2>Project Settings</h2>"), html.index("<h2>Scene Plan</h2>"))
        self.assertLess(html.index("<h2>Scene Plan</h2>"), html.index("<h2>Lyrics / Timing</h2>"))

    def test_project_page_has_sticky_header_and_no_audio_final_info_panel(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "final.mp4"}

        html = _page("Demo", _project_html(project, [], queue_estimate_seconds=70.0), queue_count=4)

        self.assertIn("<title>(4) Demo</title>", html)
        self.assertIn('class="project-topbar"', html)
        self.assertIn('class="project-title-row"', html)
        self.assertIn('id="queue-estimate"', html)
        self.assertIn('data-seconds="70"', html)
        self.assertIn("Queue ca. 1m 10s", html)
        self.assertIn('class="scroll-top-button"', html)
        self.assertIn("function scrollToTop", html)
        self.assertIn(".project-topbar", html)
        self.assertIn("position: sticky", html)
        self.assertNotIn("<strong>Audio:</strong>", html)
        self.assertNotIn("<strong>Final:</strong>", html)

    def test_project_page_has_bottom_clear_button_with_confirmation(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _project_html(project, [])

        self.assertIn('<details class="danger-panel">', html)
        self.assertIn("<summary>Danger Zone</summary>", html)
        self.assertIn('action="/projects/7/clear"', html)
        self.assertIn('action="/projects/7/delete"', html)
        self.assertIn("return confirm('Projekt wirklich leeren?", html)
        self.assertIn("return confirm('Projekt wirklich loeschen?", html)
        self.assertIn('class="danger-button"', html)
        self.assertGreater(html.index('action="/projects/7/clear"'), html.index('<table>'))
        self.assertGreater(html.index('action="/projects/7/delete"'), html.index('action="/projects/7/clear"'))

    def test_project_page_renders_editable_project_settings(self):
        project = {
            "id": 7,
            "name": "Demo Song",
            "audio_path": "song.wav",
            "lyrics_path": "lyrics.txt",
            "global_style_prompt": "cinematic steel",
            "reference_image_paths": '["ref-a.png", "ref-b.png"]',
            "genre": "metal ballad",
            "comfy_base_url": "http://127.0.0.1:8188",
            "output_resolution": "1024x576",
            "fps": 30,
            "final_video_path": None,
            "lyric_group_size": 2,
            "chorus_group_size": 4,
            "transition_handle_seconds": 0.75,
            "whisper_model_size": "medium",
        }

        html = _project_html(project, [])

        self.assertIn('action="/projects/7/settings"', html)
        self.assertIn('name="name"', html)
        self.assertIn('value="Demo Song"', html)
        self.assertIn('name="audio_path"', html)
        self.assertIn('value="song.wav"', html)
        self.assertIn('name="lyrics_path"', html)
        self.assertIn('value="lyrics.txt"', html)
        self.assertIn('name="global_style_prompt"', html)
        self.assertIn("cinematic steel", html)
        self.assertIn('action="/projects/7/global-style-prompt"', html)
        self.assertIn("KI-Vorschlag erstellen", html)
        self.assertIn('name="reference_image_paths"', html)
        self.assertIn("ref-a.png", html)
        self.assertIn("ref-b.png", html)
        self.assertIn('name="genre"', html)
        self.assertIn('value="metal ballad"', html)
        self.assertIn('name="comfy_base_url"', html)
        self.assertIn('value="http://127.0.0.1:8188"', html)
        self.assertIn('name="output_resolution"', html)
        self.assertIn('value="1024x576"', html)
        self.assertIn('name="fps"', html)
        self.assertIn('value="30"', html)
        self.assertIn('name="transition_handle_seconds"', html)
        self.assertIn('value="0.75"', html)
        self.assertIn('name="whisper_model_size"', html)
        self.assertIn('<option value="medium" selected>medium</option>', html)
        self.assertLess(html.index('name="transition_handle_seconds"'), html.index('name="whisper_model_size"'))
        self.assertLess(html.index('name="whisper_model_size"'), html.index("<button>Save Project Settings</button>"))
        self.assertIn('data-original-lyric-group-size="2"', html)
        self.assertIn('data-original-chorus-group-size="4"', html)

    def test_reference_paths_from_text_keeps_non_empty_lines(self):
        self.assertEqual(_reference_paths_from_text(" ref-a.png \n\nref-b.png"), ["ref-a.png", "ref-b.png"])

    def test_local_asset_url_maps_absolute_project_output_path_to_assets_url(self):
        url = _local_asset_url(
            "D:\\data\\Projekte\\ComfyUI\\MusicvideoGen\\.musicvideogen\\outputs\\project-1\\audio-segments\\segment-000.wav"
        )

        self.assertTrue(url.startswith("/assets/outputs/project-1/audio-segments/segment-000.wav"))

    def test_local_asset_url_adds_cache_buster_for_existing_generated_assets(self):
        asset = APP_ROOT / "outputs" / "project-999" / "clips" / "segment-000.mp4"
        asset.parent.mkdir(parents=True, exist_ok=True)
        try:
            asset.write_bytes(b"first-version")

            url = _local_asset_url(str(asset))

            self.assertRegex(url, r"^/assets/outputs/project-999/clips/segment-000\.mp4\?v=\d+-13$")
        finally:
            if asset.exists():
                asset.unlink()

    def test_generated_image_path_renders_as_thumbnail_from_comfy_view_url(self):
        project = RowLike({
            "id": 7,
            "name": "Demo",
            "audio_path": "song.wav",
            "final_video_path": None,
            "comfy_base_url": "http://127.0.0.1:8188",
        })
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "musicvideogen/project-1/line-0-1782236016441_00001_.png",
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines, used_actions={"scene-plan"})

        self.assertIn('<img class="preview-image"', html)
        self.assertIn("openImageLightbox('http://127.0.0.1:8188/view?filename=line-0-1782236016441_00001_.png&amp;subfolder=musicvideogen%2Fproject-1&amp;type=output')", html)
        self.assertIn(
            'src="http://127.0.0.1:8188/view?filename=line-0-1782236016441_00001_.png&amp;subfolder=musicvideogen%2Fproject-1&amp;type=output"',
            html,
        )
        self.assertNotIn('target="_blank"', html)

    def test_generated_local_project_assets_render_from_assets_url(self):
        project = RowLike({
            "id": 7,
            "name": "Demo",
            "audio_path": "song.wav",
            "final_video_path": None,
            "comfy_base_url": "http://127.0.0.1:8188",
        })
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": 0.0,
                "end_sec": 3.0,
                "prompt": None,
                "image_path": "D:\\data\\Projekte\\ComfyUI\\MusicvideoGen\\.musicvideogen\\outputs\\project-1\\images\\segment-000.png",
                "avatar_image_path": "D:\\data\\Projekte\\ComfyUI\\MusicvideoGen\\.musicvideogen\\outputs\\project-1\\images\\avatar-segment-000.png",
                "clip_path": "D:\\data\\Projekte\\ComfyUI\\MusicvideoGen\\.musicvideogen\\outputs\\project-1\\clips\\segment-000.mp4",
                "audio_path": None,
                "scene_plan": "",
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, [], segments, used_actions={"scene-plan"})
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]

        self.assertIn('src="/assets/outputs/project-1/images/segment-000.png', html)
        self.assertIn('src="/assets/outputs/project-1/images/avatar-segment-000.png"', html)
        self.assertIn("openClipLightbox('/assets/outputs/project-1/clips/segment-000.mp4", html)
        self.assertIn('<td class="assets-column">', html)
        self.assertIn('<div class="asset-previews">', html)
        self.assertIn('<form class="compact-form image-choice"', html)
        self.assertLess(html.index("segment-000.png"), html.index("avatar-segment-000.png"))
        self.assertLess(table_html.index('class="asset-previews"'), table_html.index('class="compact-form image-choice"'))
        self.assertNotIn('<span class="asset-path">', html)

    def test_project_page_is_full_width_and_includes_image_lightbox(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, []))

        self.assertIn("max-width: none", html)
        self.assertIn(".preview-image { width: 292px; height: 164px;", html)
        self.assertIn(".asset-previews { display: flex;", html)
        self.assertIn('id="image-lightbox"', html)
        self.assertIn('id="image-lightbox-image"', html)
        self.assertIn("function openImageLightbox", html)
        self.assertIn("function closeImageLightbox", html)

    def test_prompts_are_editable_and_status_combines_error(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": "image prompt",
                "video_prompt": "video prompt",
                "image_path": None,
                "clip_path": None,
                "status": "failed",
                "error": "bad node",
            }
        ]

        html = _project_html(project, lines, used_actions={"scene-plan"})

        self.assertIn('action="/projects/7/lines/3/prompts/image/save"', html)
        self.assertIn('action="/projects/7/lines/3/prompts/image/ai-fill"', html)
        self.assertIn('action="/projects/7/lines/3/prompts/video/save"', html)
        self.assertIn('action="/projects/7/lines/3/prompts/video/ai-fill"', html)
        self.assertIn('name="prompt"', html)
        self.assertIn('name="video_prompt"', html)
        self.assertIn("<button>Save</button>", html)
        self.assertIn('formaction="/projects/7/lines/3/prompts/image/ai-fill">AI fill</button>', html)
        self.assertIn('formaction="/projects/7/lines/3/prompts/video/ai-fill">AI fill</button>', html)
        self.assertIn("<th>Status</th>", html)
        self.assertNotIn("<th>Error</th>", html)
        self.assertIn("failed", html)
        self.assertIn("bad node", html)

    def test_rows_show_image_choice_radios_only_when_both_images_exist(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "video_prompt": None,
                "image_path": "outputs/project-7/images/line-003.png",
                "avatar_image_path": "outputs/project-7/images/avatar-line-003.png",
                "selected_image_source": "image",
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines, used_actions={"scene-plan"})

        self.assertIn('action="/projects/7/lines/3/image-source"', html)
        self.assertIn(
            'type="radio" name="selected_image_source" value="image" checked onchange="rememberScrollPosition(); this.form.submit()"',
            html,
        )
        self.assertIn(
            'type="radio" name="selected_image_source" value="avatar" onchange="rememberScrollPosition(); this.form.submit()"',
            html,
        )

    def test_rows_show_autosave_video_approval_before_status(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 3,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Hallo Welt",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "video_prompt": None,
                "image_path": None,
                "clip_path": None,
                "video_approved": 1,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines, used_actions={"scene-plan"})

        self.assertIn("<th>Redo</th><th>OK</th><th>Status</th>", html)
        self.assertIn('action="/projects/7/lines/3/approval"', html)
        self.assertIn(
            'type="checkbox" name="video_approved" value="1" checked onchange="rememberScrollPosition(); this.form.submit()"',
            html,
        )
        self.assertLess(html.index("<th>Redo</th>"), html.index("<th>OK</th>"))

    def test_approved_rows_get_strong_green_marker(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Approved row",
                "start_sec": 0.0,
                "end_sec": 3.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "video_approved": 1,
                "status": "done",
                "error": "",
            }
        ]

        html = _page("Demo", _project_html(project, [], segments))

        self.assertIn('class="section-verse approved-row"', html)
        self.assertIn("tr.approved-row", html)

    def test_project_topbar_has_static_open_approval_counter(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Open row",
                "start_sec": 0.0,
                "end_sec": 3.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "video_approved": 0,
                "status": "done",
                "error": "",
            },
            {
                "segment_index": 1,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Approved row",
                "start_sec": 3.0,
                "end_sec": 6.0,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "scene_plan": "",
                "video_approved": 1,
                "status": "done",
                "error": "",
            },
        ]

        html = _page("Demo", _project_html(project, [], segments))

        self.assertIn('<span class="open-count-label">1/2 offen</span>', html)
        self.assertIn(".open-count-label { margin-left: auto", html)
        self.assertNotIn("open-filter-button", html)
        self.assertNotIn("open-filter-info", html)
        self.assertIn('data-work-item="1" data-video-approved="0"', html)
        self.assertIn('data-work-item="1" data-video-approved="1"', html)
        self.assertNotIn("function toggleOpenItemsFilter", html)
        self.assertNotIn("row.dataset.videoApproved === '1'", html)

    def test_assemble_final_alerts_until_all_visible_items_are_approved(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "One",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "video_prompt": None,
                "image_path": None,
                "clip_path": "one.mp4",
                "video_approved": 1,
                "status": "done",
                "error": "",
            },
            {
                "line_index": 1,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Two",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "video_prompt": None,
                "image_path": None,
                "clip_path": "two.mp4",
                "video_approved": 0,
                "status": "done",
                "error": "",
            },
        ]

        html = _project_html(project, lines)

        self.assertIn('type="button"', html)
        self.assertIn("alert('Bitte erst alle Videos mit OK freigeben.')", html)
        self.assertIn('title="Alle Videos erst mit OK markieren"', html)
        self.assertIn("9. Assemble Final", html)

        lines[1]["video_approved"] = 1
        approved_html = _project_html(project, lines)

        self.assertIn('action="/projects/7/assemble"', approved_html)
        self.assertNotIn("alert('Bitte erst alle Videos mit OK freigeben.')", approved_html)

    def test_lyrics_table_has_insert_and_delete_line_controls(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "One",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "video_prompt": None,
                "image_path": None,
                "clip_path": None,
                "video_approved": 0,
                "status": "pending",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('action="/projects/7/lines/0/insert-after"', html)
        self.assertIn('placeholder="Neue Zeile darunter"', html)
        self.assertIn('action="/projects/7/lines/0/delete"', html)
        self.assertIn("<th>Loeschen</th>", html)
        self.assertIn("Lyrics-Zeile wirklich loeschen?", html)

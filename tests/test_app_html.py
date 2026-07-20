import tempfile
import unittest
from html import unescape
from pathlib import Path

from fastapi.testclient import TestClient

import VocaVid.app as app_module
import VocaVid.ui.context as ui_context
from VocaVid.app import APP_ROOT
from VocaVid.ui.assets import _page
from VocaVid.ui.formatting import (
    _job_name,
    _local_asset_url,
    _reference_paths_from_text,
    _section_type,
)
from VocaVid.ui.projects import (
    _project_html,
    _project_navigation_ids,
    _project_status_payload,
    _projects_html,
)
from VocaVid.ui.queue import _queue_estimate_label
from VocaVid.ui.storyboard import (
    _segment_inspector_html,
    _storyboard_item_display_label,
)
from VocaVid.worker import Job


class RowLike:
    def __init__(self, data):
        self.data = data

    def __getitem__(self, key):
        return self.data[key]


class AppHtmlTests(unittest.TestCase):
    def setUp(self):
        ui_context.APP_ROOT = app_module.APP_ROOT

    def test_page_uses_dark_studio_shell_styles(self):
        html = _page("Projects", "")

        self.assertIn(":root", html)
        self.assertIn("--studio-bg", html)
        self.assertIn("background:", html)
        self.assertIn(".studio-topbar", html)
        self.assertIn(".studio-logo", html)
        self.assertIn(".studio-logo { width: 68px; height: 68px;", html)
        self.assertIn(".studio-panel", html)
        self.assertIn(".studio-button", html)
        self.assertIn(".studio-chip", html)
        self.assertIn("--bg-app: #0b1012;", html)
        self.assertIn("--action: #29d3b0;", html)
        self.assertIn("--accent: #e9489f;", html)
        self.assertIn("radial-gradient(ellipse 60% 280px at 8% 0%, rgba(41,211,176,.07), transparent 72%)", html)
        self.assertIn("form, .panel { background: var(--bg-panel); border: 1px solid var(--border-subtle); color: var(--text-primary);", html)
        self.assertIn("table { width: 100%; border-collapse: collapse; background: var(--bg-card); color: var(--text-primary);", html)
        self.assertIn("button, .button {", html)
        self.assertIn("background: var(--action);", html)
        self.assertIn(".actions button { border: 1px solid #3a454b; background: #293136; color: #c8d0d4;", html)
        self.assertIn(".wip-button { border-color: var(--accent); background: var(--accent);", html)
        self.assertIn(".actions .wip-button { border-color: var(--accent); background: var(--accent); color: #fff;", html)
        self.assertIn(".danger-panel { margin-top: 24px; border-color: rgba(238,102,117,.48); background: transparent; color: var(--danger);", html)
        self.assertIn(".danger-panel[open] { background: transparent;", html)
        self.assertIn(".project-title-right { justify-content: flex-end;", html)
        self.assertIn(".queue-estimate { padding: 6px 10px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: #202a2f; color: var(--text-secondary);", html)
        self.assertIn(".queue-modal { z-index: 180;", html)
        self.assertIn(".queue-modal-content { width: min(1120px, 96vw); height: 75vh; max-height: 75vh;", html)
        self.assertIn(".queue-modal-body { min-height: 0; overflow: auto; padding-bottom: 16px;", html)

    def test_project_form_does_not_ask_for_workflow_json_paths(self):
        html = _projects_html([], [])

        self.assertNotIn("Workflow JSON Path", html)
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
        self.assertIn('<label>Genre</label><input name="genre" required>', html)
        self.assertIn('<label>Avatar</label><input name="avatar" type="file" accept="image/*">', html)
        self.assertIn('<label>Male / Female Avatar</label><select name="avatar_gender">', html)
        self.assertIn('<option value="male">Male</option>', html)
        self.assertIn('<label>Avatar face description</label><textarea name="avatar_face_description" placeholder=""></textarea>', html)
        self.assertNotIn('title="Available after creating the project">AI describe avatar</button>', html)
        self.assertIn('<label>Comfy Base URL</label><input name="comfy_base_url" placeholder="http://127.0.0.1:8188">', html)
        self.assertIn('name="lyric_group_size" type="number" min="1" max="8" placeholder="2"', html)
        self.assertIn('name="chorus_group_size" type="number" min="1" max="8" placeholder="1"', html)
        self.assertIn('name="output_resolution" placeholder="1280x720"', html)
        self.assertIn('name="fps" type="number" min="1" placeholder="24"', html)
        self.assertIn('name="transition_handle_seconds" type="number" min="0" step="0.1" placeholder="0.5"', html)
        self.assertIn('<option value="large-v3" selected>large-v3</option>', html)
        self.assertNotIn("SUNO Lyrics", html)
        self.assertNotIn("Global Style Prompt", html)
        self.assertNotIn('name="global_style_prompt"', html)
        self.assertNotIn("Reference Images", html)
        self.assertNotIn('name="references"', html)
        self.assertIn("<label>Resolution</label>", html)
        self.assertIn("<label>FPS</label>", html)
        self.assertIn("<label>Whisper Model</label>", html)

    def test_project_form_includes_clip_group_defaults(self):
        html = _projects_html([], [])
        html = html[html.index('id="new-project-modal"'):]

        self.assertIn('name="lyric_group_size" type="number" min="1" max="8" placeholder="2"', html)
        self.assertIn('name="chorus_group_size" type="number" min="1" max="8" placeholder="1"', html)
        self.assertIn('name="transition_handle_seconds" type="number" min="0" step="0.1" placeholder="0.5"', html)
        self.assertIn('<option value="large-v3" selected>large-v3</option>', html)
        self.assertLess(html.index('name="lyrics"'), html.index('name="lyric_group_size"'))
        self.assertLess(html.index('name="lyric_group_size"'), html.index('name="chorus_group_size"'))
        self.assertLess(html.index('name="chorus_group_size"'), html.index('name="transition_handle_seconds"'))
        self.assertLess(html.index('name="transition_handle_seconds"'), html.index('name="whisper_model_size"'))
        self.assertLess(html.index('name="whisper_model_size"'), html.index("<p><button>Create Project</button></p>"))

    def test_start_page_has_persistent_global_configuration_modal(self):
        settings = {
            "avatar_path": "global/band.png",
            "avatar_gender": "female",
            "avatar_face_description": "silver hair",
            "comfy_base_url": "http://127.0.0.1:9000",
            "output_resolution": "1920x1080",
            "fps": 30,
            "lyric_group_size": 3,
            "chorus_group_size": 2,
            "transition_handle_seconds": 0.8,
            "whisper_model_size": "medium",
            "project_browser_sort": "name-asc",
            "autodelete_finished": 1,
            "shutdown_after_queue": 0,
        }

        html = _projects_html([], [], global_settings=settings)

        self.assertIn('title="Global Configuration"', html)
        self.assertIn('onclick="openGlobalSettingsModal()"', html)
        self.assertIn('id="global-settings-modal"', html)
        self.assertIn('action="/settings"', html)
        self.assertIn('src="/assets/global/band.png"', html)
        self.assertIn('placeholder="http://127.0.0.1:9000"', html)
        self.assertIn('placeholder="1920x1080"', html)
        self.assertIn('<option value="medium" selected>medium</option>', html)
        self.assertIn('<option value="name-asc" selected>Name asc</option>', html)
        self.assertIn('name="autodelete_finished" checked', html)

    def test_start_page_renders_project_cards_and_marks_done_projects(self):
        projects = [
            {"id": 2, "name": "Finished Song", "final_video_path": "outputs/finished/final.kdenlive"},
            {"id": 1, "name": "Open Song", "final_video_path": None},
        ]

        body = _projects_html(projects, [])
        html = _page("Projects", body)

        self.assertIn('class="project-card project-card-done"', body)
        self.assertLess(body.index('data-project-id="2"'), body.index('data-project-id="1"'))
        self.assertIn('<a class="project-card-link" href="/projects/2">', body)
        self.assertIn("Finished Song", body)
        self.assertIn('class="project-done-badge" aria-label="Done"', body)
        self.assertIn("&#10003;", body)
        self.assertIn('<a class="project-card-link" href="/projects/1">', body)
        self.assertIn('data-project-id="2"', body)
        self.assertIn('data-status="done"', body)
        self.assertIn('data-status="in-progress"', body)
        self.assertIn('class="progress-pill project-progress-badge"', body)
        self.assertIn('<span class="progress-pill-label">0/0</span>', body)
        self.assertNotIn("Open project", body)
        self.assertNotIn(">DONE<", body)
        self.assertIn(".project-grid", html)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", html)
        self.assertIn("aspect-ratio: 16 / 9", html)
        self.assertIn(".project-done-badge", html)
        self.assertIn('id="project-search"', body)
        self.assertIn('id="project-filter"', body)
        self.assertIn('id="project-sort"', body)
        self.assertIn("function applyProjectBrowserControls", html)
        self.assertIn("function saveProjectBrowserSort", html)
        self.assertIn("fetch('/settings/project-browser'", html)
        self.assertNotIn("projectBrowserPreferences", html)
        self.assertNotIn("localStorage", html)
        self.assertIn("setupProjectBrowserControls();", html)
        self.assertIn('class="project-card-placeholder-mark" aria-label="No preview yet"', body)
        self.assertNotIn(">FS<", body)
        self.assertNotIn(">OS<", body)
        self.assertIn('<img class="studio-logo" src="/icon/VocaVid_icon.svg" alt="" aria-hidden="true">', body)
        self.assertLess(body.index('onclick="openNewProjectModal()"'), body.index('onclick="openGlobalSettingsModal()"'))

    def test_project_cards_use_chorus_clip_preview_before_other_media(self):
        projects = [{"id": 7, "name": "Demo Song", "final_video_path": None}]
        previews = {
            7: [
                {
                    "section": "Verse",
                    "is_chorus": 0,
                    "clip_path": "outputs/demo/clips/verse.mp4",
                    "image_path": "outputs/demo/images/verse.png",
                    "avatar_image_path": None,
                },
                {
                    "section": "Refrain",
                    "is_chorus": 1,
                    "clip_path": "outputs/demo/clips/refrain.mp4",
                    "image_path": "outputs/demo/images/refrain.png",
                    "avatar_image_path": None,
                },
            ]
        }

        body = _projects_html(projects, [], project_previews=previews)

        self.assertIn('<video src="/assets/outputs/demo/clips/refrain.mp4', body)
        self.assertIn('preload="metadata" muted playsinline', body)
        self.assertNotIn("verse.mp4", body)
        self.assertIn('class="progress-pill project-progress-badge"', body)
        self.assertIn('<span class="progress-pill-fill" style="--progress: 0%"></span>', body)
        self.assertIn('<span class="progress-pill-label">0/2</span>', body)

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
        self.assertIn('class="queue-cleanup-actions"', html)
        self.assertIn('class="compact-form queue-settings-line"', html)
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

    def test_queue_jobs_with_project_targets_are_clickable(self):
        jobs = [
            Job(
                id=5,
                name="generate clips: Demo Song (segment 3)",
                status="queued",
                created_at="2026-06-27T19:15:24",
                project_id=7,
                action="clips",
                item_kind="segments",
                selected_indices=[2],
            )
        ]

        html = _projects_html([], jobs)

        self.assertIn('class="queue-job-row"', html)
        self.assertIn('data-href="/projects/7"', html)
        self.assertIn('data-template-id="segment-inspector-template-segments-2"', html)
        self.assertIn("openQueueJobRow(this)", html)
        self.assertIn("Open target", html)

    def test_start_page_queue_summary_shows_status_counts_and_estimate(self):
        jobs = [
            Job(id=4, name="queued", status="queued", created_at="2026-06-27T19:15:24"),
            Job(id=3, name="running", status="running", created_at="2026-06-27T19:03:22"),
            Job(id=2, name="done", status="done", created_at="2026-06-27T18:00:00"),
            Job(id=1, name="failed", status="failed", created_at="2026-06-27T17:00:00"),
        ]

        html = _projects_html([], jobs, queue_estimate_seconds=70.0)

        self.assertNotIn('id="jobs-panel"', html)
        self.assertIn('id="queue-modal"', html)
        self.assertIn('class="queue-modal-body"', html)
        self.assertIn('class="queue-summary-card queue-summary-card-active"', html)
        self.assertIn("<strong>1</strong><span>queued</span>", html)
        self.assertIn("<strong>1</strong><span>running</span>", html)
        self.assertIn("<strong>1</strong><span>done</span>", html)
        self.assertIn("<strong>1</strong><span>failed</span>", html)
        self.assertIn("<strong>1m 10s</strong><span>estimate</span>", html)

    def test_queue_estimate_label_shows_count_and_unknown_when_time_runs_out(self):
        self.assertEqual(_queue_estimate_label(126, 3), "3 ~2m 6s")
        self.assertEqual(_queue_estimate_label(0, 1), "1 ~?s")
        self.assertEqual(_queue_estimate_label(0, 0), "Queue 0")

    def test_start_page_has_queue_polling_and_queue_options(self):
        jobs = [
            Job(id=4, name="queued", status="queued", created_at="2026-06-27T19:15:24"),
            Job(id=3, name="running", status="running", created_at="2026-06-27T19:03:22"),
        ]
        html = _page("Projects", _projects_html([], jobs, queue_estimate_seconds=70.0), queue_count=2)

        self.assertIn('id="queue-estimate"', html)
        self.assertNotIn('id="production-queue-estimate"', html)
        self.assertIn('data-queue-estimate="1"', html)
        self.assertIn('data-count="2"', html)
        self.assertIn(">2 ~1m 10s</button>", html)
        self.assertIn('onclick="openQueueModal()"', html)
        self.assertNotIn('href="#jobs-panel"', html)
        self.assertNotIn('id="jobs-panel"', html)
        self.assertIn('id="queue-summary"', html)
        self.assertIn('id="jobs-table-body"', html)
        self.assertIn('name="autodelete_finished"', html)
        self.assertIn("Autodelete finished", html)
        self.assertIn('name="shutdown_after_queue"', html)
        self.assertIn("Shutdown computer 15mins after last queue", html)
        self.assertIn('data-queue-form="1" action="/jobs/delete-queued"', html)
        self.assertIn('data-queue-form="1" action="/jobs/options"', html)
        self.assertIn('onchange="submitQueueForm(event, this.form)"', html)
        self.assertIn("setupQueueEstimateCountdown(); pollJobsStatus();", html)
        self.assertIn("fetch('/jobs/status')", html)
        self.assertIn("function submitQueueForm", html)
        self.assertIn("form[data-queue-form=\"1\"]", html)
        self.assertIn("data.queue_summary_html", html)
        self.assertIn("queueSummary.innerHTML = data.queue_summary_html", html)

    def test_jobs_status_endpoint_returns_queue_summary_for_polling(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"

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
        self.assertEqual(_job_name("generate clips", "Demo Song", [13], item_kind="segments"), "generate clips: Demo Song (segment 14)")
        self.assertEqual(_job_name("generate prompts", "Demo Song", [1], item_kind="lines"), "generate prompts: Demo Song (line 2)")

    def test_storyboard_item_display_label_is_one_based(self):
        self.assertEqual(_storyboard_item_display_label("segments", 13), "# 14")
        self.assertEqual(_storyboard_item_display_label("lines", 1), "# 02")

    def test_project_actions_include_finalize_and_combined_render(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        html = _page("Demo", _project_html(project, []))

        self.assertIn('<button>1. Analyze + Split</button>', html)
        self.assertNotIn("Segs + Audio", html)
        self.assertIn('<button>3. Gen Prompts</button>', html)
        self.assertNotIn("Gen Image Prompts", html)
        self.assertNotIn("Gen Video Prompts", html)
        self.assertIn('<button>4. Gen Images</button>', html)
        self.assertIn('<button>5. Gen Avatar Images</button>', html)
        self.assertIn('<button>6. Gen Clips</button>', html)
        self.assertIn('disabled title="Generate all clips first">7. Finalize', html)
        self.assertIn('disabled title="Finish all clips first">8. Assemble &amp; Render MP4', html)

    def test_project_page_offers_select_all_for_explicit_regeneration(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        rows = [{
            "segment_index": 0, "kind": "lyrics", "section": "Verse", "is_chorus": 0,
            "clean_text": "One", "start_sec": 0.0, "end_sec": 1.0,
            "prompt": "", "video_prompt": "", "image_path": None,
            "avatar_image_path": None, "selected_image_source": "avatar", "clip_path": None,
            "audio_path": None, "last_action": "", "scene_plan": "", "video_approved": 0,
            "status": "", "error": "",
        }]

        html = _page("Demo", _project_html(project, [], rows))

        self.assertIn('id="project-select-all"', html)
        self.assertIn('Alle markieren', html)
        self.assertIn('bewusst neu erstellt', html)

    def test_project_page_includes_reels_button_and_modal(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "outputs/demo/final.kdenlive"}

        html = _page("Demo", _project_html(project, []))

        self.assertIn('<button type="button" disabled title="Render the final MP4 first">9. Make reels</button>', html)
        self.assertNotIn('class="reels-open-button"', html)
        self.assertNotIn('onclick="openReelsModal()"', html)
        self.assertIn('id="reels-modal"', html)
        self.assertIn('id="reels-status"', html)
        self.assertIn('action="/projects/7/reels/analyze"', html)
        self.assertIn('data-reels-form="1"', html)
        self.assertIn("If empty, VocaVid uses", html)
        self.assertIn("outputs/demo/Demo.mp4", html)
        self.assertNotIn('name="source_video_path"', html)
        self.assertIn('name="source_video" type="file" accept="video/mp4,.mp4" onchange="updateReelsUploadLabel(this)"', html)
        self.assertIn('class="reels-upload-name" aria-live="polite">No upload selected</p>', html)
        self.assertIn("If empty, VocaVid uses", html)
        self.assertNotIn('name="lyrics"', html[html.index('id="reels-modal"') :])
        self.assertIn("function openReelsModal", html)

    def test_reels_button_is_enabled_after_rendered_mp4_exists(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "outputs/demo/final.kdenlive"}
        rendered_mp4 = app_module.APP_ROOT / "outputs" / "demo" / "Demo.mp4"
        rendered_mp4.parent.mkdir(parents=True, exist_ok=True)
        try:
            rendered_mp4.write_bytes(b"mp4")

            html = _page("Demo", _project_html(project, []))

            self.assertIn('<button type="button" onclick="openReelsModal()">9. Make reels</button>', html)
            self.assertNotIn('disabled title="Bitte zuerst das finale MP4 rendern."', html)
            self.assertNotIn('class="reels-open-button"', html)
        finally:
            if rendered_mp4.exists():
                rendered_mp4.unlink()
        self.assertIn("function submitReelsForm", html)
        self.assertIn("function markReelsFormProcessing", html)
        self.assertIn("button.textContent = 'Processing...'", html)
        self.assertIn("function hasActiveReelsVideo", html)
        self.assertIn("function preserveReelsVideos", html)
        self.assertIn("function preserveReelsUploadInput", html)
        self.assertIn("function pauseReelsUploadRefresh", html)
        self.assertIn("function hasActiveReelsUploadInteraction", html)
        self.assertIn("if (!force && hasActiveReelsUploadInteraction()) return", html)
        self.assertIn("pauseReelsUploadRefresh()", html)
        self.assertIn("preserveReelsVideos(template.content)", html)
        self.assertIn("preserveReelsUploadInput(template.content)", html)
        self.assertIn("box.replaceChildren(template.content)", html)
        self.assertIn("if (box.innerHTML === data.reels_html) return", html)
        self.assertIn("if (!force && hasPendingReelsUpload()) return", html)
        self.assertIn("if (!force && hasActiveReelsVideo()) return", html)
        self.assertIn("updateReelsStatus(await response.json(), force)", html)
        self.assertIn("function updateReelsUploadLabel", html)
        self.assertIn("Selected: ' + file.name", html)
        self.assertIn("function hasPendingReelsUpload", html)
        self.assertIn("if (!force && hasPendingReelsUpload()) return", html)
        self.assertGreaterEqual(html.count("if (!force && hasPendingReelsUpload()) return"), 2)
        self.assertIn("await refreshReelsStatus(projectId, true)", html)
        self.assertIn("fetch('/projects/' + projectId + '/reels/status')", html)
        self.assertIn("pollReelsStatus(7)", html)
        self.assertIn(".reels-modal-content { width: min(1500px, 98vw); height: min(980px, 94vh);", html)
        self.assertIn(".reels-modal-content .lightbox-close { top: 12px; right: 12px;", html)
        self.assertIn(".reels-grid { display: grid; grid-template-columns: 1fr;", html)
        self.assertIn(".reels-source-form { display: grid; grid-template-columns: minmax(280px, 420px) minmax(260px, 1fr) auto;", html)
        self.assertIn(".reels-source-upload, .reels-source-info { display: grid; gap: 7px;", html)
        self.assertIn(".reels-source-path { display: inline-block;", html)
        self.assertIn(".reels-candidate-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));", html)
        self.assertIn(".reels-candidate-card { display: grid; grid-template-rows: auto minmax(260px, 1fr) auto;", html)
        self.assertIn(".reels-status-pill { flex: 0 0 auto;", html)
        self.assertIn(".reels-candidate-card.reels-candidate-processing", html)

    def test_reels_modal_renders_candidates_and_export_actions(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        analyses = [
            {
                "id": 3,
                "project_id": 7,
                "source_video_path": "D:/exports/final.mp4",
                "status": "done",
                "error": "",
                "metadata_json": '{"duration": 95.0, "width": 1920, "height": 1080, "fps": 25.0}',
            }
        ]
        candidates = {
            3: [
                {
                    "id": 9,
                    "analysis_id": 3,
                    "label": "Final Chorus 2",
                    "start_sec": 30.0,
                    "end_sec": 58.5,
                    "score": 1.92,
                    "reasons_json": '["final chorus", "hook"]',
                    "preview_path": "outputs/demo/reels/previews/reel-009-preview.mp4",
                    "export_path": "",
                }
            ]
        }

        html = _project_html(project, [], reel_analyses=analyses, reel_candidates_by_analysis=candidates)

        self.assertIn("Final Chorus 2", html)
        self.assertIn('class="reels-status-pill reels-status-pending">pending</span>', html)
        self.assertIn('src="/assets/outputs/demo/reels/previews/reel-009-preview.mp4', html)
        self.assertIn('data-reels-form="1" action="/projects/7/reels/3/candidates/9/preview"', html)
        self.assertIn('data-reels-form="1" action="/projects/7/reels/3/candidates/9/export"', html)
        self.assertIn('data-reels-form="1" action="/projects/7/reels/3/candidates/9/clear"', html)
        self.assertIn('data-reels-form="1" action="/projects/7/reels/3/candidates/9/delete"', html)
        self.assertLess(html.index("<h4>Final Chorus 2</h4>"), html.index('class="reels-preview-frame"'))
        self.assertLess(html.index('class="reels-preview-frame"'), html.index('class="reels-candidate-actions"'))
        self.assertNotIn('aria-label="Export"', html)

        candidates[3][0]["export_path"] = "outputs/demo/reels/reel-009-export.mp4"
        html = _project_html(project, [], reel_analyses=analyses, reel_candidates_by_analysis=candidates)

        self.assertIn('src="/assets/outputs/demo/reels/reel-009-export.mp4', html)
        self.assertIn('aria-label="Export"', html)
        self.assertNotIn('src="/assets/outputs/demo/reels/previews/reel-009-preview.mp4', html)
        self.assertLess(html.index("<h3>Source MP4</h3>"), html.index("<h3>Analysis</h3>"))
        self.assertLess(html.index("<h3>Analysis</h3>"), html.index("<h3>Candidates</h3>"))

    def test_project_header_has_previous_and_next_project_triangle_links(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, [], previous_project_id=8, next_project_id=6))

        self.assertIn('<a class="project-nav-button" href="/projects/8" title="Vorhergehendes Projekt">◀</a>', html)
        self.assertIn('<a class="project-nav-button" href="/projects/6" title="Nachfolgendes Projekt">▶</a>', html)
        self.assertLess(html.index('title="Vorhergehendes Projekt"'), html.index("<h1>Demo</h1>"))
        self.assertLess(html.index("<h1>Demo</h1>"), html.index('title="Nachfolgendes Projekt"'))
        self.assertIn(".project-nav-button", html)

    def test_project_navigation_uses_saved_sort_over_all_projects(self):
        projects = [
            {"id": 4, "name": "Zebra", "final_video_path": "outputs/zebra/final.kdenlive"},
            {"id": 3, "name": "Äther", "final_video_path": None},
            {"id": 2, "name": "Beta", "final_video_path": None},
            {"id": 1, "name": "Alpha", "final_video_path": None},
        ]

        previous_id, next_id = _project_navigation_ids(
            projects,
            2,
            project_sort="name-asc",
        )

        self.assertEqual((previous_id, next_id), (3, 4))

    def test_project_navigation_links_are_parameterless(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _project_html(
            project,
            [],
            previous_project_id=8,
            next_project_id=6,
        )

        self.assertIn('href="/projects/8"', html)
        self.assertIn('href="/projects/6"', html)
        self.assertIn('href="/" aria-label="Back to projects"', html)

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
        self.assertIn('class="project-title-row"', html)
        self.assertIn('class="project-title-left"', html)
        self.assertIn('class="project-title-center"', html)
        self.assertIn('class="project-title-right"', html)
        self.assertLess(html.index('class="project-title-left"'), html.index('class="project-title-center"'))
        self.assertLess(html.index('class="project-title-center"'), html.index('class="project-title-right"'))
        self.assertIn('aria-label="Back to projects" title="Back to projects">←</a>', html)
        self.assertLess(html.index('aria-label="Back to projects"'), html.index('title="Project Settings"'))
        self.assertLess(html.index('title="Project Settings"'), html.index('id="project-progress-pill"'))
        self.assertLess(html.index('id="project-progress-pill"'), html.index('title="Vorhergehendes Projekt"'))
        self.assertLess(html.index('title="Vorhergehendes Projekt"'), html.index("<h1>Demo</h1>"))
        self.assertLess(html.index("<h1>Demo</h1>"), html.index('title="Nachfolgendes Projekt"'))
        self.assertLess(html.index('title="Nachfolgendes Projekt"'), html.index('id="queue-estimate"'))
        self.assertLess(html.index('id="queue-estimate"'), html.index('class="actions"'))
        self.assertNotIn('class="view-switch"', html)
        self.assertNotIn('data-project-view="storyboard"', html)
        self.assertNotIn('data-project-view="table"', html)
        self.assertNotIn(">Advanced Table</button>", html)
        self.assertIn('id="project-storyboard"', html)
        self.assertIn('class="storyboard-rail"', html)
        self.assertIn('id="project-table-view" class="project-table-view" hidden', html)
        self.assertIn('class="project-table-view"', html)
        self.assertIn("Storyboard lyric", html)
        self.assertIn("<table>", html)
        self.assertLess(html.index('id="project-storyboard"'), html.index('id="project-table-view"'))
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]
        self.assertIn("<table>", table_html)
        self.assertLess(html.index('id="project-table-view"'), html.index("<h2>Project Settings</h2>"))
        self.assertIn('name="scene_plan" form="scene-plan-form-7"', html)
        self.assertLess(html.index('name="global_style_prompt"'), html.index('name="scene_plan" form="scene-plan-form-7"'))
        self.assertIn('<tr id="line-row-3"', table_html)
        self.assertIn('action="/projects/7/lines/3/timing"', table_html)
        self.assertIn('action="/projects/7/lines/3/insert-after"', table_html)
        self.assertIn('action="/projects/7/lines/3/delete"', table_html)

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
        self.assertIn('class="storyboard-card-video"', html)
        self.assertIn('src="/assets/outputs/project-7/clips/line-000.mp4', html)
        self.assertNotIn('poster="/assets/outputs/project-7/images/avatar-line-000.png', html)
        self.assertIn('preload="metadata"', html)
        self.assertNotIn('preload="none"', html)
        self.assertNotIn(" muted", html)
        self.assertIn('onclick="toggleStoryboardVideo(event, this)"', html)
        self.assertIn('class="storyboard-video-toggle"', html)
        self.assertIn('class="storyboard-video-expand"', html)
        self.assertIn('aria-label="Open clip in lightbox"', html)
        self.assertIn("openClipLightbox(&quot;/assets/outputs/project-7/clips/line-000.mp4", html)
        self.assertIn(", this)", html)
        self.assertIn("function toggleStoryboardVideo", _page("Demo", ""))
        page_html = _page("Demo", "")
        self.assertIn("function resetStoryboardVideo(target)", page_html)
        self.assertIn("video.currentTime = 0;", page_html)
        self.assertIn("resetStoryboardVideo(source);", page_html)
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
        card_html = html[html.index('<article class="storyboard-card') : html.index("</article>", html.index('<article class="storyboard-card'))]

        self.assertIn('src="/assets/outputs/project-7/images/avatar-line-000.png"', card_html)
        self.assertIn("openImageLightbox(&quot;/assets/outputs/project-7/images/avatar-line-000.png&quot;)", card_html)
        self.assertNotIn('src="/assets/outputs/project-7/images/line-000.png"', card_html)

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
        card_html = html[html.index('<article class="storyboard-card') : html.index("</article>", html.index('<article class="storyboard-card'))]

        self.assertIn('src="/assets/outputs/project-7/images/line-000.png"', card_html)
        self.assertIn("openImageLightbox(&quot;/assets/outputs/project-7/images/line-000.png&quot;)", card_html)
        self.assertNotIn('src="/assets/outputs/project-7/images/avatar-line-000.png"', card_html)

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
        inspector_html = html[html.index('<aside id="segment-inspector"') : html.index("</aside>", html.index('<aside id="segment-inspector"'))]

        self.assertIn('class="segment-inspector"', html)
        self.assertIn('class="segment-inspector-resize-handle" role="separator" aria-orientation="vertical" aria-label="Resize side panel" tabindex="0"', inspector_html)
        self.assertIn('<h3 class="segment-inspector-title"># 03</h3>', html)
        self.assertIn("Inspector lyric", html)
        self.assertIn('action="/projects/7/segments/2/prompts/image/save"', html)
        self.assertIn('formaction="/projects/7/segments/2/prompts/image/ai-fill"', html)
        self.assertIn('action="/projects/7/segments/2/prompts/video/save"', html)
        self.assertIn('formaction="/projects/7/segments/2/prompts/video/ai-fill"', html)
        self.assertIn('action="/projects/7/segments/2/image-source"', html)
        self.assertIn('name="selected_image_source" value="image" checked', html)
        self.assertNotIn('action="/projects/7/segments/2/redo"', inspector_html)
        self.assertNotIn('<div class="redo-action">images</div>', inspector_html)
        self.assertIn('action="/projects/7/segments/2/approval"', html)
        self.assertIn('onsubmit="rememberApprovalProgressBeforeSubmit()" data-project-sidepanel-form="1"', html)
        self.assertIn('name="video_approved" value="0"', html)
        self.assertIn('class="finish-toggle finish-toggle-active"', html)
        self.assertIn("Mark as unfinished", html)
        self.assertIn('<span class="finish-toggle-check" aria-hidden="true">&#10003;</span>', html)
        self.assertIn('class="segment-inspector-label-row"', html)
        self.assertIn('<div class="segment-inspector-label">Text</div><div class="segment-inspector-meta">1.0 - 2.0</div>', html)
        self.assertNotIn('<div class="segment-inspector-label">Status</div>', inspector_html)
        self.assertIn('class="storyboard-card-media storyboard-card-media-image"', html)
        self.assertIn(".segment-inspector", _page("Demo", ""))
        self.assertIn("--segment-inspector-width: minmax(360px, 520px)", _page("Demo", ""))
        self.assertIn("minmax(360px, 520px)", _page("Demo", ""))

    def test_segment_inspector_can_play_segment_audio_next_to_timing(self):
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

        html = _project_html(project, [], segments)
        inspector_html = html[html.index('<aside id="segment-inspector"') : html.index("</aside>", html.index('<aside id="segment-inspector"'))]

        self.assertIn('class="segment-inspector-meta segment-inspector-audio-meta"', inspector_html)
        self.assertIn('class="segment-audio-button icon-button" type="button" title="Segment audio abspielen" onclick="toggleAudio(this)">▶</button>', inspector_html)
        self.assertIn('src="/assets/outputs/project-7/audio-segments/segment-000.wav', inspector_html)
        self.assertIn("<span>0.0 - 8.0</span>", inspector_html)
        self.assertIn(".segment-inspector-audio-meta audio { display: none;", _page("Demo", ""))

    def test_storyboard_cards_select_active_inspector_and_show_progress(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "First segment",
                "start_sec": None,
                "end_sec": None,
                "prompt": "image prompt",
                "video_prompt": "video prompt",
                "image_path": "outputs/project-7/images/segment-000.png",
                "avatar_image_path": "outputs/project-7/images/avatar-segment-000.png",
                "clip_path": "outputs/project-7/clips/segment-000.mp4",
                "audio_path": None,
                "last_action": "clips",
                "video_approved": 1,
                "status": "done",
                "error": "",
            },
            {
                "segment_index": 1,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Second segment",
                "start_sec": None,
                "end_sec": None,
                "prompt": None,
                "video_prompt": None,
                "image_path": None,
                "avatar_image_path": None,
                "clip_path": None,
                "audio_path": None,
                "last_action": "",
                "video_approved": 0,
                "status": "pending",
                "error": "",
            },
        ]

        html = _page("Demo", _project_html(project, [], segments))

        self.assertIn('class="storyboard-card storyboard-card-active storyboard-card-approved"', html)
        self.assertIn('class="storyboard-card storyboard-card-unfinished"', html)
        self.assertNotIn("<h2>Storyboard</h2>", html)
        self.assertIn('data-inspector-template="segment-inspector-template-segments-0"', html)
        self.assertIn('class="segment-select storyboard-select" name="selected_lines" value="0"', html)
        self.assertIn('title="Segment markieren"', html)
        self.assertIn("!event.target.closest('.storyboard-select-wrap')", html)
        self.assertIn('<div class="storyboard-card-title"><span># 01</span>', html)
        self.assertIn('<span class="storyboard-card-meta"><span class="storyboard-section-badge storyboard-section-badge-verse">Verse</span></span>', html)
        self.assertIn(".storyboard-section-badge-verse", html)
        self.assertNotIn("Segment 0", html)
        self.assertIn('onclick="selectStoryboardItem(event, this)"', html)
        self.assertIn('<template id="segment-inspector-template-segments-1">', html)
        self.assertIn('class="segment-inspector-nav"', html)
        self.assertIn('<h3 class="segment-inspector-title"># 01</h3>', html)
        self.assertIn('<span class="project-nav-button project-nav-disabled" title="Kein vorhergehendes Segment">◀</span>', html)
        self.assertIn('<button class="project-nav-button segment-nav-button" type="button" title="Nachfolgendes Segment" onclick="selectStoryboardTemplate(&#x27;segment-inspector-template-segments-1&#x27;)">▶</button>', html)
        self.assertIn('<button class="project-nav-button segment-nav-button" type="button" title="Vorhergehendes Segment" onclick="selectStoryboardTemplate(&#x27;segment-inspector-template-segments-0&#x27;)">◀</button>', html)
        self.assertIn('<span class="project-nav-button project-nav-disabled" title="Kein nachfolgendes Segment">▶</span>', html)
        self.assertIn('class="storyboard-progress-strip"', html)
        self.assertIn('<span class="progress-step progress-step-done">Prompt</span>', html)
        self.assertIn('<span class="progress-step progress-step-done">Image</span>', html)
        self.assertIn('<span class="progress-step progress-step-done">Avatar</span>', html)
        self.assertIn('<span class="progress-step progress-step-done">Clip</span>', html)
        self.assertNotIn('<span class="progress-step progress-step-done">OK</span>', html)
        self.assertIn('<span class="storyboard-ok-badge" aria-label="Finished">&#10003;</span>', html)
        self.assertIn("function selectStoryboardItem", html)
        self.assertIn("function selectStoryboardTemplate", html)
        self.assertIn("storyboard-card-active", html)

    def test_segment_inspector_shows_quick_generation_actions_when_prompts_exist(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segment = {
            "segment_index": 3,
            "kind": "lyrics",
            "section": "Verse",
            "is_chorus": 0,
            "clean_text": "Prompted segment",
            "start_sec": None,
            "end_sec": None,
            "prompt": "image prompt",
            "video_prompt": "video prompt",
            "image_path": None,
            "avatar_image_path": None,
            "clip_path": None,
            "last_action": "prompts",
            "video_approved": 0,
            "status": "done",
            "error": "",
        }

        html = _segment_inspector_html(project, "segments", segment)

        self.assertIn('class="inspector-generation-actions"', html)
        self.assertIn('action="/projects/7/images"', html)
        self.assertIn('<input type="hidden" name="selected_lines" value="3">', html)
        self.assertIn("<button>Gen Image</button>", html)
        self.assertIn('action="/projects/7/avatar-image"', html)
        self.assertIn("<button>Gen Avatar</button>", html)
        self.assertIn('action="/projects/7/clips"', html)
        self.assertIn("<button>Gen Clip</button>", html)

    def test_segment_inspector_uses_compact_prompt_lightboxes_and_hides_noise(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segment = {
            "segment_index": 3,
            "kind": "lyrics",
            "section": "Verse",
            "is_chorus": 0,
            "clean_text": "Prompted segment",
            "start_sec": None,
            "end_sec": None,
            "prompt": "image prompt",
            "video_prompt": "video prompt",
            "image_path": "outputs/project-7/images/segment-003.png",
            "avatar_image_path": "outputs/project-7/images/avatar-segment-003.png",
            "clip_path": "outputs/project-7/clips/segment-003.mp4",
            "last_action": "clips",
            "video_approved": 0,
            "status": "done",
            "error": "boom",
        }

        html = _segment_inspector_html(project, "segments", segment)

        self.assertIn('class="inspector-prompt-preview"', html)
        self.assertIn('class="inspector-prompt-media-grid"', html)
        self.assertIn('class="inspector-prompt-media inspector-prompt-media-image"', html)
        self.assertIn('class="inspector-prompt-media inspector-prompt-media-avatar"', html)
        self.assertNotIn("inspector-prompt-media-wide", html)
        self.assertIn('src="/assets/outputs/project-7/images/segment-003.png', html)
        self.assertIn('src="/assets/outputs/project-7/images/avatar-segment-003.png', html)
        self.assertIn("<span>Image</span>", html)
        self.assertIn("<span>Avatar</span>", html)
        self.assertNotIn("Show image", html)
        self.assertIn("Edit image prompt", html)
        self.assertIn("Edit video prompt", html)
        self.assertIn('onclick="openImageLightbox(&#x27;/assets/outputs/project-7/images/segment-003.png&#x27;)"', html)
        self.assertIn('onclick="openImageLightbox(&#x27;/assets/outputs/project-7/images/avatar-segment-003.png&#x27;)"', html)
        self.assertIn('id="image-prompt-modal-segments-3"', html)
        self.assertIn('id="video-prompt-modal-segments-3"', html)
        self.assertIn('onclick="openPromptModal(&#x27;image-prompt-modal-segments-3&#x27;)"', html)
        self.assertIn('onclick="openPromptModal(&#x27;video-prompt-modal-segments-3&#x27;)"', html)
        self.assertIn('onclick="if (event.target === this) closePromptModal(&#x27;image-prompt-modal-segments-3&#x27;)"', html)
        self.assertIn('onclick="if (event.target === this) closePromptModal(&#x27;video-prompt-modal-segments-3&#x27;)"', html)
        self.assertIn('action="/projects/7/segments/3/prompts/image/save"', html)
        self.assertIn('name="prompt"', html)
        self.assertIn('action="/projects/7/segments/3/prompts/video/save"', html)
        self.assertIn('name="video_prompt"', html)
        self.assertNotIn("<div class=\"segment-inspector-label\">Redo</div>", html)
        self.assertNotIn("<div class=\"segment-inspector-label\">Status</div>", html)
        self.assertNotIn('action="/projects/7/segments/3/redo"', html)

    def test_segment_inspector_places_actions_directly_below_navigation(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segment = {
            "segment_index": 3,
            "kind": "lyrics",
            "section": "Verse",
            "is_chorus": 0,
            "clean_text": "Prompted segment",
            "start_sec": None,
            "end_sec": None,
            "prompt": "image prompt",
            "video_prompt": "video prompt",
            "image_path": "outputs/project-7/images/segment-003.png",
            "avatar_image_path": "outputs/project-7/images/avatar-segment-003.png",
            "clip_path": None,
            "last_action": "clips",
            "video_approved": 0,
            "status": "done",
            "error": "",
        }

        html = _segment_inspector_html(project, "segments", segment)

        self.assertLess(html.index("Gen Image"), html.index("Image source"))
        self.assertLess(html.index("Mark as finished"), html.index("Image source"))
        self.assertLess(html.index("Image source"), html.index("Preview"))
        self.assertLess(html.index("Preview"), html.index("Prompts"))
        self.assertNotIn("Next renders", html)
        self.assertIn('class="compact-form image-choice image-choice-inline"', html)
        self.assertIn('class="finish-toggle finish-toggle-inactive"', html)
        self.assertIn("Mark as finished", html)

    def test_segment_inspector_css_keeps_actions_and_media_balanced(self):
        html = _page("Demo", "")

        self.assertIn(".inspector-prompt-media-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));", html)
        self.assertIn(".inspector-prompt-actions { display: flex; justify-content: space-between;", html)
        self.assertIn(".segment-inspector-header-actions { display: grid; gap: 8px;", html)
        self.assertIn(".inspector-generation-actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px;", html)
        self.assertIn(".inspector-generation-actions .compact-form { min-width: 0; width: auto;", html)
        self.assertIn(".inspector-generation-actions button { width: 100%; min-height: 42px;", html)
        self.assertIn(".finish-toggle { display: flex; width: 100%;", html)
        self.assertIn(".storyboard-card { position: relative; display: grid; grid-template-rows: auto 1fr; min-width: 0; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-card); color: var(--text-primary);", html)
        self.assertIn(".storyboard-card-approved { background: linear-gradient(180deg, rgba(69,201,141,.075), rgba(69,201,141,.025)), var(--bg-card); border-color: rgba(69,201,141,.58);", html)
        self.assertIn(".storyboard-card-unfinished { background: linear-gradient(180deg, rgba(233,72,159,.07), rgba(233,72,159,.025)), var(--bg-card); border-color: rgba(233,72,159,.58);", html)
        self.assertIn(".storyboard-card-approved:hover, .storyboard-card-approved:focus { border-color: rgba(69,201,141,.72); box-shadow: 0 0 0 3px rgba(69,201,141,.14);", html)
        self.assertIn(".storyboard-card-unfinished:hover, .storyboard-card-unfinished:focus { border-color: rgba(233,72,159,.72); box-shadow: 0 0 0 3px rgba(233,72,159,.14);", html)
        self.assertIn(".storyboard-card-locked { cursor: not-allowed; background: linear-gradient(180deg, rgba(69,201,141,.075), rgba(69,201,141,.025)), var(--bg-card);", html)
        self.assertIn(".storyboard-card-locked > .storyboard-select-wrap, .storyboard-card-locked > .storyboard-card-body { pointer-events: none; opacity: .58;", html)
        self.assertIn(".storyboard-card-locked > .storyboard-card-media { pointer-events: none;", html)
        self.assertIn(".storyboard-lock-overlay { position: absolute; inset: 0; z-index: 20;", html)
        self.assertIn("background: rgba(11,16,18,.34);", html)
        self.assertNotIn("filter: grayscale(1)", html)
        self.assertNotIn("backdrop-filter: grayscale(1)", html)
        self.assertIn("@keyframes storyboardActiveRing", html)
        self.assertIn("--storyboard-ring-angle: 0deg;", html)
        self.assertIn("to { --storyboard-ring-angle: 360deg;", html)
        self.assertIn(".storyboard-card-active::before { --storyboard-ring-angle: 0deg; content: \"\";", html)
        self.assertIn(".storyboard-card-active:hover, .storyboard-card-active:focus { border-color: transparent;", html)
        self.assertIn("background: conic-gradient(from var(--storyboard-ring-angle), var(--studio-accent) 0 23%, transparent 23% 27%, var(--studio-pink) 27% 50%, transparent 50% 54%, var(--studio-accent) 54% 77%, transparent 77% 81%, var(--studio-pink) 81% 100%);", html)
        self.assertIn("animation: storyboardActiveRing 2.2s linear infinite;", html)
        self.assertNotIn("storyboardActiveRing { to { transform: rotate", html)
        self.assertIn(".storyboard-card-body { display: grid; grid-template-rows: auto auto 1fr;", html)
        self.assertNotIn(".storyboard-card-status", html)
        self.assertIn(".storyboard-select-wrap { position: absolute; top: 8px; left: 8px;", html)
        self.assertIn("width: 32px; height: 32px; margin: 0;", html)
        self.assertIn("background: rgba(12,18,21,.88);", html)
        self.assertIn(".storyboard-select-wrap:has(.storyboard-select:checked) { background: var(--action);", html)
        self.assertIn(".storyboard-select { width: 18px; height: 18px;", html)
        self.assertIn(".storyboard-video-expand { position: absolute; right: 8px; bottom: 8px;", html)
        self.assertIn(".modal-content { position: relative; width: min(560px, 94vw); max-height: 88vh; overflow: visible; border: 1px solid #344149; border-radius: var(--radius-lg); background: var(--bg-panel); color: var(--text-primary);", html)
        self.assertIn(".modal-content > form { max-height: calc(88vh - 74px); overflow: auto;", html)
        self.assertIn(".lightbox { position: fixed; inset: 0; z-index: 120;", html)
        self.assertIn(".lightbox-close { position: absolute;", html)
        self.assertIn("background: #29343a;", html)
        self.assertIn(".lightbox-close:hover, .lightbox-close:focus { background: var(--accent);", html)
        self.assertIn(".storyboard-ok-badge { position: absolute;", html)
        self.assertIn("width: 32px; height: 32px;", html)
        self.assertIn(".finish-toggle-check { margin-left: auto; font-size: 23px;", html)
        self.assertIn("pointer-events: none;", html)
        self.assertIn(".segment-inspector { position: sticky; z-index: 70;", html)
        self.assertIn(".segment-inspector-resize-handle { position: absolute; inset: 0 auto 0 0;", html)
        self.assertIn(".storyboard-workspace-resizing .segment-inspector-resize-handle::after", html)
        self.assertIn("background: var(--bg-panel); color: var(--text-primary);", html)
        self.assertIn(".prompt-modal.lightbox { z-index: 120;", html)
        self.assertIn(".image-prompt-modal-content .prompt-textarea { min-height: 144px;", html)
        self.assertIn(".project-settings-body { max-height: calc(88vh - 74px); overflow: auto;", html)
        self.assertIn(".project-settings-body > form { max-height: none; overflow: visible;", html)
        self.assertIn(".settings-realign-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px;", html)
        self.assertIn(".settings-save-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--border-subtle);", html)
        self.assertIn(".manual-audio-bar { position: sticky; top: 0; z-index: 3; display: grid; grid-template-columns: minmax(0, 1fr) auto auto;", html)
        self.assertIn(".manual-time-input.manual-time-filled { border-color: var(--action); box-shadow: 0 0 0 3px var(--action-soft);", html)
        self.assertIn(".segment-inspector-nav { display: grid; grid-template-columns: 32px minmax(0, 1fr) 32px;", html)
        self.assertIn(".segment-inspector-title { color: var(--text-primary); font-size: 24px;", html)
        self.assertIn(".segment-nav-button { border: 0;", html)
        self.assertIn("scrollbar-color: #536168 #182126;", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)

    def test_project_polling_does_not_replace_storyboard_while_prompt_modal_is_open(self):
        html = _page("Demo", "body")

        self.assertIn("function projectStoryboardHasOpenPromptModal(storyboard)", html)
        self.assertIn("storyboard.querySelector('.prompt-modal.open')", html)
        self.assertIn("!projectStoryboardHasOpenPromptModal(storyboard)", html)

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

        self.assertIn('<h3 class="segment-inspector-title"># 04</h3>', html)
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
                "image_path": "VocaVid/project-7/line-000.png",
                "avatar_image_path": None,
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('src="http://example.test/&quot;quoted&quot;/view?filename=line-000.png&amp;subfolder=VocaVid%2Fproject-7&amp;type=output"', html)
        self.assertIn('onclick="openImageLightbox(&quot;http://example.test/\\&quot;quoted\\&quot;/view?filename=line-000.png&amp;subfolder=VocaVid%2Fproject-7&amp;type=output&quot;)"', html)
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
                "image_path": "VocaVid/project-7/line-000.png",
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
                "clip_path": "VocaVid/project-7/clip-001.mp4",
                "status": "done",
                "error": "",
            },
        ]

        html = _project_html(project, lines)
        image_onclick = html.split('onclick="openImageLightbox(', 1)[1].split(')"', 1)[0]
        clip_src = html.split('<video class="storyboard-card-video"', 1)[1].split('src="', 1)[1].split('"', 1)[0]

        self.assertNotIn("\n", image_onclick)
        self.assertNotIn("\n", clip_src)
        self.assertNotIn("\x01", image_onclick)
        self.assertNotIn("\x01", clip_src)
        self.assertIn(r"\ncontrol\u0001/view?filename=line-000.png", unescape(image_onclick))
        self.assertIn(r"\ncontrol\u0001/view?filename=clip-001.mp4", unescape(clip_src))
        self.assertIn(r"http://example.test/'quoted", unescape(image_onclick))
        self.assertIn(r"http://example.test/'quoted", unescape(clip_src))

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

        self.assertIn("VocaVid-scroll:", html)
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
            "avatar_gender": "female",
            "avatar_face_description": "sharp jawline, short black hair",
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
                "clip_path": "VocaVid/project-1/clip-000.mp4",
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
        self.assertIn('action="/projects/7/avatar-description"', html)
        self.assertIn('<label>Male / Female Avatar</label><select name="avatar_gender">', html)
        self.assertIn('<option value="female" selected>Female</option>', html)
        self.assertIn('<label>Avatar face description</label><textarea name="avatar_face_description">sharp jawline, short black hair</textarea>', html)
        self.assertIn('AI describe avatar</button>', html)
        self.assertIn('action="/projects/7/align"', html)
        self.assertIn('<button>1. Analyze + Split</button>', html)
        self.assertNotIn('<button>2. Segs + Audio</button>', html)
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

        self.assertIn('name="scene_plan" form="scene-plan-form-7"', html)
        self.assertNotIn("<h2>Scene Plan</h2>", html)
        self.assertNotIn('<th class="scene-plan-column">Scene Plan</th>', html)
        self.assertNotIn("A long scene plan that should wrap in a narrow column", html)

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
        self.assertIn('class="storyboard-card storyboard-card-active storyboard-card-locked"', html)
        self.assertNotIn('storyboard-card-unfinished storyboard-card-locked', html)
        self.assertIn('data-locked="1"', html)
        self.assertIn('class="segment-select storyboard-select" name="selected_lines" value="0" aria-label="Segment markieren" disabled', html)
        self.assertIn('<div class="storyboard-lock-overlay"><span>running</span></div>', html)
        self.assertIn('class="segment-inspector segment-inspector-locked"', html)
        self.assertIn('class="segment-inspector-lockable" inert', html)
        self.assertIn('<div class="segment-inspector-lock-overlay"><span>running</span></div>', html)
        self.assertIn("card.dataset.locked === '1'", html)
        self.assertIn("'.segment-select:checked:not(:disabled)'", html)
        self.assertIn("pollProjectStatus(7)", html)
        self.assertIn("fetch('/projects/' + projectId + '/status')", html)
        self.assertIn("function replaceProjectRow", html)
        self.assertIn("replacementCheckbox.checked = checkbox.checked", html)
        self.assertIn("replaceProjectRow(row, html)", html)

    def test_storyboard_card_does_not_lock_from_stale_row_status_without_active_job(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Running line",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": "outputs/project-7/images/line-000.png",
                "clip_path": None,
                "audio_path": None,
                "status": "running",
                "error": "",
            }
        ]

        html = _project_html(project, lines)

        self.assertIn('class="storyboard-card storyboard-card-active storyboard-card-unfinished"', html)
        self.assertIn('data-locked="0"', html)
        self.assertIn('class="line-select storyboard-select" name="selected_lines" value="0" aria-label="Zeile markieren"', html)
        self.assertNotIn('storyboard-card-locked', html)
        self.assertNotIn('storyboard-lock-overlay', html)

    def test_project_status_polling_skips_unchanged_rows(self):
        html = _page("Demo", "")

        self.assertIn("const projectRowServerHtml = new Map()", html)
        self.assertIn("function rememberProjectRows", html)
        self.assertIn("function projectRowChanged", html)
        self.assertIn("projectRowServerHtml.get(row.id) || row.outerHTML", html)
        self.assertIn("return previousHtml !== replacement.outerHTML", html)
        self.assertIn("if (!projectRowChanged(row, replacement)) return", html)
        self.assertIn("projectRowServerHtml.set(replacement.id, replacement.outerHTML)", html)
        self.assertIn("const actions = document.querySelector('.project-topbar .actions')", html)
        self.assertIn("actions.innerHTML = data.actions_html", html)

    def test_project_status_payload_includes_storyboard_and_segment_rows_for_polling(self):
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

        self.assertIn("actions_html", payload)
        self.assertIn('disabled title="Finish all clips first">8. Assemble &amp; Render MP4', payload["actions_html"])
        self.assertIn("finalize_items_html", payload)
        self.assertIn("storyboard_html", payload)
        self.assertIn('id="project-storyboard"', payload["storyboard_html"])
        self.assertIn("Fresh storyboard text", payload["storyboard_html"])
        self.assertNotIn("storyboard-card-status", payload["storyboard_html"])
        self.assertIn("storyboard-card-unfinished", payload["storyboard_html"])
        self.assertIn('class="segment-inspector"', payload["storyboard_html"])
        self.assertIn('action="/projects/7/segments/0/approval"', payload["storyboard_html"])
        self.assertIn("rows", payload)
        self.assertIn("segment-row-0", payload["rows"])
        self.assertIn('id="segment-row-0"', payload["rows"]["segment-row-0"])
        self.assertIn("Fresh storyboard text", payload["rows"]["segment-row-0"])
        self.assertIn('action="/projects/7/segments/0/timing"', payload["rows"]["segment-row-0"])
        self.assertIn('<div class="status">done</div>', payload["rows"]["segment-row-0"])
        self.assertNotIn('id="project-storyboard"', payload["rows"]["segment-row-0"])

    def test_project_status_payload_updates_render_button_to_preview_existing_mp4(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "outputs/demo/Demo.kdenlive"}
        finished = app_module.APP_ROOT / "outputs" / "demo" / "Demo.mp4"
        finished.parent.mkdir(parents=True, exist_ok=True)
        try:
            finished.write_bytes(b"mp4")
            segments = [
                {
                    "segment_index": 0,
                    "kind": "lyrics",
                    "section": "Verse",
                    "is_chorus": 0,
                    "clean_text": "Done",
                    "start_sec": 1.0,
                    "end_sec": 2.0,
                    "prompt": None,
                    "image_path": None,
                    "clip_path": "clip.mp4",
                    "audio_path": None,
                    "scene_plan": "",
                    "video_approved": 1,
                    "status": "done",
                    "error": "",
                }
            ]

            payload = _project_status_payload(project, [], segments, active_jobs=[], used_actions={"render-mp4"})

            self.assertIn('type="button" title="Preview rendered MP4"', payload["actions_html"])
            self.assertIn("openClipLightbox(&#x27;/assets/outputs/demo/Demo.mp4", payload["actions_html"])
            self.assertNotIn('action="/projects/7/render-mp4"', payload["actions_html"])
        finally:
            if finished.exists():
                finished.unlink()

    def test_project_status_payload_locks_storyboard_cards_for_queued_jobs(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Running line",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "status": "running",
                "error": "",
            },
            {
                "line_index": 1,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Queued line",
                "start_sec": None,
                "end_sec": None,
                "confidence": None,
                "prompt": None,
                "image_path": None,
                "clip_path": None,
                "audio_path": None,
                "status": "pending",
                "error": "",
            },
        ]
        active_jobs = [
            Job(1, "avatar line 1", "running", "now", project_id=7, item_kind="lines", selected_indices=[0]),
            Job(2, "avatar line 2", "queued", "now", project_id=7, item_kind="lines", selected_indices=[1]),
        ]

        payload = _project_status_payload(project, lines, [], active_jobs=active_jobs)

        self.assertEqual(payload["locked"], {"segments": [], "lines": [0, 1]})
        self.assertEqual(payload["storyboard_html"].count("storyboard-card-locked"), 2)
        self.assertNotIn("storyboard-card-unfinished", payload["storyboard_html"])
        self.assertIn('<div class="storyboard-lock-overlay"><span>running</span></div>', payload["storyboard_html"])
        self.assertIn('<div class="storyboard-lock-overlay"><span>queued</span></div>', payload["storyboard_html"])
        self.assertEqual(payload["storyboard_html"].count("segment-inspector-locked"), 3)
        self.assertIn('<div class="segment-inspector-lock-overlay"><span>running</span></div>', payload["storyboard_html"])
        self.assertIn('<div class="segment-inspector-lock-overlay"><span>queued</span></div>', payload["storyboard_html"])
        self.assertEqual(payload["storyboard_html"].count('disabled>'), 2)

    def test_project_status_payload_includes_line_rows_when_storyboard_exists(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 2,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Fresh line text",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "confidence": None,
                "prompt": "image prompt",
                "video_prompt": "video prompt",
                "image_path": None,
                "clip_path": None,
                "video_approved": 0,
                "status": "done",
                "error": "",
            }
        ]

        payload = _project_status_payload(project, lines, [], active_jobs=[])

        self.assertIn("storyboard_html", payload)
        self.assertIn('id="project-storyboard"', payload["storyboard_html"])
        self.assertIn("Fresh line text", payload["storyboard_html"])
        self.assertIn("rows", payload)
        self.assertEqual(set(payload["rows"]), {"line-row-2"})
        self.assertIn('id="line-row-2"', payload["rows"]["line-row-2"])
        self.assertIn("Fresh line text", payload["rows"]["line-row-2"])
        self.assertIn('action="/projects/7/lines/2/timing"', payload["rows"]["line-row-2"])
        self.assertIn('action="/projects/7/lines/2/insert-after"', payload["rows"]["line-row-2"])
        self.assertIn('<div class="status">done</div>', payload["rows"]["line-row-2"])
        self.assertNotIn('id="project-storyboard"', payload["rows"]["line-row-2"])

    def test_project_status_polling_replaces_visible_storyboard(self):
        html = _page("Demo", "")

        self.assertIn("function replaceProjectStoryboard", html)
        self.assertIn("data.storyboard_html", html)
        self.assertIn("const storyboard = document.getElementById('project-storyboard')", html)
        self.assertIn("let projectStoryboardServerHtml = ''", html)
        self.assertIn("function rememberProjectStoryboard", html)
        self.assertIn("function projectStoryboardChanged", html)
        self.assertIn("if (!projectStoryboardChanged(storyboard, replacement)) return", html)
        self.assertIn("const replacementHtml = replacement.outerHTML", html)
        self.assertIn("projectStoryboardServerHtml = replacementHtml", html)
        self.assertIn("function storyboardCanPatchInPlace(storyboard, replacement)", html)
        self.assertIn("patchChangedStoryboardCards(storyboard, replacement)", html)
        self.assertIn("function storyboardMediaEquivalent(currentMedia, replacementMedia)", html)
        self.assertIn("selector === '.storyboard-card-media' && storyboardMediaEquivalent(currentChild, replacementChild)", html)
        self.assertIn("replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-card-media')", html)
        self.assertIn("replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-lock-overlay')", html)
        self.assertIn("replacement.hidden = storyboard.hidden", html)
        self.assertIn("storyboard.replaceWith(replacement)", html)
        self.assertLess(html.index("if (storyboardCanPatchInPlace(storyboard, replacement))"), html.index("storyboard.replaceWith(replacement)"))
        self.assertLess(html.index("if (!projectStoryboardChanged(storyboard, replacement)) return"), html.index("storyboard.replaceWith(replacement)"))

    def test_project_status_polling_skips_storyboard_when_editor_is_active_or_dirty(self):
        html = _page("Demo", "")

        self.assertIn("const projectStoryboardFieldSelector = 'input:not(.storyboard-select), textarea, select'", html)
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
        self.assertIn("if (!force && !shouldReplaceProjectStoryboard(storyboard)) return", html)
        self.assertLess(html.index("if (!force && !shouldReplaceProjectStoryboard(storyboard)) return"), html.index("storyboard.replaceWith(replacement)"))

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
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]

        self.assertIn("<h2>Render Segments</h2>", table_html)
        self.assertIn("Segment row", table_html)
        self.assertNotIn("Old lyric row", table_html)
        self.assertIn('<input type="checkbox" class="segment-select" name="selected_lines" value="0">', table_html)
        self.assertNotIn('class="line-select"', table_html)
        self.assertNotIn("<th>Lyrics</th>", table_html)

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
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]

        self.assertIn('class="section-verse"', html)
        self.assertIn('class="section-chorus"', html)
        self.assertIn("1.0 - 2.1", html)
        self.assertIn("2.1 - 5.4", html)
        self.assertNotIn("<th>#</th>", table_html)
        self.assertNotIn("<th>Section</th>", table_html)
        self.assertNotIn("<th>Chorus</th>", table_html)
        self.assertIn('<span class="legend-swatch section-verse"></span>Verse', html)
        self.assertIn('<span class="legend-swatch section-chorus"></span>Refrain', html)

    def test_pre_chorus_is_not_displayed_as_refrain_without_chorus_flag(self):
        self.assertEqual(_section_type("Pre-Chorus", False), "gap")
        self.assertEqual(_section_type("Chorus 2", False), "refrain")
        self.assertEqual(_section_type("Refrain:", False), "refrain")

    def test_page_includes_clip_lightbox_player(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, []))

        self.assertIn('id="clip-lightbox"', html)
        self.assertIn('id="clip-lightbox-video"', html)
        self.assertIn('class="lightbox-close" type="button" aria-label="Close window"', html)
        self.assertIn(">X</button>", html)
        self.assertIn("function openClipLightbox", html)
        self.assertIn("function closeClipLightbox", html)

    def test_finalize_review_renders_clips_progress_actions_and_shortcuts(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "First line",
                "start_sec": 0.0,
                "end_sec": 2.0,
                "clip_path": "clips/segment-000.mp4",
                "audio_path": None,
                "image_path": None,
                "avatar_image_path": None,
                "prompt": "wide cinematic frame",
                "video_prompt": "slow camera move",
                "video_approved": 1,
                "status": "done",
                "error": "",
            },
            {
                "segment_index": 1,
                "kind": "lyrics",
                "section": "Chorus",
                "is_chorus": 1,
                "clean_text": "Sing it again",
                "start_sec": 2.0,
                "end_sec": 4.0,
                "clip_path": "clips/segment-001.mp4",
                "audio_path": None,
                "image_path": None,
                "avatar_image_path": None,
                "prompt": "bright stage",
                "video_prompt": "energetic performance",
                "video_approved": 0,
                "status": "done",
                "error": "",
            },
        ]

        html = _page("Demo", _project_html(project, [], segments))

        self.assertIn('onclick="openFinalizeModal()">7. Finalize</button>', html)
        self.assertIn('id="finalize-modal"', html)
        self.assertIn('aria-label="Close finalize review" onclick="closeFinalizeModal()"', html)
        self.assertIn('data-position="2" data-total="2"', html)
        self.assertIn('data-title="Chorus', html)
        self.assertIn('data-approved="1"', html)
        self.assertIn('data-approved="0"', html)
        self.assertIn('<kbd>1</kbd><span>Generate Clip</span>', html)
        self.assertIn('<kbd>2</kbd><span>Generate Avatar</span>', html)
        self.assertIn('<kbd>3</kbd><span>Generate Image</span>', html)
        self.assertIn('<kbd>4</kbd><span>Edit Image Prompt</span>', html)
        self.assertIn('<kbd>5</kbd><span>Edit Video Prompt</span>', html)
        self.assertIn("finalizeCountdownValue = 3", html)
        self.assertIn("event.key === ' ' || event.key === 'Enter'", html)
        self.assertIn("formData.append('video_approved', '1')", html)
        self.assertIn("function queueFinalizeAction", html)
        self.assertIn("function submitFinalizePrompt", html)
        self.assertIn(".lightbox.finalize-modal { z-index: 210;", html)

    def test_render_mp4_button_previews_existing_named_video(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "outputs/demo/final.kdenlive"}
        finished = app_module.APP_ROOT / "outputs" / "demo" / "Demo.mp4"
        finished.parent.mkdir(parents=True, exist_ok=True)
        try:
            finished.write_bytes(b"mp4")
            segments = [
                {
                    "segment_index": 0,
                    "kind": "lyrics",
                    "section": "Verse",
                    "is_chorus": 0,
                    "clean_text": "Hello",
                    "start_sec": 0.0,
                    "end_sec": 3.0,
                    "prompt": None,
                    "image_path": None,
                    "clip_path": "clip.mp4",
                    "audio_path": None,
                    "scene_plan": "",
                    "video_approved": 1,
                    "status": "done",
                    "error": "",
                }
            ]

            html = _project_html(project, [], segments)

            self.assertIn('type="button" title="Preview rendered MP4"', html)
            self.assertIn("8. Assemble &amp; Render MP4", html)
            self.assertIn("openClipLightbox(&#x27;/assets/outputs/demo/Demo.mp4", html)
            self.assertNotIn('action="/projects/7/render-mp4"', html)
        finally:
            if finished.exists():
                finished.unlink()

    def test_render_mp4_button_previews_legacy_finished_video(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "outputs/demo/final.kdenlive"}
        finished = app_module.APP_ROOT / "outputs" / "demo" / "finished.mp4"
        finished.parent.mkdir(parents=True, exist_ok=True)
        try:
            finished.write_bytes(b"mp4")
            segments = [
                {
                    "segment_index": 0,
                    "kind": "lyrics",
                    "section": "Verse",
                    "is_chorus": 0,
                    "clean_text": "Hello",
                    "start_sec": 0.0,
                    "end_sec": 3.0,
                    "prompt": None,
                    "image_path": None,
                    "clip_path": "clip.mp4",
                    "audio_path": None,
                    "scene_plan": "",
                    "video_approved": 1,
                    "status": "done",
                    "error": "",
                }
            ]

            html = _project_html(project, [], segments)

            self.assertIn("openClipLightbox(&#x27;/assets/outputs/demo/finished.mp4", html)
            self.assertNotIn('action="/projects/7/render-mp4"', html)
        finally:
            if finished.exists():
                finished.unlink()

    def test_render_mp4_button_previews_legacy_final_video(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "outputs/demo/final.kdenlive"}
        finished = app_module.APP_ROOT / "outputs" / "demo" / "final.mp4"
        finished.parent.mkdir(parents=True, exist_ok=True)
        try:
            finished.write_bytes(b"mp4")
            segments = [
                {
                    "segment_index": 0,
                    "kind": "lyrics",
                    "section": "Verse",
                    "is_chorus": 0,
                    "clean_text": "Hello",
                    "start_sec": 0.0,
                    "end_sec": 3.0,
                    "prompt": None,
                    "image_path": None,
                    "clip_path": "clip.mp4",
                    "audio_path": None,
                    "scene_plan": "",
                    "video_approved": 1,
                    "status": "done",
                    "error": "",
                }
            ]

            html = _project_html(project, [], segments)

            self.assertIn("openClipLightbox(&#x27;/assets/outputs/demo/final.mp4", html)
            self.assertNotIn('action="/projects/7/render-mp4"', html)
        finally:
            if finished.exists():
                finished.unlink()

    def test_analyze_split_is_single_top_action_before_generation(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, []))

        align_index = html.index('<button>1. Analyze + Split</button>')
        scene_plan_index = html.index('<button>2. Scene Plan</button>')
        prompts_index = html.index('<button>3. Gen Prompts</button>')
        images_index = html.index('<button>4. Gen Images</button>')
        avatar_index = html.index('<button>5. Gen Avatar Images</button>')
        clips_index = html.index('<button>6. Gen Clips</button>')
        finalize_index = html.index('7. Finalize')
        render_index = html.index('8. Assemble &amp; Render MP4')
        settings_index = html.index('action="/projects/7/settings"')
        self.assertNotIn('<button>2. Segs + Audio</button>', html)
        self.assertNotIn("Gen Image Prompts", html)
        self.assertNotIn("Gen Video Prompts", html)
        self.assertNotIn('action="/projects/7/segments"', html[:settings_index])
        self.assertLess(align_index, scene_plan_index)
        self.assertLess(scene_plan_index, prompts_index)
        self.assertLess(prompts_index, images_index)
        self.assertLess(images_index, avatar_index)
        self.assertLess(avatar_index, clips_index)
        self.assertLess(clips_index, finalize_index)
        self.assertLess(finalize_index, render_index)
        self.assertLess(align_index, settings_index)

    def test_used_top_actions_are_numbered_and_dark_grey_but_clickable(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _project_html(project, [], used_actions={"align", "prompts", "video-prompts"})

        self.assertIn('<button class="used-button" title="Already used; click to run again">1. Analyze + Split</button>', html)
        self.assertIn('<button class="used-button" title="Already used; click to run again">3. Gen Prompts</button>', html)
        self.assertIn('action="/projects/7/align"', html)
        self.assertIn('action="/projects/7/generate-prompts"', html)

    def test_assemble_render_requires_all_clips_to_be_finished(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [{
            "line_index": 0,
            "section": "Verse",
            "is_chorus": 0,
            "clean_text": "Hello",
            "start_sec": 0.0,
            "end_sec": 2.0,
            "confidence": 1.0,
            "prompt": "portrait",
            "video_prompt": "camera move",
            "image_path": None,
            "avatar_image_path": None,
            "clip_path": "clip.mp4",
            "audio_path": None,
            "video_approved": 0,
            "status": "done",
            "error": "",
        }]

        html = _project_html(project, lines, used_actions={"clips"})

        self.assertIn('disabled title="Finish all clips first">8. Assemble &amp; Render MP4', html)
        self.assertNotIn('action="/projects/7/assemble-render"', html)

        lines[0]["video_approved"] = 1
        approved_html = _project_html(project, lines, used_actions={"clips"})

        self.assertIn('action="/projects/7/assemble-render"', approved_html)

    def test_project_settings_are_visible_by_default_without_group_size_reset_warning(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _page("Demo", _project_html(project, []))

        self.assertNotIn("<details>", html)
        self.assertNotIn("<summary>Project Settings</summary>", html)
        self.assertIn('id="project-settings-modal"', html)
        self.assertNotIn('id="scene-plan-modal"', html)
        self.assertIn('class="project-icon-button" type="button" title="Project Settings" onclick="openProjectSettingsModal()"', html)
        self.assertNotIn('title="Scene Plan" onclick="openScenePlanModal()"', html)
        self.assertIn("function openProjectSettingsModal", html)
        self.assertNotIn("function openScenePlanModal", html)
        self.assertIn("<h2>Project Settings</h2>", html)
        self.assertEqual(html.count("<h2>Project Settings</h2>"), 1)
        self.assertIn('data-original-lyric-group-size="2"', html)
        self.assertIn('data-original-chorus-group-size="1"', html)
        self.assertIn("confirmProjectSettingsSave(this)", html)
        self.assertNotIn("Projekt leeren und Segmente neu erstellen?", html)
        self.assertIn("Lyrics per GeForce GPU neu alignen und Segmente neu erstellen?", html)
        self.assertIn("Lyrics per CPU neu alignen und Segmente neu erstellen?", html)
        self.assertIn("Realign Lyrics (manually)", html)
        self.assertIn('class="hidden-action-form" id="global-style-prompt-form-7"', html)
        self.assertIn('class="hidden-action-form" id="scene-plan-form-7"', html)
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

        self.assertNotIn("<h2>Scene Plan</h2>", html)
        self.assertIn('action="/projects/7/scene-plan/save"', html)
        self.assertIn('name="scene_plan" form="scene-plan-form-7"', html)
        self.assertIn("0: Neon intro", html)
        self.assertIn("1: Close chorus", html)
        self.assertIn('<button type="submit" form="scene-plan-form-7">Save Scene Plan</button>', html)
        self.assertLess(html.index('id="project-storyboard"'), html.index("<h2>Project Settings</h2>"))
        self.assertLess(html.index("<h2>Lyrics / Timing</h2>"), html.index("<h2>Project Settings</h2>"))
        self.assertLess(html.index('name="global_style_prompt"'), html.index('name="scene_plan" form="scene-plan-form-7"'))
        self.assertLess(html.index('name="scene_plan" form="scene-plan-form-7"'), html.index('name="genre"'))

    def test_project_page_has_sticky_header_and_no_audio_final_info_panel(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": "final.mp4"}

        html = _page("Demo", _project_html(project, [], queue_estimate_seconds=70.0, queue_count=4), queue_count=4)

        self.assertIn("<title>(4) Demo</title>", html)
        self.assertIn('class="project-topbar"', html)
        self.assertIn('class="project-title-row"', html)
        self.assertIn('id="queue-estimate"', html)
        self.assertIn('data-seconds="70"', html)
        self.assertIn('data-count="4"', html)
        self.assertIn(">4 ~1m 10s</button>", html)
        self.assertIn('id="queue-modal"', html)
        self.assertIn('class="modal lightbox queue-modal"', html)
        self.assertIn('class="queue-modal-body"', html)
        self.assertGreater(html.index('id="queue-modal"'), html.index('class="actions"'))
        self.assertLess(html.index('id="queue-modal"'), html.index('id="project-storyboard"'))
        self.assertIn("openQueueModal()", html)
        self.assertIn("closeQueueModal()", html)
        self.assertIn("pollProjectStatus(7); pollJobsStatus();", html)
        self.assertNotIn('class="scroll-top-button"', html)
        self.assertNotIn('aria-label="Nach oben"', html)
        self.assertNotIn(">Top</button>", html)
        self.assertNotIn("function scrollToTop", html)
        self.assertIn(".project-topbar", html)
        self.assertIn("position: sticky", html)
        self.assertIn(".project-topbar { position: sticky; top: 0; z-index: 100;", html)
        self.assertIn(".project-storyboard { position: relative; z-index: 0;", html)
        self.assertIn("background: rgba(13,19,22,.96)", html)
        self.assertIn(".project-title-row h1 { color: var(--studio-text);", html)
        self.assertIn(".segment-inspector { position: sticky;", html)
        self.assertIn("top: 156px", html)
        self.assertNotIn("<strong>Audio:</strong>", html)
        self.assertNotIn("<strong>Final:</strong>", html)

    def test_project_settings_modal_has_danger_zone_with_confirmation(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}

        html = _project_html(project, [])
        settings_html = html[html.index('id="project-settings-modal"') : html.index("</div>\n  </div>\n</div>", html.index('id="project-settings-modal"'))]

        self.assertIn('<div class="project-settings-body">', settings_html)
        self.assertIn('<details class="danger-panel">', settings_html)
        self.assertIn("<summary>Danger Zone</summary>", settings_html)
        self.assertIn('action="/projects/7/clear"', settings_html)
        self.assertIn('action="/projects/7/delete"', settings_html)
        self.assertIn("return confirm('Projekt wirklich leeren?", settings_html)
        self.assertIn("return confirm('Projekt wirklich loeschen?", settings_html)
        self.assertIn('class="danger-button"', settings_html)
        self.assertIn(".danger-panel { margin-top: 24px;", _page("Demo", ""))
        self.assertIn(".danger-panel[open] { background: transparent;", _page("Demo", ""))
        self.assertIn(".danger-panel .compact-form { background: transparent;", _page("Demo", ""))
        self.assertIn(".danger-panel .actions { padding-top: 12px;", _page("Demo", ""))
        self.assertLess(settings_html.index("<button>Save Project Settings</button>"), settings_html.index("<summary>Danger Zone</summary>"))
        self.assertGreater(settings_html.index('action="/projects/7/clear"'), settings_html.index('name="whisper_model_size"'))
        self.assertGreater(settings_html.index('action="/projects/7/delete"'), settings_html.index('action="/projects/7/clear"'))

    def test_project_settings_groups_realign_buttons_above_save(self):
        project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
        lines = [
            {
                "line_index": 0,
                "section": "Verse",
                "is_chorus": 0,
                "clean_text": "Manual row",
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

        self.assertIn('class="settings-realign-actions"', html)
        self.assertIn('class="settings-save-actions"', html)
        self.assertIn('action="/projects/7/realign-lyrics"', html)
        self.assertIn('action="/projects/7/realign-lyrics-cpu"', html)
        self.assertIn("Realign Lyrics (GeForce GPU)", html)
        self.assertIn("Realign Lyrics (CPU)", html)
        self.assertIn("Realign Lyrics (manually)", html)
        self.assertIn('type="button" onclick="closeProjectSettingsModal(); openManualTimingModal()"', html)
        self.assertIn('id="manual-timing-modal"', html)
        self.assertIn('action="/projects/7/manual-timing"', html)
        self.assertIn('<output id="manual-timing-current">0.0</output>', html)
        self.assertIn('onclick="applyManualTimingTimestamp()"', html)
        self.assertIn('onclick="addManualInterlude(this, 0)"', html)
        self.assertIn('class="manual-interlude-add" onclick="addManualInterlude(this, 0)" title="Instrumental- oder Interlude-Segment einfuegen">+</button>', html)
        self.assertIn("function addManualInterlude", _page("Demo", ""))
        self.assertIn('<select name="sections"><option value="Intro">Intro</option><option value="Verse" selected>Verse</option>', html)
        self.assertIn('<option value="Instrumental Fade-Out">Instrumental Fade-Out</option>', html)
        self.assertIn('placeholder="0.0"', html)
        self.assertIn("function applyManualTimingTimestamp", _page("Demo", ""))
        self.assertIn("Save Manual Timing", html)
        self.assertLess(html.index('class="settings-realign-actions"'), html.index("Realign Lyrics (GeForce GPU)"))
        self.assertLess(html.index("Realign Lyrics (GeForce GPU)"), html.index("Realign Lyrics (CPU)"))
        self.assertLess(html.index("Realign Lyrics (CPU)"), html.index("Realign Lyrics (manually)"))
        self.assertLess(html.index("Realign Lyrics (manually)"), html.index('class="settings-save-actions"'))
        self.assertLess(html.index('class="settings-save-actions"'), html.index("<button>Save Project Settings</button>"))

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
            "D:\\data\\Projekte\\ComfyUI\\VocaVid\\.VocaVid\\outputs\\project-1\\audio-segments\\segment-000.wav"
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
                "image_path": "VocaVid/project-1/line-0-1782236016441_00001_.png",
                "clip_path": None,
                "status": "done",
                "error": "",
            }
        ]

        html = _project_html(project, lines, used_actions={"scene-plan"})

        self.assertIn('<img class="preview-image"', html)
        self.assertIn("openImageLightbox('http://127.0.0.1:8188/view?filename=line-0-1782236016441_00001_.png&amp;subfolder=VocaVid%2Fproject-1&amp;type=output')", html)
        self.assertIn(
            'src="http://127.0.0.1:8188/view?filename=line-0-1782236016441_00001_.png&amp;subfolder=VocaVid%2Fproject-1&amp;type=output"',
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
                "image_path": "D:\\data\\Projekte\\ComfyUI\\VocaVid\\.VocaVid\\outputs\\project-1\\images\\segment-000.png",
                "avatar_image_path": "D:\\data\\Projekte\\ComfyUI\\VocaVid\\.VocaVid\\outputs\\project-1\\images\\avatar-segment-000.png",
                "clip_path": "D:\\data\\Projekte\\ComfyUI\\VocaVid\\.VocaVid\\outputs\\project-1\\clips\\segment-000.mp4",
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
        self.assertIn('<form class="compact-form image-choice image-choice-inline"', html)
        self.assertLess(table_html.index("segment-000.png"), table_html.index("avatar-segment-000.png"))
        self.assertLess(table_html.index('class="asset-previews"'), table_html.index('class="compact-form image-choice image-choice-inline"'))
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
        table_html = html[html.index('id="project-table-view"') : html.index("</section>", html.index('id="project-table-view"'))]

        self.assertIn('action="/projects/7/lines/3/prompts/image/save"', html)
        self.assertIn('action="/projects/7/lines/3/prompts/image/ai-fill"', html)
        self.assertIn('action="/projects/7/lines/3/prompts/video/save"', html)
        self.assertIn('action="/projects/7/lines/3/prompts/video/ai-fill"', html)
        self.assertIn('name="prompt"', html)
        self.assertIn('name="video_prompt"', html)
        self.assertIn("<button>Save</button>", html)
        self.assertIn('formaction="/projects/7/lines/3/prompts/image/ai-fill">AI fill</button>', html)
        self.assertIn('formaction="/projects/7/lines/3/prompts/video/ai-fill">AI fill</button>', html)
        self.assertIn("<th>Status</th>", table_html)
        self.assertNotIn("<th>Error</th>", table_html)
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
        self.assertIn('data-project-sidepanel-form="1"', html)
        self.assertIn(
            'type="radio" name="selected_image_source" value="image" checked onchange="submitProjectSidepanelForm(event, this.form)"',
            html,
        )
        self.assertIn(
            'type="radio" name="selected_image_source" value="avatar" onchange="submitProjectSidepanelForm(event, this.form)"',
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
            'type="checkbox" name="video_approved" value="1" checked onchange="rememberApprovalProgressBeforeSubmit(); submitProjectSidepanelForm(event, this.form)"',
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

        self.assertIn('id="project-progress-pill" class="progress-pill"', html)
        self.assertIn('data-approved="1" data-total="2"', html)
        self.assertIn('id="project-completion-celebration" class="project-completion-celebration"', html)
        self.assertIn('<span class="progress-pill-fill" style="--progress: 50%"></span>', html)
        self.assertIn('<span class="progress-pill-label">1/2</span>', html)
        self.assertNotIn("1/2 offen", html)
        self.assertIn(".progress-pill { position: relative;", html)
        self.assertIn(".project-completion-celebration", html)
        self.assertIn("@keyframes completionParticleBurst", html)
        self.assertIn("@keyframes completionConfettiFall", html)
        self.assertIn('onsubmit="rememberApprovalProgressBeforeSubmit()" data-project-sidepanel-form="1"', html)
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
        self.assertIn('onclick="openFinalizeModal()">7. Finalize', html)
        self.assertIn('disabled title="Finish all clips first">8. Assemble &amp; Render MP4', html)

        lines[1]["video_approved"] = 1
        approved_html = _project_html(project, lines)

        self.assertIn('action="/projects/7/assemble-render"', approved_html)
        self.assertNotIn('title="Finish all clips first"', approved_html)

        assembled_html = _project_html(project, lines, used_actions={"assemble"})
        self.assertIn('action="/projects/7/assemble-render"', assembled_html)
        self.assertIn('class="used-button"', assembled_html)

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

import json
import tempfile
import subprocess
import time
import unittest
from threading import Event
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import VocaVid.app as app_module
from VocaVid.alignment import TranscriptWord
from VocaVid.lyrics import parse_suno_lyrics
from VocaVid.models import RenderSegment
from VocaVid.pipeline import Pipeline
from VocaVid.store import Store


class AppEndpointTests(unittest.TestCase):
    def test_assemble_render_endpoint_runs_both_steps_in_order(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []

        class FakePipeline:
            def __init__(self, store, output_root):
                self.store = store
                self.output_root = output_root

            def assemble(self, project_id, selected):
                calls.append(("assemble", project_id, selected))

            def render_final_mp4(self, project_id):
                calls.append(("render", project_id))

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.Pipeline = FakePipeline
                store = Store(app_module.DB_PATH)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": "song.wav",
                        "lyrics_path": "lyrics.txt",
                        "global_style_prompt": "cinematic",
                    },
                    parse_suno_lyrics("[Verse]\nHello\n"),
                )
                app = app_module.create_app()
                client = TestClient(app)

                response = client.post(f"/projects/{project_id}/assemble-render", follow_redirects=False)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], f"/projects/{project_id}")
                self.assertEqual(calls, [("assemble", project_id, []), ("render", project_id)])
                self.assertEqual(Store(app_module.DB_PATH).list_used_project_actions(project_id), {"assemble", "render-mp4"})
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_assemble_render_endpoint_keeps_existing_kdenlive_project(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []

        class FakePipeline:
            def __init__(self, store, output_root):
                self.store = store

            def assemble(self, project_id, selected):
                calls.append(("assemble", project_id, selected))

            def render_final_mp4(self, project_id):
                calls.append(("render", project_id))

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.Pipeline = FakePipeline
                store = Store(app_module.DB_PATH)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": "song.wav",
                        "lyrics_path": "lyrics.txt",
                        "global_style_prompt": "cinematic",
                        "final_video_path": "outputs/demo/final.kdenlive",
                    },
                    parse_suno_lyrics("[Verse]\\nHello\\n"),
                )
                store.update_project(project_id, final_video_path="outputs/demo/final.kdenlive")
                existing_project = app_module.APP_ROOT / "outputs" / "demo" / "final.kdenlive"
                existing_project.parent.mkdir(parents=True)
                existing_project.write_text("<mlt />", encoding="utf-8")
                app = app_module.create_app()
                client = TestClient(app)

                response = client.post(f"/projects/{project_id}/assemble-render", follow_redirects=False)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(calls, [("render", project_id)])
                self.assertEqual(Store(app_module.DB_PATH).list_used_project_actions(project_id), {"render-mp4"})
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_icon_assets_are_served(self):
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
                client = TestClient(app)

                response = client.get("/icon/VocaVid_icon.svg")

                self.assertEqual(response.status_code, 200)
                self.assertIn("image/svg", response.headers["content-type"])
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_jobs_status_endpoint_returns_current_queue_payload(self):
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
                self.assertIn("jobs_html", payload)
                self.assertIn("queued job", payload["jobs_html"])
                self.assertIn("queue_summary_html", payload)
                self.assertIn("<span>queued</span>", payload["queue_summary_html"])
                self.assertIn("queue_count", payload)
                self.assertIn("queue_estimate_seconds", payload)
                self.assertFalse(payload["autodelete_finished"])
                self.assertFalse(payload["shutdown_after_queue"])
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_job_options_endpoint_toggles_autodelete_and_shutdown(self):
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
                client = TestClient(app)
                response = client.post(
                    "/jobs/options",
                    data={"autodelete_finished": "on", "shutdown_after_queue": "on"},
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/")
                self.assertTrue(app.state.job_options.autodelete_finished)
                self.assertTrue(app.state.job_options.shutdown_after_queue)
                saved = Store(app_module.DB_PATH).get_global_settings()
                self.assertEqual(saved["autodelete_finished"], 1)
                self.assertEqual(saved["shutdown_after_queue"], 1)
                app.state.jobs.executor.shutdown(wait=True)
                restarted = app_module.create_app()
                self.assertTrue(restarted.state.job_options.autodelete_finished)
                self.assertTrue(restarted.state.job_options.shutdown_after_queue)
                restarted.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_shutdown_controller_schedules_fifteen_minute_shutdown_after_last_queue(self):
        commands = []
        controller = app_module.ShutdownController(runner=commands.append)

        controller.enable()
        controller.schedule_after_queue_empty()

        self.assertEqual(commands, [["shutdown", "/s", "/t", "900"]])
        self.assertTrue(controller.scheduled)

    def test_shutdown_controller_cancels_pending_shutdown_when_disabled_or_queue_restarts(self):
        commands = []
        controller = app_module.ShutdownController(runner=commands.append)

        controller.enable()
        controller.schedule_after_queue_empty()
        controller.cancel_pending()
        controller.disable()

        self.assertEqual(commands, [["shutdown", "/s", "/t", "900"], ["shutdown", "/a"]])
        self.assertFalse(controller.scheduled)

    def test_prompt_field_save_endpoints_update_only_one_field(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.update_line(project_id, 0, prompt="old image", video_prompt="old video")

                client = TestClient(app_module.create_app())
                image_response = client.post(
                    f"/projects/{project_id}/lines/0/prompts/image/save",
                    data={"prompt": "new image"},
                    follow_redirects=False,
                )
                video_response = client.post(
                    f"/projects/{project_id}/lines/0/prompts/video/save",
                    data={"video_prompt": "new video"},
                    follow_redirects=False,
                )

                self.assertEqual(image_response.status_code, 303)
                self.assertEqual(video_response.status_code, 303)
                line = Store(app_module.DB_PATH).list_lines(project_id)[0]
                self.assertEqual(line["prompt"], "new image")
                self.assertEqual(line["video_prompt"], "new video")
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_delete_finished_jobs_endpoint_redirects_to_start_page(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"

                client = TestClient(app_module.create_app())
                response = client.post("/jobs/delete-finished", follow_redirects=False)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/")
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_create_project_saves_clip_group_settings_from_start_page(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []

        class FakePipeline:
            def __init__(self, store, output_root):
                self.store = store
                self.output_root = output_root

            def generate_global_style_prompt(self, project_id):
                calls.append(("global-style-prompt", project_id))

            def align_with_whisper(self, project_id, selected_line_indices=None):
                calls.append(("align", project_id, list(selected_line_indices or [])))

            def build_segments(self, project_id):
                calls.append(("segments", project_id))

            def generate_scene_plan(self, project_id, selected_segment_indices=None):
                calls.append(("scene-plan", project_id, list(selected_segment_indices or [])))

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.Pipeline = FakePipeline
                audio = root / "song.wav"
                _write_wav(audio)

                app = app_module.create_app()
                Store(app_module.DB_PATH).update_global_settings(
                    comfy_base_url="http://127.0.0.1:9000",
                    output_resolution="1920x1080",
                    fps=30,
                )
                client = TestClient(app)
                with audio.open("rb") as audio_file:
                    response = client.post(
                        "/projects",
                        data={
                            "name": "Demo",
                            "genre": "industrial rock",
                            "avatar_gender": "female",
                            "avatar_face_description": "angular face, silver hair",
                            "lyric_group_size": "3",
                            "chorus_group_size": "2",
                            "transition_handle_seconds": "0.7",
                            "whisper_model_size": "large-v3",
                        },
                        files={
                            "audio": ("song.wav", audio_file, "audio/wav"),
                            "lyrics": ("lyrics.txt", b"[Verse]\nOne\nTwo\n", "text/plain"),
                            "avatar": ("avatar.png", b"fake image", "image/png"),
                        },
                        follow_redirects=False,
                    )

                self.assertEqual(response.status_code, 303)
                project = Store(app_module.DB_PATH).list_projects()[0]
                self.assertEqual(project["genre"], "industrial rock")
                self.assertEqual(project["avatar_gender"], "female")
                self.assertEqual(project["avatar_face_description"], "angular face, silver hair")
                self.assertEqual(project["lyric_group_size"], 3)
                self.assertEqual(project["chorus_group_size"], 2)
                self.assertEqual(project["transition_handle_seconds"], 0.7)
                self.assertEqual(project["whisper_model_size"], "large-v3")
                self.assertEqual(project["output_resolution"], "1920x1080")
                self.assertEqual(project["fps"], 30)
                self.assertEqual(project["comfy_base_url"], "http://127.0.0.1:9000")
                self.assertEqual(len(json.loads(project["reference_image_paths"])), 1)
                deadline = time.time() + 2
                while len(calls) < 4 and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual([call[0] for call in calls], ["global-style-prompt", "align", "segments", "scene-plan"])
                self.assertEqual(
                    [job.action for job in sorted(app.state.jobs.list_jobs(), key=lambda job: job.id)],
                    ["global-style-prompt", "align", "segments", "scene-plan"],
                )
                used_actions = Store(app_module.DB_PATH).list_used_project_actions(project["id"])
                self.assertEqual(used_actions, {"align", "segments", "scene-plan"})
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_create_project_queues_avatar_description_when_face_description_is_empty(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []

        class FakePipeline:
            def __init__(self, store, output_root):
                self.store = store
                self.output_root = output_root

            def describe_avatar_face(self, project_id):
                calls.append(("avatar-description", project_id))

            def generate_global_style_prompt(self, project_id):
                calls.append(("global-style-prompt", project_id))

            def align_with_whisper(self, project_id, selected_line_indices=None):
                calls.append(("align", project_id, list(selected_line_indices or [])))

            def build_segments(self, project_id):
                calls.append(("segments", project_id))

            def generate_scene_plan(self, project_id, selected_segment_indices=None):
                calls.append(("scene-plan", project_id, list(selected_segment_indices or [])))

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.Pipeline = FakePipeline
                audio = root / "song.wav"
                _write_wav(audio)

                app = app_module.create_app()
                client = TestClient(app)
                with audio.open("rb") as audio_file:
                    response = client.post(
                        "/projects",
                        data={
                            "name": "Demo",
                            "genre": "industrial rock",
                            "avatar_gender": "male",
                            "avatar_face_description": "",
                        },
                        files={
                            "audio": ("song.wav", audio_file, "audio/wav"),
                            "lyrics": ("lyrics.txt", b"[Verse]\nOne\nTwo\n", "text/plain"),
                            "avatar": ("avatar.png", b"fake image", "image/png"),
                        },
                        follow_redirects=False,
                    )

                self.assertEqual(response.status_code, 303)
                project = Store(app_module.DB_PATH).list_projects()[0]
                deadline = time.time() + 2
                while len(calls) < 5 and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual(
                    [call[0] for call in calls],
                    ["avatar-description", "global-style-prompt", "align", "segments", "scene-plan"],
                )
                self.assertEqual(
                    [job.action for job in sorted(app.state.jobs.list_jobs(), key=lambda job: job.id)],
                    ["avatar-description", "global-style-prompt", "align", "segments", "scene-plan"],
                )
                self.assertEqual(project["avatar_face_description"], "")
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_global_style_prompt_endpoint_queues_generation_job(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        release = Event()
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "",
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )

                class FakePipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def generate_global_style_prompt(self, project_id):
                        self.store.update_project(project_id, global_style_prompt="ai style")

                app_module.Pipeline = FakePipeline
                client = TestClient(app_module.create_app())
                response = client.post(f"/projects/{project_id}/global-style-prompt", follow_redirects=False)

                self.assertEqual(response.status_code, 303)
                jobs = client.get("/").text
                self.assertIn("generate global style prompt: Demo", jobs)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_avatar_description_endpoint_queues_generation_job(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "",
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )

                class FakePipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def describe_avatar_face(self, project_id):
                        calls.append(project_id)

                app_module.Pipeline = FakePipeline
                app = app_module.create_app()
                client = TestClient(app)

                response = client.post(f"/projects/{project_id}/avatar-description", follow_redirects=False)

                self.assertEqual(response.status_code, 303)
                deadline = time.time() + 2
                while not calls and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual(calls, [project_id])
                jobs = app.state.jobs.list_jobs()
                self.assertEqual(jobs[0].action, "avatar-description")
                self.assertEqual(jobs[0].project_id, project_id)
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_project_page_queue_estimate_includes_jobs_from_other_projects(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        release = Event()
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
                _write_wav(audio)
                project_1 = store.create_project(
                    {"name": "One", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                project_2 = store.create_project(
                    {"name": "Two", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.record_job_run("prompts", "lines", 1, 30.0, "done")
                started = Event()

                class BlockingPipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def generate_prompts(self, project_id, selected_line_indices=None):
                        started.set()
                        release.wait(timeout=2)

                app_module.Pipeline = BlockingPipeline
                client = TestClient(app_module.create_app())
                client.post(f"/projects/{project_1}/prompts", follow_redirects=False)
                self.assertTrue(started.wait(timeout=2))

                page = client.get(f"/projects/{project_2}").text

                self.assertIn("<title>(1) Two</title>", page)
                self.assertIn('id="queue-estimate" class="queue-estimate" type="button" data-seconds=', page)
                self.assertIn('data-count="1"', page)
                self.assertIn(">1 ~", page)
                self.assertIn('id="queue-modal"', page)
                self.assertNotIn(">Queue 0</button>", page)
                release.set()
                time.sleep(0.1)
        finally:
            release.set()
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_generate_prompts_endpoint_queues_image_then_video_prompt_per_line(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )

                class RecordingPipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def generate_prompts(self, project_id, selected_line_indices=None):
                        calls.append(("image", list(selected_line_indices or [])))

                    def generate_video_prompts(self, project_id, selected_line_indices=None):
                        calls.append(("video", list(selected_line_indices or [])))

                app_module.Pipeline = RecordingPipeline
                app = app_module.create_app()
                client = TestClient(app)

                response = client.post(f"/projects/{project_id}/generate-prompts", follow_redirects=False)

                self.assertEqual(response.status_code, 303)
                for _ in range(30):
                    if len(calls) >= 4:
                        break
                    time.sleep(0.05)
                self.assertEqual(calls, [("image", [0]), ("video", [0]), ("image", [1]), ("video", [1])])
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_project_status_endpoint_returns_current_segment_row_html(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.replace_segments(
                    project_id,
                    [RenderSegment(0, "lyrics", "Verse", False, False, [0], "Updated row", 1.0, 2.0, status="done")],
                )

                client = TestClient(app_module.create_app())
                response = client.get(f"/projects/{project_id}/status")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("segment-row-0", payload["rows"])
                self.assertIn("Updated row", payload["rows"]["segment-row-0"])
                self.assertIn('id="project-storyboard"', payload["storyboard_html"])
                self.assertIn("Updated row", payload["storyboard_html"])
                self.assertEqual(payload["locked"], {"segments": [], "lines": []})
                self.assertEqual(payload["queue_count"], 0)
                self.assertEqual(payload["queue_estimate_seconds"], 0)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_project_image_action_queues_only_segments_without_an_image_by_default(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.replace_segments(
                    project_id,
                    [
                        RenderSegment(0, "lyrics", "Verse", False, False, [0], "One", 1.0, 2.0),
                        RenderSegment(1, "lyrics", "Verse", False, False, [1], "Two", 2.0, 3.0),
                    ],
                )
                store.update_segment(project_id, 0, image_path="existing.png")
                calls = []

                class FakePipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def generate_images(self, project_id, selected_line_indices=None):
                        calls.append(list(selected_line_indices or []))

                app_module.Pipeline = FakePipeline
                client = TestClient(app_module.create_app())

                response = client.post(f"/projects/{project_id}/images", follow_redirects=False)
                for _ in range(20):
                    if calls:
                        break
                    time.sleep(0.01)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(calls, [[1]])
                jobs_html = client.get("/").text
                self.assertNotIn("generate images: Demo (segment 1)", jobs_html)
                self.assertIn("generate images: Demo (segment 2)", jobs_html)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_project_image_action_skips_approved_segments_even_when_processing_all(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.replace_segments(
                    project_id,
                    [
                        RenderSegment(0, "lyrics", "Verse", False, False, [0], "One", 1.0, 2.0),
                        RenderSegment(1, "lyrics", "Verse", False, False, [1], "Two", 2.0, 3.0),
                    ],
                )
                store.update_segment(project_id, 1, video_approved=1)
                calls = []

                class FakePipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def generate_images(self, project_id, selected_line_indices=None):
                        calls.append(list(selected_line_indices or []))

                app_module.Pipeline = FakePipeline
                client = TestClient(app_module.create_app())

                response = client.post(f"/projects/{project_id}/images", follow_redirects=False)
                for _ in range(20):
                    if calls:
                        break
                    time.sleep(0.01)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(calls, [[0]])
                jobs_html = client.get("/").text
                self.assertIn("generate images: Demo (segment 1)", jobs_html)
                self.assertNotIn("generate images: Demo (segment 2)", jobs_html)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_project_image_action_with_only_approved_segments_queues_nothing_and_does_not_mark_used(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.replace_segments(project_id, [RenderSegment(0, "lyrics", "Verse", False, False, [0], "One", 1.0, 2.0)])
                store.update_segment(project_id, 0, video_approved=1)
                calls = []

                class FakePipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def generate_images(self, project_id, selected_line_indices=None):
                        calls.append(list(selected_line_indices or []))

                app_module.Pipeline = FakePipeline
                client = TestClient(app_module.create_app())

                response = client.post(f"/projects/{project_id}/images", follow_redirects=False)
                time.sleep(0.05)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(calls, [])
                self.assertEqual(Store(app_module.DB_PATH).list_used_project_actions(project_id), set())
                self.assertNotIn("generate images: Demo", client.get("/").text)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_render_mp4_endpoint_renders_without_queueing(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []

        class FakePipeline:
            def __init__(self, store, workspace):
                self.store = store

            def render_final_mp4(self, project_id):
                calls.append(project_id)

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.Pipeline = FakePipeline
                store = Store(app_module.DB_PATH)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": "song.wav",
                        "lyrics_path": "lyrics.txt",
                        "global_style_prompt": "cinematic",
                        "final_video_path": "outputs/demo/final.kdenlive",
                    },
                    parse_suno_lyrics("[Verse]\nHello\n"),
                )
                store.replace_segments(project_id, [RenderSegment(0, "lyrics", "Verse", False, False, [0], "Hello", 0.0, 3.0)])
                store.update_segment(project_id, 0, clip_path="clip.mp4", video_approved=1)

                app = app_module.create_app()
                client = TestClient(app)
                response = client.post(f"/projects/{project_id}/render-mp4", follow_redirects=False)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], f"/projects/{project_id}")
                self.assertEqual(calls, [project_id])
                self.assertEqual(app.state.jobs.list_jobs(), [])
                self.assertEqual(Store(app_module.DB_PATH).list_used_project_actions(project_id), {"render-mp4"})
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_assemble_endpoint_writes_kdenlive_project_without_queueing(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        calls = []

        class FakePipeline:
            def __init__(self, store, workspace):
                self.store = store

            def assemble(self, project_id, selected_line_indices=None):
                calls.append((project_id, list(selected_line_indices or [])))

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.Pipeline = FakePipeline
                store = Store(app_module.DB_PATH)
                project_id = store.create_project(
                    {"name": "Demo", "audio_path": "song.wav", "lyrics_path": "lyrics.txt", "global_style_prompt": "cinematic"},
                    parse_suno_lyrics("[Verse]\nHello\n"),
                )

                app = app_module.create_app()
                client = TestClient(app)
                response = client.post(
                    f"/projects/{project_id}/assemble",
                    data={"selected_lines": [0]},
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], f"/projects/{project_id}")
                self.assertEqual(calls, [(project_id, [0])])
                self.assertEqual(app.state.jobs.list_jobs(), [])
                self.assertEqual(Store(app_module.DB_PATH).list_used_project_actions(project_id), {"assemble"})
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_global_settings_endpoint_persists_defaults_and_avatar(self):
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
                client = TestClient(app)

                response = client.post(
                    "/settings",
                    data={
                        "avatar_gender": "female",
                        "avatar_face_description": "silver hair, green eyes",
                        "comfy_base_url": "http://127.0.0.1:9000",
                        "output_resolution": "1920x1080",
                        "fps": "30",
                        "lyric_group_size": "3",
                        "chorus_group_size": "2",
                        "transition_handle_seconds": "0.8",
                        "whisper_model_size": "medium",
                        "autodelete_finished": "on",
                    },
                    files={"avatar": ("band.png", b"fake image", "image/png")},
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 303)
                saved = Store(app_module.DB_PATH).get_global_settings()
                self.assertEqual(saved["avatar_path"], "global/band.png")
                self.assertEqual(saved["avatar_gender"], "female")
                self.assertEqual(saved["avatar_face_description"], "silver hair, green eyes")
                self.assertEqual(saved["comfy_base_url"], "http://127.0.0.1:9000")
                self.assertEqual(saved["output_resolution"], "1920x1080")
                self.assertEqual(saved["fps"], 30)
                self.assertEqual(saved["lyric_group_size"], 3)
                self.assertEqual(saved["chorus_group_size"], 2)
                self.assertEqual(saved["transition_handle_seconds"], 0.8)
                self.assertEqual(saved["whisper_model_size"], "medium")
                self.assertEqual(saved["autodelete_finished"], 1)
                self.assertEqual(saved["shutdown_after_queue"], 0)
                self.assertTrue((app_module.APP_ROOT / "global" / "band.png").exists())
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_line_insert_and_delete_endpoints_update_project_lines(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )

                client = TestClient(app_module.create_app())
                insert_response = client.post(
                    f"/projects/{project_id}/lines/0/insert-after",
                    data={"text": "Inserted", "section": ""},
                    follow_redirects=False,
                )
                delete_response = client.post(
                    f"/projects/{project_id}/lines/0/delete",
                    follow_redirects=False,
                )

                self.assertEqual(insert_response.status_code, 303)
                self.assertEqual(delete_response.status_code, 303)
                lines = Store(app_module.DB_PATH).list_lines(project_id)
                self.assertEqual([(line["line_index"], line["clean_text"]) for line in lines], [(0, "Inserted"), (1, "Two")])
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_settings_group_size_change_preserves_generated_project_state(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"

                def fake_run(command, check, capture_output, text):
                    Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                    Path(command[-1]).write_text("wav", encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, "", "")

                app_module.Pipeline = lambda store, workspace: Pipeline(store, workspace, ffmpeg_runner=fake_run)
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                        "lyric_group_size": 1,
                        "chorus_group_size": 1,
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.update_line(project_id, 0, start_sec=1.0, end_sec=2.0, prompt="old prompt", video_approved=1)
                store.replace_segments(
                    project_id,
                    [RenderSegment(0, "lyrics", "Verse", False, False, [0], "Hello", 1.0, 2.0, audio_path="old.wav")],
                )
                store.mark_project_action_used(project_id, "align")

                client = TestClient(app_module.create_app())
                with patch("VocaVid.pipeline.transcribe_words_with_fallback", return_value=[TranscriptWord("Hello", 1.0, 2.0)]) as transcribe:
                    response = client.post(
                        f"/projects/{project_id}/settings",
                        data={
                            "name": "Demo",
                            "audio_path": str(audio),
                            "lyrics_path": str(lyrics),
                            "global_style_prompt": "cinematic",
                            "genre": "",
                            "avatar_gender": "male",
                            "avatar_face_description": "weathered face, dark beard",
                            "reference_image_paths": "",
                            "comfy_base_url": "http://127.0.0.1:8188",
                            "output_resolution": "1280x720",
                            "fps": "24",
                            "lyric_group_size": "2",
                            "chorus_group_size": "1",
                            "transition_handle_seconds": "0.5",
                            "whisper_model_size": "medium",
                        },
                        follow_redirects=False,
                    )

                self.assertEqual(response.status_code, 303)
                transcribe.assert_not_called()
                updated_store = Store(app_module.DB_PATH)

                project = updated_store.get_project(project_id)
                line = updated_store.list_lines(project_id)[0]
                self.assertEqual(project["lyric_group_size"], 2)
                self.assertEqual(project["whisper_model_size"], "medium")
                self.assertEqual(project["avatar_gender"], "male")
                self.assertEqual(project["avatar_face_description"], "weathered face, dark beard")
                self.assertEqual(line["start_sec"], 1.0)
                self.assertEqual(line["end_sec"], 2.0)
                self.assertEqual(line["prompt"], "old prompt")
                self.assertEqual(line["video_approved"], 1)
                segments = updated_store.list_segments(project_id)
                self.assertEqual(len(segments), 1)
                self.assertEqual(segments[0]["audio_path"], "old.wav")
                self.assertEqual(updated_store.list_used_project_actions(project_id), {"align"})
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_settings_group_size_change_saves_only_without_regroup_or_queueing_job(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                        "lyric_group_size": 1,
                        "chorus_group_size": 1,
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                store.replace_segments(
                    project_id,
                    [RenderSegment(0, "lyrics", "Verse", False, False, [0], "Hello", 0.0, 3.0)],
                )

                class RecordingPipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def regroup_project(self, project_id):
                        raise AssertionError("settings save must not regroup")

                app_module.Pipeline = RecordingPipeline
                client = TestClient(app_module.create_app())
                response = client.post(
                    f"/projects/{project_id}/settings",
                    data={
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                        "genre": "",
                        "reference_image_paths": "",
                        "comfy_base_url": "http://127.0.0.1:8188",
                        "output_resolution": "1280x720",
                        "fps": "24",
                        "lyric_group_size": "2",
                        "chorus_group_size": "1",
                        "transition_handle_seconds": "0.5",
                        "whisper_model_size": "medium",
                    },
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 303)
                self.assertEqual(Store(app_module.DB_PATH).get_project(project_id)["lyric_group_size"], 2)
                self.assertEqual(Store(app_module.DB_PATH).get_project(project_id)["whisper_model_size"], "medium")
                self.assertEqual(len(Store(app_module.DB_PATH).list_segments(project_id)), 1)
                self.assertEqual(Store(app_module.DB_PATH).list_used_project_actions(project_id), set())
                self.assertNotIn("regroup segments: Demo", client.get("/").text)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_realign_lyrics_endpoint_regroups_without_changing_settings(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                        "lyric_group_size": 2,
                        "chorus_group_size": 1,
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )

                class RecordingPipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def regroup_project(self, project_id):
                        self.store.replace_segments(
                            project_id,
                            [RenderSegment(0, "lyrics", "Verse", False, False, [0], "Hello", 1.0, 2.0)],
                        )

                app_module.Pipeline = RecordingPipeline
                client = TestClient(app_module.create_app())
                page = client.get(f"/projects/{project_id}").text

                response = client.post(f"/projects/{project_id}/realign-lyrics", follow_redirects=False)

                self.assertIn('action="/projects/1/realign-lyrics"', page)
                self.assertIn("Realign Lyrics", page)
                self.assertEqual(response.status_code, 303)
                updated_store = Store(app_module.DB_PATH)
                self.assertEqual(updated_store.get_project(project_id)["lyric_group_size"], 2)
                self.assertEqual(len(updated_store.list_segments(project_id)), 1)
                self.assertEqual(updated_store.list_used_project_actions(project_id), {"align", "segments"})
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_realign_lyrics_cpu_endpoint_regroups_with_cpu_only_alignment(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = root / "song.wav"
                lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                        "lyric_group_size": 2,
                        "chorus_group_size": 1,
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                calls = []

                class RecordingPipeline:
                    def __init__(self, store, workspace):
                        self.store = store

                    def regroup_project(self, project_id, force_cpu=False):
                        calls.append(force_cpu)
                        self.store.replace_segments(
                            project_id,
                            [RenderSegment(0, "lyrics", "Verse", False, False, [0], "Hello", 1.0, 2.0)],
                        )

                app_module.Pipeline = RecordingPipeline
                client = TestClient(app_module.create_app())
                page = client.get(f"/projects/{project_id}").text

                response = client.post(f"/projects/{project_id}/realign-lyrics-cpu", follow_redirects=False)

                self.assertIn('action="/projects/1/realign-lyrics-cpu"', page)
                self.assertIn("Realign Lyrics (CPU)", page)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(calls, [True])
                updated_store = Store(app_module.DB_PATH)
                self.assertEqual(len(updated_store.list_segments(project_id)), 1)
                self.assertEqual(updated_store.list_used_project_actions(project_id), {"align", "segments"})
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.Pipeline = old_pipeline

    def test_manual_timing_endpoint_saves_lines_builds_segments_and_marks_setup_used(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                lyrics = root / "lyrics.txt"
                audio = app_module.UPLOADS / "demo" / "song.wav"
                lyrics.write_text("[Verse]\nOne\nTwo\nThree\n", encoding="utf-8")
                audio.parent.mkdir(parents=True)
                _write_wav(audio)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": str(audio),
                        "lyrics_path": str(lyrics),
                        "global_style_prompt": "cinematic",
                    },
                    parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
                )
                client = TestClient(app_module.create_app())

                response = client.post(
                    f"/projects/{project_id}/manual-timing",
                    data={
                        "line_indices": ["0", "1", "2"],
                        "clean_texts": ["Edited one", "Edited two", "Edited three"],
                        "sections": ["Verse", "Verse", "Refrain"],
                        "start_secs": ["0:00", "0:01", "0:02"],
                        "end_secs": ["0:01", "0:02", "0:03"],
                        "manual_segment_starts": ["0", "2"],
                    },
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 303)
                updated_store = Store(app_module.DB_PATH)
                lines = updated_store.list_lines(project_id)
                self.assertEqual(lines[0]["clean_text"], "Edited one")
                self.assertEqual(lines[0]["confidence"], 1.0)
                self.assertEqual(lines[2]["manual_segment_start"], 1)
                segments = updated_store.list_segments(project_id)
                self.assertEqual(len(segments), 2)
                self.assertEqual(segments[0]["clean_text"], "Edited one\nEdited two")
                self.assertEqual(segments[0]["start_sec"], 0.0)
                self.assertEqual(segments[0]["end_sec"], 2.0)
                self.assertEqual(segments[1]["clean_text"], "Edited three")
                self.assertEqual(segments[1]["section"], "Refrain")
                self.assertTrue(str(segments[0]["audio_path"]).endswith("audio-segments/segment-000.wav"))
                self.assertEqual(updated_store.list_used_project_actions(project_id), {"align", "segments"})
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_reels_analyze_endpoint_accepts_upload_fallback_and_queues_job(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_reels_pipeline = app_module.ReelsPipeline
        calls = []

        class FakeReelsPipeline:
            def __init__(self, store, app_root):
                self.store = store
                self.app_root = app_root

            def analyze(self, project_id, source_video_path):
                calls.append(("analyze", project_id, source_video_path))

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.ReelsPipeline = FakeReelsPipeline
                store = Store(app_module.DB_PATH)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": "song.wav",
                        "lyrics_path": "lyrics.txt",
                        "global_style_prompt": "cinematic",
                    },
                    parse_suno_lyrics("[Verse]\nHello\n"),
                )
                app = app_module.create_app()
                client = TestClient(app)

                response = client.post(
                    f"/projects/{project_id}/reels/analyze",
                    files={"source_video": ("upload.mp4", b"mp4", "video/mp4")},
                    follow_redirects=False,
                )
                app.state.jobs.executor.shutdown(wait=True)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], f"/projects/{project_id}")
                analyses = Store(app_module.DB_PATH).list_reel_analyses(project_id)
                self.assertEqual(len(analyses), 1)
                self.assertEqual(analyses[0]["source_video_path"], "outputs/demo/reels/source/upload.mp4")
                self.assertEqual(calls, [("analyze", project_id, "outputs/demo/reels/source/upload.mp4")])
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.ReelsPipeline = old_reels_pipeline

    def test_reels_analyze_uses_project_named_mp4_when_present(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_reels_pipeline = app_module.ReelsPipeline
        calls = []

        class FakeReelsPipeline:
            def __init__(self, store, app_root):
                self.store = store
                self.app_root = app_root

            def analyze(self, project_id, source_video_path):
                calls.append(("analyze", project_id, source_video_path))

        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                app_module.ReelsPipeline = FakeReelsPipeline
                store = Store(app_module.DB_PATH)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": "song.wav",
                        "lyrics_path": "lyrics.txt",
                        "global_style_prompt": "cinematic",
                    },
                    parse_suno_lyrics("[Verse]\nHello\n"),
                )
                finished = app_module.APP_ROOT / "outputs" / "demo" / "Demo.mp4"
                finished.parent.mkdir(parents=True)
                finished.write_bytes(b"mp4")
                app = app_module.create_app()
                client = TestClient(app)

                response = client.post(
                    f"/projects/{project_id}/reels/analyze",
                    data={"source_video_path": "outputs/demo/final.kdenlive"},
                    follow_redirects=False,
                )
                app.state.jobs.executor.shutdown(wait=True)

                self.assertEqual(response.status_code, 303)
                analyses = Store(app_module.DB_PATH).list_reel_analyses(project_id)
                self.assertEqual(analyses[0]["source_video_path"], "outputs/demo/Demo.mp4")
                self.assertEqual(calls, [("analyze", project_id, "outputs/demo/Demo.mp4")])
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path
            app_module.ReelsPipeline = old_reels_pipeline

    def test_reels_status_endpoint_returns_modal_snippet(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".VocaVid"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
                store = Store(app_module.DB_PATH)
                project_id = store.create_project(
                    {
                        "name": "Demo",
                        "audio_path": "song.wav",
                        "lyrics_path": "lyrics.txt",
                        "global_style_prompt": "cinematic",
                    },
                    parse_suno_lyrics("[Verse]\nHello\n"),
                )
                analysis_id = store.create_reel_analysis(project_id, "D:/exports/final.mp4")
                store.update_reel_analysis(analysis_id, status="done", metadata_json='{"duration": 60, "width": 1920, "height": 1080, "fps": 25}')

                app = app_module.create_app()
                client = TestClient(app)
                response = client.get(f"/projects/{project_id}/reels/status")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("reels_html", payload)
                self.assertIn("Source MP4", payload["reels_html"])
                self.assertIn("Candidates", payload["reels_html"])
                app.state.jobs.executor.shutdown(wait=True)
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path


def _write_wav(path: Path) -> None:
    import wave

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00" * 44100 * 3)

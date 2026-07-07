import tempfile
import subprocess
import time
import unittest
from threading import Event
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import musicvideogen.app as app_module
from musicvideogen.alignment import TranscriptWord
from musicvideogen.lyrics import parse_suno_lyrics
from musicvideogen.models import RenderSegment
from musicvideogen.pipeline import Pipeline
from musicvideogen.store import Store


class AppEndpointTests(unittest.TestCase):
    def test_jobs_status_endpoint_returns_current_queue_payload(self):
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"

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
                app.state.jobs.executor.shutdown(wait=True)
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"

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
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
                audio = root / "song.wav"
                _write_wav(audio)

                client = TestClient(app_module.create_app())
                with audio.open("rb") as audio_file:
                    response = client.post(
                        "/projects",
                        data={
                            "name": "Demo",
                            "lyric_group_size": "3",
                            "chorus_group_size": "2",
                            "transition_handle_seconds": "0.7",
                            "whisper_model_size": "large-v3",
                        },
                        files={
                            "audio": ("song.wav", audio_file, "audio/wav"),
                            "lyrics": ("lyrics.txt", b"[Verse]\nOne\nTwo\n", "text/plain"),
                        },
                        follow_redirects=False,
                    )

                self.assertEqual(response.status_code, 303)
                project = Store(app_module.DB_PATH).list_projects()[0]
                self.assertEqual(project["lyric_group_size"], 3)
                self.assertEqual(project["chorus_group_size"], 2)
                self.assertEqual(project["transition_handle_seconds"], 0.7)
                self.assertEqual(project["whisper_model_size"], "large-v3")
        finally:
            app_module.APP_ROOT = old_app_root
            app_module.UPLOADS = old_uploads
            app_module.DB_PATH = old_db_path

    def test_global_style_prompt_endpoint_queues_generation_job(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        release = Event()
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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

    def test_project_page_queue_estimate_includes_jobs_from_other_projects(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        release = Event()
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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
                self.assertIn('id="queue-estimate" class="queue-estimate" data-seconds=', page)
                self.assertIn(">Queue ca.", page)
                self.assertNotIn('id="queue-estimate" class="queue-estimate" data-seconds="0">Queue frei</span>', page)
                release.set()
                time.sleep(0.1)
        finally:
            release.set()
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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

    def test_project_image_action_queues_one_job_per_segment(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        old_pipeline = app_module.Pipeline
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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
                    if len(calls) == 2:
                        break
                    time.sleep(0.01)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(calls, [[0], [1]])
                jobs_html = client.get("/").text
                self.assertIn("generate images: Demo (segment 1)", jobs_html)
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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

    def test_line_insert_and_delete_endpoints_update_project_lines(self):
        old_app_root = app_module.APP_ROOT
        old_uploads = app_module.UPLOADS
        old_db_path = app_module.DB_PATH
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
                root = Path(directory)
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"

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
                with patch("musicvideogen.pipeline.transcribe_words_with_fallback", return_value=[TranscriptWord("Hello", 1.0, 2.0)]) as transcribe:
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
                transcribe.assert_not_called()
                updated_store = Store(app_module.DB_PATH)

                project = updated_store.get_project(project_id)
                line = updated_store.list_lines(project_id)[0]
                self.assertEqual(project["lyric_group_size"], 2)
                self.assertEqual(project["whisper_model_size"], "medium")
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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
                app_module.APP_ROOT = root / ".musicvideogen"
                app_module.UPLOADS = app_module.APP_ROOT / "uploads"
                app_module.DB_PATH = app_module.APP_ROOT / "musicvideogen.sqlite3"
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


def _write_wav(path: Path) -> None:
    import wave

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00" * 44100 * 3)

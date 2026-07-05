import tempfile
import subprocess
import unittest
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
                self.assertEqual(payload["locked"], {"segments": [], "lines": []})
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

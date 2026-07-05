import sqlite3
import tempfile
import unittest
import wave
from pathlib import Path

from musicvideogen.lyrics import parse_suno_lyrics
from musicvideogen.pipeline import Pipeline
from musicvideogen.store import Store
from musicvideogen.workflows import WorkflowPaths


class PipelineSelectionTests(unittest.TestCase):
    def test_generate_prompts_only_updates_selected_lines(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=2.0)
            lyrics.write_text("[Verse]\nLine one\nLine two\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            pipeline = Pipeline(store, root / "outputs")
            pipeline.workflows = WorkflowPaths.defaults(root)

            pipeline.generate_prompts(project_id, selected_line_indices=[1])

            rows = store.list_lines(project_id)
            self.assertIsNone(rows[0]["prompt"])
            self.assertEqual(rows[0]["status"], "pending")
            self.assertEqual(rows[1]["prompt"], "Line two. cinematic")
            self.assertEqual(rows[1]["status"], "prompted")

    def test_align_evenly_only_updates_selected_lines(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.0)
            lyrics.write_text("[Verse]\nLine one\nLine two\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            pipeline = Pipeline(store, root / "outputs")
            pipeline.workflows = WorkflowPaths.defaults(root)

            pipeline.align_evenly(project_id, selected_line_indices=[1])

            rows = store.list_lines(project_id)
            self.assertIsNone(rows[0]["start_sec"])
            self.assertEqual(rows[1]["start_sec"], 2.0)
            self.assertEqual(rows[1]["end_sec"], 4.0)

    def test_insert_line_after_inherits_section_and_parses_inline_tags(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.0)
            lyrics.write_text("[Verse]\nLine one\nLine two\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            pipeline = Pipeline(store, root / "outputs")

            pipeline.insert_line_after(project_id, 0, "[me] Inserted line", "")

            rows = store.list_lines(project_id)
            self.assertEqual([(row["line_index"], row["clean_text"]) for row in rows], [(0, "Line one"), (1, "Inserted line"), (2, "Line two")])
            self.assertEqual(rows[1]["section"], "Verse")
            self.assertEqual(rows[1]["use_reference"], 1)

    def test_delete_line_removes_line_through_pipeline(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.0)
            lyrics.write_text("[Verse]\nLine one\nLine two\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            pipeline = Pipeline(store, root / "outputs")

            pipeline.delete_line(project_id, 0)

            rows = store.list_lines(project_id)
            self.assertEqual([(row["line_index"], row["clean_text"]) for row in rows], [(0, "Line two")])

    def test_variables_use_selected_base_image_when_avatar_exists(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            pipeline = Pipeline(store, root / "outputs")
            project = {
                "reference_image_paths": "[]",
                "global_style_prompt": "cinematic",
                "fps": 24,
                "output_resolution": "1280x720",
                "genre": "",
            }
            row = {
                "clean_text": "Line",
                "section": "Verse",
                "is_chorus": 0,
                "use_reference": 0,
                "start_sec": 0.0,
                "end_sec": 1.0,
                "prompt": "image prompt",
                "video_prompt": "video prompt",
                "scene_plan": "",
                "audio_path": "",
                "image_path": "base.png",
                "avatar_image_path": "avatar.png",
                "selected_image_source": "image",
            }

            variables = pipeline._variables(project, row, prefer_avatar=True)

            self.assertEqual(variables["image_path"], "base.png")
            self.assertEqual(variables["source_image_path"], "base.png")

    def test_delete_project_removes_output_and_upload_directories(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio_dir = root / "uploads" / "demo"
            audio_dir.mkdir(parents=True)
            audio = audio_dir / "song.wav"
            lyrics = audio_dir / "lyrics.txt"
            _write_wav(audio, duration_sec=1.0)
            lyrics.write_text("[Verse]\nLine\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            output_dir = root / "outputs" / "demo"
            output_dir.mkdir(parents=True)
            (output_dir / "file.png").write_text("image", encoding="utf-8")
            pipeline = Pipeline(store, root / "outputs")

            pipeline.delete_project(project_id)

            self.assertFalse(output_dir.exists())
            self.assertFalse(audio_dir.exists())
            with self.assertRaises(KeyError):
                store.get_project(project_id)


def _write_wav(path: Path, duration_sec: float) -> None:
    sample_rate = 8000
    frames = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)

import tempfile
import unittest
from pathlib import Path

from musicvideogen.lyrics import parse_suno_lyrics
from musicvideogen.models import LineTiming, RenderSegment
from musicvideogen.store import Store


class ProjectActionTests(unittest.TestCase):
    def test_project_action_usage_is_persisted(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            store.mark_project_action_used(project_id, "align")
            store.mark_project_action_used(project_id, "prompts")

            self.assertEqual(store.list_used_project_actions(project_id), {"align", "prompts"})

    def test_delete_project_removes_project_related_rows(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.mark_project_action_used(project_id, "align")

            store.delete_project(project_id)

            with self.assertRaises(KeyError):
                store.get_project(project_id)
            self.assertEqual(store.list_lines(project_id), [])
            self.assertEqual(store.list_segments(project_id), [])
            self.assertEqual(store.list_used_project_actions(project_id), set())

    def test_job_run_durations_are_averaged_by_action(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")

            store.record_job_run("images", "segments", 1, 10.0, "done")
            store.record_job_run("images", "segments", 1, 20.0, "done")
            store.record_job_run("images", "segments", 1, 99.0, "failed")
            store.record_job_run("clips", "segments", 1, 120.0, "done")

            self.assertEqual(store.average_job_durations(), {"clips": 120.0, "images": 15.0})

    def test_video_approval_is_persisted_for_lines(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            self.assertEqual(store.list_lines(project_id)[0]["video_approved"], 0)

            store.update_line(project_id, 0, video_approved=1)

            self.assertEqual(store.list_lines(project_id)[0]["video_approved"], 1)

    def test_insert_line_after_shifts_indices_and_clears_generated_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 1.0, 2.0, 0.9), LineTiming(1, 3.0, 4.0, 0.9)])
            store.update_line(project_id, 1, prompt="old prompt", image_path="old.png", clip_path="old.mp4", video_approved=1)
            store.replace_segments(
                project_id,
                [RenderSegment(0, "lyrics", "Verse", False, False, [0, 1], "One\nTwo", 1.0, 4.0, audio_path="old.wav")],
            )
            store.mark_project_action_used(project_id, "segments")

            store.insert_line_after(project_id, 0, section="Verse", raw_text="Inserted line", clean_text="Inserted line", is_chorus=False, use_reference=False)

            lines = store.list_lines(project_id)
            self.assertEqual([(line["line_index"], line["clean_text"]) for line in lines], [(0, "One"), (1, "Inserted line"), (2, "Two")])
            self.assertIsNone(lines[1]["start_sec"])
            self.assertIsNone(lines[2]["start_sec"])
            self.assertIsNone(lines[2]["prompt"])
            self.assertIsNone(lines[2]["clip_path"])
            self.assertEqual(lines[2]["video_approved"], 0)
            self.assertEqual(store.list_segments(project_id), [])
            self.assertEqual(store.list_used_project_actions(project_id), set())

    def test_delete_line_shifts_indices_and_clears_generated_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            lyrics.write_text("[Verse]\nOne\nTwo\nThree\n", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 1.0, 2.0, 0.9), LineTiming(1, 3.0, 4.0, 0.9), LineTiming(2, 5.0, 6.0, 0.9)])
            store.update_line(project_id, 2, prompt="old prompt", image_path="old.png", clip_path="old.mp4", video_approved=1)
            store.replace_segments(
                project_id,
                [RenderSegment(0, "lyrics", "Verse", False, False, [0, 1, 2], "One\nTwo\nThree", 1.0, 6.0, audio_path="old.wav")],
            )
            store.mark_project_action_used(project_id, "segments")

            store.delete_line(project_id, 1)

            lines = store.list_lines(project_id)
            self.assertEqual([(line["line_index"], line["clean_text"]) for line in lines], [(0, "One"), (1, "Three")])
            self.assertEqual(lines[0]["start_sec"], 1.0)
            self.assertIsNone(lines[1]["start_sec"])
            self.assertIsNone(lines[1]["prompt"])
            self.assertIsNone(lines[1]["clip_path"])
            self.assertEqual(lines[1]["video_approved"], 0)
            self.assertEqual(store.list_segments(project_id), [])
            self.assertEqual(store.list_used_project_actions(project_id), set())

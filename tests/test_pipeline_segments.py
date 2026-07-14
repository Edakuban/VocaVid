import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from VocaVid.lyrics import parse_suno_lyrics
from VocaVid.models import LineTiming
from VocaVid.alignment import TranscriptWord
from VocaVid.pipeline import Pipeline
from VocaVid.store import Store
from VocaVid.workflows import WorkflowPaths


class PipelineSegmentTests(unittest.TestCase):
    def test_generate_global_style_prompt_uses_promptgen_workflow_and_project_lyrics(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=5.0)
            lyrics.write_text("[Verse]\nOne line\n[Chorus]\nHook line\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "",
                    "genre": "industrial rock",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "promptgen.json").write_text('{"1": {"class_type": "TextGenerate", "inputs": {"prompt": ""}}}', encoding="utf-8")
            pipeline = Pipeline(store, root / "outputs")
            pipeline.workflows = WorkflowPaths.defaults(root)
            captured = {}

            class FakeClient:
                def __init__(self, base_url):
                    self.base_url = base_url

                def run_workflow(self, workflow, variables):
                    captured["prompt"] = workflow["1"]["inputs"]["prompt"]
                    return type("Result", (), {"ok": True, "output_files": [], "text_outputs": ["noir cathedral performance, rain, 35mm"], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.generate_global_style_prompt(project_id)
            finally:
                pipeline_module.ComfyClient = original_client

            project = store.get_project(project_id)
            self.assertEqual(project["global_style_prompt"], "noir cathedral performance, rain, 35mm")
            self.assertIn("Genre: industrial rock", captured["prompt"])
            self.assertIn("Lyrics: One line\nHook line", captured["prompt"])

    def test_describe_avatar_face_uses_optional_workflow_and_stores_text(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            avatar = root / "avatar.png"
            _write_wav(audio, duration_sec=5.0)
            lyrics.write_text("[Verse]\nOne line\n", encoding="utf-8")
            avatar.write_bytes(b"avatar")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "",
                    "reference_image_paths": [str(avatar)],
                    "avatar_gender": "female",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "avatar_description.json").write_text(
                '{"image":{"class_type":"LoadImage","inputs":{"image":"old.png"}},"text":{"class_type":"TextGenerate","inputs":{"prompt":"old"}}}',
                encoding="utf-8",
            )
            pipeline = Pipeline(store, root / "outputs")
            pipeline.workflows = WorkflowPaths.defaults(root)

            import VocaVid.pipeline as pipeline_module

            captured = {}

            class FakeClient:
                def __init__(self, base_url):
                    self.base_url = base_url

                def run_workflow(self, workflow, variables):
                    captured["workflow"] = workflow
                    captured["variables"] = variables
                    return type("Result", (), {"ok": True, "output_files": [], "text_outputs": ["oval face, dark eyes"], "error": ""})()

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.describe_avatar_face(project_id)
            finally:
                pipeline_module.ComfyClient = original_client

            project = store.get_project(project_id)
            self.assertEqual(project["avatar_face_description"], "oval face, dark eyes")
            self.assertEqual(captured["workflow"]["image"]["inputs"]["image"], str(avatar))
            self.assertIn("Describe the visible face", captured["workflow"]["text"]["inputs"]["prompt"])
            self.assertEqual(captured["variables"]["avatar_gender"], "female")

    def test_describe_avatar_face_fails_when_workflow_is_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=5.0)
            lyrics.write_text("[Verse]\nOne line\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            pipeline = Pipeline(store, root / "outputs")
            pipeline.workflows = WorkflowPaths.defaults(root)

            with self.assertRaisesRegex(FileNotFoundError, "avatar_description workflow is missing"):
                pipeline.describe_avatar_face(project_id)

    def test_generate_global_style_prompt_falls_back_when_promptgen_workflow_is_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=5.0)
            lyrics.write_text("[Verse]\nOne line\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "",
                    "genre": "dark pop",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            pipeline = Pipeline(store, root / "outputs")
            pipeline.workflows = WorkflowPaths.defaults(root)

            pipeline.generate_global_style_prompt(project_id)

            self.assertIn("dark pop", store.get_project(project_id)["global_style_prompt"])

    def test_build_segments_uses_project_group_sizes_and_splits_audio(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=50.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n[Chorus]\nHook one\nHook two\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                    "chorus_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(
                project_id,
                [
                    LineTiming(0, 35, 37, 0.9),
                    LineTiming(1, 37, 39, 0.9),
                    LineTiming(2, 39, 41, 0.9),
                    LineTiming(3, 41, 43, 0.9),
                ],
            )
            calls = []

            def fake_run(command, check, capture_output, text):
                calls.append(command)
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)

            pipeline.build_segments(project_id)

            segments = store.list_segments(project_id)
            self.assertEqual(segments[0]["kind"], "gap")
            self.assertEqual(segments[-1]["kind"], "gap")
            self.assertEqual(len([row for row in segments if row["kind"] == "lyrics"]), 2)
            self.assertEqual([row["clean_text"] for row in segments if row["kind"] == "lyrics"], ["One\nTwo", "Hook one\nHook two"])
            self.assertTrue(all(row["audio_path"] for row in segments))
            self.assertEqual(len(calls), len(segments))

    def test_build_segments_stores_internal_audio_paths_relative_to_app_root(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            app_root = root / ".VocaVid"
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0.0, 1.0, 0.9), LineTiming(1, 1.0, 2.0, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, app_root / "outputs", ffmpeg_runner=fake_run)

            pipeline.build_segments(project_id)

            segment = store.list_segments(project_id)[0]
            self.assertEqual(segment["audio_path"], "outputs/demo/audio-segments/segment-000.wav")

    def test_align_with_whisper_uses_transcript_window_fallback_when_too_few_lines_match_confidently(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=40.0)
            lyrics.write_text("[Verse]\nOne two\nMissing three\nMissing four\nMissing five\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            transcript = [
                TranscriptWord("One", 8.0, 8.3),
                TranscriptWord("two", 8.4, 8.7),
                TranscriptWord("noise", 30.0, 30.5),
                TranscriptWord("tail", 31.5, 32.0),
            ]

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", return_value=transcript):
                pipeline.align_with_whisper(project_id)

            lines = store.list_lines(project_id)
            self.assertEqual([(line["start_sec"], line["end_sec"], line["confidence"]) for line in lines], [(8.0, 14.0, 0.0), (14.0, 20.0, 0.0), (20.0, 26.0, 0.0), (26.0, 32.0, 0.0)])
            self.assertEqual([segment["kind"] for segment in store.list_segments(project_id)], ["gap", "lyrics", "lyrics", "gap"])

    def test_align_with_whisper_keeps_leading_instrumental_before_transcript_window_fallback(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=80.0)
            lyrics.write_text("[Instrumental Intro]\n\n[Verse]\nOne two\nMissing three\nMissing four\nMissing five\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            transcript = [
                TranscriptWord("One", 35.0, 35.3),
                TranscriptWord("two", 35.4, 35.7),
                TranscriptWord("tail", 75.0, 76.0),
            ]

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", return_value=transcript):
                pipeline.align_with_whisper(project_id)

            lines = store.list_lines(project_id)
            self.assertEqual((lines[0]["start_sec"], lines[0]["end_sec"]), (0.0, 35.0))
            first_lyric = next(line for line in lines if line["clean_text"] == "One two")
            self.assertEqual((first_lyric["start_sec"], first_lyric["end_sec"]), (35.0, 45.25))

    def test_align_with_whisper_passes_project_model_size_to_transcriber(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=12.0)
            lyrics.write_text("[Verse]\nOne two\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "whisper_model_size": "medium",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            transcript = [
                TranscriptWord("One", 2.0, 2.3),
                TranscriptWord("two", 2.4, 2.7),
            ]

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", return_value=transcript) as transcribe:
                pipeline.align_with_whisper(project_id)

            self.assertEqual(transcribe.call_args.kwargs["model_size"], "medium")

    def test_regroup_project_resets_generated_state_and_rebuilds_segments_with_align_fallback(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=8.0)
            lyrics.write_text("[Verse]\nOne\nTwo\nThree\nFour\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(
                project_id,
                [
                    LineTiming(0, 0.0, 1.0, 0.9),
                    LineTiming(1, 1.0, 2.0, 0.9),
                    LineTiming(2, 2.0, 3.0, 0.9),
                    LineTiming(3, 3.0, 4.0, 0.9),
                ],
            )
            store.update_line(project_id, 0, prompt="old prompt", clip_path="old.mp4", video_approved=1)
            store.mark_project_action_used(project_id, "prompts")
            project_dir = root / "outputs" / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "old.txt").write_text("generated", encoding="utf-8")

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", side_effect=RuntimeError("offline")) as transcribe:
                with self.assertRaises(RuntimeError):
                    pipeline.regroup_project(project_id)

            transcribe.assert_called_once()
            lines = store.list_lines(project_id)
            self.assertEqual([(row["start_sec"], row["end_sec"]) for row in lines], [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)])
            self.assertEqual(lines[0]["prompt"], "old prompt")
            self.assertEqual(lines[0]["clip_path"], "old.mp4")
            self.assertEqual(lines[0]["video_approved"], 1)
            self.assertEqual(store.list_used_project_actions(project_id), {"prompts"})
            self.assertTrue((project_dir / "old.txt").exists())

    def test_regroup_project_reloads_lyrics_file_so_instrumental_markers_are_restored(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=30.0)
            lyrics.write_text("[Instrumental Intro]\n\n[Verse]\nOne\nTwo\n\n[Instrumental]\n\n[Chorus]\nHook\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                [
                    parse_suno_lyrics("[Verse]\nOne\nTwo\n[Chorus]\nHook\n")[0],
                    parse_suno_lyrics("[Verse]\nOne\nTwo\n[Chorus]\nHook\n")[1],
                    parse_suno_lyrics("[Verse]\nOne\nTwo\n[Chorus]\nHook\n")[2],
                ],
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", side_effect=RuntimeError("offline")):
                with self.assertRaises(RuntimeError):
                    pipeline.regroup_project(project_id)

            self.assertEqual([line["clean_text"] for line in store.list_lines(project_id)], ["One", "Two", "Hook"])
            self.assertEqual(store.list_segments(project_id), [])

    def test_generate_prompts_uses_segments_when_they_exist(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 2, 0.9), LineTiming(1, 2, 4, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            pipeline.generate_prompts(project_id)

            segments = store.list_segments(project_id)
            lyric_segment = next(row for row in segments if row["kind"] == "lyrics")
            self.assertEqual(lyric_segment["prompt"], "One\nTwo. cinematic")
            self.assertEqual(lyric_segment["status"], "prompted")
            self.assertEqual(lyric_segment["last_action"], "prompts")

    def test_generate_prompts_records_last_action_for_lines_without_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)

            pipeline.generate_prompts(project_id, [1])

            lines = store.list_lines(project_id)
            self.assertIsNone(lines[0]["last_action"])
            self.assertEqual(lines[1]["last_action"], "prompts")

    def test_generate_video_prompts_uses_scene_plan_and_image_prompt(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 1,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 2, 0.9), LineTiming(1, 2, 4, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, prompt="rainy alley still frame", scene_plan="slow intro push-in")

            pipeline.generate_video_prompts(project_id, [0])

            segments = store.list_segments(project_id)
            self.assertIn("rainy alley still frame", segments[0]["video_prompt"])
            self.assertIn("slow intro push-in", segments[0]["video_prompt"])
            self.assertEqual(segments[0]["status"], "video prompted")
            self.assertIsNone(segments[1]["video_prompt"])

    def test_generate_avatar_images_stores_separate_avatar_image_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            reference = root / "ref.png"
            _write_wav(audio, duration_sec=3.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            reference.write_bytes(b"ref")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "reference_image_paths": [str(reference)],
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "avatartoimage_flux.json").write_text(
                '{"1":{"class_type":"LoadImage","inputs":{"image":"base.png"}},"2":{"class_type":"LoadImage","inputs":{"image":"ref.png"}},"9":{"class_type":"SaveImage","inputs":{"filename_prefix":"old"}}}',
                encoding="utf-8",
            )
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path=str(root / "outputs" / "project-1" / "images" / "segment-000.png"))
            comfy_output = root / "comfy" / "avatar.png"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"avatar")

            class FakeClient:
                def __init__(self, base_url):
                    self.base_url = base_url

                def run_workflow(self, workflow, variables):
                    self.workflow = workflow
                    self.variables = variables
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.generate_avatar_images(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client

            segment = store.list_segments(project_id)[0]
            self.assertTrue(segment["avatar_image_path"].endswith("images\\avatar-segment-000.png") or segment["avatar_image_path"].endswith("images/avatar-segment-000.png"))
            self.assertEqual((root / segment["avatar_image_path"]).read_bytes(), b"avatar")
            self.assertEqual(segment["status"], "done")

    def test_generate_images_skips_approved_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=3.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "image_z_image_turbo.json").write_text(
                '{"sampler":{"class_type":"Sampler","inputs":{"seed":1,"sampling_mode.seed":0}},"9":{"class_type":"SaveImage","inputs":{"filename_prefix":"old","images":["1",0]}}}',
                encoding="utf-8",
            )
            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(
                project_id,
                0,
                image_path="old-image.png",
                avatar_image_path="old-avatar.png",
                clip_path="old-clip.mp4",
                video_approved=1,
            )
            comfy_output = root / "comfy" / "image.png"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"image")
            captured = {}

            class FakeClient:
                def __init__(self, base_url):
                    pass

                def run_workflow(self, workflow, variables):
                    captured["workflow"] = workflow
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            original_new_seed = pipeline_module._new_seed
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline_module._new_seed = lambda: 987654321
                pipeline.generate_images(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client
                pipeline_module._new_seed = original_new_seed

            self.assertEqual(captured, {})
            segment = store.list_segments(project_id)[0]
            self.assertEqual(segment["image_path"], "old-image.png")
            self.assertEqual(segment["avatar_image_path"], "old-avatar.png")
            self.assertEqual(segment["clip_path"], "old-clip.mp4")
            self.assertEqual(segment["video_approved"], 1)

    def test_generate_avatar_images_skips_approved_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            reference = root / "ref.png"
            _write_wav(audio, duration_sec=3.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            reference.write_bytes(b"ref")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "reference_image_paths": [str(reference)],
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "avatartoimage_flux.json").write_text(
                '{"1":{"class_type":"LoadImage","inputs":{"image":"base.png"}},"2":{"class_type":"LoadImage","inputs":{"image":"ref.png"}},"sampler":{"class_type":"Sampler","inputs":{"seed":1}},"9":{"class_type":"SaveImage","inputs":{"filename_prefix":"old"}}}',
                encoding="utf-8",
            )
            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path="base.png", clip_path="old-clip.mp4", video_approved=1)
            comfy_output = root / "comfy" / "avatar.png"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"avatar")
            captured = {}

            class FakeClient:
                def __init__(self, base_url):
                    pass

                def run_workflow(self, workflow, variables):
                    captured["workflow"] = workflow
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            original_new_seed = pipeline_module._new_seed
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline_module._new_seed = lambda: 555
                pipeline.generate_avatar_images(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client
                pipeline_module._new_seed = original_new_seed

            self.assertEqual(captured, {})
            segment = store.list_segments(project_id)[0]
            self.assertIsNone(segment["avatar_image_path"])
            self.assertEqual(segment["clip_path"], "old-clip.mp4")
            self.assertEqual(segment["video_approved"], 1)

    def test_clip_variables_prefer_avatar_image_when_available(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=3.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path="base.png", avatar_image_path="avatar.png")

            project = store.get_project(project_id)
            segment = store.list_segments(project_id)[0]
            variables = pipeline._variables(project, segment, prefer_avatar=True)

            self.assertEqual(variables["image_path"], "avatar.png")
            self.assertEqual(variables["base_image_path"], "base.png")
            self.assertEqual(variables["avatar_image_path"], "avatar.png")
            self.assertEqual(variables["duration"], "3.000")

    def test_avatar_variables_use_default_images_when_project_reference_is_missing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=3.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.build_segments(project_id)
            project = store.get_project(project_id)
            segment = store.list_segments(project_id)[0]

            variables = pipeline._variables(project, segment)

            self.assertTrue(variables["reference_image_path"].replace("\\", "/").endswith("images/avatar.jpeg"))
            self.assertTrue(variables["fullbody_reference_image_path"].replace("\\", "/").endswith("images/avatar_fullbody.png"))

    def test_avatar_workflow_injects_base_image_and_project_avatar_image(self):
        workflow = {
            "base": {"class_type": "LoadImage", "inputs": {"image": "old-base.png"}},
            "avatar": {"class_type": "LoadImage", "inputs": {"image": "old-avatar.png"}},
        }
        variables = {
            "input_image_path": "segment.png",
            "reference_image_path": "project-avatar.jpeg",
            "fullbody_reference_image_path": "fullbody.png",
        }

        import VocaVid.pipeline as pipeline_module

        injected = pipeline_module._inject_avatar_load_images(workflow, variables)

        self.assertEqual(injected["base"]["inputs"]["image"], "segment.png")
        self.assertEqual(injected["avatar"]["inputs"]["image"], "project-avatar.jpeg")

    def test_avatar_workflow_injects_editable_prompt_context(self):
        workflow = {
            "positive": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "old prompt"},
                "_meta": {"title": "CLIP Text Encode (Positive Prompt)"},
            }
        }
        variables = {
            "image_prompt": "focus singer on stage",
            "scene_plan": "chorus performance with microphone",
            "genre": "industrial rock",
            "global_style": "cinematic",
            "avatar_identity_context": "female avatar; oval face, dark eyes",
        }

        import VocaVid.pipeline as pipeline_module

        injected = pipeline_module._inject_avatar_prompt(workflow, variables)

        prompt = injected["positive"]["inputs"]["text"]
        self.assertIn("replacing only the primary focus person", prompt)
        self.assertIn("focus singer on stage", prompt)
        self.assertIn("chorus performance with microphone", prompt)
        self.assertIn("female avatar; oval face, dark eyes", prompt)
        self.assertIn("Do not alter non-focus people", prompt)

    def test_avatar_workflow_uses_fullbody_avatar_when_project_avatar_is_empty(self):
        workflow = {
            "base": {"class_type": "LoadImage", "inputs": {"image": "old-base.png"}},
            "avatar": {"class_type": "LoadImage", "inputs": {"image": "old-avatar.png"}},
        }
        variables = {
            "input_image_path": "segment.png",
            "reference_image_path": "",
            "fullbody_reference_image_path": "fullbody.png",
        }

        import VocaVid.pipeline as pipeline_module

        injected = pipeline_module._inject_avatar_load_images(workflow, variables)

        self.assertEqual(injected["base"]["inputs"]["image"], "segment.png")
        self.assertEqual(injected["avatar"]["inputs"]["image"], "fullbody.png")

    def test_generate_clips_injects_image_audio_and_duration_into_video_workflow(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.5)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 4.5, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "imageaudiotovideo.json").write_text(
                '{"269":{"class_type":"LoadImage","inputs":{"image":"old.png"}},"276":{"class_type":"LoadAudio","inputs":{"audio":"old.wav","audioUI":"old"}},"340:319":{"class_type":"PrimitiveStringMultiline","inputs":{"value":"old prompt"},"_meta":{"title":"Prompt"}},"340:331":{"class_type":"PrimitiveFloat","inputs":{"value":8},"_meta":{"title":"Duration"}},"341":{"class_type":"SaveVideo","inputs":{"filename_prefix":"old","video":["1",0]}}}',
                encoding="utf-8",
            )
            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path="base.png", avatar_image_path="avatar.png", video_prompt="manual camera push")
            comfy_output = root / "comfy" / "clip.mp4"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"mp4")
            captured = {}

            class FakeClient:
                def __init__(self, base_url):
                    self.base_url = base_url

                def run_workflow(self, workflow, variables):
                    captured["workflow"] = workflow
                    captured["variables"] = variables
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.generate_clips(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client

            workflow = captured["workflow"]
            segment = store.list_segments(project_id)[0]
            self.assertEqual(workflow["269"]["inputs"]["image"], "avatar.png")
            self.assertEqual(workflow["276"]["inputs"]["audio"], str(root / segment["audio_path"]))
            self.assertEqual(workflow["340:319"]["inputs"]["value"], "manual camera push")
            self.assertEqual(workflow["340:331"]["inputs"]["value"], 5.0)
            self.assertIn("demo/clips", segment["clip_path"].replace("\\", "/"))

    def test_generate_clips_randomizes_video_workflow_seed_inputs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.5)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 4.5, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "imageaudiotovideo.json").write_text(
                '{"noise_a":{"class_type":"RandomNoise","inputs":{"noise_seed":42}},"noise_b":{"class_type":"RandomNoise","inputs":{"noise_seed":926348162336178}},"sampler":{"class_type":"Sampler","inputs":{"seed":1,"sampling_mode.seed":0}},"341":{"class_type":"SaveVideo","inputs":{"filename_prefix":"old","video":["1",0]}}}',
                encoding="utf-8",
            )
            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path="base.png")
            comfy_output = root / "comfy" / "clip.mp4"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"mp4")
            captured = {}

            class FakeClient:
                def __init__(self, base_url):
                    pass

                def run_workflow(self, workflow, variables):
                    captured["workflow"] = workflow
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            original_new_seed = pipeline_module._new_seed
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline_module._new_seed = lambda: 123456789
                pipeline.generate_clips(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client
                pipeline_module._new_seed = original_new_seed

            workflow = captured["workflow"]
            self.assertEqual(workflow["noise_a"]["inputs"]["noise_seed"], 123456789)
            self.assertEqual(workflow["noise_b"]["inputs"]["noise_seed"], 123456789)
            self.assertEqual(workflow["sampler"]["inputs"]["seed"], 123456789)
            self.assertEqual(workflow["sampler"]["inputs"]["sampling_mode.seed"], 123456789)

    def test_generate_clips_skips_approved_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.5)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 4.5, 0.9)])
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "imageaudiotovideo.json").write_text(
                '{"341":{"class_type":"SaveVideo","inputs":{"filename_prefix":"old","video":["1",0]}}}',
                encoding="utf-8",
            )
            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path="base.png", clip_path="old-clip.mp4", video_approved=1)
            comfy_output = root / "comfy" / "clip.mp4"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"mp4")

            class FakeClient:
                def __init__(self, base_url):
                    pass

                def run_workflow(self, workflow, variables):
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.generate_clips(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client

            segment = store.list_segments(project_id)[0]
            self.assertEqual(segment["clip_path"], "old-clip.mp4")
            self.assertEqual(segment["video_approved"], 1)

    def test_generate_video_prompts_skips_approved_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 4, 0.9)])
            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, prompt="old image prompt", clip_path="old-clip.mp4", video_approved=1)

            pipeline.generate_video_prompts(project_id, [0])

            segment = store.list_segments(project_id)[0]
            self.assertIsNone(segment["video_prompt"])
            self.assertEqual(segment["clip_path"], "old-clip.mp4")
            self.assertEqual(segment["video_approved"], 1)

    def test_generate_clips_adds_project_transition_handle_to_video_duration(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=4.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 1,
                    "chorus_group_size": 1,
                    "transition_handle_seconds": 0.75,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 4.0, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "imageaudiotovideo.json").write_text(
                '{"269":{"class_type":"LoadImage","inputs":{"image":"old.png"}},"276":{"class_type":"LoadAudio","inputs":{"audio":"old.wav"}},"340:331":{"class_type":"PrimitiveFloat","inputs":{"value":8},"_meta":{"title":"Duration"}},"341":{"class_type":"SaveVideo","inputs":{"filename_prefix":"old","video":["1",0]}}}',
                encoding="utf-8",
            )
            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path="base.png")
            comfy_output = root / "comfy" / "clip.mp4"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"mp4")
            captured = {}

            class FakeClient:
                def __init__(self, base_url):
                    pass

                def run_workflow(self, workflow, variables):
                    captured["workflow"] = workflow
                    captured["variables"] = variables
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.generate_clips(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client

            self.assertEqual(captured["variables"]["duration"], "4.750")
            self.assertEqual(captured["workflow"]["340:331"]["inputs"]["value"], 4.75)

    def test_generate_clips_uses_image_audio_video_workflow_for_chorus_segments_too(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=3.0)
            lyrics.write_text("[Chorus]\nHook\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "imageaudiotovideo.json").write_text(
                '{"269":{"class_type":"LoadImage","inputs":{"image":"old.png"}},"276":{"class_type":"LoadAudio","inputs":{"audio":"old.wav"}},"340:331":{"class_type":"PrimitiveFloat","inputs":{"value":8},"_meta":{"title":"Duration"}},"341":{"class_type":"SaveVideo","inputs":{"filename_prefix":"old","video":["1",0]}}}',
                encoding="utf-8",
            )
            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, image_path="chorus.png")
            comfy_output = root / "comfy" / "clip.mp4"
            comfy_output.parent.mkdir()
            comfy_output.write_bytes(b"mp4")

            class FakeClient:
                def __init__(self, base_url):
                    pass

                def run_workflow(self, workflow, variables):
                    return type("Result", (), {"ok": True, "output_files": [str(comfy_output)], "text_outputs": [], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.generate_clips(project_id, [0])
            finally:
                pipeline_module.ComfyClient = original_client

            self.assertTrue(store.list_segments(project_id)[0]["clip_path"])

    def test_generate_scene_plan_fallback_updates_segments_before_prompts(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "genre": "industrial rock",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 2, 0.9), LineTiming(1, 2, 4, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)

            pipeline.generate_scene_plan(project_id)
            pipeline.generate_prompts(project_id)

            project = store.get_project(project_id)
            lyric_segment = next(row for row in store.list_segments(project_id) if row["kind"] == "lyrics")
            self.assertIn("Fallback scene plan used", project["scene_plan"])
            self.assertIn("industrial rock", lyric_segment["scene_plan"])
            self.assertIn("Scene plan:", lyric_segment["prompt"])
            self.assertIn(lyric_segment["scene_plan"], lyric_segment["prompt"])

    def test_generate_scene_plan_uses_video_bible_before_segment_plan(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n[Chorus]\nHook\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "genre": "industrial rock",
                    "lyric_group_size": 2,
                    "chorus_group_size": 1,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(
                project_id,
                [
                    LineTiming(0, 0, 2, 0.9),
                    LineTiming(1, 2, 4, 0.9),
                    LineTiming(2, 4, 6, 0.9),
                ],
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "promptgen.json").write_text('{"1": {"class_type": "TextGenerate", "inputs": {"prompt": ""}}}', encoding="utf-8")
            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)
            captured_prompts = []

            class FakeClient:
                def __init__(self, base_url):
                    self.base_url = base_url

                def run_workflow(self, workflow, variables):
                    captured_prompts.append(workflow["1"]["inputs"]["prompt"])
                    if len(captured_prompts) == 1:
                        return type("Result", (), {"ok": True, "output_files": [], "text_outputs": ["Core concept: lone fire becomes collective ritual.\nChorus escalation plan: first close, then wide and massive."], "error": ""})()
                    return type("Result", (), {"ok": True, "output_files": [], "text_outputs": ["0: memory shot, low dolly through ash\n1: large-scale chorus shot, silhouettes rise behind singer"], "error": ""})()

            import VocaVid.pipeline as pipeline_module

            original_client = pipeline_module.ComfyClient
            try:
                pipeline_module.ComfyClient = FakeClient
                pipeline.generate_scene_plan(project_id)
            finally:
                pipeline_module.ComfyClient = original_client

            project = store.get_project(project_id)
            segments = store.list_segments(project_id)
            self.assertEqual(len(captured_prompts), 2)
            self.assertIn("Create a concise music video bible", captured_prompts[0])
            self.assertIn("Video bible to follow:", captured_prompts[1])
            self.assertIn("lone fire becomes collective ritual", captured_prompts[1])
            self.assertIn("Video bible:", project["scene_plan"])
            self.assertIn("Segment plan:", project["scene_plan"])
            self.assertEqual(segments[0]["scene_plan"], "memory shot, low dolly through ash")
            self.assertEqual(segments[1]["scene_plan"], "large-scale chorus shot, silhouettes rise behind singer")

    def test_save_scene_plan_updates_project_and_matching_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 1,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 2, 0.9), LineTiming(1, 2, 4, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.workflows = WorkflowPaths.defaults(root)
            pipeline.build_segments(project_id)

            pipeline.save_scene_plan(project_id, "0: Manual intro\n1: Manual lyric one\n2: Manual lyric two")
            pipeline.generate_prompts(project_id)

            project = store.get_project(project_id)
            segments = store.list_segments(project_id)
            self.assertEqual(project["scene_plan"], "0: Manual intro\n1: Manual lyric one\n2: Manual lyric two")
            self.assertEqual(segments[0]["scene_plan"], "Manual intro")
            self.assertEqual(segments[1]["scene_plan"], "Manual lyric one")
            self.assertIn("Manual lyric one", segments[1]["prompt"])

    def test_update_segment_timing_persists_manual_values_and_regenerates_audio(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])
            calls = []

            def fake_run(command, check, capture_output, text):
                calls.append(command)
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text(f"wav {command[3]} {command[5]}", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.build_segments(project_id)

            pipeline.update_segment_timing(project_id, 0, 1.25, 4.75)

            segment = store.list_segments(project_id)[0]
            self.assertEqual(segment["start_sec"], 1.25)
            self.assertEqual(segment["end_sec"], 4.75)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[-1][3], "1.250")
            self.assertEqual(calls[-1][5], "4.750")
            self.assertEqual((root / segment["audio_path"]).read_text(encoding="utf-8"), "wav 1.250 4.750")

    def test_update_segment_timing_invalidates_existing_clip_approval(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, clip_path="old.mp4", video_approved=1, status="done")

            pipeline.update_segment_timing(project_id, 0, 1.25, 4.75)

            segment = store.list_segments(project_id)[0]
            self.assertIsNone(segment["clip_path"])
            self.assertEqual(segment["video_approved"], 0)
            self.assertEqual(segment["status"], "pending")

    def test_update_segment_section_persists_refrain_bridge_and_verse_classification(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.build_segments(project_id)

            pipeline.update_segment_section(project_id, 0, "refrain")

            segment = store.list_segments(project_id)[0]
            self.assertEqual(segment["section"], "Refrain")
            self.assertEqual(segment["is_chorus"], 1)
            self.assertEqual(segment["use_reference"], 1)

            pipeline.update_segment_section(project_id, 0, "bridge")

            segment = store.list_segments(project_id)[0]
            self.assertEqual(segment["section"], "Bridge")
            self.assertEqual(segment["is_chorus"], 0)
            self.assertEqual(segment["use_reference"], 0)

            pipeline.update_segment_section(project_id, 0, "verse")

            segment = store.list_segments(project_id)[0]
            self.assertEqual(segment["section"], "Verse")
            self.assertEqual(segment["is_chorus"], 0)
            self.assertEqual(segment["use_reference"], 0)

    def test_video_approval_controls_assemble_guard(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=3.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 3, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, clip_path=str(root / "clip.mp4"))

            self.assertFalse(pipeline.all_videos_approved(project_id))
            with self.assertRaisesRegex(ValueError, "not approved"):
                pipeline.assemble(project_id)

            pipeline.set_segment_video_approved(project_id, 0, True)

            self.assertTrue(pipeline.all_videos_approved(project_id))

    def test_assemble_writes_kdenlive_project_with_transition_handle(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            clip_a = root / "clip-a.mp4"
            clip_b = root / "clip-b.mp4"
            template = root / "template.kdenlive"
            _write_wav(audio, duration_sec=7.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            clip_a.write_bytes(b"a")
            clip_b.write_bytes(b"b")
            template.write_text(
                """<?xml version='1.0' encoding='utf-8'?>
<mlt producer="main_bin">
 <profile frame_rate_num="25" frame_rate_den="1"/>
 <producer id="producer0"><property name="resource">black</property></producer>
 <playlist id="playlist2"/>
 <playlist id="playlist10"/>
 <playlist id="playlist12"/>
 <tractor id="{sequence}">
  <track producer="producer0"/>
  <track producer="playlist2"/>
  <track producer="playlist10"/>
  <track producer="playlist12"/>
 </tractor>
 <playlist id="main_bin"/>
 <tractor id="tractor7"><track producer="{sequence}"/></tractor>
</mlt>
""",
                encoding="utf-8",
            )
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 1,
                    "chorus_group_size": 1,
                    "transition_handle_seconds": 0.75,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 0, 4, 0.9), LineTiming(1, 4, 7, 0.9)])

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.kdenlive_template = template
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, clip_path=str(clip_a), video_approved=1)
            store.update_segment(project_id, 1, clip_path=str(clip_b), video_approved=1)

            result = pipeline.assemble(project_id)

            self.assertEqual(result, root / "outputs" / "demo" / "Demo.kdenlive")
            self.assertTrue(result.exists())
            self.assertEqual(store.get_project(project_id)["final_video_path"], "outputs/demo/Demo.kdenlive")
            xml = result.read_text(encoding="utf-8")
            self.assertIn('out="00:00:04.720"', xml)
            self.assertIn('<property name="kdenlive:docproperties.renderurl">Demo.mp4</property>', xml)
            self.assertIn('<property name="kdenlive:docproperties.renderpath">Demo.mp4</property>', xml)
            self.assertIn('producer="clip0"', xml)
            self.assertIn('producer="clip1"', xml)

    def test_clear_project_removes_generated_state_but_keeps_project_inputs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "reference_image_paths": ["ref.png"],
                    "lyric_group_size": 2,
                    "chorus_group_size": 4,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(project_id, [LineTiming(0, 1, 3, 0.8)])
            store.update_line(
                project_id,
                0,
                prompt="prompt",
                image_path="image.png",
                clip_path="clip.mp4",
                status="failed",
                error="boom",
            )
            store.update_project(project_id, scene_plan="full plan")
            store.set_final_video(project_id, root / "outputs" / "demo" / "final.mp4")
            store.mark_project_action_used(project_id, "align")

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.build_segments(project_id)
            generated_file = root / "outputs" / "demo" / "junk.txt"
            generated_file.write_text("generated", encoding="utf-8")

            pipeline.clear_project(project_id)

            project = store.get_project(project_id)
            line = store.list_lines(project_id)[0]
            self.assertEqual(project["audio_path"], str(audio))
            self.assertEqual(project["lyrics_path"], str(lyrics))
            self.assertEqual(project["global_style_prompt"], "cinematic")
            self.assertEqual(project["reference_image_paths"], '["ref.png"]')
            self.assertIsNone(project["final_video_path"])
            self.assertIsNone(project["scene_plan"])
            self.assertEqual(store.list_segments(project_id), [])
            self.assertEqual(store.list_used_project_actions(project_id), set())
            self.assertFalse((root / "outputs" / "demo").exists())
            self.assertIsNone(line["start_sec"])
            self.assertIsNone(line["end_sec"])
            self.assertIsNone(line["confidence"])
            self.assertIsNone(line["prompt"])
            self.assertIsNone(line["image_path"])
            self.assertIsNone(line["clip_path"])
            self.assertEqual(line["status"], "pending")
            self.assertEqual(line["error"], "")

    def test_render_final_mp4_uses_named_output_for_existing_legacy_kdenlive_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            project_path = root / "outputs" / "feuer-und-stahl---02---kampf-und-ehre" / "final.kdenlive"
            audio.write_text("wav", encoding="utf-8")
            lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
            project_path.parent.mkdir(parents=True)
            project_path.write_text("<mlt/>", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Feuer und Stahl - 02 - Kampf und Ehre",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.update_project(project_id, final_video_path="outputs/feuer-und-stahl---02---kampf-und-ehre/final.kdenlive")
            calls = []

            def fake_render(input_path, output_path):
                calls.append((input_path, output_path))
                output_path.write_bytes(b"mp4")
                return output_path

            pipeline = Pipeline(store, root / "outputs")
            with patch("VocaVid.pipeline.render_kdenlive_project", fake_render):
                result = pipeline.render_final_mp4(project_id)

            expected = root / "outputs" / "feuer-und-stahl---02---kampf-und-ehre" / "02 - Kampf und Ehre.mp4"
            self.assertEqual(result, expected)
            self.assertEqual(calls, [(project_path, expected)])

    def test_regroup_project_realigned_existing_line_timings_and_rebuilds_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=30.0)
            lyrics.write_text("[Verse]\nOne two\nThree four\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 1,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.set_timings(
                project_id,
                [
                    LineTiming(0, 0.0, 15.0, 0.0),
                    LineTiming(1, 15.0, 30.0, 0.0),
                ],
            )
            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            pipeline.build_segments(project_id)
            store.update_segment(project_id, 0, prompt="old prompt", image_path="old.png", clip_path="old.mp4", video_approved=1)
            store.mark_project_action_used(project_id, "segments")
            store.update_project(project_id, lyric_group_size=2)

            transcript = [
                TranscriptWord("One", 10.0, 10.3),
                TranscriptWord("two", 10.35, 10.7),
                TranscriptWord("Three", 12.0, 12.4),
                TranscriptWord("four", 12.45, 12.9),
            ]
            with patch("VocaVid.pipeline.transcribe_words_with_fallback", return_value=transcript) as transcribe:
                pipeline.regroup_project(project_id)

            transcribe.assert_called_once()
            lines = store.list_lines(project_id)
            segments = store.list_segments(project_id)
            self.assertEqual([(line["start_sec"], line["end_sec"]) for line in lines], [(10.0, 10.7), (12.0, 12.9)])
            self.assertEqual([segment["kind"] for segment in segments[:2]], ["gap", "lyrics"])
            self.assertTrue(all(segment["kind"] == "gap" for segment in segments[2:]))
            self.assertEqual(segments[0]["section"], "Instrumental intro")
            self.assertEqual(segments[1]["clean_text"], "One two\nThree four")
            self.assertTrue(all(segment["prompt"] is None for segment in segments))
            self.assertTrue(all(segment["image_path"] is None for segment in segments))
            self.assertTrue(all(segment["clip_path"] is None for segment in segments))
            self.assertTrue(all(segment["video_approved"] == 0 for segment in segments))
            self.assertEqual(store.list_used_project_actions(project_id), set())

    def test_regroup_project_logs_long_running_stages(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=30.0)
            lyrics.write_text("[Verse]\nOne two\nThree four\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)
            transcript = [
                TranscriptWord("One", 10.0, 10.3),
                TranscriptWord("two", 10.35, 10.7),
                TranscriptWord("Three", 12.0, 12.4),
                TranscriptWord("four", 12.45, 12.9),
            ]

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", return_value=transcript):
                with self.assertLogs("VocaVid.pipeline", level="INFO") as logs:
                    pipeline.regroup_project(project_id)

            output = "\n".join(logs.output)
            self.assertIn("regroup start", output)
            self.assertIn("clear generated state done", output)
            self.assertIn("whisper transcribe start", output)
            self.assertIn("whisper transcribe done", output)
            self.assertIn("timings stored", output)
            self.assertIn("build segments start", output)
            self.assertIn("split audio done", output)
            self.assertIn("regroup done", output)

    def test_regroup_project_resolves_legacy_VocaVid_upload_paths(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            app_root = root / ".VocaVid"
            current_audio = app_root / "uploads" / "demo" / "song.wav"
            legacy_audio = root / "old-location" / ".VocaVid" / "uploads" / "demo" / "song.wav"
            lyrics = root / "lyrics.txt"
            current_audio.parent.mkdir(parents=True)
            _write_wav(current_audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\n", encoding="utf-8")
            store = Store(root / "test.sqlite3")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(legacy_audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            calls = []

            def fake_run(command, check, capture_output, text):
                calls.append(command)
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, app_root / "outputs", ffmpeg_runner=fake_run)

            pipeline.regroup_project(project_id)

            self.assertEqual([segment["kind"] for segment in store.list_segments(project_id)], ["gap", "lyrics"])
            self.assertIn(str(current_audio), calls[0])

    def test_regroup_project_recreates_missing_line_timings_before_rebuilding_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=6.0)
            lyrics.write_text("[Verse]\nOne\nTwo\nThree\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", side_effect=RuntimeError("offline")):
                with self.assertRaises(RuntimeError):
                    pipeline.regroup_project(project_id)

            lines = store.list_lines(project_id)
            segments = store.list_segments(project_id)
            self.assertTrue(all(line["start_sec"] is None and line["end_sec"] is None for line in lines))
            self.assertEqual(segments, [])

    def test_regroup_project_fills_missing_line_timings_evenly_before_rebuilding_segments(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            audio = root / "song.wav"
            lyrics = root / "lyrics.txt"
            _write_wav(audio, duration_sec=30.0)
            lyrics.write_text("[Verse]\nOne two\nThree four\n", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                    "lyric_group_size": 2,
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            def fake_run(command, check, capture_output, text):
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(command[-1]).write_text("wav", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            pipeline = Pipeline(store, root / "outputs", ffmpeg_runner=fake_run)

            with patch("VocaVid.pipeline.transcribe_words_with_fallback", side_effect=RuntimeError("offline")) as transcribe:
                with self.assertRaises(RuntimeError):
                    pipeline.regroup_project(project_id)

            transcribe.assert_called_once()
            lines = store.list_lines(project_id)
            segments = store.list_segments(project_id)
            self.assertTrue(all(line["start_sec"] is None and line["end_sec"] is None for line in lines))
            self.assertEqual(segments, [])

    def test_localize_comfy_output_copies_generated_files_into_project_folder(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "comfy-output" / "VocaVid" / "project-1" / "segment-0.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"png-data")
            store = Store(root / "test.sqlite3")
            pipeline = Pipeline(store, root / "outputs")

            copied = pipeline._localize_comfy_output(
                project={"comfy_base_url": "http://127.0.0.1:8188"},
                project_id=7,
                item_kind="segment",
                item_index=3,
                output_field="image_path",
                output_path=str(source),
            )

            self.assertEqual(copied, root / "outputs" / "project-7" / "images" / "segment-003.png")
            self.assertEqual(copied.read_bytes(), b"png-data")

    def test_localize_comfy_output_downloads_relative_comfy_paths_into_project_folder(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            pipeline = Pipeline(store, root / "outputs")
            downloads = []

            def fake_download(url, target):
                downloads.append((url, target))
                target.write_bytes(b"movie")

            pipeline._download_file = fake_download

            copied = pipeline._localize_comfy_output(
                project={"comfy_base_url": "http://127.0.0.1:8188"},
                project_id=7,
                item_kind="segment",
                item_index=3,
                output_field="clip_path",
                output_path="VocaVid/project-7/raw-clip.mp4",
            )

            self.assertEqual(copied, root / "outputs" / "project-7" / "clips" / "segment-003.mp4")
            self.assertEqual(copied.read_bytes(), b"movie")
            self.assertEqual(len(downloads), 1)
            self.assertIn("filename=raw-clip.mp4", downloads[0][0])
            self.assertIn("subfolder=VocaVid%2Fproject-7", downloads[0][0])


def _write_wav(path: Path, duration_sec: float) -> None:
    sample_rate = 8000
    frames = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)

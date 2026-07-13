import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from VocaVid.alignment import TranscriptWord
from VocaVid.lyrics import parse_suno_lyrics
from VocaVid.reels.audio import audio_window_score
from VocaVid.reels.candidates import center_crop, generate_candidates
from VocaVid.reels.lyrics import align_project_rows_to_words, project_rows_to_sections
from VocaVid.reels.media import metadata_from_ffprobe_json
from VocaVid.reels.models import ReelCandidate, ReelVideoMetadata
from VocaVid.reels.pipeline import ReelsPipeline
from VocaVid.reels.render import render_reel_command
from VocaVid.store import Store


class ReelsTests(unittest.TestCase):
    def test_store_persists_reel_analyses_and_candidates(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            store = Store(Path(directory) / "VocaVid.sqlite3")
            lyrics = parse_suno_lyrics("[Verse]\nHello\n[Chorus]\nHook\n")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": "song.wav", "lyrics_path": "lyrics.txt", "global_style_prompt": "style"},
                lyrics,
            )

            analysis_id = store.create_reel_analysis(project_id, "D:/exports/final.mp4")
            candidate = ReelCandidate(
                label="Chorus 1",
                start_sec=10.0,
                end_sec=40.0,
                score=1.7,
                reasons=["hook"],
                crop={"mode": "static_center", "crop_x": 656, "crop_y": 0, "crop_width": 608, "crop_height": 1080},
            )
            store.update_reel_analysis(analysis_id, status="done", metadata_json=json.dumps({"duration": 120}))
            store.replace_reel_candidates(analysis_id, [candidate])

            analysis = store.latest_reel_analysis(project_id)
            candidates = store.list_reel_candidates(analysis_id)

            self.assertEqual(analysis["status"], "done")
            self.assertEqual(analysis["source_video_path"], "D:/exports/final.mp4")
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["label"], "Chorus 1")
            self.assertEqual(json.loads(candidates[0]["reasons_json"]), ["hook"])

    def test_ffprobe_metadata_requires_video_audio_and_duration(self):
        metadata = metadata_from_ffprobe_json(
            {
                "format": {"duration": "123.45"},
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "25/1", "codec_name": "h264"},
                    {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
                ],
            }
        )

        self.assertEqual(metadata.duration, 123.45)
        self.assertEqual(metadata.width, 1920)
        self.assertEqual(metadata.height, 1080)
        self.assertEqual(metadata.fps, 25.0)
        self.assertEqual(metadata.audio_sample_rate, 48000)

    def test_project_rows_to_sections_preserves_repeated_choruses(self):
        rows = [
            {"line_index": 0, "section": "Verse", "is_chorus": 0, "clean_text": "A", "start_sec": 0.0, "end_sec": 8.0},
            {"line_index": 1, "section": "Chorus", "is_chorus": 1, "clean_text": "Hook", "start_sec": 8.0, "end_sec": 20.0},
            {"line_index": 2, "section": "Verse", "is_chorus": 0, "clean_text": "B", "start_sec": 20.0, "end_sec": 30.0},
            {"line_index": 3, "section": "Chorus", "is_chorus": 1, "clean_text": "Hook", "start_sec": 30.0, "end_sec": 45.0},
        ]

        sections = project_rows_to_sections(rows)

        self.assertEqual([section.type for section in sections], ["Verse", "Chorus", "Verse", "Chorus"])
        self.assertEqual([section.occurrence for section in sections], [1, 1, 2, 2])
        self.assertEqual(sections[3].start_sec, 30.0)

    def test_align_project_rows_to_words_uses_whisper_times_for_reel_sections(self):
        rows = [
            {"line_index": 0, "section": "Verse", "is_chorus": 0, "clean_text": "Hello world", "start_sec": 0.0, "end_sec": 2.0},
            {"line_index": 1, "section": "Chorus", "is_chorus": 1, "clean_text": "Big hook", "start_sec": 2.0, "end_sec": 4.0},
        ]
        words = [
            TranscriptWord("hello", 10.0, 10.3),
            TranscriptWord("world", 10.4, 10.8),
            TranscriptWord("big", 42.0, 42.2),
            TranscriptWord("hook", 42.3, 42.8),
        ]

        aligned_rows, timings = align_project_rows_to_words(rows, words, total_duration_sec=90.0)
        sections = project_rows_to_sections(aligned_rows)

        self.assertEqual(timings[0].start_sec, 10.0)
        self.assertEqual(timings[1].start_sec, 42.0)
        self.assertEqual(sections[1].type, "Chorus")
        self.assertEqual(sections[1].start_sec, 42.0)
        self.assertEqual(sections[1].end_sec, 42.8)

    def test_candidate_generation_limits_duration_and_prefers_final_chorus(self):
        metadata = ReelVideoMetadata(duration=140.0, width=1920, height=1080, fps=25.0)
        sections = project_rows_to_sections(
            [
                {"segment_index": 0, "section": "Verse", "is_chorus": 0, "clean_text": "Verse", "start_sec": 0.0, "end_sec": 35.0},
                {"segment_index": 1, "section": "Chorus", "is_chorus": 1, "clean_text": "Hook 1", "start_sec": 35.0, "end_sec": 75.0},
                {"segment_index": 2, "section": "Bridge", "is_chorus": 0, "clean_text": "Bridge", "start_sec": 75.0, "end_sec": 95.0},
                {"segment_index": 3, "section": "Chorus", "is_chorus": 1, "clean_text": "Hook 2", "start_sec": 95.0, "end_sec": 135.0},
            ]
        )

        candidates = generate_candidates(sections, metadata, limit=5)

        self.assertTrue(candidates)
        self.assertTrue(all(candidate.duration_sec <= 60.0 for candidate in candidates))
        self.assertIn("Final Chorus", {candidate.label.rsplit(" ", 1)[0] for candidate in candidates})

    def test_candidate_generation_returns_more_candidates_by_default(self):
        metadata = ReelVideoMetadata(duration=220.0, width=1920, height=1080, fps=25.0)
        rows = []
        start = 0.0
        for index in range(12):
            section = "Chorus" if index % 2 else "Verse"
            rows.append({"segment_index": index, "section": section, "is_chorus": int(section == "Chorus"), "clean_text": section, "start_sec": start, "end_sec": start + 12.0})
            start += 14.0

        candidates = generate_candidates(project_rows_to_sections(rows), metadata)

        self.assertEqual(len(candidates), 10)

    def test_audio_features_boost_energetic_candidates_and_strongest_verse(self):
        metadata = ReelVideoMetadata(duration=90.0, width=1920, height=1080, fps=25.0)
        sections = project_rows_to_sections(
            [
                {"segment_index": 0, "section": "Verse", "is_chorus": 0, "clean_text": "Quiet", "start_sec": 0.0, "end_sec": 12.0},
                {"segment_index": 1, "section": "Chorus", "is_chorus": 1, "clean_text": "Hook", "start_sec": 14.0, "end_sec": 18.0},
                {"segment_index": 2, "section": "Verse", "is_chorus": 0, "clean_text": "Loud", "start_sec": 20.0, "end_sec": 32.0},
                {"segment_index": 3, "section": "Chorus", "is_chorus": 1, "clean_text": "Hook", "start_sec": 40.0, "end_sec": 55.0},
            ]
        )
        features = [
            {"time": 3.0, "rms": 0.1, "onset_strength": 0.1, "beat": False},
            {"time": 24.0, "rms": 1.0, "onset_strength": 0.9, "beat": True},
            {"time": 26.0, "rms": 0.9, "onset_strength": 0.8, "beat": True},
            {"time": 45.0, "rms": 0.4, "onset_strength": 0.3, "beat": True},
        ]

        candidates = generate_candidates(sections, metadata, limit=5, audio_features=features)
        strong_verse = next(candidate for candidate in candidates if candidate.label == "Strong Verse")

        self.assertGreaterEqual(strong_verse.start_sec, 19.5)
        self.assertIn("energy", " ".join(strong_verse.reasons))
        self.assertGreater(audio_window_score(features, 20.0, 32.0)["score"], audio_window_score(features, 0.0, 12.0)["score"])

    def test_center_crop_and_render_command_make_vertical_output(self):
        metadata = ReelVideoMetadata(duration=120.0, width=1920, height=1080, fps=25.0)
        crop = center_crop(metadata)
        candidate = ReelCandidate("Hook", 10.0, 40.0, 1.0, crop=crop)

        command = render_reel_command("input.mp4", "preview.mp4", candidate, 540, 960)

        self.assertEqual(crop["crop_width"], 608)
        self.assertEqual(crop["crop_height"], 1080)
        self.assertIn("crop=608:1080:656:0,scale=540:960", command)
        self.assertIn("h264_mf", command)
        self.assertIn("8M", command)
        self.assertIn("-t", command)
        self.assertIn("30.000", command)

        x264_command = render_reel_command("input.mp4", "preview.mp4", candidate, 540, 960, codec="libx264")
        self.assertIn("libx264", x264_command)
        self.assertIn("-crf", x264_command)

    def test_reels_pipeline_transcribes_and_aligns_project_lyrics_before_scoring(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "final.mp4"
            source.write_bytes(b"fake mp4")
            store = Store(root / "VocaVid.sqlite3")
            project_id = store.create_project(
                {
                    "name": "Demo",
                    "audio_path": "song.wav",
                    "lyrics_path": "lyrics.txt",
                    "global_style_prompt": "style",
                    "whisper_model_size": "large-v3",
                },
                parse_suno_lyrics("[Verse]\nHello world\n[Chorus]\nBig hook\n"),
            )

            def fake_runner(command, capture_output=True, text=True, check=False):
                class Result:
                    returncode = 0
                    stderr = ""
                    stdout = ""

                result = Result()
                if Path(command[0]).name.lower() in {"ffprobe", "ffprobe.exe"}:
                    result.stdout = json.dumps(
                        {
                            "format": {"duration": "90.0"},
                            "streams": [
                                {"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "25/1"},
                                {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
                            ],
                        }
                    )
                return result

            transcript = [
                TranscriptWord("hello", 10.0, 10.3),
                TranscriptWord("world", 10.4, 10.8),
                TranscriptWord("big", 42.0, 42.2),
                TranscriptWord("hook", 42.3, 42.8),
            ]
            audio_features = [{"time": 42.2, "rms": 1.0, "onset_strength": 0.8, "beat": True}]
            with (
                patch("VocaVid.reels.pipeline.transcribe_words_with_fallback", return_value=transcript) as transcribe,
                patch("VocaVid.reels.pipeline.analyze_audio_features", return_value=audio_features) as analyze_audio,
            ):
                ReelsPipeline(store, root, runner=fake_runner).analyze(project_id, str(source))

            analysis = store.latest_reel_analysis(project_id)
            candidates = store.list_reel_candidates(int(analysis["id"]))
            alignment = json.loads(analysis["lyric_alignment_json"])
            transcript_json = json.loads(analysis["transcript_json"])
            stored_audio_features = json.loads(analysis["audio_features_json"])

            self.assertEqual(analysis["status"], "done")
            self.assertEqual(alignment[1]["type"], "Chorus")
            self.assertEqual(alignment[1]["start_sec"], 42.0)
            self.assertEqual(transcript_json[2]["text"], "big")
            self.assertEqual(stored_audio_features, audio_features)
            self.assertTrue(any(candidate["label"].startswith("Chorus") for candidate in candidates))
            self.assertTrue(any("energy" in candidate["reasons_json"] for candidate in candidates))
            transcribe.assert_called_once()
            self.assertEqual(transcribe.call_args.kwargs["model_size"], "large-v3")
            analyze_audio.assert_called_once()

    def test_reels_pipeline_exports_reels_to_project_reels_folder(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "outputs" / "demo" / "finished.mp4"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"mp4")
            store = Store(root / "VocaVid.sqlite3")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": "song.wav", "lyrics_path": "lyrics.txt", "global_style_prompt": "style"},
                parse_suno_lyrics("[Verse]\nHello\n"),
            )
            analysis_id = store.create_reel_analysis(project_id, "outputs/demo/finished.mp4")
            store.update_reel_analysis(
                analysis_id,
                status="done",
                metadata_json=json.dumps({"duration": 90.0, "width": 1920, "height": 1080, "fps": 25.0}),
            )
            store.replace_reel_candidates(
                analysis_id,
                [ReelCandidate("Hook", 10.0, 35.0, 1.0, crop={"mode": "static_center", "crop_x": 0, "crop_y": 0, "crop_width": 1080, "crop_height": 1080})],
            )
            candidate_id = int(store.list_reel_candidates(analysis_id)[0]["id"])
            calls = []

            def fake_render(source_path, target_path, candidate, width, height, runner=None):
                calls.append((Path(source_path), Path(target_path), width, height))
                Path(target_path).write_bytes(b"reel")

            with patch("VocaVid.reels.pipeline.render_reel", side_effect=fake_render):
                ReelsPipeline(store, root).export(project_id, analysis_id, candidate_id)

            candidate = store.get_reel_candidate(candidate_id)
            self.assertEqual(calls[0][0], source)
            self.assertEqual(calls[0][1], root / "outputs" / "demo" / "reels" / f"reel-hook-{candidate_id:03d}-export.mp4")
            self.assertEqual(calls[0][2:], (1080, 1920))
            self.assertEqual(candidate["export_path"], f"outputs/demo/reels/reel-hook-{candidate_id:03d}-export.mp4")

    def test_reels_pipeline_can_clear_and_delete_candidate_outputs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "VocaVid.sqlite3")
            project_id = store.create_project(
                {"name": "Demo", "audio_path": "song.wav", "lyrics_path": "lyrics.txt", "global_style_prompt": "style"},
                parse_suno_lyrics("[Verse]\nHello\n"),
            )
            analysis_id = store.create_reel_analysis(project_id, "outputs/demo/finished.mp4")
            store.replace_reel_candidates(analysis_id, [ReelCandidate("Hook", 1.0, 9.0, 1.0)])
            candidate_id = int(store.list_reel_candidates(analysis_id)[0]["id"])
            preview = root / "outputs" / "demo" / "reels" / "previews" / "reel-hook-001-preview.mp4"
            export = root / "outputs" / "demo" / "reels" / "reel-hook-001-export.mp4"
            preview.parent.mkdir(parents=True)
            export.parent.mkdir(parents=True, exist_ok=True)
            preview.write_bytes(b"preview")
            export.write_bytes(b"export")
            store.update_reel_candidate(
                candidate_id,
                status="done",
                preview_path="outputs/demo/reels/previews/reel-hook-001-preview.mp4",
                export_path="outputs/demo/reels/reel-hook-001-export.mp4",
            )
            pipeline = ReelsPipeline(store, root)

            pipeline.clear_candidate_outputs(project_id, analysis_id, candidate_id)
            candidate = store.get_reel_candidate(candidate_id)

            self.assertFalse(preview.exists())
            self.assertFalse(export.exists())
            self.assertEqual(candidate["status"], "pending")
            self.assertIsNone(candidate["preview_path"])
            self.assertIsNone(candidate["export_path"])

            pipeline.delete_candidate(project_id, analysis_id, candidate_id)
            self.assertEqual(store.list_reel_candidates(analysis_id), [])


if __name__ == "__main__":
    unittest.main()

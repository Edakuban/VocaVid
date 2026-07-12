import tempfile
import unittest
from pathlib import Path

from VocaVid.lyrics import parse_suno_lyrics
from VocaVid.models import RenderSegment
from VocaVid.pipeline import Pipeline
from VocaVid.store import Store


class ProjectOutputPathTests(unittest.TestCase):
    def test_localized_outputs_use_project_title_folder(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            source = root / "comfy-output" / "segment.png"
            lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            source.parent.mkdir(parents=True)
            source.write_text("image", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Feuer und Stahl - 01 - Feuer und Stahl",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            pipeline = Pipeline(store, root / "outputs")

            copied = pipeline._localize_comfy_output(
                store.get_project(project_id),
                project_id=project_id,
                item_kind="segment",
                item_index=0,
                output_field="image_path",
                output_path=str(source),
            )

            self.assertEqual(
                copied,
                root / "outputs" / "feuer-und-stahl---01---feuer-und-stahl" / "images" / "segment-000.png",
            )

    def test_assemble_writes_kdenlive_file_to_project_title_folder(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            store = Store(root / "test.sqlite3")
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            clip = root / "clip.mp4"
            lyrics.write_text("[Verse]\nHello\n", encoding="utf-8")
            audio.write_text("wav", encoding="utf-8")
            clip.write_text("clip", encoding="utf-8")
            project_id = store.create_project(
                {
                    "name": "Feuer und Stahl - 02 - Kampf und Ehre",
                    "audio_path": str(audio),
                    "lyrics_path": str(lyrics),
                    "global_style_prompt": "cinematic",
                },
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )
            store.replace_segments(
                project_id,
                [
                    RenderSegment(
                        0,
                        "lyrics",
                        "Verse",
                        False,
                        False,
                        [0],
                        "Hello",
                        0.0,
                        1.0,
                        clip_path=str(clip),
                    )
                ],
            )
            store.update_segment(project_id, 0, video_approved=1)
            pipeline = Pipeline(store, root / "outputs")

            result = pipeline.assemble(project_id)

            self.assertEqual(
                result,
                root / "outputs" / "feuer-und-stahl---02---kampf-und-ehre" / "final.kdenlive",
            )

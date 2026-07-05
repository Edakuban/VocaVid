import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from musicvideogen.migrate_relative_paths import migrate
from musicvideogen.store import Store


class RelativePathMigrationTests(unittest.TestCase):
    def test_migrate_converts_internal_database_paths_to_relative_values(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            app_root = Path(directory) / ".musicvideogen"
            db_path = app_root / "musicvideogen.sqlite3"
            Store(db_path)
            legacy_root = Path(directory) / "old" / ".musicvideogen"
            external = r"D:\media\reference.png"
            con = sqlite3.connect(db_path)
            try:
                con.execute(
                    """
                    INSERT INTO projects (
                        id, name, audio_path, lyrics_path, global_style_prompt,
                        reference_image_paths, final_video_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "Demo",
                        str(legacy_root / "uploads" / "demo" / "song.wav"),
                        str(legacy_root / "uploads" / "demo" / "lyrics.txt"),
                        "cinematic",
                        json.dumps([str(legacy_root / "uploads" / "demo" / "references" / "ref.png"), external]),
                        str(legacy_root / "outputs" / "demo" / "final.kdenlive"),
                    ),
                )
                con.execute(
                    """
                    INSERT INTO render_segments (
                        project_id, segment_index, kind, section, is_chorus,
                        source_line_indices, clean_text, start_sec, end_sec,
                        image_path, clip_path, audio_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        0,
                        "lyrics",
                        "Verse",
                        0,
                        "[]",
                        "Hello",
                        0.0,
                        1.0,
                        str(legacy_root / "outputs" / "demo" / "images" / "segment-000.png"),
                        str(legacy_root / "outputs" / "demo" / "clips" / "segment-000.mp4"),
                        str(legacy_root / "outputs" / "demo" / "audio-segments" / "segment-000.wav"),
                    ),
                )
                con.commit()
            finally:
                con.close()

            changed = migrate(app_root)

            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            try:
                project = con.execute("SELECT * FROM projects WHERE id = 1").fetchone()
                segment = con.execute("SELECT * FROM render_segments WHERE project_id = 1").fetchone()
            finally:
                con.close()

            self.assertEqual(changed, 7)
            self.assertEqual(project["audio_path"], "uploads/demo/song.wav")
            self.assertEqual(project["lyrics_path"], "uploads/demo/lyrics.txt")
            self.assertEqual(json.loads(project["reference_image_paths"]), ["uploads/demo/references/ref.png", external])
            self.assertEqual(project["final_video_path"], "outputs/demo/final.kdenlive")
            self.assertEqual(segment["image_path"], "outputs/demo/images/segment-000.png")
            self.assertEqual(segment["clip_path"], "outputs/demo/clips/segment-000.mp4")
            self.assertEqual(segment["audio_path"], "outputs/demo/audio-segments/segment-000.wav")

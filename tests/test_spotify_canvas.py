from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from VocaVid.spotify_canvas import canvas_render_command, normalize_canvas_duration
from VocaVid.store import Store
from VocaVid.ui.projects import _project_actions_html
from VocaVid.ui.spotify_canvas import _spotify_canvas_status_html
from VocaVid.ui.scripts import SCRIPTS


class SpotifyCanvasTests(unittest.TestCase):
    def test_duration_must_be_strictly_between_three_and_eight_seconds(self):
        self.assertEqual(normalize_canvas_duration("6.25"), 6.25)
        for value in (3, 8, 2.99, 8.01):
            with self.assertRaises(ValueError):
                normalize_canvas_duration(value)

    def test_pingpong_render_is_vertical_silent_mp4(self):
        command = canvas_render_command(Path("source.mp4"), Path("canvas.mp4"), 1.5, 6.0, "pingpong")
        joined = " ".join(command)
        self.assertIn("reverse", joined)
        self.assertIn("concat=n=2:v=1:a=0", joined)
        self.assertIn("scale=1080:1920", joined)
        self.assertIn("-an", command)
        self.assertEqual(command[-1], "canvas.mp4")

    def test_store_persists_one_canvas_per_project(self):
        cache_dir = Path(".pycache-codex")
        cache_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache_dir, ignore_cleanup_errors=True) as directory:
            store = Store(Path(directory) / "test.sqlite3")
            store.update_spotify_canvas(7, mode="generated", duration_sec=6.5, prompt="Cyclical smoke")
            store.update_spotify_canvas(7, status="done", export_path="outputs/demo/spotify-canvas/spotify-canvas.mp4")
            canvas = store.get_spotify_canvas(7)
            self.assertEqual(canvas["mode"], "generated")
            self.assertEqual(canvas["duration_sec"], 6.5)
            self.assertEqual(canvas["prompt"], "Cyclical smoke")
            self.assertEqual(canvas["status"], "done")

    def test_project_action_and_modal_offer_both_canvas_routes(self):
        project = {"id": 7, "name": "Demo", "final_video_path": None}
        rows = [{"clip_path": "outputs/demo/clips/segment-000.mp4"}]
        actions = _project_actions_html(project, rows)
        self.assertIn('onclick="openSpotifyCanvasModal()">10. Spotify Canvas', actions)

        candidate = {"label": "Chorus", "export_path": "outputs/demo/reels/chorus.mp4", "preview_path": None}
        scene = {
            "segment_index": 0, "section": "Chorus", "clean_text": "Fire",
            "image_path": "outputs/demo/images/segment-000.png", "avatar_image_path": None,
        }
        html = _spotify_canvas_status_html(project, None, [candidate], [scene])
        self.assertIn("Trim a reel", html)
        self.assertIn("Generate a new loop", html)
        self.assertIn('formaction="/projects/7/spotify-canvas/prompt"', html)
        self.assertIn('action="/projects/7/spotify-canvas/generate"', html)
        self.assertIn("Generate prompt", html)
        self.assertIn('class="spotify-canvas-trim-editor"', html)
        self.assertIn('data-canvas-trim-start type="range"', html)
        self.assertIn('data-canvas-trim-end type="range"', html)
        self.assertIn('data-preview-url="/assets/outputs/demo/reels/chorus.mp4"', html)
        self.assertIn("function setupSpotifyCanvasTrimEditor", SCRIPTS)
        self.assertIn("button.hasAttribute('formaction') ? button.formAction : form.action", SCRIPTS)
        self.assertIn("video.currentTime = start", SCRIPTS)
        self.assertIn("duration > maximum", SCRIPTS)


if __name__ == "__main__":
    unittest.main()

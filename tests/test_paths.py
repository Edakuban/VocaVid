import tempfile
import unittest
from pathlib import Path

from VocaVid.paths import resolve_storage_path, storage_relative_path


class PathStorageTests(unittest.TestCase):
    def test_storage_relative_path_keeps_internal_paths_relative(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            app_root = Path(directory) / ".VocaVid"
            audio = app_root / "uploads" / "demo" / "song.wav"

            self.assertEqual(storage_relative_path(app_root, audio), "uploads/demo/song.wav")

    def test_storage_relative_path_converts_legacy_VocaVid_absolute_paths(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            app_root = Path(directory) / ".VocaVid"
            legacy = r"D:\old\VocaVid\.VocaVid\outputs\demo\clip.mp4"

            self.assertEqual(storage_relative_path(app_root, legacy), "outputs/demo/clip.mp4")

    def test_storage_relative_path_keeps_external_absolute_paths(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            app_root = Path(directory) / ".VocaVid"
            external = r"D:\media\reference.png"

            self.assertEqual(storage_relative_path(app_root, external), external)

    def test_resolve_storage_path_maps_relative_internal_path_to_app_root(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            app_root = Path(directory) / ".VocaVid"

            self.assertEqual(resolve_storage_path(app_root, "outputs/demo/clip.mp4"), app_root / "outputs" / "demo" / "clip.mp4")

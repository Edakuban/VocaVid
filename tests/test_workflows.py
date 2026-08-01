import json
import tempfile
import unittest
from pathlib import Path

from VocaVid.workflows import WorkflowPaths


class WorkflowPathTests(unittest.TestCase):
    def test_all_bundled_workflows_are_runtime_candidates_or_marked_unused(self):
        repo_root = Path(__file__).resolve().parents[1]
        paths = WorkflowPaths.defaults(repo_root)
        runtime_candidates = {
            paths.promptgen,
            paths.avatar_description,
            paths.qwen35_promptgen,
            paths.qwen35_avatar_description,
            paths.image,
            *paths.image_aliases,
            paths.image_reference,
            paths.avatar_image,
            paths.video,
            *paths.video_aliases,
            paths.chorus,
        }
        unclassified = {
            path
            for path in (repo_root / "workflows").glob("*.json")
            if not path.name.startswith("_unused_") and path not in runtime_candidates
        }

        self.assertEqual(unclassified, set())

    def test_default_paths_use_project_workflows_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.promptgen, root / "workflows" / "promptgen.json")
            self.assertEqual(paths.qwen35_promptgen, root / "workflows" / "qwen35_text_promptgen.json")
            self.assertEqual(paths.qwen35_avatar_description, root / "workflows" / "qwen35_avatar_description.json")
            self.assertEqual(paths.avatar_description, root / "workflows" / "avatar_description.json")
            self.assertEqual(paths.image, root / "workflows" / "image.json")
            self.assertEqual(paths.image_aliases[0], root / "workflows" / "image_z_image_turbo.json")
            self.assertEqual(paths.avatar_image, root / "workflows" / "avatartoimage_flux.json")
            self.assertEqual(paths.video, root / "workflows" / "video.json")
            self.assertEqual(paths.video_aliases[0], root / "workflows" / "imageaudiotovideo.json")
            self.assertEqual(paths.chorus, root / "workflows" / "chorus.json")

    def test_image_alias_is_used_when_image_json_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "image_z_image_turbo.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.require_image(), workflows / "image_z_image_turbo.json")

    def test_existing_optional_promptgen_is_returned_only_when_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "promptgen.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.optional_promptgen(), workflows / "promptgen.json")

    def test_existing_optional_avatar_description_is_returned_only_when_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "avatar_description.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.optional_avatar_description(), workflows / "avatar_description.json")

    def test_missing_required_workflow_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = WorkflowPaths.defaults(Path(directory))

            with self.assertRaisesRegex(FileNotFoundError, "workflows.image"):
                paths.require_image()

    def test_avatar_image_workflow_is_required_from_flux_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "avatartoimage_flux.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.require_avatar_image(), workflows / "avatartoimage_flux.json")

    def test_avatar_image_workflow_prompt_replaces_character_hair_from_reference(self):
        workflow = json.loads((Path("workflows") / "avatartoimage_flux.json").read_text(encoding="utf-8"))
        positive_prompt = workflow["92:113"]["inputs"]["text"]

        self.assertIn("replacing only the primary focus person", positive_prompt)
        self.assertIn("person closest to camera", positive_prompt)
        self.assertIn("most centered", positive_prompt)
        self.assertIn("replace only that focus person", positive_prompt)
        self.assertIn("Do not change background people", positive_prompt)
        self.assertIn("secondary characters", positive_prompt)
        self.assertIn("Do not alter non-focus people", positive_prompt)
        self.assertIn("Replace all visible character hair", positive_prompt)
        self.assertIn("hairline", positive_prompt)
        self.assertIn("facial hair", positive_prompt)
        self.assertIn("Do not keep the original character's hair", positive_prompt)
        self.assertNotIn("from with Image 2", positive_prompt)

    def test_image_audio_to_video_alias_is_used_when_video_json_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "imageaudiotovideo.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.require_video(), workflows / "imageaudiotovideo.json")

import json
import tempfile
import unittest
from pathlib import Path

from VocaVid.comfy import load_workflow
from VocaVid.workflows import (
    DEFAULT_AVATAR_IMAGE_PROFILE,
    DEFAULT_CLIP_GENERATION_PROFILE,
    WorkflowPaths,
    normalize_avatar_image_profile,
    normalize_clip_generation_profile,
)


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
            paths.avatar_image_flux2_klein_4b_base,
            paths.avatar_image_flux2_klein_4b_distilled,
            paths.video,
            *paths.video_aliases,
            paths.video_ltx23_fast,
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
            self.assertEqual(paths.avatar_image_flux2_klein_4b_base, root / "workflows" / "image_flux2_klein_image_edit_4b_base.json")
            self.assertEqual(paths.avatar_image_flux2_klein_4b_distilled, root / "workflows" / "image_flux2_klein_image_edit_4b_distilled.json")
            self.assertEqual(paths.video, root / "workflows" / "video.json")
            self.assertEqual(paths.video_aliases[0], root / "workflows" / "imageaudiotovideo.json")
            self.assertEqual(paths.video_ltx23_fast, root / "workflows" / "imageaudiotovideo_ltx23_fast.json")
            self.assertEqual(paths.chorus, root / "workflows" / "chorus.json")

    def test_clip_generation_profile_defaults_to_quality_and_selects_fast_workflow(self):
        self.assertEqual(normalize_clip_generation_profile(None), DEFAULT_CLIP_GENERATION_PROFILE)
        self.assertEqual(normalize_clip_generation_profile("ltx23-fast"), "ltx23-fast")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            quality = workflows / "imageaudiotovideo.json"
            fast = workflows / "imageaudiotovideo_ltx23_fast.json"
            quality.write_text("{}", encoding="utf-8")
            fast.write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.require_video_for_profile("ltx23-quality"), quality)
            self.assertEqual(paths.require_video_for_profile("ltx23-fast"), fast)

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

            self.assertEqual(paths.require_avatar_image("flux2-klein-9b-base"), workflows / "avatartoimage_flux.json")

    def test_avatar_image_profiles_resolve_new_workflows_and_default_to_distilled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            base = workflows / "image_flux2_klein_image_edit_4b_base.json"
            distilled = workflows / "image_flux2_klein_image_edit_4b_distilled.json"
            base.write_text("{}", encoding="utf-8")
            distilled.write_text("{}", encoding="utf-8")
            paths = WorkflowPaths.defaults(root)

            self.assertEqual(DEFAULT_AVATAR_IMAGE_PROFILE, "flux2-klein-4b-distilled")
            self.assertEqual(normalize_avatar_image_profile("unknown"), DEFAULT_AVATAR_IMAGE_PROFILE)
            self.assertEqual(normalize_avatar_image_profile("legacy"), "flux2-klein-9b-base")
            self.assertEqual(paths.require_avatar_image("flux2-klein-4b-base"), base)
            self.assertEqual(paths.require_avatar_image(), distilled)
            self.assertEqual(paths.avatar_output_targets(distilled), ["94"])
            self.assertIsNone(paths.avatar_output_targets(base))

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

    def test_distilled_avatar_workflow_expands_nested_subgraphs_with_required_widget_inputs(self):
        workflow = load_workflow(Path("workflows") / "image_flux2_klein_image_edit_4b_distilled.json")

        self.assertEqual(workflow["92_61"]["inputs"]["sampler_name"], "euler")
        self.assertEqual(workflow["92_62"]["inputs"]["steps"], 4)
        self.assertEqual(workflow["92_63"]["inputs"]["cfg"], 1)
        self.assertIn("noise_seed", workflow["92_73"]["inputs"])
        self.assertEqual(workflow["92_66"]["inputs"]["batch_size"], 1)
        self.assertEqual(workflow["92_80"]["inputs"]["megapixels"], 1)
        self.assertEqual(workflow["92_80"]["inputs"]["resolution_steps"], 1)
        self.assertEqual(workflow["92_80"]["inputs"]["image"], ["76", 0])
        self.assertEqual(workflow["92_85"]["inputs"]["image"], ["81", 0])

    def test_image_audio_to_video_alias_is_used_when_video_json_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "imageaudiotovideo.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.require_video(), workflows / "imageaudiotovideo.json")

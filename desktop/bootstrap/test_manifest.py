from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
import sys


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DESKTOP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from VocaVid.comfy import load_workflow


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((DESKTOP_ROOT / "stack.lock.json").read_text(encoding="utf-8"))

    def test_profiles_reference_existing_entries(self) -> None:
        for profile_id, profile in self.manifest["profiles"].items():
            with self.subTest(profile=profile_id):
                self.assertGreater(profile["estimated_download_gb"], 0)
                for model_id in profile["models"]:
                    self.assertIn(model_id, self.manifest["models"])
                for node_id in profile["custom_nodes"]:
                    self.assertIn(node_id, self.manifest["custom_nodes"])

    def test_downloads_have_sha256_and_safe_relative_targets(self) -> None:
        for model_id, model in self.manifest["models"].items():
            with self.subTest(model=model_id):
                self.assertRegex(model["sha256"], r"^[0-9a-f]{64}$")
                target = Path(model["target"])
                self.assertFalse(target.is_absolute())
                self.assertNotIn("..", target.parts)
                self.assertTrue(model["url"].startswith("https://"))

    def test_workflow_model_files_are_managed_or_explicitly_gated(self) -> None:
        managed_names = {Path(model["target"]).name for model in self.manifest["models"].values()}
        referenced: set[str] = set()
        for workflow in (REPO_ROOT / "workflows").glob("*.json"):
            if workflow.name.startswith("_unused_"):
                continue
            text = workflow.read_text(encoding="utf-8")
            referenced.update(re.findall(r"[\w.+-]+\.safetensors", text, flags=re.IGNORECASE))
        self.assertEqual(referenced - managed_names, set())

    def test_creator_required_nodes_cover_active_workflows(self) -> None:
        referenced: set[str] = set()
        for workflow in (REPO_ROOT / "workflows").glob("*.json"):
            if workflow.name.startswith("_unused_"):
                continue
            for node in load_workflow(workflow).values():
                if isinstance(node, dict) and isinstance(node.get("class_type"), str):
                    referenced.add(node["class_type"])
        self.assertEqual(set(self.manifest["comfyui"]["required_nodes"]), referenced)

    def test_gated_models_declare_license_metadata(self) -> None:
        gated = [model for model in self.manifest["models"].values() if model.get("gated")]
        self.assertTrue(gated)
        for model in gated:
            self.assertTrue(model["license_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()

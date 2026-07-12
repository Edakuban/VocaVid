import tempfile
import unittest
from pathlib import Path

from VocaVid.workflows import WorkflowPaths


class ImageWorkflowSelectionTests(unittest.TestCase):
    def test_reference_image_workflow_is_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "image.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.image_for_reference(use_reference=True), workflows / "image.json")

    def test_reference_image_workflow_is_used_when_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflows = root / "workflows"
            workflows.mkdir()
            (workflows / "image.json").write_text("{}", encoding="utf-8")
            (workflows / "image_reference.json").write_text("{}", encoding="utf-8")

            paths = WorkflowPaths.defaults(root)

            self.assertEqual(paths.image_for_reference(use_reference=True), workflows / "image_reference.json")
            self.assertEqual(paths.image_for_reference(use_reference=False), workflows / "image.json")

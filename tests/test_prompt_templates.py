import tempfile
import unittest
from pathlib import Path

from VocaVid.prompt_templates import load_named_prompt_template, load_prompt_template, render_prompt_template


class PromptTemplateTests(unittest.TestCase):
    def test_project_prompt_template_includes_scene_plan_placeholder(self):
        template = load_prompt_template(Path("prompts") / "promptgen.txt")

        self.assertIn("{{ scene_plan }}", template)

    def test_load_prompt_template_reads_custom_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "promptgen.txt"
            path.write_text("Line: {{ lyric_text }}", encoding="utf-8")

            template = load_prompt_template(path)

            self.assertEqual(template, "Line: {{ lyric_text }}")

    def test_load_prompt_template_falls_back_when_file_is_missing(self):
        template = load_prompt_template(Path("missing-template.txt"))

        self.assertIn("{{ lyric_text }}", template)
        self.assertIn("Return only the image prompt", template)

    def test_render_prompt_template_replaces_known_variables(self):
        rendered = render_prompt_template(
            "Line={{ lyric_text }} Style={{ global_style }}",
            {"lyric_text": "Hello", "global_style": "noir"},
        )

        self.assertEqual(rendered, "Line=Hello Style=noir")

    def test_render_prompt_template_replaces_uppercase_brace_variables(self):
        rendered = render_prompt_template(
            "Lyrics={LYRICS} Style={GLOBAL_STYLE} Keep={{ lyric_text }}",
            {"lyrics": "Line one", "global_style": "noir", "lyric_text": "single line"},
        )

        self.assertEqual(rendered, "Lyrics=Line one Style=noir Keep=single line")

    def test_named_prompt_templates_are_editable_files(self):
        template = load_named_prompt_template("sceneplan.txt")

        self.assertIn("{SEGMENTS}", template)
        self.assertIn("Chorus/refrain performance policy", template)

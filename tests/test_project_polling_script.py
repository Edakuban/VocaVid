from pathlib import Path
import unittest


class ProjectPollingScriptTests(unittest.TestCase):
    def test_status_polling_skips_unchanged_rows(self):
        app_source = Path("musicvideogen/app.py").read_text(encoding="utf-8")

        self.assertIn("const projectRowServerHtml = new Map()", app_source)
        self.assertIn("function rememberProjectRows", app_source)
        self.assertIn("function projectRowChanged", app_source)
        self.assertIn("projectRowServerHtml.get(row.id) || row.outerHTML", app_source)
        self.assertIn("return previousHtml !== replacement.outerHTML", app_source)
        self.assertIn("if (!projectRowChanged(row, replacement)) return", app_source)
        self.assertIn("projectRowServerHtml.set(replacement.id, replacement.outerHTML)", app_source)


if __name__ == "__main__":
    unittest.main()

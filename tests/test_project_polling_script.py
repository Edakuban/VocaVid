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

    def test_project_actions_refresh_queue_estimate_after_submit_and_poll_callback(self):
        app_source = Path("musicvideogen/app.py").read_text(encoding="utf-8")

        self.assertIn("function currentProjectId()", app_source)
        self.assertIn("function projectActionSubmitted(form)", app_source)
        self.assertIn("window.setTimeout(() => refreshProjectStatus(projectId), 150)", app_source)
        self.assertIn("async function refreshProjectStatus(projectId)", app_source)
        self.assertIn("updateProjectStatus(data)", app_source)
        self.assertIn("updateQueueEstimate(data.queue_estimate_seconds)", app_source)
        self.assertIn("updateBrowserTitle(data.queue_count)", app_source)
        self.assertIn("function updateBrowserTitle(queueCount)", app_source)
        self.assertIn('onsubmit="return projectActionSubmitted(this)"', app_source)

    def test_scroll_top_targets_first_segment_row(self):
        app_source = Path("musicvideogen/app.py").read_text(encoding="utf-8")

        self.assertIn("function scrollToTop()", app_source)
        self.assertIn("document.querySelector('tr[id^=\"segment-row-\"]')", app_source)
        self.assertIn("document.querySelector('.project-topbar')", app_source)


if __name__ == "__main__":
    unittest.main()

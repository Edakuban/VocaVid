from pathlib import Path
import unittest


class ProjectPollingScriptTests(unittest.TestCase):
    def app_source(self) -> str:
        return "\n".join(path.read_text(encoding="utf-8") for path in Path("VocaVid/ui").glob("*.py"))

    def test_status_polling_skips_unchanged_rows(self):
        app_source = self.app_source()

        self.assertIn("const projectRowServerHtml = new Map()", app_source)
        self.assertIn("function rememberProjectRows", app_source)
        self.assertIn("function projectRowChanged", app_source)
        self.assertIn("projectRowServerHtml.get(row.id) || row.outerHTML", app_source)
        self.assertIn("return previousHtml !== replacement.outerHTML", app_source)
        self.assertIn("if (!projectRowChanged(row, replacement)) return", app_source)
        self.assertIn("projectRowServerHtml.set(replacement.id, replacement.outerHTML)", app_source)

    def test_status_polling_skips_unchanged_storyboard(self):
        app_source = self.app_source()

        self.assertIn("let projectStoryboardServerHtml = ''", app_source)
        self.assertIn("function rememberProjectStoryboard", app_source)
        self.assertIn("function projectStoryboardChanged", app_source)
        self.assertIn("projectStoryboardServerHtml || storyboard.outerHTML", app_source)
        self.assertIn("return previousHtml !== replacement.outerHTML", app_source)
        self.assertIn("if (!projectStoryboardChanged(storyboard, replacement)) return", app_source)
        self.assertIn("const replacementHtml = replacement.outerHTML", app_source)
        self.assertIn("projectStoryboardServerHtml = replacementHtml", app_source)
        self.assertLess(app_source.index("if (!projectStoryboardChanged(storyboard, replacement)) return"), app_source.index("storyboard.replaceWith(replacement)"))

    def test_storyboard_polling_patches_changed_cards_in_place(self):
        app_source = self.app_source()

        self.assertIn("const projectStoryboardCardServerHtml = new Map()", app_source)
        self.assertIn("const projectStoryboardTemplateServerHtml = new Map()", app_source)
        self.assertIn("function storyboardCanPatchInPlace(storyboard, replacement)", app_source)
        self.assertIn("function patchStoryboardCard(currentCard, replacementCard)", app_source)
        self.assertIn("function patchChangedStoryboardCards(storyboard, replacement)", app_source)
        self.assertIn("function replaceChangedStoryboardTemplates(storyboard, replacement)", app_source)
        self.assertIn("function storyboardMediaEquivalent(currentMedia, replacementMedia)", app_source)
        self.assertIn("selector === '.storyboard-card-media' && storyboardMediaEquivalent(currentChild, replacementChild)", app_source)
        self.assertIn("copyStoryboardCardAttributes(currentCard, replacementCard)", app_source)
        self.assertIn("replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-card-media')", app_source)
        self.assertIn("replaceStoryboardCardChildIfChanged(currentCard, replacementCard, '.storyboard-lock-overlay')", app_source)
        self.assertIn("patchChangedStoryboardCards(storyboard, replacement)", app_source)
        self.assertLess(app_source.index("if (storyboardCanPatchInPlace(storyboard, replacement))"), app_source.index("storyboard.replaceWith(replacement)"))

    def test_project_actions_refresh_queue_estimate_after_submit_and_poll_callback(self):
        app_source = self.app_source()

        self.assertIn("function currentProjectId()", app_source)
        self.assertIn("function projectActionSubmitted(form)", app_source)
        self.assertIn("window.setTimeout(() => refreshProjectStatus(projectId), 150)", app_source)
        self.assertIn("async function refreshProjectStatus(projectId)", app_source)
        self.assertIn("updateProjectStatus(data)", app_source)
        self.assertIn("updateQueueEstimate(data.queue_estimate_seconds, data.queue_count)", app_source)
        self.assertIn("function queueEstimateLabel(seconds, queueCount)", app_source)
        self.assertIn("updateBrowserTitle(data.queue_count)", app_source)
        self.assertIn("function updateBrowserTitle(queueCount)", app_source)
        self.assertIn('onsubmit="return projectActionSubmitted(this)"', app_source)

    def test_project_page_no_longer_registers_scroll_top_button(self):
        app_source = self.app_source()

        self.assertNotIn("function scrollToTop()", app_source)
        self.assertNotIn("scroll-top-button", app_source)

    def test_storyboard_polling_preserves_active_card_selection(self):
        app_source = self.app_source()

        self.assertIn("function activeProjectStoryboardTemplateId(storyboard)", app_source)
        self.assertIn("function restoreProjectStoryboardSelection(storyboard, templateId)", app_source)
        self.assertIn("storyboard.querySelector('.storyboard-card-active')", app_source)
        self.assertIn("storyboard.querySelector('[data-inspector-template=\"' + templateId + '\"]')", app_source)
        self.assertIn("selectStoryboardCard(storyboard, card)", app_source)
        self.assertLess(app_source.index("const activeTemplateId = activeProjectStoryboardTemplateId(storyboard)"), app_source.index("storyboard.replaceWith(replacement)"))
        self.assertLess(app_source.index("storyboard.replaceWith(replacement)"), app_source.index("restoreProjectStoryboardSelection(replacement, activeTemplateId)"))

    def test_storyboard_polling_preserves_checked_card_checkboxes(self):
        app_source = self.app_source()

        self.assertIn("const projectStoryboardFieldSelector = 'input:not(.storyboard-select), textarea, select'", app_source)
        self.assertIn("function checkedProjectStoryboardValues(storyboard)", app_source)
        self.assertIn("storyboard.querySelectorAll('.storyboard-select:checked')", app_source)
        self.assertIn("function restoreProjectStoryboardCheckedValues(storyboard, values)", app_source)
        self.assertIn("checkbox.checked = values.has(checkbox.value)", app_source)
        self.assertLess(app_source.index("const checkedValues = checkedProjectStoryboardValues(storyboard)"), app_source.index("storyboard.replaceWith(replacement)"))
        self.assertLess(app_source.index("storyboard.replaceWith(replacement)"), app_source.index("restoreProjectStoryboardCheckedValues(replacement, checkedValues)"))

    def test_storyboard_polling_skips_replacement_while_video_is_playing(self):
        app_source = self.app_source()

        self.assertIn("function projectStoryboardHasPlayingVideo(storyboard)", app_source)
        self.assertIn("storyboard.querySelectorAll('.storyboard-card-video')", app_source)
        self.assertIn("!video.paused && !video.ended", app_source)
        self.assertIn("!projectStoryboardHasPlayingVideo(storyboard)", app_source)

    def test_storyboard_selection_is_restored_after_form_reload(self):
        app_source = self.app_source()

        self.assertIn("function storyboardSelectionStorageKey()", app_source)
        self.assertIn("function rememberProjectStoryboardSelection()", app_source)
        self.assertIn("sessionStorage.setItem(storyboardSelectionStorageKey(), activeTemplateId)", app_source)
        self.assertIn("rememberProjectStoryboardSelection();", app_source)
        self.assertIn("const storedStoryboardTemplate = sessionStorage.getItem(storyboardSelectionStorageKey())", app_source)
        self.assertIn("restoreProjectStoryboardSelection(storyboard, storedStoryboardTemplate)", app_source)
        self.assertLess(app_source.index("rememberProjectRows();"), app_source.index("restoreProjectStoryboardSelection(storyboard, storedStoryboardTemplate)"))

    def test_segment_inspector_width_is_resizable_and_restored(self):
        app_source = self.app_source()

        self.assertIn("function inspectorWidthStorageKey()", app_source)
        self.assertIn("'VocaVid-segment-inspector-width'", app_source)
        self.assertIn("function beginSegmentInspectorResize(event, handle)", app_source)
        self.assertIn("rect.right - moveEvent.clientX", app_source)
        self.assertIn("workspace.style.setProperty('--segment-inspector-width'", app_source)
        self.assertIn("sessionStorage.setItem(inspectorWidthStorageKey()", app_source)
        self.assertIn("sessionStorage.getItem(inspectorWidthStorageKey())", app_source)
        self.assertIn("restoreSegmentInspectorWidth();", app_source)
        self.assertIn("document.addEventListener('pointerdown'", app_source)
        self.assertIn("document.addEventListener('keydown'", app_source)
        fallback_replace = app_source.index("storyboard.replaceWith(replacement)")
        restore_after_fallback = app_source.index("restoreSegmentInspectorWidth();", fallback_replace)
        self.assertLess(fallback_replace, restore_after_fallback)


if __name__ == "__main__":
    unittest.main()

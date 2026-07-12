import unittest

from VocaVid.sceneplan import fallback_scene_plans, make_sceneplan_concept_prompt, make_sceneplan_prompt, parse_scene_plan_text


class ScenePlanTests(unittest.TestCase):
    def test_make_sceneplan_prompt_requests_continuous_indexed_video_plan_with_project_context(self):
        project = {
            "genre": "industrial rock",
            "global_style_prompt": "cinematic neon ruins",
            "lyric_group_size": 2,
            "chorus_group_size": 4,
        }
        segments = [
            {
                "segment_index": 0,
                "kind": "gap",
                "section": "Instrumental intro",
                "is_chorus": 0,
                "use_reference": 0,
                "source_line_indices": "[]",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "clean_text": "Instrumental intro",
            },
            {
                "segment_index": 1,
                "kind": "lyrics",
                "section": "Chorus",
                "is_chorus": 1,
                "use_reference": 1,
                "source_line_indices": "[2, 3]",
                "start_sec": 8.0,
                "end_sec": 15.0,
                "clean_text": "Hook one\nHook two",
            },
        ]

        prompt = make_sceneplan_prompt(project, segments)

        self.assertIn("continuous music video", prompt)
        self.assertIn("Global visual style: cinematic neon ruins", prompt)
        self.assertIn("Lyrics lines per normal clip: 2", prompt)
        self.assertIn("Lyrics lines per chorus/refrain clip: 4", prompt)
        self.assertIn("Total render segments: 2", prompt)
        self.assertIn("You must return exactly 2 numbered segment lines, from 0 to 1.", prompt)
        self.assertIn("The scene plan must feel like a real edited music video", prompt)
        self.assertIn("Maximum 1 out of 3 consecutive segments may primarily show the main character walking or standing.", prompt)
        self.assertIn("At least 30% of all segments must focus on something other than the main character.", prompt)
        self.assertIn("performance shots", prompt)
        self.assertIn("worldbuilding/location shots", prompt)
        self.assertIn("abstract rhythm montage shots", prompt)
        self.assertIn("Chorus/refrain performance policy", prompt)
        self.assertIn("microphone", prompt)
        self.assertIn("live band", prompt)
        self.assertIn("electronic", prompt)
        self.assertIn("Every scene that includes the performer must show visible singing or lip-sync", prompt)
        self.assertIn("Continuity rules:", prompt)
        self.assertIn("Creative interpretation rules:", prompt)
        self.assertIn("Do not simply visualize the lyrics word-for-word.", prompt)
        self.assertIn("Use concrete visual language: camera framing, subject, movement, lighting, location, color, action, and mood.", prompt)
        self.assertIn("Return every render segment index exactly once", prompt)
        self.assertIn('Do not write "segment_index".', prompt)
        self.assertIn("Overall concept", prompt)
        self.assertIn("0. gap", prompt)
        self.assertIn("1. lyrics", prompt)
        self.assertIn("chorus=True", prompt)
        self.assertIn("uses_reference=True", prompt)
        self.assertIn("line_indices=[2, 3]", prompt)
        self.assertIn("Hook one / Hook two", prompt)

    def test_make_sceneplan_concept_prompt_requests_video_bible_with_chorus_escalation(self):
        project = {
            "genre": "industrial rock",
            "global_style_prompt": "cinematic neon ruins",
            "lyric_group_size": 2,
            "chorus_group_size": 1,
        }
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Verse",
                "is_chorus": 0,
                "use_reference": 0,
                "source_line_indices": "[0, 1]",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "clean_text": "Verse one\nVerse two",
            },
            {
                "segment_index": 1,
                "kind": "lyrics",
                "section": "Chorus",
                "is_chorus": 1,
                "use_reference": 1,
                "source_line_indices": "[2]",
                "start_sec": 8.0,
                "end_sec": 12.0,
                "clean_text": "Hook",
            },
        ]

        prompt = make_sceneplan_concept_prompt(project, segments)

        self.assertIn("Create a concise music video bible", prompt)
        self.assertIn("Core concept", prompt)
        self.assertIn("Recurring motifs", prompt)
        self.assertIn("performer appears in chorus/refrain sections", prompt)
        self.assertIn("live performance language", prompt)
        self.assertIn("Chorus escalation plan", prompt)
        self.assertIn("Final escalation", prompt)
        self.assertIn("Total render segments: 2", prompt)
        self.assertIn("0. lyrics", prompt)
        self.assertIn("1. lyrics", prompt)

    def test_make_sceneplan_prompt_uses_video_bible_context_when_provided(self):
        project = {
            "genre": "industrial rock",
            "global_style_prompt": "cinematic neon ruins",
            "lyric_group_size": 2,
            "chorus_group_size": 1,
        }
        segments = [
            {
                "segment_index": 0,
                "kind": "lyrics",
                "section": "Chorus",
                "is_chorus": 1,
                "use_reference": 1,
                "source_line_indices": "[0]",
                "start_sec": 0.0,
                "end_sec": 4.0,
                "clean_text": "Hook",
            },
        ]

        prompt = make_sceneplan_prompt(project, segments, video_bible="Chorus grows from lone singer to massive fire ritual.")

        self.assertIn("Video bible to follow:", prompt)
        self.assertIn("Chorus grows from lone singer to massive fire ritual.", prompt)
        self.assertIn("For each segment, make a concrete director's decision", prompt)

    def test_parse_scene_plan_text_accepts_segment_index_prefix(self):
        parsed = parse_scene_plan_text(
            "Overall concept: haunted battlefield\n"
            "segment_index: 0: Wide shot over the ruined trench\n"
            "segment_index: 1: Close-up on the survivor's hands",
            [0, 1],
        )

        self.assertEqual(
            parsed,
            {
                0: "Wide shot over the ruined trench",
                1: "Close-up on the survivor's hands",
            },
        )

    def test_fallback_scene_plans_rotate_specific_shot_types_instead_of_repeating_style_text(self):
        project = {
            "genre": "industrial rock",
            "global_style_prompt": "cinematic neon ruins",
        }
        segments = [
            {"segment_index": 0, "kind": "gap", "section": "Intro", "is_chorus": 0, "use_reference": 0, "clean_text": "Intro"},
            {"segment_index": 1, "kind": "lyrics", "section": "Verse", "is_chorus": 0, "use_reference": 0, "clean_text": "Verse one"},
            {"segment_index": 3, "kind": "lyrics", "section": "Chorus", "is_chorus": 1, "use_reference": 1, "clean_text": "Hook one"},
            {"segment_index": 4, "kind": "lyrics", "section": "Chorus", "is_chorus": 1, "use_reference": 1, "clean_text": "Hook two"},
            {"segment_index": 7, "kind": "lyrics", "section": "Verse", "is_chorus": 0, "use_reference": 0, "clean_text": "Object line"},
            {"segment_index": 8, "kind": "lyrics", "section": "Verse", "is_chorus": 0, "use_reference": 0, "clean_text": "Memory line"},
        ]

        plans = fallback_scene_plans(project, segments)

        self.assertEqual(set(plans), {0, 1, 3, 4, 7, 8})
        self.assertEqual(len(set(plans.values())), 6)
        self.assertTrue(any("object close-up" in plan for plan in plans.values()))
        self.assertTrue(any("wide location" in plan for plan in plans.values()))
        self.assertTrue(any("performance" in plan for plan in plans.values()))
        self.assertTrue(any("memory" in plan for plan in plans.values()))
        self.assertFalse(any("scene beat for" in plan for plan in plans.values()))
        self.assertFalse(all("cinematic neon ruins" in plan for plan in plans.values()))

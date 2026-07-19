import unittest

from VocaVid.promptgen import inject_promptgen_context, make_global_style_prompt, make_promptgen_prompt, make_videoprompt_prompt


class PromptgenTests(unittest.TestCase):
    def test_make_promptgen_prompt_contains_line_context_and_output_instruction(self):
        prompt = make_promptgen_prompt(
            lyric_text="I fall through neon rain",
            section="Verse",
            is_chorus=False,
            global_style="cinematic synthwave",
            duration="4.200",
            scene_plan="low angle shot of abandoned neon station",
            avatar_identity_context="female lead vocalist; short black hair",
        )

        self.assertIn("I fall through neon rain", prompt)
        self.assertIn("Verse", prompt)
        self.assertIn("cinematic synthwave", prompt)
        self.assertIn("low angle shot of abandoned neon station", prompt)
        self.assertIn("female lead vocalist; short black hair", prompt)
        self.assertIn("Return only the image prompt", prompt)

    def test_make_videoprompt_prompt_contains_controlled_performance_rules(self):
        prompt = make_videoprompt_prompt(
            lyric_text="I sing into the dark",
            image_prompt="close-up singer in black coat",
            section="Chorus",
            is_chorus=True,
            global_style="cinematic noir",
            duration="5.000",
            genre="dark pop",
            scene_plan="steady emotional performance shot",
            avatar_identity_context="male lead vocalist; weathered face",
        )

        self.assertIn("Generate a controlled image-to-video motion prompt", prompt)
        self.assertIn("The singer stays in the same physical position", prompt)
        self.assertIn("walking, running, stepping forward", prompt)
        self.assertIn("Clearly separate subject motion, camera motion, and environment motion", prompt)
        self.assertIn("I sing into the dark", prompt)
        self.assertIn("close-up singer in black coat", prompt)
        self.assertIn("steady emotional performance shot", prompt)
        self.assertIn("male lead vocalist; weathered face", prompt)

    def test_make_videoprompt_prompt_requests_motion_variety_and_blocks_invented_actions(self):
        prompt = make_videoprompt_prompt(
            lyric_text="The city burns behind my eyes",
            image_prompt="wide shot of ruined street and drifting smoke",
            section="Verse",
            is_chorus=False,
            global_style="cinematic war drama",
            duration="5.000",
            genre="industrial rock",
            scene_plan="environmental tracking shot through ruins",
        )

        self.assertIn("Choose one motion approach that fits this specific scene", prompt)
        self.assertIn("Do not default to a slow push-in", prompt)
        self.assertIn('Never describe motion as "almost imperceptible"', prompt)
        self.assertIn("The selected motion must be clearly visible within the clip duration", prompt)
        self.assertIn("lateral tracking", prompt)
        self.assertIn("foreground wipes", prompt)
        self.assertIn("Do not invent new props", prompt)
        self.assertIn("coffee cup", prompt)
        self.assertIn("sitting down", prompt)

    def test_make_videoprompt_prompt_makes_visible_characters_sing(self):
        prompt = make_videoprompt_prompt(
            lyric_text="I carry the fire through the night",
            image_prompt="medium shot of the main character in a torn coat",
            section="Verse",
            is_chorus=False,
            global_style="cinematic rock video",
            duration="4.000",
            genre="rock",
            scene_plan="the main character faces camera in the ruins",
        )

        self.assertIn("If any character, singer, performer, face, or person is visible", prompt)
        self.assertIn("show visible singing or lip-sync", prompt)
        self.assertIn("mouth movement", prompt)
        self.assertIn("silent posing", prompt)

    def test_make_global_style_prompt_contains_genre_and_lyrics_request(self):
        prompt = make_global_style_prompt("industrial rock", "One line\nHook line")

        self.assertIn("Ich will ein KI-Musikvideo zu dem Song erstellen", prompt)
        self.assertIn("Welchen 'Global Style Prompt' sollte ich nutzen?", prompt)
        self.assertIn("Genre: industrial rock", prompt)
        self.assertIn("Lyrics: One line\nHook line", prompt)

    def test_inject_promptgen_context_replaces_textgenerate_prompt_without_placeholders(self):
        workflow = {
            "1": {
                "class_type": "TextGenerate",
                "inputs": {"prompt": "manual test prompt", "max_length": 2048},
            }
        }

        injected = inject_promptgen_context(workflow, {"lyric_text": "Hello", "global_style": "noir"})

        self.assertIn("Hello", injected["1"]["inputs"]["prompt"])
        self.assertIn("noir", injected["1"]["inputs"]["prompt"])
        self.assertEqual(workflow["1"]["inputs"]["prompt"], "manual test prompt")

    def test_inject_promptgen_context_keeps_placeholder_workflows_supported(self):
        workflow = {
            "1": {
                "class_type": "TextGenerate",
                "inputs": {"prompt": "{{ lyric_text }} / {{ global_style }}"},
            }
        }

        injected = inject_promptgen_context(workflow, {"lyric_text": "Hello", "global_style": "noir"})

        self.assertEqual(injected["1"]["inputs"]["prompt"], "Hello / noir")

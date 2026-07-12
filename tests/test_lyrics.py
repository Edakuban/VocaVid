import unittest

from VocaVid.lyrics import parse_suno_lyrics


class LyricsTests(unittest.TestCase):
    def test_parse_suno_lyrics_strips_tags_and_keeps_section_metadata(self):
        lyrics = """
[Verse]
First line
Second line

[Chorus]
Hook one
Hook two
"""

        lines = parse_suno_lyrics(lyrics)

        self.assertEqual([line.clean_text for line in lines], ["First line", "Second line", "Hook one", "Hook two"])
        self.assertEqual([line.section for line in lines], ["Verse", "Verse", "Chorus", "Chorus"])
        self.assertEqual([line.is_chorus for line in lines], [False, False, True, True])

    def test_parse_suno_lyrics_handles_repeated_chorus_blocks_in_order(self):
        lyrics = """
[Chorus]
Same hook

[Verse]
Story

[Refrain]
Same hook
"""

        lines = parse_suno_lyrics(lyrics)

        self.assertEqual(
            [(line.index, line.section, line.clean_text, line.is_chorus) for line in lines],
            [
                (0, "Chorus", "Same hook", True),
                (1, "Verse", "Story", False),
                (2, "Refrain", "Same hook", True),
            ],
        )

    def test_parse_suno_lyrics_treats_punctuated_or_numbered_refrain_tags_as_chorus(self):
        lyrics = """
[Refrain:]
Hook one

[Chorus 2]
Hook two
"""

        lines = parse_suno_lyrics(lyrics)

        self.assertEqual([line.section for line in lines], ["Refrain:", "Chorus 2"])
        self.assertEqual([line.is_chorus for line in lines], [True, True])
        self.assertEqual([line.use_reference for line in lines], [True, True])

    def test_parse_suno_lyrics_marks_inline_reference_tags(self):
        lyrics = """
[Verse]
[me] I stand in the smoke
Normal line
"""

        lines = parse_suno_lyrics(lyrics)

        self.assertEqual(lines[0].clean_text, "I stand in the smoke")
        self.assertTrue(lines[0].use_reference)
        self.assertFalse(lines[1].use_reference)

    def test_parse_suno_lyrics_keeps_standalone_instrumental_tags_as_markers(self):
        lyrics = """
[Instrumental Intro]

[Verse]
First line

[Instrumental]

[Chorus]
Hook

[End]
"""

        lines = parse_suno_lyrics(lyrics)

        self.assertEqual(
            [(line.index, line.section, line.clean_text) for line in lines],
            [
                (0, "Instrumental Intro", "Instrumental Intro"),
                (1, "Verse", "First line"),
                (2, "Instrumental", "Instrumental"),
                (3, "Chorus", "Hook"),
                (4, "End", "End"),
            ],
        )

    def test_parse_suno_lyrics_supports_issue_9_meta_tags(self):
        lyrics = """
[Intro]

[Break]

[Build-Up]

[Drop]

[Bridge]
Middle eight

[Refrain]
Hook one

[Pre-Chorus]
Before the hook

[Chorus]
Hook two

[Interlude]
"""

        lines = parse_suno_lyrics(lyrics)

        self.assertEqual(
            [(line.section, line.clean_text, line.is_chorus) for line in lines],
            [
                ("Intro", "Intro", False),
                ("Break", "Break", False),
                ("Build-Up", "Build-Up", False),
                ("Drop", "Drop", False),
                ("Bridge", "Middle eight", False),
                ("Refrain", "Hook one", True),
                ("Pre-Chorus", "Before the hook", False),
                ("Chorus", "Hook two", True),
                ("Interlude", "Interlude", False),
            ],
        )

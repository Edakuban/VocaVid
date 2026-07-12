import unittest

from VocaVid.models import RenderSegment
from VocaVid.segments import build_render_segments


class SegmentTests(unittest.TestCase):
    def test_groups_lyrics_with_separate_normal_and_chorus_sizes(self):
        lines = [
            _line(0, "Verse", False, "One", 10, 12),
            _line(1, "Verse", False, "Two", 12, 14),
            _line(2, "Chorus", True, "Hook one", 14, 15),
            _line(3, "Chorus", True, "Hook two", 15, 16),
            _line(4, "Chorus", True, "Hook three", 16, 17),
            _line(5, "Verse", False, "Three", 17, 18),
        ]

        segments = build_render_segments(lines, total_duration_sec=18, lyric_group_size=2, chorus_group_size=4)

        lyrics = [segment for segment in segments if segment.kind == "lyrics"]
        self.assertEqual([segment.clean_text for segment in lyrics], ["One\nTwo", "Hook one\nHook two\nHook three", "Three"])
        self.assertEqual([(segment.start_sec, segment.end_sec) for segment in lyrics], [(10, 14), (14, 17), (17, 18)])
        self.assertFalse(lyrics[0].is_chorus)
        self.assertTrue(lyrics[1].is_chorus)

    def test_reclassifies_punctuated_refrain_sections_when_grouping_existing_projects(self):
        lines = [
            _line(0, "Refrain:", False, "Hook one", 10, 12),
            _line(1, "Refrain:", False, "Hook two", 12, 14),
            _line(2, "Refrain:", False, "Hook three", 14, 16),
            _line(3, "Refrain:", False, "Hook four", 16, 18),
        ]

        segments = build_render_segments(lines, total_duration_sec=18, lyric_group_size=2, chorus_group_size=1)

        lyrics = [segment for segment in segments if segment.kind == "lyrics"]
        self.assertEqual([segment.clean_text for segment in lyrics], ["Hook one", "Hook two", "Hook three", "Hook four"])
        self.assertTrue(all(segment.is_chorus for segment in lyrics))
        self.assertTrue(all(segment.use_reference for segment in lyrics))

    def test_adds_intro_and_outro_gap_segments_in_eight_to_twelve_second_chunks(self):
        lines = [_line(0, "Verse", False, "First lyric", 35, 40)]

        segments = build_render_segments(lines, total_duration_sec=53, lyric_group_size=1, chorus_group_size=1)

        self.assertEqual(segments[0].kind, "gap")
        self.assertEqual(segments[-1].kind, "gap")
        self.assertEqual(segments[0].start_sec, 0.0)
        self.assertEqual(segments[-1].end_sec, 53.0)
        self.assertIn("Instrumental intro", segments[0].clean_text)
        self.assertIn("Instrumental outro", segments[-1].clean_text)
        for segment in [item for item in segments if item.kind == "gap"]:
            self.assertGreaterEqual(segment.duration_sec, 8.0)
            self.assertLessEqual(segment.duration_sec, 14.0)

    def test_does_not_cross_timing_gaps_when_grouping_lyrics(self):
        lines = [
            _line(0, "Verse", False, "Before gap", 0, 4),
            _line(1, "Verse", False, "After gap", 15, 18),
        ]

        segments = build_render_segments(lines, total_duration_sec=18, lyric_group_size=2, chorus_group_size=2)

        self.assertEqual(segments[0].kind, "lyrics")
        self.assertTrue(all(segment.kind == "gap" for segment in segments[1:-1]))
        self.assertEqual(segments[-1].kind, "lyrics")
        self.assertEqual(segments[0].clean_text, "Before gap")
        self.assertEqual(segments[-1].clean_text, "After gap")

    def test_absorbs_sub_four_second_gaps_into_adjacent_lyric_segments(self):
        lines = [
            _line(0, "Verse", False, "First", 2, 5),
            _line(1, "Verse", False, "Second", 8.5, 11),
        ]

        segments = build_render_segments(lines, total_duration_sec=13.5, lyric_group_size=1, chorus_group_size=1)

        self.assertEqual([segment.kind for segment in segments], ["lyrics", "lyrics"])
        self.assertEqual((segments[0].start_sec, segments[0].end_sec), (0.0, 8.5))
        self.assertEqual((segments[1].start_sec, segments[1].end_sec), (8.5, 13.5))

    def test_four_second_gaps_become_instrumental_breaks(self):
        lines = [
            _line(0, "Verse", False, "Before gap", 0, 4),
            _line(1, "Verse", False, "After gap", 8, 10),
        ]

        segments = build_render_segments(lines, total_duration_sec=10, lyric_group_size=1, chorus_group_size=1)

        self.assertEqual([segment.kind for segment in segments], ["lyrics", "gap", "lyrics"])
        self.assertEqual((segments[1].start_sec, segments[1].end_sec), (4, 8))

    def test_instrumental_markers_become_gap_segments_in_even_fallback_timeline(self):
        lines = [
            _line(0, "Instrumental Intro", False, "Instrumental Intro", 0, 10, confidence=0.0),
            _line(1, "Verse", False, "First", 10, 20, confidence=0.0),
            _line(2, "Verse", False, "Second", 20, 30, confidence=0.0),
            _line(3, "Instrumental", False, "Instrumental", 30, 40, confidence=0.0),
            _line(4, "Chorus", True, "Hook", 40, 50, confidence=0.0),
            _line(5, "End", False, "End", 50, 60, confidence=0.0),
        ]

        segments = build_render_segments(lines, total_duration_sec=60, lyric_group_size=2, chorus_group_size=1)

        self.assertEqual(
            [(segment.kind, segment.section, segment.clean_text, segment.source_line_indices) for segment in segments],
            [
                ("gap", "Instrumental Intro", "Instrumental Intro", []),
                ("lyrics", "Verse", "First\nSecond", [1, 2]),
                ("gap", "Instrumental", "Instrumental", []),
                ("lyrics", "Chorus", "Hook", [4]),
                ("gap", "End", "End", []),
            ],
        )

    def test_long_instrumental_marker_splits_into_eight_to_twelve_second_parts(self):
        lines = [
            _line(0, "Instrumental Intro", False, "Instrumental Intro", 0, 35, confidence=0.0),
            _line(1, "Verse", False, "First lyric", 35, 40, confidence=0.0),
        ]

        segments = build_render_segments(lines, total_duration_sec=40, lyric_group_size=1, chorus_group_size=1)

        intro_parts = [segment for segment in segments if segment.kind == "gap" and segment.section == "Instrumental Intro"]
        self.assertEqual(len(intro_parts), 3)
        self.assertEqual(intro_parts[0].start_sec, 0.0)
        self.assertEqual(intro_parts[-1].end_sec, 35.0)
        self.assertTrue(all(8.0 <= segment.duration_sec <= 12.0 for segment in intro_parts))
        self.assertEqual(segments[3].kind, "lyrics")

    def test_long_detected_instrumental_gap_splits_into_eight_to_twelve_second_parts(self):
        lines = [
            _line(0, "Verse", False, "Before", 0, 4),
            _line(1, "Verse", False, "After", 39, 42),
        ]

        segments = build_render_segments(lines, total_duration_sec=42, lyric_group_size=1, chorus_group_size=1)

        gap_parts = [segment for segment in segments if segment.kind == "gap"]
        self.assertEqual(len(gap_parts), 3)
        self.assertEqual(gap_parts[0].start_sec, 4.0)
        self.assertEqual(gap_parts[-1].end_sec, 39.0)
        self.assertTrue(all(8.0 <= segment.duration_sec <= 12.0 for segment in gap_parts))

    def test_short_or_slightly_long_instrumental_gaps_can_stay_single_segments(self):
        lines = [
            _line(0, "Verse", False, "Before", 0, 4),
            _line(1, "Verse", False, "After", 18, 22),
        ]

        segments = build_render_segments(lines, total_duration_sec=22, lyric_group_size=1, chorus_group_size=1)

        gap_parts = [segment for segment in segments if segment.kind == "gap"]
        self.assertEqual(len(gap_parts), 1)
        self.assertEqual(gap_parts[0].duration_sec, 14.0)

    def test_low_confidence_fallback_lines_do_not_displace_instrumental_gaps(self):
        lines = [
            _line(28, "Chorus", True, "Maschinenherz, wir marschieren,", 261.28, 264.32),
            _line(29, "Chorus", True, "Durch die Hoelle, dominieren,", 264.32, 267.5),
            _line(30, "Chorus", True, "Stahl und Eisen, unser Blut,", 267.5, 271.5),
            _line(31, "Chorus", True, "In der Schlacht, sind wir gut.", 271.5, 275.54),
            _line(32, "Verse 5", False, "Maschinenherz, im Takt der Schlacht,", 275.54, 278.122, confidence=0.0),
            _line(33, "Verse 5", False, "ein leeres Herz, das nichts mehr macht,", 278.122, 280.704, confidence=0.0),
            _line(34, "Verse 5", False, "durch Feuer und Rauch geh ich voran,", 280.704, 283.286, confidence=0.0),
            _line(35, "Verse 5", False, "doch spuer nicht mehr, wer ich mal war.", 283.286, 285.868, confidence=0.0),
            _line(36, "Pre-Chorus", False, "Keine Angst, kein Schmerz,", 285.868, 288.45, confidence=0.0),
            _line(37, "Pre-Chorus", False, "doch ich such mein Herz.", 288.45, 291.032, confidence=0.0),
        ]

        segments = build_render_segments(lines, total_duration_sec=301.36, lyric_group_size=2, chorus_group_size=1)

        lyric_texts = [segment.clean_text for segment in segments if segment.kind == "lyrics"]
        self.assertEqual(
            lyric_texts,
            [
                "Maschinenherz, wir marschieren,",
                "Durch die Hoelle, dominieren,",
                "Stahl und Eisen, unser Blut,",
                "In der Schlacht, sind wir gut.",
            ],
        )
        self.assertTrue(all("Verse 5" not in segment.section for segment in segments if segment.kind == "lyrics"))
        self.assertEqual(segments[-1].kind, "gap")
        self.assertEqual(segments[-1].section, "Instrumental outro")
        self.assertEqual(segments[-1].end_sec, 301.36)

    def test_bounded_low_confidence_fallback_lines_remain_visible_between_trusted_anchors(self):
        lines = [
            _line(7, "Bridge", True, "nie zu schwaechen.", 256.5, 265.84, confidence=0.5),
            _line(8, "Verse 2", False, "Unschuld, die im Feuer schmilzt,", 265.84, 270.0, confidence=0.0),
            _line(9, "Verse 2", False, "seh die Traeume, die man stiehlt,", 270.0, 274.16, confidence=0.0),
            _line(10, "Verse 2", False, "in der Dunkelheit der Nacht,", 314.64, 317.2, confidence=0.6),
        ]

        segments = build_render_segments(lines, total_duration_sec=350.32, lyric_group_size=2, chorus_group_size=1)

        lyric_texts = [segment.clean_text for segment in segments if segment.kind == "lyrics"]
        self.assertEqual(
            lyric_texts,
            [
                "nie zu schwaechen.",
                "Unschuld, die im Feuer schmilzt,\nseh die Traeume, die man stiehlt,",
                "in der Dunkelheit der Nacht,",
            ],
        )

    def test_tiny_low_confidence_fallback_line_between_anchors_is_not_rendered(self):
        lines = [
            _line(13, "Pre-Chorus", False, "trag ich alles, weit und breit.", 95.08, 104.8, confidence=0.519),
            _line(14, "Chorus", True, "Zerbrochene Traeume, was bleibt zurueck,", 104.8, 104.85, confidence=0.0),
            _line(15, "Chorus", True, "In den Schatten, kein Glueck,", 104.8, 109.7, confidence=1.0),
        ]

        segments = build_render_segments(lines, total_duration_sec=110.0, lyric_group_size=2, chorus_group_size=1)

        lyric_texts = [segment.clean_text for segment in segments if segment.kind == "lyrics"]
        self.assertEqual(
            lyric_texts,
            [
                "trag ich alles, weit und breit.",
                "In den Schatten, kein Glueck,",
            ],
        )


def _line(index, section, is_chorus, text, start, end, confidence=0.9):
    return {
        "line_index": index,
        "section": section,
        "is_chorus": int(is_chorus),
        "use_reference": int(is_chorus),
        "clean_text": text,
        "raw_text": text,
        "start_sec": start,
        "end_sec": end,
        "confidence": confidence,
    }

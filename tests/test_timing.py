import unittest

from VocaVid.models import LyricLine, LineTiming
from VocaVid.timing import apply_manual_timing, distribute_evenly


class TimingTests(unittest.TestCase):
    def test_distribute_evenly_computes_positive_line_durations(self):
        lines = [
            LyricLine(index=0, section="Verse", raw_text="A", clean_text="A", is_chorus=False),
            LyricLine(index=1, section="Chorus", raw_text="B", clean_text="B", is_chorus=True),
        ]

        timings = distribute_evenly(lines, total_duration_sec=10.0)

        self.assertEqual(
            timings,
            [
                LineTiming(line_index=0, start_sec=0.0, end_sec=5.0, confidence=0.0),
                LineTiming(line_index=1, start_sec=5.0, end_sec=10.0, confidence=0.0),
            ],
        )
        self.assertEqual(timings[0].duration_sec, 5.0)

    def test_apply_manual_timing_rejects_zero_or_negative_duration(self):
        timing = LineTiming(line_index=0, start_sec=0.0, end_sec=3.0, confidence=0.5)

        with self.assertRaisesRegex(ValueError, "end_sec must be greater"):
            apply_manual_timing(timing, start_sec=4.0, end_sec=4.0)

    def test_apply_manual_timing_persists_new_values_and_confidence(self):
        timing = LineTiming(line_index=0, start_sec=0.0, end_sec=3.0, confidence=0.5)

        updated = apply_manual_timing(timing, start_sec=1.25, end_sec=4.5)

        self.assertEqual(updated.start_sec, 1.25)
        self.assertEqual(updated.end_sec, 4.5)
        self.assertEqual(updated.duration_sec, 3.25)
        self.assertEqual(updated.confidence, 1.0)

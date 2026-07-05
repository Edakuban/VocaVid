import unittest

from musicvideogen.alignment import (
    TranscriptWord,
    align_lyrics_to_words,
    infer_language_from_lyrics,
    normalize_word,
    transcribe_words_with_fallback,
)
from musicvideogen.models import LyricLine


class AlignmentTests(unittest.TestCase):
    def test_normalize_word_handles_german_english_and_romance_punctuation(self):
        self.assertEqual(normalize_word("Schön!"), "schon")
        self.assertEqual(normalize_word("L'amour,"), "lamour")
        self.assertEqual(normalize_word("can't"), "cant")
        self.assertEqual(normalize_word("cuore."), "cuore")

    def test_align_lyrics_to_words_maps_lines_to_transcript_word_times(self):
        lines = [
            LyricLine(index=0, section="Verse", raw_text="Hallo Welt", clean_text="Hallo Welt", is_chorus=False),
            LyricLine(index=1, section="Verse", raw_text="Ich bin hier", clean_text="Ich bin hier", is_chorus=False),
        ]
        words = [
            TranscriptWord(text="hallo", start_sec=0.52, end_sec=0.82),
            TranscriptWord(text="welt", start_sec=0.95, end_sec=1.25),
            TranscriptWord(text="ich", start_sec=1.70, end_sec=1.90),
            TranscriptWord(text="bin", start_sec=1.95, end_sec=2.10),
            TranscriptWord(text="hier", start_sec=2.20, end_sec=2.55),
        ]

        timings = align_lyrics_to_words(lines, words, total_duration_sec=4.0)

        self.assertEqual(timings[0].line_index, 0)
        self.assertAlmostEqual(timings[0].start_sec, 0.52)
        self.assertAlmostEqual(timings[0].end_sec, 1.25)
        self.assertGreater(timings[0].confidence, 0.95)
        self.assertAlmostEqual(timings[1].start_sec, 1.70)
        self.assertAlmostEqual(timings[1].end_sec, 2.55)

    def test_align_lyrics_to_words_falls_back_after_previous_match_for_unmatched_lines(self):
        lines = [
            LyricLine(index=0, section="Verse", raw_text="Hallo Welt", clean_text="Hallo Welt", is_chorus=False),
            LyricLine(index=1, section="Verse", raw_text="Ganz anders", clean_text="Ganz anders", is_chorus=False),
        ]
        words = [
            TranscriptWord(text="hallo", start_sec=0.50, end_sec=0.80),
            TranscriptWord(text="welt", start_sec=0.90, end_sec=1.20),
        ]

        timings = align_lyrics_to_words(lines, words, total_duration_sec=6.0)

        self.assertGreater(timings[0].confidence, 0.9)
        self.assertEqual(timings[1].start_sec, 1.2)
        self.assertEqual(timings[1].end_sec, 1.9)
        self.assertEqual(timings[1].confidence, 0.0)

    def test_align_lyrics_to_words_keeps_unmatched_fallback_between_matched_anchors(self):
        lines = [
            LyricLine(index=0, section="Verse", raw_text="Alpha", clean_text="Alpha", is_chorus=False),
            LyricLine(index=1, section="Verse", raw_text="Missing one", clean_text="Missing one", is_chorus=False),
            LyricLine(index=2, section="Verse", raw_text="Missing two", clean_text="Missing two", is_chorus=False),
            LyricLine(index=3, section="Verse", raw_text="Omega", clean_text="Omega", is_chorus=False),
        ]
        words = [
            TranscriptWord(text="alpha", start_sec=10.0, end_sec=11.0),
            TranscriptWord(text="omega", start_sec=20.0, end_sec=21.0),
        ]

        timings = align_lyrics_to_words(lines, words, total_duration_sec=30.0)

        self.assertEqual(timings[0].start_sec, 10.0)
        self.assertEqual(timings[0].end_sec, 11.0)
        self.assertEqual(timings[3].start_sec, 20.0)
        self.assertEqual(timings[3].end_sec, 21.0)
        self.assertGreaterEqual(timings[1].start_sec, timings[0].end_sec)
        self.assertLessEqual(timings[2].end_sec, timings[3].start_sec)
        self.assertLessEqual(timings[1].end_sec, timings[2].start_sec)

    def test_align_lyrics_to_words_stretches_unmatched_lines_between_matched_anchors(self):
        lines = [
            LyricLine(index=0, section="Verse", raw_text="Alpha", clean_text="Alpha", is_chorus=False),
            LyricLine(index=1, section="Verse", raw_text="Missing", clean_text="Missing", is_chorus=False),
            LyricLine(index=2, section="Verse", raw_text="Omega", clean_text="Omega", is_chorus=False),
        ]
        words = [
            TranscriptWord(text="alpha", start_sec=10.0, end_sec=11.0),
            TranscriptWord(text="omega", start_sec=50.0, end_sec=51.0),
        ]

        timings = align_lyrics_to_words(lines, words, total_duration_sec=60.0)

        self.assertEqual(timings[1].start_sec, 11.0)
        self.assertEqual(timings[1].end_sec, 50.0)
        self.assertEqual(timings[2].start_sec, 50.0)

    def test_align_lyrics_to_words_tolerates_small_whisper_word_errors(self):
        lines = [
            LyricLine(index=0, section="Chorus", raw_text="Mon coeur brennt", clean_text="Mon coeur brennt", is_chorus=True),
        ]
        words = [
            TranscriptWord(text="mon", start_sec=10.0, end_sec=10.2),
            TranscriptWord(text="coeur", start_sec=10.3, end_sec=10.7),
            TranscriptWord(text="brennt", start_sec=10.8, end_sec=11.2),
        ]

        timings = align_lyrics_to_words(lines, words, total_duration_sec=20.0)

        self.assertEqual(timings[0].start_sec, 10.0)
        self.assertEqual(timings[0].end_sec, 11.2)
        self.assertGreater(timings[0].confidence, 0.95)

    def test_align_lyrics_to_words_prefers_compact_line_match_over_late_token_jump(self):
        lines = [
            LyricLine(
                index=0,
                section="Verse",
                raw_text="doch ich seh, was wir zerstören",
                clean_text="doch ich seh, was wir zerstören",
                is_chorus=False,
            ),
            LyricLine(
                index=1,
                section="Refrain",
                raw_text="Feuer und Stahl",
                clean_text="Feuer und Stahl",
                is_chorus=True,
            ),
        ]
        words = [
            TranscriptWord("doch", 105.14, 106.36),
            TranscriptWord("ich", 106.36, 106.8),
            TranscriptWord("sehe", 106.8, 107.3),
            TranscriptWord("was", 107.3, 107.7),
            TranscriptWord("wird", 107.7, 107.9),
            TranscriptWord("zerstören", 107.9, 109.04),
            TranscriptWord("Feuer", 110.64, 111.8),
            TranscriptWord("und", 111.8, 112.18),
            TranscriptWord("Stahl", 112.18, 112.92),
            TranscriptWord("was", 218.0, 218.3),
            TranscriptWord("wir", 218.4, 218.7),
            TranscriptWord("zerstören", 219.0, 219.3),
        ]

        timings = align_lyrics_to_words(lines, words, total_duration_sec=240.0)

        self.assertEqual(timings[0].start_sec, 105.14)
        self.assertEqual(timings[0].end_sec, 109.04)
        self.assertEqual(timings[1].start_sec, 110.64)

    def test_transcribe_words_with_fallback_retries_cuda_dll_errors_on_cpu(self):
        calls = []

        class FakeTranscriber:
            def __init__(self, device, compute_type):
                self.device = device
                self.compute_type = compute_type

            def transcribe_words(self, audio_path, language=None):
                calls.append((self.device, self.compute_type, language))
                if self.device == "cuda":
                    raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                return [TranscriptWord(text="hallo", start_sec=0.0, end_sec=0.5)]

        words = transcribe_words_with_fallback("song.wav", language="de", transcriber_factory=FakeTranscriber)

        self.assertEqual(calls, [("cuda", "float16", "de"), ("cpu", "int8", "de")])
        self.assertEqual(words, [TranscriptWord(text="hallo", start_sec=0.0, end_sec=0.5)])

    def test_transcribe_words_with_fallback_retries_cuda_timeout_on_cpu(self):
        calls = []

        def fake_runner(audio_path, language, device, compute_type, timeout_sec):
            calls.append((device, compute_type, language, timeout_sec))
            if device == "cuda":
                raise TimeoutError("whisper cuda timed out")
            return [TranscriptWord(text="cpu", start_sec=0.0, end_sec=0.5)]

        words = transcribe_words_with_fallback(
            "song.wav",
            language="de",
            runner=fake_runner,
            cuda_timeout_sec=480,
            cpu_timeout_sec=900,
        )

        self.assertEqual(calls, [("cuda", "float16", "de", 480), ("cpu", "int8", "de", 900)])
        self.assertEqual(words, [TranscriptWord(text="cpu", start_sec=0.0, end_sec=0.5)])

    def test_transcribe_words_with_fallback_can_force_cpu_only(self):
        calls = []

        def fake_runner(audio_path, language, device, compute_type, timeout_sec):
            calls.append((device, compute_type, language, timeout_sec))
            return [TranscriptWord(text="cpu", start_sec=0.0, end_sec=0.5)]

        words = transcribe_words_with_fallback(
            "song.wav",
            language="de",
            runner=fake_runner,
            prefer_device="cpu",
            cpu_timeout_sec=900,
        )

        self.assertEqual(calls, [("cpu", "int8", "de", 900)])
        self.assertEqual(words, [TranscriptWord(text="cpu", start_sec=0.0, end_sec=0.5)])

    def test_transcribe_words_with_fallback_passes_model_size_to_cuda_and_cpu_retry(self):
        calls = []

        def fake_runner(audio_path, language, device, compute_type, timeout_sec, model_size="small"):
            calls.append((device, compute_type, language, model_size))
            if device == "cuda":
                raise RuntimeError("cublas64_12.dll failed")
            return [TranscriptWord(text="cpu", start_sec=0.0, end_sec=0.5)]

        words = transcribe_words_with_fallback("song.wav", language="de", runner=fake_runner, model_size="large-v3")

        self.assertEqual(calls, [("cuda", "float16", "de", "large-v3"), ("cpu", "int8", "de", "large-v3")])
        self.assertEqual(words, [TranscriptWord(text="cpu", start_sec=0.0, end_sec=0.5)])

    def test_infer_language_from_lyrics_prefers_german_for_german_song(self):
        lines = [
            LyricLine(index=0, section="Verse", raw_text="In der Nacht", clean_text="In der Nacht", is_chorus=False),
            LyricLine(index=1, section="Verse", raw_text="und ich kann nicht mehr", clean_text="und ich kann nicht mehr", is_chorus=False),
        ]

        self.assertEqual(infer_language_from_lyrics(lines), "de")

    def test_infer_language_from_lyrics_detects_english_song(self):
        lines = [
            LyricLine(index=0, section="Verse", raw_text="In the night", clean_text="In the night", is_chorus=False),
            LyricLine(index=1, section="Verse", raw_text="and I can't let go", clean_text="and I can't let go", is_chorus=False),
        ]

        self.assertEqual(infer_language_from_lyrics(lines), "en")

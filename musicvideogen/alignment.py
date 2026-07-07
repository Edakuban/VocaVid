from __future__ import annotations

import logging
import multiprocessing
import re
import time
import traceback
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import LineTiming, LyricLine
from .timing import distribute_evenly

try:
    from rapidfuzz.distance import Levenshtein
except ImportError:  # pragma: no cover
    Levenshtein = None


logger = logging.getLogger(__name__)
WHISPER_CUDA_TIMEOUT_SEC = 8 * 60
WHISPER_CPU_TIMEOUT_SEC = 30 * 60
WHISPER_MODEL_SIZES = ("small", "medium", "large-v3")
WORD_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ']+", re.UNICODE)


@dataclass(frozen=True)
class TranscriptWord:
    text: str
    start_sec: float
    end_sec: float


class WhisperTranscriber:
    def __init__(self, model_size: str = "small", device: str = "cuda", compute_type: str = "float16"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def transcribe_words(self, audio_path: Path, language: str | None = None) -> list[TranscriptWord]:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("Install faster-whisper to use real audio alignment") from exc
            started = time.monotonic()
            logger.info(
                "whisper model load start model_size=%s device=%s compute_type=%s",
                self.model_size,
                self.device,
                self.compute_type,
            )
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            logger.info(
                "whisper model load done model_size=%s device=%s compute_type=%s elapsed_sec=%.3f",
                self.model_size,
                self.device,
                self.compute_type,
                time.monotonic() - started,
            )

        started = time.monotonic()
        logger.info(
            "whisper model transcribe start audio=%s language=%s device=%s compute_type=%s",
            audio_path,
            language or "auto",
            self.device,
            self.compute_type,
        )
        segments, _info = self._model.transcribe(
            str(audio_path),
            language=language,
            vad_filter=False,
            word_timestamps=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        words: list[TranscriptWord] = []
        for segment in segments:
            for word in segment.words or []:
                text = getattr(word, "word", "").strip()
                if text:
                    words.append(
                        TranscriptWord(
                            text=text,
                            start_sec=float(getattr(word, "start", 0.0)),
                            end_sec=float(getattr(word, "end", 0.0)),
                        )
                    )
        logger.info(
            "whisper model transcribe done audio=%s words=%s elapsed_sec=%.3f",
            audio_path,
            len(words),
            time.monotonic() - started,
        )
        return words


def transcribe_words_with_fallback(
    audio_path: Path | str,
    language: str | None = None,
    transcriber_factory=None,
    runner=None,
    prefer_device: str = "cuda",
    model_size: str = "small",
    cuda_timeout_sec: float = WHISPER_CUDA_TIMEOUT_SEC,
    cpu_timeout_sec: float = WHISPER_CPU_TIMEOUT_SEC,
) -> list[TranscriptWord]:
    model_size = normalize_whisper_model_size(model_size)
    if transcriber_factory is not None:
        active_runner = _runner_from_factory(transcriber_factory)
    else:
        active_runner = runner or _transcribe_words_direct

    if prefer_device == "cpu":
        logger.info("whisper attempt start model_size=%s device=cpu compute_type=int8 audio=%s language=%s", model_size, audio_path, language or "auto")
        return _run_transcriber(active_runner, Path(audio_path), language, "cpu", "int8", cpu_timeout_sec, model_size)

    try:
        logger.info("whisper attempt start model_size=%s device=cuda compute_type=float16 audio=%s language=%s", model_size, audio_path, language or "auto")
        return _run_transcriber(active_runner, Path(audio_path), language, "cuda", "float16", cuda_timeout_sec, model_size)
    except TimeoutError as exc:
        logger.info("whisper cuda timed out after %.1fs; retrying on cpu error=%s", cuda_timeout_sec, exc)
        logger.info("whisper attempt start model_size=%s device=cpu compute_type=int8 audio=%s language=%s", model_size, audio_path, language or "auto")
        return _run_transcriber(active_runner, Path(audio_path), language, "cpu", "int8", cpu_timeout_sec, model_size)
    except Exception as exc:
        if not _is_cuda_runtime_error(exc):
            raise
        logger.info("whisper cuda failed; retrying on cpu error=%s", exc)
        logger.info("whisper attempt start model_size=%s device=cpu compute_type=int8 audio=%s language=%s", model_size, audio_path, language or "auto")
        return _run_transcriber(active_runner, Path(audio_path), language, "cpu", "int8", cpu_timeout_sec, model_size)


def normalize_whisper_model_size(value: str | None) -> str:
    normalized = str(value or "small").strip()
    return normalized if normalized in WHISPER_MODEL_SIZES else "small"


def _run_transcriber(
    runner,
    audio_path: Path,
    language: str | None,
    device: str,
    compute_type: str,
    timeout_sec: float,
    model_size: str,
) -> list[TranscriptWord]:
    try:
        return runner(audio_path, language, device, compute_type, timeout_sec, model_size=model_size)
    except TypeError as exc:
        if "model_size" not in str(exc):
            raise
        return runner(audio_path, language, device, compute_type, timeout_sec)


def _runner_from_factory(transcriber_factory):
    def run(
        audio_path: Path,
        language: str | None,
        device: str,
        compute_type: str,
        timeout_sec: float,
        model_size: str = "small",
    ) -> list[TranscriptWord]:
        try:
            transcriber = transcriber_factory(model_size=model_size, device=device, compute_type=compute_type)
        except TypeError as exc:
            if "model_size" not in str(exc):
                raise
            transcriber = transcriber_factory(device=device, compute_type=compute_type)
        return transcriber.transcribe_words(audio_path, language=language)

    return run



def _transcribe_words_direct(
    audio_path: Path,
    language: str | None,
    device: str,
    compute_type: str,
    timeout_sec: float,
    model_size: str = "small",
) -> list[TranscriptWord]:
    """Transcribe words directly in the current process without spawning a subprocess."""
    try:
        words = WhisperTranscriber(model_size=model_size, device=device, compute_type=compute_type).transcribe_words(audio_path, language=language)
        return words
    except Exception:
        logger.exception("whisper transcription failed device=%s", device)
        raise


def _transcribe_words_in_process(
    audio_path: Path,
    language: str | None,
    device: str,
    compute_type: str,
    timeout_sec: float,
    model_size: str = "small",
) -> list[TranscriptWord]:
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(
        target=_transcribe_words_worker,
        args=(str(audio_path), language, device, compute_type, model_size, result_queue),
    )
    process.start()
    process.join(timeout_sec)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        raise TimeoutError(f"whisper {device} transcription timed out after {timeout_sec:.1f}s")
    if result_queue.empty():
        raise RuntimeError(f"whisper {device} transcription exited without result code={process.exitcode}")
    status, payload = result_queue.get()
    if status == "ok":
        return [TranscriptWord(text=item[0], start_sec=item[1], end_sec=item[2]) for item in payload]
    raise RuntimeError(str(payload))


def _transcribe_words_worker(
    audio_path: str,
    language: str | None,
    device: str,
    compute_type: str,
    model_size: str,
    result_queue,
) -> None:
    try:
        words = WhisperTranscriber(model_size=model_size, device=device, compute_type=compute_type).transcribe_words(Path(audio_path), language=language)
        result_queue.put(("ok", [(word.text, word.start_sec, word.end_sec) for word in words]))
    except Exception:
        result_queue.put(("error", traceback.format_exc()))


def _is_cuda_runtime_error(exc: Exception) -> bool:
    message = str(exc).lower()
    needles = ("cuda", "cublas", "cudnn", "cudart", "dll")
    return any(needle in message for needle in needles)


def normalize_word(word: str) -> str:
    decomposed = unicodedata.normalize("NFKD", word.casefold())
    no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^\w]+", "", no_marks, flags=re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [normalized for normalized in (normalize_word(match.group(0)) for match in WORD_RE.finditer(text)) if normalized]


def infer_language_from_lyrics(lines: list[LyricLine]) -> str | None:
    tokens = []
    for line in lines:
        tokens.extend(tokenize(line.clean_text))
    if not tokens:
        return None

    scores = {
        "de": _count_language_hits(tokens, {"der", "die", "das", "und", "ich", "nicht", "mehr", "keine", "durch", "nacht"}),
        "en": _count_language_hits(tokens, {"the", "and", "i", "you", "me", "my", "we", "in", "night", "not"}),
        "fr": _count_language_hits(tokens, {"le", "la", "les", "et", "je", "tu", "mon", "ma", "dans", "nuit"}),
        "it": _count_language_hits(tokens, {"il", "la", "gli", "e", "io", "tu", "mio", "mia", "nel", "notte"}),
    }
    language, score = max(scores.items(), key=lambda item: item[1])
    return language if score >= 2 else None


def _count_language_hits(tokens: list[str], hints: set[str]) -> int:
    return sum(1 for token in tokens if token in hints)


def align_lyrics_to_words(
    lines: list[LyricLine],
    transcript_words: list[TranscriptWord],
    total_duration_sec: float,
    min_line_confidence: float = 0.45,
    search_window: int = 80,
) -> list[LineTiming]:
    normalized_transcript = [(word, normalize_word(word.text)) for word in transcript_words if normalize_word(word.text)]
    cursor = 0
    timings: list[LineTiming | None] = []

    for line in lines:
        lyric_tokens = tokenize(line.clean_text)
        match = _best_line_match(lyric_tokens, normalized_transcript, cursor, search_window)
        confidence = match[2] if match else 0.0
        if match and confidence >= min_line_confidence:
            start_index, end_index, _score = match
            first = normalized_transcript[start_index][0]
            last = normalized_transcript[end_index][0]
            timings.append(
                LineTiming(
                    line_index=line.index,
                    start_sec=round(first.start_sec, 3),
                    end_sec=round(max(first.start_sec + 0.05, last.end_sec), 3),
                    confidence=round(confidence, 3),
                )
            )
            cursor = end_index + 1
        else:
            timings.append(None)

    return _fill_missing_timings(lines, timings, total_duration_sec)


def _fill_missing_timings(
    lines: list[LyricLine],
    timings: list[LineTiming | None],
    total_duration_sec: float,
) -> list[LineTiming]:
    if all(timing is None for timing in timings):
        return distribute_evenly(lines, total_duration_sec)

    filled = list(timings)
    fallback_duration = _fallback_line_duration(timing for timing in filled if timing is not None)
    index = 0
    while index < len(filled):
        if filled[index] is not None:
            index += 1
            continue

        start = index
        while index < len(filled) and filled[index] is None:
            index += 1
        end = index

        previous_timing = filled[start - 1] if start > 0 else None
        next_timing = filled[end] if end < len(filled) else None
        block_start = previous_timing.end_sec if previous_timing is not None else 0.0
        block_end = next_timing.start_sec if next_timing is not None else total_duration_sec
        if block_end <= block_start:
            block_end = block_start + 0.05 * (end - start)
        if previous_timing is None or next_timing is None:
            block_duration = block_end - block_start
            max_fallback_duration = fallback_duration * (end - start)
            if block_duration > max_fallback_duration * 2:
                block_end = block_start + max_fallback_duration
        step = (block_end - block_start) / (end - start)
        for offset, line_index in enumerate(range(start, end)):
            filled[line_index] = LineTiming(
                line_index=lines[line_index].index,
                start_sec=round(block_start + step * offset, 6),
                end_sec=round(block_start + step * (offset + 1), 6),
                confidence=0.0,
            )

    return [timing for timing in filled if timing is not None]


def _fallback_line_duration(timings: Iterable[LineTiming]) -> float:
    durations = sorted(max(0.05, timing.duration_sec) for timing in timings)
    if not durations:
        return 4.0
    middle = len(durations) // 2
    if len(durations) % 2:
        return durations[middle]
    return (durations[middle - 1] + durations[middle]) / 2


def _best_line_match(
    lyric_tokens: list[str],
    transcript: list[tuple[TranscriptWord, str]],
    cursor: int,
    search_window: int,
) -> tuple[int, int, float] | None:
    if not lyric_tokens:
        return None

    best: tuple[int, int, float] | None = None
    best_score = 0.0
    start_limit = min(len(transcript), cursor + search_window)
    for start in range(cursor, start_limit):
        max_length = min(len(transcript) - start, max(len(lyric_tokens) + 3, 1))
        min_length = max(1, len(lyric_tokens) - 2)
        for length in range(min_length, max_length + 1):
            end = start + length - 1
            line_duration = transcript[end][0].end_sec - transcript[start][0].start_sec
            if line_duration > 14.0:
                continue
            candidate_tokens = [item[1] for item in transcript[start : end + 1]]
            score = _line_similarity(lyric_tokens, candidate_tokens)
            if score > best_score:
                best = (start, end, score)
                best_score = score
    return best


def _line_similarity(lyric_tokens: list[str], candidate_tokens: list[str]) -> float:
    if not lyric_tokens or not candidate_tokens:
        return 0.0
    used: set[int] = set()
    scores: list[float] = []
    for lyric_token in lyric_tokens:
        best_index = -1
        best_score = 0.0
        for index, candidate in enumerate(candidate_tokens):
            if index in used:
                continue
            score = _similarity(lyric_token, candidate)
            if score > best_score:
                best_index = index
                best_score = score
        if best_index >= 0 and best_score >= 0.62:
            used.add(best_index)
            scores.append(best_score)
    coverage = len(scores) / len(lyric_tokens)
    average = sum(scores) / len(scores) if scores else 0.0
    length_penalty = min(len(lyric_tokens), len(candidate_tokens)) / max(len(lyric_tokens), len(candidate_tokens))
    return coverage * average * length_penalty


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if Levenshtein is not None:
        return float(Levenshtein.normalized_similarity(left, right))
    return _fallback_similarity(left, right)


def _fallback_similarity(left: str, right: str) -> float:
    common = sum(1 for a, b in zip(left, right) if a == b)
    return common / max(len(left), len(right))


def _confidence(matches: Iterable[tuple[int, float]], lyric_tokens: list[str]) -> float:
    match_list = list(matches)
    if not lyric_tokens or not match_list:
        return 0.0
    coverage = len(match_list) / len(lyric_tokens)
    average_score = sum(score for _index, score in match_list) / len(match_list)
    return max(0.0, min(1.0, coverage * average_score))

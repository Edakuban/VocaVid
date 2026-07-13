from __future__ import annotations

from collections import defaultdict

from ..alignment import align_lyrics_to_words
from ..models import LyricLine
from .models import ReelLyricSection


def project_rows_to_sections(rows) -> list[ReelLyricSection]:
    sections: list[ReelLyricSection] = []
    occurrence_by_type: defaultdict[str, int] = defaultdict(int)
    current_key: str | None = None
    current_rows = []
    for row in rows:
        section_type = _section_type(row)
        if current_key is not None and section_type != current_key:
            sections.append(_section_from_rows(current_key, occurrence_by_type, current_rows))
            current_rows = []
        current_key = section_type
        current_rows.append(row)
    if current_key is not None and current_rows:
        sections.append(_section_from_rows(current_key, occurrence_by_type, current_rows))
    return sections


def project_rows_to_lyric_lines(rows) -> list[LyricLine]:
    lines: list[LyricLine] = []
    for position, row in enumerate(rows):
        index = int(_row_value(row, "segment_index", _row_value(row, "line_index", position)))
        clean_text = str(_row_value(row, "clean_text", "") or "")
        lines.append(
            LyricLine(
                index=index,
                section=str(_row_value(row, "section", "") or "Verse"),
                raw_text=str(_row_value(row, "raw_text", clean_text) or clean_text),
                clean_text=clean_text,
                is_chorus=bool(_row_value(row, "is_chorus", 0)),
                use_reference=bool(_row_value(row, "use_reference", 0)),
            )
        )
    return lines


def align_project_rows_to_words(rows, transcript_words, total_duration_sec: float) -> tuple[list[dict], list]:
    lyric_lines = project_rows_to_lyric_lines(rows)
    timings = align_lyrics_to_words(lyric_lines, transcript_words, total_duration_sec)
    timing_by_index = {timing.line_index: timing for timing in timings}
    aligned_rows = []
    for position, row in enumerate(rows):
        index = int(_row_value(row, "segment_index", _row_value(row, "line_index", position)))
        timing = timing_by_index.get(index)
        aligned = _row_to_dict(row)
        if timing is not None:
            aligned["start_sec"] = timing.start_sec
            aligned["end_sec"] = timing.end_sec
            aligned["confidence"] = timing.confidence
        aligned_rows.append(aligned)
    return aligned_rows, timings


def _section_from_rows(section_type: str, occurrence_by_type: defaultdict[str, int], rows) -> ReelLyricSection:
    occurrence_by_type[section_type] += 1
    starts = [_float_or_none(_row_value(row, "start_sec", None)) for row in rows]
    ends = [_float_or_none(_row_value(row, "end_sec", None)) for row in rows]
    indices = [int(_row_value(row, "segment_index", _row_value(row, "line_index", index))) for index, row in enumerate(rows)]
    text = "\n".join(str(_row_value(row, "clean_text", "") or "").strip() for row in rows if str(_row_value(row, "clean_text", "") or "").strip())
    known_starts = [value for value in starts if value is not None]
    known_ends = [value for value in ends if value is not None]
    return ReelLyricSection(
        type=section_type,
        occurrence=occurrence_by_type[section_type],
        text=text,
        start_sec=min(known_starts) if known_starts else None,
        end_sec=max(known_ends) if known_ends else None,
        source_indices=indices,
    )


def _section_type(row) -> str:
    raw = str(_row_value(row, "section", "") or "").strip()
    is_chorus = bool(_row_value(row, "is_chorus", 0))
    normalized = raw.casefold()
    if is_chorus or normalized in {"chorus", "refrain"}:
        return "Chorus"
    if normalized in {"pre-chorus", "pre chorus", "prechorus"}:
        return "Pre-Chorus"
    if normalized == "bridge":
        return "Bridge"
    return raw or "Verse"


def _row_value(row, key: str, default):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _row_to_dict(row) -> dict:
    if isinstance(row, dict):
        return dict(row)
    keys = getattr(row, "keys", None)
    if callable(keys):
        return {key: row[key] for key in keys()}
    return {
        "line_index": _row_value(row, "line_index", _row_value(row, "segment_index", 0)),
        "section": _row_value(row, "section", "Verse"),
        "is_chorus": _row_value(row, "is_chorus", 0),
        "use_reference": _row_value(row, "use_reference", 0),
        "raw_text": _row_value(row, "raw_text", _row_value(row, "clean_text", "")),
        "clean_text": _row_value(row, "clean_text", ""),
        "start_sec": _row_value(row, "start_sec", None),
        "end_sec": _row_value(row, "end_sec", None),
    }


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

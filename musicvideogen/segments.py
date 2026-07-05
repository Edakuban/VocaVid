from __future__ import annotations

from typing import Any, Iterable

from .lyrics import is_chorus_section, is_instrumental_section
from .models import RenderSegment


MIN_GAP_SEC = 8.0
MAX_GAP_SEC = 12.0
SINGLE_GAP_TOLERANCE_SEC = 14.0
GAP_THRESHOLD_SEC = 4.0
MIN_RENDER_CONFIDENCE = 0.45


def build_render_segments(
    lyric_rows: Iterable[Any],
    total_duration_sec: float,
    lyric_group_size: int = 1,
    chorus_group_size: int = 1,
) -> list[RenderSegment]:
    timed_rows = [
        _row_dict(row)
        for row in lyric_rows
        if row["start_sec"] is not None
        and row["end_sec"] is not None
    ]
    rows = _select_render_rows(timed_rows)
    rows.sort(key=lambda row: (float(row["start_sec"]), int(row["line_index"])))
    segments: list[RenderSegment] = []
    cursor = 0.0

    for group in _group_lyric_rows(rows, max(1, lyric_group_size), max(1, chorus_group_size)):
        start = float(group[0]["start_sec"])
        end = float(group[-1]["end_sec"])
        segment_start = start
        if start - cursor >= GAP_THRESHOLD_SEC:
            segments.extend(_gap_segments(cursor, start, _gap_label(cursor, start, total_duration_sec)))
        elif start > cursor:
            if segments:
                segments[-1] = _with_bounds(segments[-1], end_sec=start)
            else:
                segment_start = cursor
        if _is_instrumental(group[0]):
            segments.extend(_marker_gap_segments(len(segments), group[0], segment_start, end))
        else:
            segments.append(_lyric_segment(len(segments), group, segment_start, end))
        cursor = max(cursor, end)

    if total_duration_sec - cursor >= GAP_THRESHOLD_SEC:
        segments.extend(_gap_segments(cursor, total_duration_sec, _gap_label(cursor, total_duration_sec, total_duration_sec)))
    elif total_duration_sec > cursor and segments:
        segments[-1] = _with_bounds(segments[-1], end_sec=total_duration_sec)

    return [_renumber(segment, index) for index, segment in enumerate(segments)]


def _select_render_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trusted_positions = [index for index, row in enumerate(rows) if _is_trusted_timing(row)]
    if not trusted_positions:
        return rows

    first_trusted = trusted_positions[0]
    last_trusted = trusted_positions[-1]
    return [
        row
        for index, row in enumerate(rows)
        if _is_trusted_timing(row) or first_trusted < index < last_trusted
    ]


def _group_lyric_rows(rows: list[dict[str, Any]], lyric_group_size: int, chorus_group_size: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in rows:
        size = chorus_group_size if _is_chorus(row) else lyric_group_size
        if current and _starts_new_group(current, row, size):
            groups.append(current)
            current = []
        current.append(row)
    if current:
        groups.append(current)
    return groups


def _starts_new_group(current: list[dict[str, Any]], row: dict[str, Any], size: int) -> bool:
    previous = current[-1]
    if _is_instrumental(previous) or _is_instrumental(row):
        return True
    if len(current) >= size:
        return True
    if _is_chorus(previous) != _is_chorus(row):
        return True
    if previous["section"] != row["section"]:
        return True
    if float(row["start_sec"]) - float(previous["end_sec"]) >= GAP_THRESHOLD_SEC:
        return True
    return False


def _lyric_segment(index: int, group: list[dict[str, Any]], start: float, end: float) -> RenderSegment:
    is_chorus = _is_chorus(group[0])
    return RenderSegment(
        index=index,
        kind="lyrics",
        section=str(group[0]["section"]),
        is_chorus=is_chorus,
        use_reference=is_chorus or any(bool(row["use_reference"]) for row in group),
        source_line_indices=[int(row["line_index"]) for row in group],
        clean_text="\n".join(str(row["clean_text"]) for row in group),
        start_sec=round(start, 6),
        end_sec=round(end, 6),
    )


def _marker_gap_segments(index: int, row: dict[str, Any], start: float, end: float) -> list[RenderSegment]:
    label = str(row["clean_text"] or row["section"])
    return _gap_segments(start, end, label, section=str(row["section"]), start_index=index)


def _is_chorus(row: dict[str, Any]) -> bool:
    return bool(row["is_chorus"]) or is_chorus_section(str(row["section"]))


def _is_instrumental(row: dict[str, Any]) -> bool:
    return is_instrumental_section(str(row["section"]))


def _is_trusted_timing(row: Any) -> bool:
    confidence = row["confidence"]
    return confidence is None or float(confidence) >= MIN_RENDER_CONFIDENCE


def _gap_segments(start: float, end: float, label: str, section: str | None = None, start_index: int = 0) -> list[RenderSegment]:
    duration = end - start
    if duration <= 0:
        return []
    chunks = _gap_chunks(start, end)
    cursor = start
    segments: list[RenderSegment] = []
    for offset, length in enumerate(chunks, start=1):
        segment_end = min(end, cursor + length)
        suffix = "" if len(chunks) == 1 else f" {offset}"
        segments.append(
            RenderSegment(
                index=start_index + len(segments),
                kind="gap",
                section=section or label,
                is_chorus=False,
                use_reference=False,
                source_line_indices=[],
                clean_text=f"{label}{suffix}",
                start_sec=round(cursor, 6),
                end_sec=round(segment_end, 6),
            )
        )
        cursor = segment_end
    return segments


def _gap_chunks(start: float, end: float) -> list[float]:
    remaining = round(end - start, 6)
    if remaining <= SINGLE_GAP_TOLERANCE_SEC:
        return [remaining]
    count = max(1, int(-(-remaining // MAX_GAP_SEC)))
    if remaining / count < MIN_GAP_SEC:
        count = max(1, int(remaining // MIN_GAP_SEC))
    chunk = remaining / count
    return [round(chunk, 6) for _ in range(count)]


def _gap_label(start: float, end: float, total: float) -> str:
    if start <= 0.001:
        return "Instrumental intro"
    if end >= total - 0.001:
        return "Instrumental outro"
    return "Instrumental break"


def _renumber(segment: RenderSegment, index: int) -> RenderSegment:
    return _copy_segment(segment, index=index)


def _with_bounds(segment: RenderSegment, start_sec: float | None = None, end_sec: float | None = None) -> RenderSegment:
    return _copy_segment(
        segment,
        start_sec=segment.start_sec if start_sec is None else round(start_sec, 6),
        end_sec=segment.end_sec if end_sec is None else round(end_sec, 6),
    )


def _copy_segment(
    segment: RenderSegment,
    index: int | None = None,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> RenderSegment:
    return RenderSegment(
        index=segment.index if index is None else index,
        kind=segment.kind,
        section=segment.section,
        is_chorus=segment.is_chorus,
        use_reference=segment.use_reference,
        source_line_indices=segment.source_line_indices,
        clean_text=segment.clean_text,
        start_sec=segment.start_sec if start_sec is None else start_sec,
        end_sec=segment.end_sec if end_sec is None else end_sec,
        prompt=segment.prompt,
        image_path=segment.image_path,
        clip_path=segment.clip_path,
        audio_path=segment.audio_path,
        scene_plan=segment.scene_plan,
        status=segment.status,
        error=segment.error,
    )


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()} if hasattr(row, "keys") else dict(row)

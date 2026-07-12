from __future__ import annotations

from .models import LineTiming, LyricLine


def distribute_evenly(lines: list[LyricLine], total_duration_sec: float) -> list[LineTiming]:
    if total_duration_sec <= 0:
        raise ValueError("total_duration_sec must be greater than zero")
    if not lines:
        return []

    segment = total_duration_sec / len(lines)
    timings: list[LineTiming] = []
    for line in lines:
        start_sec = round(line.index * segment, 6)
        end_sec = round(total_duration_sec if line.index == len(lines) - 1 else (line.index + 1) * segment, 6)
        timings.append(LineTiming(line_index=line.index, start_sec=start_sec, end_sec=end_sec, confidence=0.0))
    return timings


def apply_manual_timing(timing: LineTiming, start_sec: float, end_sec: float) -> LineTiming:
    if start_sec < 0:
        raise ValueError("start_sec must be zero or greater")
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")
    return LineTiming(line_index=timing.line_index, start_sec=start_sec, end_sec=end_sec, confidence=1.0)

from __future__ import annotations

from .audio import audio_window_score
from .models import ReelCandidate, ReelLyricSection, ReelVideoMetadata

MAX_REEL_SECONDS = 60.0
SECTION_SCORE = {
    "Chorus": 1.0,
    "Pre-Chorus": 0.75,
    "Bridge": 0.7,
    "Verse": 0.6,
}


def generate_candidates(
    sections: list[ReelLyricSection],
    metadata: ReelVideoMetadata,
    limit: int = 10,
    audio_features: list[dict] | None = None,
) -> list[ReelCandidate]:
    raw: list[ReelCandidate] = []
    timed = [section for section in sections if section.start_sec is not None and section.end_sec is not None and section.end_sec > section.start_sec]
    for index, section in enumerate(timed):
        raw.append(_candidate_for_sections([section], metadata, f"{section.type} {section.occurrence}", ["section"], audio_features))
        if section.type == "Chorus" and index > 0 and timed[index - 1].type == "Pre-Chorus":
            raw.append(_candidate_for_sections([timed[index - 1], section], metadata, f"Pre-Chorus + Chorus {section.occurrence}", ["pre-chorus", "hook"], audio_features))
        if section.type == "Chorus" and index > 0 and timed[index - 1].type == "Bridge":
            raw.append(_candidate_for_sections([timed[index - 1], section], metadata, f"Bridge + Chorus {section.occurrence}", ["bridge", "final lift"], audio_features))
    choruses = [section for section in timed if section.type == "Chorus"]
    if choruses:
        final = choruses[-1]
        raw.append(_candidate_for_sections([final], metadata, f"Final Chorus {final.occurrence}", ["final chorus", "hook"], audio_features))
    verses = [section for section in timed if section.type == "Verse"]
    if verses:
        verse = _strongest_section(verses, audio_features)
        raw.append(_candidate_for_sections([verse], metadata, "Strong Verse", ["verse contrast"], audio_features))
    unique = _dedupe_candidates(raw)
    return sorted(unique, key=lambda item: (-item.score, item.start_sec, item.end_sec))[:limit]


def _candidate_for_sections(
    sections: list[ReelLyricSection],
    metadata: ReelVideoMetadata,
    label: str,
    reasons: list[str],
    audio_features: list[dict] | None = None,
) -> ReelCandidate:
    start = max(0.0, min(float(section.start_sec or 0) for section in sections) - 0.4)
    end = min(float(metadata.duration), max(float(section.end_sec or 0) for section in sections) + 0.6)
    if end - start > MAX_REEL_SECONDS:
        end = start + MAX_REEL_SECONDS
    duration = max(0.0, end - start)
    primary = max(sections, key=lambda section: SECTION_SCORE.get(section.type, 0.55))
    duration_score = max(0.0, 1.0 - abs(duration - 30.0) / 60.0)
    final_bonus = 0.12 if "Final" in label else 0.0
    combo_bonus = 0.1 if len(sections) > 1 else 0.0
    audio_score = audio_window_score(audio_features or [], start, end)
    audio_bonus = float(audio_score["score"]) * 0.45
    score = SECTION_SCORE.get(primary.type, 0.55) + duration_score + final_bonus + combo_bonus + audio_bonus
    audio_reasons = []
    if audio_features:
        audio_reasons = [
            f"energy {float(audio_score['energy']):.2f}",
            f"onset {float(audio_score['onset']):.2f}",
            f"beats {int(audio_score['beat_count'])}",
        ]
    return ReelCandidate(
        label=label,
        start_sec=round(start, 3),
        end_sec=round(end, 3),
        score=round(score, 4),
        reasons=reasons + audio_reasons + [f"{duration:.1f}s"],
        crop=center_crop(metadata),
    )


def _strongest_section(sections: list[ReelLyricSection], audio_features: list[dict] | None) -> ReelLyricSection:
    if not audio_features:
        return max(sections, key=lambda item: item.end_sec - item.start_sec)
    return max(
        sections,
        key=lambda item: audio_window_score(audio_features, float(item.start_sec or 0), float(item.end_sec or 0))["score"],
    )


def center_crop(metadata: ReelVideoMetadata) -> dict[str, int | float | str]:
    crop_height = int(metadata.height)
    crop_width = round(crop_height * 9 / 16)
    if crop_width > metadata.width:
        crop_width = int(metadata.width)
        crop_height = round(crop_width * 16 / 9)
    crop_x = max(0, round((int(metadata.width) - crop_width) / 2))
    crop_y = max(0, round((int(metadata.height) - crop_height) / 2))
    return {
        "mode": "static_center",
        "source_width": int(metadata.width),
        "source_height": int(metadata.height),
        "crop_x": crop_x,
        "crop_y": crop_y,
        "crop_width": crop_width,
        "crop_height": crop_height,
    }


def _dedupe_candidates(candidates: list[ReelCandidate]) -> list[ReelCandidate]:
    seen: set[tuple[int, int, str]] = set()
    unique: list[ReelCandidate] = []
    for candidate in candidates:
        key = (round(candidate.start_sec * 10), round(candidate.end_sec * 10), candidate.label)
        if key in seen or candidate.end_sec <= candidate.start_sec:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique

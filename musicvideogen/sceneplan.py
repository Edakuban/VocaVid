from __future__ import annotations

import json
import re
from typing import Any

from .prompt_templates import load_named_prompt_template, render_prompt_template


DEFAULT_SCENEPLAN_CONCEPT_TEMPLATE = """Create a concise music video bible for a cohesive, high-impact music video.

Genre: {GENRE}
Global visual style: {GLOBAL_STYLE}
Total render segments: {TOTAL_SEGMENTS}
Lyrics lines per normal clip: {LYRIC_GROUP_SIZE}
Lyrics lines per chorus/refrain clip: {CHORUS_GROUP_SIZE}

Use the fixed render segments below to infer the song structure and energy curve.

Performance intent:
The performer appears in chorus/refrain sections whenever the lyrics and genre support it.
Use live performance language for band-friendly genres: microphone, stage, band, backlights, crowd energy, and dramatic music-video scale.
For electronic, EDM, synth, techno, ambient, or DJ-oriented genres, avoid forcing a classic band; use a microphone, DJ/controller setup, light rig, club, LED wall, or solo electronic performance when appropriate.
Every scene that includes the performer must be planned as visible singing or lip-sync, never silent posing.

Return only these sections:
Core concept: one sentence
Visual world: locations, atmosphere, color language, and production design
Main character / performer role: how the reference singer/person appears
Recurring motifs: 4-6 visual motifs that can evolve across the song
Forbidden repetitions: shots or actions to avoid repeating too often
Chorus escalation plan: how each chorus/refrain becomes bigger, heavier, and more iconic
Final escalation: how the final section resolves or transforms the video's visual idea

Keep it concrete and direct. No markdown tables.

Fixed render segments:
{SEGMENTS}"""


DEFAULT_SCENEPLAN_TEMPLATE = """Create a continuous music video scene plan for the whole song.

Genre: {GENRE}
Global visual style: {GLOBAL_STYLE}
Total render segments: {TOTAL_SEGMENTS}
Lyrics lines per normal clip: {LYRIC_GROUP_SIZE}
Lyrics lines per chorus/refrain clip: {CHORUS_GROUP_SIZE}
{VIDEO_BIBLE_CONTEXT}

First decide the overall concept and visual progression across the whole song, then assign one concise visual beat to each fixed render segment.

The scene plan must feel like a real edited music video, not a sequence of similar character shots.

Chorus/refrain performance policy:

* Prefer chorus/refrain segments as performance shots with the reference performer as the focus person, especially when the segment has uses_reference=True.
* For rock, metal, punk, pop-rock, country, folk, soul, gospel, and similar band-friendly genres, performance shots may include a microphone, live band, stage, backlights, crowd energy, dramatic silhouettes, and concert-scale lighting.
* For electronic, EDM, synth, techno, ambient, DJ, or club-oriented genres, do not force a classic live band. Use genre-appropriate performance language such as microphone, DJ/controller setup, light rig, club, LED wall, projection, solo performer, or electronic stage.
* Not every scene must include the performer. Every scene that includes the performer must show visible singing or lip-sync to the lyrics.
* Verse and bridge segments should mix story, atmosphere, symbols, inserts, locations, and occasional performance fragments.

Shot variety requirements:

* Maximum 1 out of 3 consecutive segments may primarily show the main character walking or standing.
* At least 30% of all segments must focus on something other than the main character.
* Include a balanced mix of:

  * performance shots,
  * worldbuilding/location shots,
  * symbolic metaphor shots,
  * close-up object shots,
  * machinery or environmental shots,
  * memory/inner-conflict shots,
  * abstract rhythm montage shots,
  * large-scale chorus shots.
* Every segment must introduce a new visual idea, camera angle, subject, movement, symbol, or emotional beat.
* Repeated motifs are allowed only if they evolve visually or emotionally.

Continuity rules:

* Keep locations, motifs, color language, props, characters, atmosphere, and visual symbolism consistent across the full timeline.
* Build a clear emotional progression from the beginning to the end.
* Chorus/refrain segments should feel connected through recurring performance, identity, scale, or symbolic shots, but should escalate with each repetition.
* Segments with uses_reference=True should be shots that can feature the singer/person from the reference images.
* Segments with uses_reference=False should preferably be used for worldbuilding, objects, machinery, symbolic imagery, crowds, landscapes, abstract rhythm shots, or environmental storytelling.

Creative interpretation rules:

* Do not simply visualize the lyrics word-for-word.
* Translate the lyrics into cinematic images, metaphors, atmosphere, and emotional beats.
* Avoid generic phrases like "epic shot", "dramatic scene", or "dark atmosphere" unless supported by specific visual details.
* Use concrete visual language: camera framing, subject, movement, lighting, location, color, action, and mood.
* For each segment, make a concrete director's decision: shot_type, subject, camera/framing, movement, motif, and how it differs from nearby segments.
* No dialogue, no text on screen unless explicitly requested.

Return:
Overall concept: one sentence
Visual progression: intro -> verse -> chorus -> bridge/finale style progression

Return every render segment index exactly once in this exact format:
0: scene description
1: scene description

You must return exactly {TOTAL_SEGMENTS} numbered segment lines, from {FIRST_INDEX} to {LAST_INDEX}.
Do not skip, merge, rename, or add segments.
Use only the numeric index at the start of each segment line. Do not write "segment_index".

Fixed render segments:
{SEGMENTS}"""


def make_sceneplan_concept_prompt(project: Any, segments: list[Any]) -> str:
    genre = _row_value(project, "genre", "") or "unspecified genre"
    style = _row_value(project, "global_style_prompt", "")
    lyric_group_size = _row_value(project, "lyric_group_size", "2")
    chorus_group_size = _row_value(project, "chorus_group_size", "1")
    total_segments = len(segments)
    lines = "\n".join(
        _segment_context_line(row)
        for row in segments
    )
    return render_prompt_template(
        load_named_prompt_template("sceneplan_concept.txt", DEFAULT_SCENEPLAN_CONCEPT_TEMPLATE),
        _sceneplan_variables(
            genre=genre,
            style=style,
            lyric_group_size=lyric_group_size,
            chorus_group_size=chorus_group_size,
            total_segments=total_segments,
            segments_text=lines,
        ),
    )


def make_sceneplan_prompt(project: Any, segments: list[Any], video_bible: str = "") -> str:
    genre = _row_value(project, "genre", "") or "unspecified genre"
    style = _row_value(project, "global_style_prompt", "")
    lyric_group_size = _row_value(project, "lyric_group_size", "2")
    chorus_group_size = _row_value(project, "chorus_group_size", "1")
    total_segments = len(segments)
    first_index = int(segments[0]["segment_index"]) if segments else 0
    last_index = int(segments[-1]["segment_index"]) if segments else 0
    lines = "\n".join(
        _segment_context_line(row)
        for row in segments
    )
    bible_context = f"""
Video bible to follow:
{video_bible}
""" if video_bible.strip() else ""
    return render_prompt_template(
        load_named_prompt_template("sceneplan.txt", DEFAULT_SCENEPLAN_TEMPLATE),
        _sceneplan_variables(
            genre=genre,
            style=style,
            lyric_group_size=lyric_group_size,
            chorus_group_size=chorus_group_size,
            total_segments=total_segments,
            first_index=first_index,
            last_index=last_index,
            segments_text=lines,
            video_bible_context=bible_context,
        ),
    )


def _sceneplan_variables(
    genre: str = "",
    style: str = "",
    lyric_group_size: str = "",
    chorus_group_size: str = "",
    total_segments: int = 0,
    first_index: int = 0,
    last_index: int = 0,
    segments_text: str = "",
    video_bible_context: str = "",
) -> dict[str, object]:
    return {
        "genre": genre,
        "GENRE": genre,
        "global_style": style,
        "GLOBAL_STYLE": style,
        "lyric_group_size": lyric_group_size,
        "LYRIC_GROUP_SIZE": lyric_group_size,
        "chorus_group_size": chorus_group_size,
        "CHORUS_GROUP_SIZE": chorus_group_size,
        "total_segments": total_segments,
        "TOTAL_SEGMENTS": total_segments,
        "first_index": first_index,
        "FIRST_INDEX": first_index,
        "last_index": last_index,
        "LAST_INDEX": last_index,
        "segments": segments_text,
        "SEGMENTS": segments_text,
        "video_bible_context": video_bible_context,
        "VIDEO_BIBLE_CONTEXT": video_bible_context,
    }


def _segment_context_line(row: Any) -> str:
    text = str(row["clean_text"]).replace("\n", " / ")
    source_line_indices = _line_indices(row)
    return (
        f"{row['segment_index']}. {row['kind']} {row['start_sec']}-{row['end_sec']}s "
        f"section={row['section']} chorus={bool(row['is_chorus'])} "
        f"uses_reference={bool(row['use_reference'])} line_indices={source_line_indices}: {text}"
    )


def _line_indices(row: Any) -> list[int]:
    value = _row_value(row, "source_line_indices", "[]")
    if isinstance(value, list):
        return [int(item) for item in value]
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [int(item) for item in parsed]


def fallback_scene_plans(project: Any, segments: list[Any]) -> dict[int, str]:
    genre = _row_value(project, "genre", "") or "music video"
    total = max(1, len(segments))
    plans: dict[int, str] = {}
    for row in segments:
        index = int(row["segment_index"])
        act = _act_name(index, total)
        text = str(row["clean_text"]).replace("\n", " / ")
        shot_type, camera, subject, action = _fallback_shot_parts(row, index)
        plans[index] = (
            f"{act} {genre} {shot_type}: {camera}; {subject}; "
            f"{action}; lyric cue: {text}"
        )
    return plans


def parse_scene_plan_text(text: str, segment_indices: list[int]) -> dict[int, str]:
    wanted = set(segment_indices)
    parsed: dict[int, str] = {}
    for line in text.splitlines():
        match = re.match(r"\s*(?:(?:segment(?:_index)?|segment\s+index)\s*[:#-]?\s*)?(\d+)\s*[:.)-]\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if not match:
            continue
        index = int(match.group(1))
        if index in wanted:
            parsed[index] = match.group(2).strip()
    return parsed


def _act_name(index: int, total: int) -> str:
    position = index / max(1, total - 1)
    if position < 0.25:
        return "Opening"
    if position < 0.65:
        return "Development"
    return "Finale"


def _fallback_shot_parts(row: Any, index: int) -> tuple[str, str, str, str]:
    is_chorus = bool(row["is_chorus"])
    uses_reference = bool(row["use_reference"])
    kind = str(row["kind"])
    section = str(row["section"])

    gap_cycle = [
        (
            "wide location shot",
            "slow crane over the empty battlefield with drifting ash",
            "ruined trenches, smoke columns, and a cold horizon",
            "embers pulse in time with the instrumental beat",
        ),
        (
            "object close-up",
            "macro lens tracks across scorched metal, wet earth, and glowing dust",
            "a symbolic relic half-buried in mud",
            "sparks crawl over its surface like a fading memory",
        ),
        (
            "abstract rhythm montage",
            "rapid cuts between firelight, shadows, boots, and vibrating air",
            "environmental fragments instead of the singer",
            "the edit follows the drums without literal storytelling",
        ),
    ]
    lyric_cycle = [
        (
            "memory shot",
            "handheld close frame with shallow depth of field",
            "ghostly traces of lost comrades at the edge of vision",
            "the scene bends from present ruin into traumatic memory",
        ),
        (
            "symbolic metaphor shot",
            "low angle dolly through smoke and ember light",
            "the soul fire motif reflected in water, glass, or ash",
            "the symbol changes shape instead of repeating the same pose",
        ),
        (
            "environmental storytelling shot",
            "locked-off frame that lets wind and debris create movement",
            "the battlefield itself acting as the emotional subject",
            "small details reveal the cost of the lyric without showing gore",
        ),
        (
            "object close-up",
            "tight insert with slow push-in and hard side light",
            "hands, medals, cracked earth, or a smoldering prop",
            "the object carries the lyric emotion through texture and motion",
        ),
    ]
    performance_cycle = [
        (
            "performance shot",
            "medium close-up with controlled push-in and ember backlight",
            "the singer framed against smoke, fire, and cold blue shadows",
            "the chest-level soul fire brightens with the chorus line",
        ),
        (
            "large-scale chorus shot",
            "wide heroic frame with slow lateral movement",
            "the singer and ghostly silhouettes unified by the refrain",
            "the recurring chorus image escalates in scale and intensity",
        ),
    ]

    if kind == "gap":
        return gap_cycle[index % len(gap_cycle)]
    if is_chorus or uses_reference:
        return performance_cycle[index % len(performance_cycle)]
    if "bridge" in section.lower():
        return lyric_cycle[(index + 1) % len(lyric_cycle)]
    return lyric_cycle[index % len(lyric_cycle)]


def _row_value(row: Any, key: str, default: str) -> str:
    try:
        return str(row[key])
    except (KeyError, IndexError, TypeError):
        return default

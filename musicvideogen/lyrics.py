from __future__ import annotations

import re

from .models import LyricLine

TAG_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
CHORUS_SECTIONS = {"chorus", "refrain"}
REFERENCE_TAGS = {"me", "self", "ref", "reference", "singer", "ich", "mich"}
INSTRUMENTAL_SECTION_WORDS = {"instrumental", "intro", "outro", "end"}


def parse_suno_lyrics(text: str) -> list[LyricLine]:
    lines: list[LyricLine] = []
    current_section = "Unknown"

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        tag_match = TAG_RE.match(stripped)
        if tag_match:
            current_section = tag_match.group(1).strip()
            if is_instrumental_section(current_section):
                lines.append(
                    LyricLine(
                        index=len(lines),
                        section=current_section,
                        raw_text=stripped,
                        clean_text=current_section,
                        is_chorus=False,
                        use_reference=False,
                    )
                )
            continue

        inline_tags = _inline_tags(stripped)
        clean_text = _strip_inline_tags(stripped)
        if not clean_text:
            continue

        is_chorus = is_chorus_section(current_section)
        lines.append(
            LyricLine(
                index=len(lines),
                section=current_section,
                raw_text=stripped,
                clean_text=clean_text,
                is_chorus=is_chorus,
                use_reference=is_chorus or bool(inline_tags & REFERENCE_TAGS),
            )
        )

    return lines


def is_chorus_section(section: str) -> bool:
    normalized = re.sub(r"[^a-z]+", " ", section.casefold()).strip()
    first_word = normalized.split(" ", 1)[0] if normalized else ""
    return first_word in CHORUS_SECTIONS


def is_instrumental_section(section: str) -> bool:
    words = set(re.sub(r"[^a-z]+", " ", section.casefold()).strip().split())
    return bool(words & INSTRUMENTAL_SECTION_WORDS)


def _strip_inline_tags(line: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", line).strip()


def _inline_tags(line: str) -> set[str]:
    return {tag.strip().lower() for tag in re.findall(r"\[([^\]]+)\]", line)}

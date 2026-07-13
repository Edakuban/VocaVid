from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReelVideoMetadata:
    duration: float
    width: int
    height: int
    fps: float
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    codec: str = ""
    rotation: int = 0


@dataclass(frozen=True)
class ReelLyricSection:
    type: str
    occurrence: int
    text: str
    start_sec: float | None = None
    end_sec: float | None = None
    source_indices: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ReelCandidate:
    label: str
    start_sec: float
    end_sec: float
    score: float
    reasons: list[str] = field(default_factory=list)
    crop: dict[str, float | int | str] = field(default_factory=dict)

    @property
    def duration_sec(self) -> float:
        return round(self.end_sec - self.start_sec, 6)


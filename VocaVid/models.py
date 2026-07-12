from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LyricLine:
    index: int
    section: str
    raw_text: str
    clean_text: str
    is_chorus: bool
    use_reference: bool = False


@dataclass(frozen=True)
class LineTiming:
    line_index: int
    start_sec: float
    end_sec: float
    confidence: float

    @property
    def duration_sec(self) -> float:
        return round(self.end_sec - self.start_sec, 6)


@dataclass(frozen=True)
class RenderSegment:
    index: int
    kind: str
    section: str
    is_chorus: bool
    use_reference: bool
    source_line_indices: list[int]
    clean_text: str
    start_sec: float
    end_sec: float
    prompt: str | None = None
    video_prompt: str | None = None
    image_path: str | None = None
    avatar_image_path: str | None = None
    clip_path: str | None = None
    audio_path: str | None = None
    scene_plan: str | None = None
    status: str = "pending"
    error: str = ""

    @property
    def duration_sec(self) -> float:
        return round(self.end_sec - self.start_sec, 6)


@dataclass(frozen=True)
class ComfyResult:
    prompt_id: str
    ok: bool
    output_files: list[str]
    text_outputs: list[str] | None = None
    error: str = ""


@dataclass(frozen=True)
class ProjectConfig:
    audio_path: Path
    lyrics_path: Path
    global_style_prompt: str
    reference_image_paths: list[Path]
    comfy_base_url: str = "http://127.0.0.1:8188"
    workflow_promptgen: Path | None = None
    workflow_image: Path | None = None
    workflow_video: Path | None = None
    workflow_chorus: Path | None = None
    output_resolution: str = "1280x720"
    fps: int = 24

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .media import ffmpeg_binary
from .models import ReelCandidate


Runner = Callable[..., subprocess.CompletedProcess[str]]


def render_reel_command(source: str | Path, target: str | Path, candidate: ReelCandidate, width: int, height: int, codec: str = "h264_mf") -> list[str]:
    crop = candidate.crop
    crop_filter = (
        f"crop={int(crop['crop_width'])}:{int(crop['crop_height'])}:"
        f"{int(crop['crop_x'])}:{int(crop['crop_y'])},scale={width}:{height}"
    )
    command = [
        ffmpeg_binary(),
        "-y",
        "-ss",
        f"{candidate.start_sec:.3f}",
        "-i",
        str(source),
        "-t",
        f"{candidate.duration_sec:.3f}",
        "-vf",
        crop_filter,
        "-c:v",
        codec,
    ]
    if codec == "libx264":
        command += ["-preset", "veryfast", "-crf", "20"]
    else:
        command += ["-b:v", "8M"]
    command += [
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(target),
    ]
    return command


def render_reel(source: str | Path, target: str | Path, candidate: ReelCandidate, width: int, height: int, runner: Runner = subprocess.run) -> None:
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    command = render_reel_command(source, target, candidate, width, height)
    try:
        result = runner(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required media tool not found: {command[0]}") from exc
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "FFmpeg reel render failed").strip())

from __future__ import annotations

import json
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Callable

from .models import ReelVideoMetadata


Runner = Callable[..., subprocess.CompletedProcess[str]]


def probe_video(path: str | Path, runner: Runner = subprocess.run) -> ReelVideoMetadata:
    video_path = Path(path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file does not exist: {video_path}")
    command = [
        ffprobe_binary(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        result = runner(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required media tool not found: {command[0]}") from exc
    if result.returncode != 0:
        raise ValueError((result.stderr or "ffprobe could not read the video").strip())
    return metadata_from_ffprobe_json(result.stdout)


def metadata_from_ffprobe_json(payload: str | dict) -> ReelVideoMetadata:
    data = json.loads(payload) if isinstance(payload, str) else payload
    streams = list(data.get("streams") or [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video:
        raise ValueError("Selected file has no video stream")
    if not audio:
        raise ValueError("Selected file has no audio stream")
    duration = _float_value(video.get("duration")) or _float_value(data.get("format", {}).get("duration"))
    if duration <= 0:
        raise ValueError("Selected video duration must be greater than zero")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    fps = _fps_value(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("Selected video metadata is incomplete")
    tags = video.get("tags") or {}
    rotation = int(float(video.get("rotation") or tags.get("rotate") or 0))
    return ReelVideoMetadata(
        duration=round(duration, 6),
        width=width,
        height=height,
        fps=round(fps, 6),
        audio_sample_rate=_optional_int(audio.get("sample_rate")),
        audio_channels=_optional_int(audio.get("channels")),
        codec=str(video.get("codec_name") or ""),
        rotation=rotation,
    )


def extract_audio_command(source: str | Path, target: str | Path, sample_rate: int = 16000) -> list[str]:
    return [
        ffmpeg_binary(),
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        str(target),
    ]


def run_command(command: list[str], runner: Runner = subprocess.run) -> None:
    try:
        result = runner(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required media tool not found: {command[0]}") from exc
    if result.returncode != 0:
        raise RuntimeError((result.stderr or f"Command failed: {' '.join(command)}").strip())


def ffmpeg_binary() -> str:
    return _media_binary("FFMPEG_BINARY", "ffmpeg", Path(r"C:\tmp\Dione\apps\Applio\applio\ffmpeg.exe"))


def ffprobe_binary() -> str:
    return _media_binary("FFPROBE_BINARY", "ffprobe", Path(r"C:\tmp\Dione\apps\Applio\applio\ffprobe.exe"))


def _media_binary(env_name: str, executable: str, bundled: Path) -> str:
    if os.environ.get(env_name):
        return os.environ[env_name]
    if shutil.which(executable):
        return executable
    if bundled.exists():
        return str(bundled)
    return executable


def _fps_value(value: object) -> float:
    text = str(value or "").strip()
    if not text or text == "0/0":
        return 0.0
    try:
        return float(Fraction(text))
    except (ValueError, ZeroDivisionError):
        return _float_value(text)


def _float_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .paths import resolve_storage_path, slug_folder_name, storage_relative_path
from .reels.media import ffmpeg_binary, probe_video


Runner = Callable[..., subprocess.CompletedProcess[str]]
MIN_DURATION = 3.01
MAX_DURATION = 7.99


def normalize_canvas_duration(value: object) -> float:
    duration = float(value)
    if not MIN_DURATION <= duration <= MAX_DURATION:
        raise ValueError("Spotify Canvas duration must be longer than 3 and shorter than 8 seconds")
    return round(duration, 3)


def canvas_render_command(source: Path, target: Path, start_sec: float, duration_sec: float, loop_mode: str) -> list[str]:
    base = [ffmpeg_binary(), "-y", "-ss", f"{max(0.0, start_sec):.3f}", "-i", str(source)]
    framing = "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920:flags=lanczos,setsar=1,fps=30"
    if loop_mode == "pingpong":
        half = duration_sec / 2.0
        filters = f"[0:v]trim=duration={half:.3f},setpts=PTS-STARTPTS,{framing},split[f][b];[b]reverse[r];[f][r]concat=n=2:v=1:a=0[outv]"
        return base + ["-filter_complex", filters, "-map", "[outv]", "-t", f"{duration_sec:.3f}", "-an", "-c:v", "h264_mf", "-b:v", "8M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)]
    return base + ["-t", f"{duration_sec:.3f}", "-vf", framing, "-an", "-c:v", "h264_mf", "-b:v", "8M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)]


class SpotifyCanvasPipeline:
    def __init__(self, store, generation_pipeline, app_root: Path, runner: Runner = subprocess.run):
        self.store = store
        self.generation_pipeline = generation_pipeline
        self.app_root = app_root
        self.runner = runner

    def generate_prompt(self, project_id: int, item_kind: str, item_index: int, duration_sec: float, draft: str = "") -> None:
        duration = normalize_canvas_duration(duration_sec)
        self.store.update_spotify_canvas(project_id, mode="generated", item_kind=item_kind, item_index=item_index, duration_sec=duration, prompt=draft, status="running", error="")
        try:
            prompt = self.generation_pipeline.generate_spotify_canvas_prompt(project_id, item_kind, item_index, duration, draft)
            self.store.update_spotify_canvas(project_id, prompt=prompt, status="prompted", error="")
        except Exception as exc:
            self.store.update_spotify_canvas(project_id, status="failed", error=str(exc))
            raise
    def render_existing(self, project_id: int, source_path: str, start_sec: float, duration_sec: float, loop_mode: str) -> None:
        duration = normalize_canvas_duration(duration_sec)
        mode = "pingpong" if loop_mode == "pingpong" else "cut"
        self.store.update_spotify_canvas(project_id, mode="existing", source_path=source_path, source_start_sec=max(0.0, start_sec), duration_sec=duration, loop_mode=mode, status="running", error="")
        self._render(project_id, source_path, start_sec, duration, mode)

    def generate_video(self, project_id: int, item_kind: str, item_index: int, duration_sec: float, prompt: str, loop_mode: str) -> None:
        duration = normalize_canvas_duration(duration_sec)
        if not prompt.strip():
            raise ValueError("Add or generate a Canvas prompt first")
        mode = "pingpong" if loop_mode == "pingpong" else "cut"
        self.store.update_spotify_canvas(project_id, mode="generated", item_kind=item_kind, item_index=item_index, duration_sec=duration, loop_mode=mode, prompt=prompt.strip(), status="running", error="")
        try:
            raw_path = self.generation_pipeline.generate_spotify_canvas_video(project_id, item_kind, item_index, duration, prompt.strip())
            raw_storage = storage_relative_path(self.app_root, raw_path)
            self.store.update_spotify_canvas(project_id, raw_video_path=raw_storage)
            self._render(project_id, raw_storage, 0.0, duration, mode)
        except Exception as exc:
            self.store.update_spotify_canvas(project_id, status="failed", error=str(exc))
            raise

    def _render(self, project_id: int, source_path: str, start_sec: float, duration: float, loop_mode: str) -> None:
        try:
            project = self.store.get_project(project_id)
            source = resolve_storage_path(self.app_root, source_path)
            metadata = probe_video(source, runner=self.runner)
            required_source = duration / 2.0 if loop_mode == "pingpong" else duration
            if max(0.0, float(start_sec)) + required_source > metadata.duration + 0.05:
                raise ValueError("The selected source does not contain enough video after the start point")
            folder = self.app_root / "outputs" / slug_folder_name(str(project["name"])) / "spotify-canvas"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / "spotify-canvas.mp4"
            command = canvas_render_command(source, target, float(start_sec), duration, loop_mode)
            result = self.runner(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or "FFmpeg Spotify Canvas render failed").strip())
            checked = probe_video(target, runner=self.runner, require_audio=False)
            if checked.height < 720 or checked.width * 16 != checked.height * 9:
                raise RuntimeError("Rendered Spotify Canvas failed the 9:16 / 720px validation")
            self.store.update_spotify_canvas(project_id, export_path=storage_relative_path(self.app_root, target), status="done", error="")
        except Exception as exc:
            self.store.update_spotify_canvas(project_id, status="failed", error=str(exc))
            raise


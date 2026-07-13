from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from ..alignment import infer_language_from_lyrics, transcribe_words_with_fallback
from ..paths import resolve_storage_path, slug_folder_name
from .audio import analyze_audio_features
from .candidates import generate_candidates
from .lyrics import align_project_rows_to_words, project_rows_to_lyric_lines, project_rows_to_sections
from .media import extract_audio_command, probe_video, run_command
from .models import ReelCandidate, ReelVideoMetadata
from .render import render_reel
from .storage import ensure_reels_dirs, reels_storage_path


class ReelsPipeline:
    def __init__(self, store, app_root: Path, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.store = store
        self.app_root = app_root
        self.runner = runner

    def analyze(self, project_id: int, source_video_path: str) -> None:
        project = self.store.get_project(project_id)
        analysis = self.store.latest_reel_analysis(project_id)
        if analysis is None or str(analysis["source_video_path"]) != source_video_path:
            analysis_id = self.store.create_reel_analysis(project_id, source_video_path)
        else:
            analysis_id = int(analysis["id"])
        paths = ensure_reels_dirs(self.app_root, project)
        self.store.update_reel_analysis(analysis_id, status="running", error="")
        try:
            source_path = resolve_storage_path(self.app_root, source_video_path)
            metadata = probe_video(source_path, runner=self.runner)
            analysis_wav = paths["cache"] / "analysis.wav"
            run_command(extract_audio_command(source_path, analysis_wav), runner=self.runner)
            music_wav = paths["cache"] / "analysis_music.wav"
            run_command(extract_audio_command(source_path, music_wav, sample_rate=44100), runner=self.runner)
            rows = self.store.list_segments(project_id) or self.store.list_lines(project_id)
            lyric_lines = project_rows_to_lyric_lines(rows)
            language = infer_language_from_lyrics(lyric_lines)
            words = transcribe_words_with_fallback(
                analysis_wav,
                language=language,
                model_size=str(project["whisper_model_size"] or "small"),
            )
            aligned_rows, timings = align_project_rows_to_words(rows, words, metadata.duration)
            sections = project_rows_to_sections(aligned_rows)
            audio_features = analyze_audio_features(music_wav)
            candidates = generate_candidates(sections, metadata, audio_features=audio_features)
            self.store.update_reel_analysis(
                analysis_id,
                status="done",
                error="",
                metadata_json=json.dumps(asdict(metadata)),
                transcript_json=json.dumps([asdict(word) for word in words]),
                lyric_alignment_json=json.dumps([asdict(section) for section in sections]),
                audio_features_json=json.dumps(audio_features),
            )
            self.store.replace_reel_candidates(analysis_id, candidates)
            self._write_snapshot(paths["root"] / "analysis.json", metadata, sections, candidates, words, timings, audio_features)
        except Exception as exc:
            self.store.update_reel_analysis(analysis_id, status="failed", error=str(exc))
            raise

    def render_preview(self, project_id: int, analysis_id: int, candidate_id: int) -> None:
        self._render_candidate(project_id, analysis_id, candidate_id, preview=True)

    def export(self, project_id: int, analysis_id: int, candidate_id: int) -> None:
        self._render_candidate(project_id, analysis_id, candidate_id, preview=False)

    def clear_candidate_outputs(self, project_id: int, analysis_id: int, candidate_id: int) -> None:
        _ = project_id
        _ = analysis_id
        candidate = self.store.get_reel_candidate(candidate_id)
        for field in ("preview_path", "export_path"):
            path = resolve_storage_path(self.app_root, candidate[field])
            try:
                path.resolve().relative_to(self.app_root.resolve())
            except (OSError, ValueError):
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.store.update_reel_candidate(candidate_id, status="pending", error="", preview_path=None, export_path=None)

    def delete_candidate(self, project_id: int, analysis_id: int, candidate_id: int) -> None:
        self.clear_candidate_outputs(project_id, analysis_id, candidate_id)
        self.store.delete_reel_candidate(candidate_id)

    def _render_candidate(self, project_id: int, analysis_id: int, candidate_id: int, preview: bool) -> None:
        project = self.store.get_project(project_id)
        analysis = self.store.get_reel_analysis(analysis_id)
        candidate_row = self.store.get_reel_candidate(candidate_id)
        metadata = ReelVideoMetadata(**json.loads(analysis["metadata_json"] or "{}"))
        candidate = ReelCandidate(
            label=str(candidate_row["label"]),
            start_sec=float(candidate_row["start_sec"]),
            end_sec=float(candidate_row["end_sec"]),
            score=float(candidate_row["score"]),
            reasons=json.loads(candidate_row["reasons_json"] or "[]"),
            crop=json.loads(candidate_row["crop_json"] or "{}"),
        )
        paths = ensure_reels_dirs(self.app_root, project)
        width, height = (540, 960) if preview else (1080, 1920)
        folder = paths["previews"] if preview else paths["root"]
        suffix = "preview" if preview else "export"
        title_slug = slug_folder_name(candidate.label)
        target = folder / f"reel-{title_slug}-{candidate_id:03d}-{suffix}.mp4"
        field = "preview_path" if preview else "export_path"
        self.store.update_reel_candidate(candidate_id, status="running", error="")
        try:
            render_reel(resolve_storage_path(self.app_root, analysis["source_video_path"]), target, candidate, width, height, runner=self.runner)
            self.store.update_reel_candidate(
                candidate_id,
                status="done",
                error="",
                **{field: reels_storage_path(self.app_root, target)},
            )
        except Exception as exc:
            self.store.update_reel_candidate(candidate_id, status="failed", error=str(exc))
            raise

    def _write_snapshot(self, path: Path, metadata: ReelVideoMetadata, sections, candidates, words=None, timings=None, audio_features=None) -> None:
        words = words or []
        timings = timings or []
        audio_features = audio_features or []
        path.write_text(
            json.dumps(
                {
                    "video": asdict(metadata),
                    "lyrics": {"sections": [asdict(section) for section in sections]},
                    "clip_candidates": [asdict(candidate) for candidate in candidates],
                    "transcript": {"words": [asdict(word) for word in words]},
                    "alignment": [asdict(timing) for timing in timings],
                    "audio_features": audio_features,
                    "scenes": [],
                    "detections": [],
                    "focus_tracks": [],
                    "manual_keyframes": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

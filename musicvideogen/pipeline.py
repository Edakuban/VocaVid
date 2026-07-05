from __future__ import annotations

import json
import logging
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from urllib.request import urlretrieve

from .assembly import assemble_kdenlive_project, split_audio_segment
from .alignment import align_lyrics_to_words, infer_language_from_lyrics, normalize_whisper_model_size, transcribe_words_with_fallback
from .audio import get_wav_duration_sec
from .comfy import ComfyClient, load_workflow, with_output_prefix
from .lyrics import is_instrumental_section, parse_suno_lyrics
from .models import LineTiming, LyricLine
from .paths import resolve_storage_path, slug_folder_name, storage_relative_path
from .promptgen import inject_promptgen_context, inject_raw_text_prompt, inject_videoprompt_context, make_global_style_prompt, make_videoprompt_prompt
from .prompt_templates import load_named_prompt_template, render_prompt_template
from .sceneplan import fallback_scene_plans, make_sceneplan_concept_prompt, make_sceneplan_prompt, parse_scene_plan_text
from .segments import build_render_segments
from .store import Store
from .timing import apply_manual_timing, distribute_evenly
from .workflows import WorkflowPaths


logger = logging.getLogger(__name__)
MIN_CONFIDENT_ALIGNMENT_RATIO = 0.30
DEFAULT_AVATAR_IMAGE_TEMPLATE = """Edit Image 1 by replacing only the primary focus person with the identity from Image 2.

Image prompt context:
{IMAGE_PROMPT}

Scene plan context:
{SCENE_PLAN}

Genre: {GENRE}
Global visual style: {GLOBAL_STYLE}

Target selection:
Replace the main focus person in Image 1: the person closest to camera, most centered, largest in frame, most brightly lit, or visually treated as the subject. If multiple people are visible, replace only that focus person. Do not change background people, crowds, silhouettes, companions, enemies, or secondary characters.

Identity transfer:
Use Image 2 as the identity reference for the focus person. Transfer the face, facial structure, skin tone, age impression, hair, hairline, hair color, hairstyle, hair length, beard, moustache, facial hair, glasses, and overall body shape from Image 2.

Hair and face priority:
Replace all visible character hair with the hair from Image 2. Do not keep the original character's hair, hairline, hair color, hairstyle, beard, facial hair, or hair silhouette from Image 1.

Preserve scene:
Keep the background, mood, lighting, camera angle, composition, clothing, pose, posture, expression, gaze direction, and cinematic atmosphere from Image 1. Keep the outfit from Image 1 unless it conflicts with preserving the focus person's head and identity.

Boundaries:
Do not alter non-focus people. Do not add new people. Do not remove people. Do not change the scene, props, weapons, furniture, environment, framing, or style. Keep the result photorealistic and natural."""


class Pipeline:
    def __init__(self, store: Store, workspace: Path, ffmpeg_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.store = store
        self.workspace = workspace
        self.ffmpeg_runner = ffmpeg_runner
        self.workflows = WorkflowPaths.defaults(Path.cwd())
        self.kdenlive_template = Path.cwd() / "templates" / "kdenlivetemplate.kdenlive"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def align_evenly(self, project_id: int, selected_line_indices: list[int] | None = None) -> None:
        project = self.store.get_project(project_id)
        lines = [
            LyricLine(
                index=row["line_index"],
                section=row["section"],
                raw_text=row["raw_text"],
                clean_text=row["clean_text"],
                is_chorus=bool(row["is_chorus"]),
                use_reference=bool(row["use_reference"]),
            )
            for row in self.store.list_lines(project_id)
        ]
        duration = get_wav_duration_sec(self._project_input_path(project["audio_path"]))
        selected_timings = self._filter_timings(distribute_evenly(lines, duration), selected_line_indices)
        self.store.set_timings(project_id, selected_timings)
        for timing in selected_timings:
            self.store.update_line(project_id, timing.line_index, last_action="align")
        if not selected_line_indices:
            self.build_segments(project_id)

    def align_with_whisper(self, project_id: int, selected_line_indices: list[int] | None = None, force_cpu: bool = False) -> None:
        project = self.store.get_project(project_id)
        lines = [
            LyricLine(
                index=row["line_index"],
                section=row["section"],
                raw_text=row["raw_text"],
                clean_text=row["clean_text"],
                is_chorus=bool(row["is_chorus"]),
                use_reference=bool(row["use_reference"]),
            )
            for row in self.store.list_lines(project_id)
        ]
        audio_path = self._project_input_path(project["audio_path"])
        duration = get_wav_duration_sec(audio_path)
        language = infer_language_from_lyrics(lines)
        whisper_model_size = normalize_whisper_model_size(_row_value(project, "whisper_model_size", "small"))
        logger.info(
            "align start project_id=%s lines=%s selected=%s audio=%s duration_sec=%.3f language=%s whisper_model_size=%s",
            project_id,
            len(lines),
            selected_line_indices or "all",
            audio_path,
            duration,
            language or "auto",
            whisper_model_size,
        )
        fallback_error = ""
        timings, fallback_error = self._compute_whisper_timings(
            project_id,
            project,
            lines,
            duration,
            language,
            force_cpu=force_cpu,
        )
        selected_timings = self._filter_timings(timings, selected_line_indices)
        self._store_alignment_timings(project_id, selected_timings, fallback_error)
        if not selected_line_indices:
            self.build_segments(project_id)

    def update_timing(self, project_id: int, line_index: int, start_sec: float, end_sec: float) -> None:
        rows = self.store.list_lines(project_id)
        row = next(item for item in rows if item["line_index"] == line_index)
        current = LineTiming(
            line_index=line_index,
            start_sec=float(row["start_sec"] or 0),
            end_sec=float(row["end_sec"] or 0),
            confidence=float(row["confidence"] or 0),
        )
        updated = apply_manual_timing(current, start_sec=start_sec, end_sec=end_sec)
        self.store.set_timings(project_id, [updated])

    def update_segment_timing(self, project_id: int, segment_index: int, start_sec: float, end_sec: float) -> None:
        start = float(start_sec)
        end = float(end_sec)
        if end <= start:
            raise ValueError("end_sec must be greater than start_sec")
        project = self.store.get_project(project_id)
        segment = next(item for item in self.store.list_segments(project_id) if item["segment_index"] == segment_index)
        audio_path = (
            self._project_input_path(segment["audio_path"])
            if segment["audio_path"]
            else self._project_dir(project) / "audio-segments" / f"segment-{segment_index:03d}.wav"
        )
        split_audio_segment(
            self._project_input_path(project["audio_path"]),
            start,
            end,
            audio_path,
            runner=self.ffmpeg_runner,
        )
        self.store.update_segment(
            project_id,
            segment_index,
            start_sec=start,
            end_sec=end,
            audio_path=self._project_storage_path(audio_path),
            clip_path=None,
            video_approved=0,
            status="pending",
            error="",
        )

    def update_segment_section(self, project_id: int, segment_index: int, section_type: str) -> None:
        normalized = str(section_type or "").strip().casefold()
        is_chorus = normalized in {"refrain", "chorus"}
        section = "Bridge" if normalized == "bridge" else "Refrain" if is_chorus else "Verse"
        self.store.update_segment(
            project_id,
            segment_index,
            section=section,
            is_chorus=int(is_chorus),
            use_reference=int(is_chorus),
        )

    def build_segments(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        duration = get_wav_duration_sec(self._project_input_path(project["audio_path"]))
        logger.info(
            "build segments start project_id=%s lyric_group_size=%s chorus_group_size=%s duration_sec=%.3f",
            project_id,
            int(project["lyric_group_size"]),
            int(project["chorus_group_size"]),
            duration,
        )
        segments = build_render_segments(
            self.store.list_lines(project_id),
            duration,
            lyric_group_size=int(project["lyric_group_size"]),
            chorus_group_size=int(project["chorus_group_size"]),
        )
        gap_count = sum(1 for segment in segments if segment.kind == "gap")
        logger.info("segments planned project_id=%s count=%s gaps=%s", project_id, len(segments), gap_count)
        output_dir = self._project_dir(project) / "audio-segments"
        split_segments = []
        for segment in segments:
            audio_path = output_dir / f"segment-{segment.index:03d}.wav"
            logger.info(
                "split audio start project_id=%s segment=%s/%s kind=%s start=%.3f end=%.3f",
                project_id,
                segment.index + 1,
                len(segments),
                segment.kind,
                segment.start_sec,
                segment.end_sec,
            )
            started = time.monotonic()
            split_audio_segment(
                self._project_input_path(project["audio_path"]),
                segment.start_sec,
                segment.end_sec,
                audio_path,
                runner=self.ffmpeg_runner,
            )
            logger.info(
                "split audio done project_id=%s segment=%s/%s output=%s elapsed_sec=%.3f",
                project_id,
                segment.index + 1,
                len(segments),
                audio_path,
                time.monotonic() - started,
            )
            split_segments.append(
                type(segment)(
                    index=segment.index,
                    kind=segment.kind,
                    section=segment.section,
                    is_chorus=segment.is_chorus,
                    use_reference=segment.use_reference,
                    source_line_indices=segment.source_line_indices,
                    clean_text=segment.clean_text,
                    start_sec=segment.start_sec,
                    end_sec=segment.end_sec,
                    audio_path=self._project_storage_path(audio_path),
                    scene_plan=segment.scene_plan,
                )
            )
        self.store.replace_segments(project_id, split_segments)
        logger.info("build segments done project_id=%s stored=%s", project_id, len(split_segments))

    def generate_scene_plan(self, project_id: int, selected_segment_indices: list[int] | None = None) -> None:
        project = self.store.get_project(project_id)
        segments = self._selected_segments(project_id, selected_segment_indices)
        if not segments:
            return
        workflow_path = self.workflows.optional_promptgen()
        plans: dict[int, str]
        full_plan = ""
        if workflow_path:
            workflow = load_workflow(workflow_path)
            client = ComfyClient(project["comfy_base_url"])
            concept_result = client.run_workflow(inject_raw_text_prompt(workflow, make_sceneplan_concept_prompt(project, segments)), {})
            video_bible = concept_result.text_outputs[0].strip() if concept_result.ok and concept_result.text_outputs else ""
            prompt = make_sceneplan_prompt(project, segments, video_bible=video_bible)
            result = client.run_workflow(inject_raw_text_prompt(workflow, prompt), {})
            if result.ok and result.text_outputs:
                segment_plan = result.text_outputs[0].strip()
                full_plan = _format_successful_scene_plan_text(segment_plan, video_bible)
                plans = parse_scene_plan_text(segment_plan, [int(row["segment_index"]) for row in segments])
                fallback = fallback_scene_plans(project, segments)
                fallback_used = any(not plans.get(index) for index in fallback)
                plans = {index: plans.get(index) or fallback[index] for index in fallback}
                if fallback_used:
                    full_plan = _format_scene_plan_text(plans, "promptgen returned missing or unusable segment lines")
            else:
                plans = fallback_scene_plans(project, segments)
                full_plan = _format_scene_plan_text(plans, "promptgen returned no usable text")
        else:
            plans = fallback_scene_plans(project, segments)
            full_plan = _format_scene_plan_text(plans, "promptgen workflow is missing")
        for index, plan in plans.items():
            self.store.update_segment(project_id, index, scene_plan=plan, status="planned", error="", last_action="scene-plan")
        self.store.update_project(project_id, scene_plan=full_plan)

    def save_scene_plan(self, project_id: int, scene_plan: str) -> None:
        segments = self.store.list_segments(project_id)
        self.store.update_project(project_id, scene_plan=scene_plan)
        parsed = parse_scene_plan_text(scene_plan, [int(row["segment_index"]) for row in segments])
        for index, plan in parsed.items():
            self.store.update_segment(project_id, index, scene_plan=plan)

    def generate_global_style_prompt(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        lyrics = "\n".join(str(row["clean_text"]) for row in self.store.list_lines(project_id) if str(row["clean_text"]).strip())
        prompt = make_global_style_prompt(str(project["genre"] or ""), lyrics)
        style_prompt = ""
        workflow_path = self.workflows.optional_promptgen()
        if workflow_path:
            workflow = load_workflow(workflow_path)
            client = ComfyClient(project["comfy_base_url"])
            result = client.run_workflow(inject_raw_text_prompt(workflow, prompt), {})
            if result.ok and result.text_outputs:
                style_prompt = result.text_outputs[0].strip()
        if not style_prompt:
            genre = str(project["genre"] or "music video").strip() or "music video"
            style_prompt = (
                f"{genre}, cinematic music video, cohesive visual language, expressive lighting, "
                "strong atmosphere, detailed production design, emotionally synced to the lyrics"
            )
        self.store.update_project(project_id, global_style_prompt=style_prompt)

    def generate_prompts(self, project_id: int, selected_line_indices: list[int] | None = None) -> None:
        project = self.store.get_project(project_id)
        segments = self._selected_segments(project_id, selected_line_indices)
        if segments:
            workflow_path = self.workflows.optional_promptgen()
            if not workflow_path:
                for row in segments:
                    scene_plan = f"\nScene plan: {row['scene_plan']}" if row["scene_plan"] else ""
                    prompt = f"{row['clean_text']}.{scene_plan} {project['global_style_prompt']}".strip()
                    self.store.update_segment(project_id, row["segment_index"], prompt=prompt, status="prompted", error="", last_action="prompts")
                return
            for row in segments:
                self._run_comfy_for_segment_prompt(project_id, row, workflow_path)
            return
        workflow_path = self.workflows.optional_promptgen()
        if not workflow_path:
            for row in self._selected_rows(project_id, selected_line_indices):
                prompt = f"{row['clean_text']}. {project['global_style_prompt']}".strip()
                self.store.update_line(project_id, row["line_index"], prompt=prompt, status="prompted", error="", last_action="prompts")
            return
        for row in self._selected_rows(project_id, selected_line_indices):
            self._run_comfy_for_prompt(project_id, row, workflow_path)

    def generate_images(self, project_id: int, selected_line_indices: list[int] | None = None) -> None:
        segments = self._selected_segments(project_id, selected_line_indices)
        if segments:
            for row in segments:
                workflow = self.workflows.image_for_reference(bool(row["use_reference"]))
                self._run_comfy_for_segment(project_id, row, workflow, output_field="image_path", action="images")
            return
        for row in self._selected_rows(project_id, selected_line_indices):
            workflow = self.workflows.image_for_reference(bool(row["use_reference"]))
            self._run_comfy_for_line(project_id, row, workflow, output_field="image_path", action="images")

    def generate_avatar_images(self, project_id: int, selected_line_indices: list[int] | None = None) -> None:
        workflow = self.workflows.require_avatar_image()
        segments = self._selected_segments(project_id, selected_line_indices)
        if segments:
            for row in segments:
                self._run_comfy_for_avatar_segment(project_id, row, workflow)
            return
        for row in self._selected_rows(project_id, selected_line_indices):
            self._run_comfy_for_avatar_line(project_id, row, workflow)

    def generate_video_prompts(self, project_id: int, selected_line_indices: list[int] | None = None) -> None:
        project = self.store.get_project(project_id)
        segments = self._selected_segments(project_id, selected_line_indices)
        if segments:
            workflow_path = self.workflows.optional_promptgen()
            if not workflow_path:
                for row in segments:
                    prompt = make_videoprompt_prompt(
                        lyric_text=str(row["clean_text"]),
                        image_prompt=str(row["prompt"] or ""),
                        section=str(row["section"]),
                        is_chorus=bool(row["is_chorus"]),
                        global_style=str(project["global_style_prompt"]),
                        duration=f"{float(row['end_sec']) - float(row['start_sec']):.3f}",
                        genre=str(project["genre"] or ""),
                        scene_plan=str(row["scene_plan"] or ""),
                    )
                    self.store.update_segment(
                        project_id,
                        row["segment_index"],
                        video_prompt=prompt,
                        clip_path=None,
                        video_approved=0,
                        status="video prompted",
                        error="",
                        last_action="video-prompts",
                    )
                return
            for row in segments:
                self._run_comfy_for_segment_video_prompt(project_id, row, workflow_path)
            return

        workflow_path = self.workflows.optional_promptgen()
        if not workflow_path:
            for row in self._selected_rows(project_id, selected_line_indices):
                duration = 0.0
                if row["start_sec"] is not None and row["end_sec"] is not None:
                    duration = float(row["end_sec"]) - float(row["start_sec"])
                prompt = make_videoprompt_prompt(
                    lyric_text=str(row["clean_text"]),
                    image_prompt=str(row["prompt"] or ""),
                    section=str(row["section"]),
                    is_chorus=bool(row["is_chorus"]),
                    global_style=str(project["global_style_prompt"]),
                    duration=f"{duration:.3f}",
                    genre=str(project["genre"] or ""),
                )
                self.store.update_line(
                    project_id,
                    row["line_index"],
                    video_prompt=prompt,
                    clip_path=None,
                    video_approved=0,
                    status="video prompted",
                    error="",
                    last_action="video-prompts",
                )
            return
        for row in self._selected_rows(project_id, selected_line_indices):
            self._run_comfy_for_line_video_prompt(project_id, row, workflow_path)

    def generate_clips(self, project_id: int, selected_line_indices: list[int] | None = None) -> None:
        segments = self._selected_segments(project_id, selected_line_indices)
        if segments:
            for row in segments:
                workflow = self.workflows.require_video()
                self._run_comfy_for_segment(project_id, row, workflow, output_field="clip_path", prefer_avatar=True, action="clips")
            return
        for row in self._selected_rows(project_id, selected_line_indices):
            workflow = self.workflows.require_video()
            self._run_comfy_for_line(project_id, row, workflow, output_field="clip_path", prefer_avatar=True, action="clips")

    def assemble(self, project_id: int, selected_line_indices: list[int] | None = None) -> Path:
        if not self.all_videos_approved(project_id):
            raise ValueError("Cannot assemble final video: not approved")
        project = self.store.get_project(project_id)
        segments = self._selected_segments(project_id, selected_line_indices)
        rows = segments or self._selected_rows(project_id, selected_line_indices)
        clips = [
            {
                "path": self._project_input_path(row["clip_path"]),
                "start_sec": float(row["start_sec"]),
                "end_sec": float(row["end_sec"]),
            }
            for row in rows
            if row["clip_path"]
        ]
        output = self._project_dir(project) / "final.kdenlive"
        result = assemble_kdenlive_project(
            clips,
            self._project_input_path(project["audio_path"]),
            output,
            self.kdenlive_template,
            transition_handle_seconds=float(project["transition_handle_seconds"]),
        )
        self.store.update_project(project_id, final_video_path=self._project_storage_path(result))
        return result

    def retry_line(self, project_id: int, line_index: int) -> None:
        self.store.update_line(project_id, line_index, status="pending", error="")

    def insert_line_after(self, project_id: int, line_index: int, text: str, section: str = "") -> None:
        rows = self.store.list_lines(project_id)
        previous = next(item for item in rows if item["line_index"] == line_index)
        selected_section = section.strip() or str(previous["section"])
        parsed = parse_suno_lyrics(f"[{selected_section}]\n{text}")
        if not parsed:
            raise ValueError("Line text must not be empty")
        line = parsed[0]
        self.store.insert_line_after(
            project_id,
            line_index,
            section=line.section,
            raw_text=line.raw_text,
            clean_text=line.clean_text,
            is_chorus=line.is_chorus,
            use_reference=line.use_reference,
        )

    def delete_line(self, project_id: int, line_index: int) -> None:
        self.store.delete_line(project_id, line_index)

    def save_line_prompts(self, project_id: int, line_index: int, prompt: str, video_prompt: str) -> None:
        self.store.update_line(project_id, line_index, prompt=prompt, video_prompt=video_prompt)

    def save_segment_prompts(self, project_id: int, segment_index: int, prompt: str, video_prompt: str) -> None:
        self.store.update_segment(project_id, segment_index, prompt=prompt, video_prompt=video_prompt)

    def select_line_image_source(self, project_id: int, line_index: int, selected_image_source: str) -> None:
        self.store.update_line(project_id, line_index, selected_image_source=_normalize_image_source(selected_image_source))

    def select_segment_image_source(self, project_id: int, segment_index: int, selected_image_source: str) -> None:
        self.store.update_segment(project_id, segment_index, selected_image_source=_normalize_image_source(selected_image_source))

    def set_line_video_approved(self, project_id: int, line_index: int, approved: bool) -> None:
        self.store.update_line(project_id, line_index, video_approved=int(bool(approved)))

    def set_segment_video_approved(self, project_id: int, segment_index: int, approved: bool) -> None:
        self.store.update_segment(project_id, segment_index, video_approved=int(bool(approved)))

    def all_videos_approved(self, project_id: int) -> bool:
        rows = self.store.list_segments(project_id) or self.store.list_lines(project_id)
        return bool(rows) and all(bool(_row_value(row, "video_approved", 0)) for row in rows)

    def _project_dir(self, project, project_id: int | None = None) -> Path:
        return self.workspace / self._project_folder_name(project, project_id)

    def _project_input_path(self, value: str | Path) -> Path:
        return resolve_storage_path(self.workspace.parent, value)

    def _project_storage_path(self, value: str | Path) -> str:
        return storage_relative_path(self.workspace.parent, value)

    def _project_folder_name(self, project, project_id: int | None = None) -> str:
        name = _row_value(project, "name", "")
        if name:
            return slug_folder_name(str(name))
        return f"project-{project_id}" if project_id is not None else "project"

    def _success_fields(self, output_field: str, output_path: str) -> dict[str, object]:
        fields: dict[str, object] = {output_field: output_path, "status": "done", "error": ""}
        if output_field == "image_path":
            fields.update({"avatar_image_path": None, "clip_path": None, "video_approved": 0})
        elif output_field == "avatar_image_path":
            fields.update({"clip_path": None, "video_approved": 0})
        elif output_field == "clip_path":
            fields.update({"video_approved": 0})
        return fields

    def clear_project(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        project_dir = self._project_dir(project).resolve()
        workspace = self.workspace.resolve()
        if workspace not in project_dir.parents:
            raise ValueError(f"Refusing to clear path outside workspace: {project_dir}")
        if project_dir.exists():
            shutil.rmtree(project_dir)
        self.store.clear_project_generated_state(project_id)

    def regroup_project(self, project_id: int, force_cpu: bool = False) -> None:
        logger.info("regroup start project_id=%s", project_id)
        project = self.store.get_project(project_id)
        project_dir = self._project_dir(project).resolve()
        workspace = self.workspace.resolve()
        if workspace not in project_dir.parents:
            raise ValueError(f"Refusing to regroup path outside workspace: {project_dir}")
        lyrics_path = self._project_input_path(project["lyrics_path"])
        lines = parse_suno_lyrics(lyrics_path.read_text(encoding="utf-8"))
        audio_path = self._project_input_path(project["audio_path"])
        duration = get_wav_duration_sec(audio_path)
        timings, fallback_error = self._compute_whisper_timings(
            project_id,
            project,
            lines,
            duration,
            infer_language_from_lyrics(lines),
            force_cpu=force_cpu,
        )
        if project_dir.exists():
            shutil.rmtree(project_dir)
        self.store.clear_project_generated_state(project_id)
        self.store.replace_lines(project_id, lines)
        logger.info("clear generated state done project_id=%s output_dir=%s", project_id, project_dir)
        try:
            self._store_alignment_timings(project_id, timings, fallback_error)
            self.build_segments(project_id)
        except Exception:
            logger.exception("regroup failed project_id=%s", project_id)
            raise
        logger.info("regroup done project_id=%s", project_id)

    def _compute_whisper_timings(
        self,
        project_id: int,
        project,
        lines: list[LyricLine],
        duration: float,
        language: str | None,
        force_cpu: bool = False,
    ) -> tuple[list[LineTiming], str]:
        audio_path = self._project_input_path(project["audio_path"])
        whisper_model_size = normalize_whisper_model_size(_row_value(project, "whisper_model_size", "small"))
        started = time.monotonic()
        logger.info("whisper transcribe start project_id=%s audio=%s", project_id, audio_path)
        words = transcribe_words_with_fallback(
            audio_path,
            language=language,
            prefer_device="cpu" if force_cpu else "cuda",
            model_size=whisper_model_size,
        )
        logger.info(
            "whisper transcribe done project_id=%s words=%s elapsed_sec=%.3f",
            project_id,
            len(words),
            time.monotonic() - started,
        )
        started = time.monotonic()
        timings = align_lyrics_to_words(lines, words, duration)
        lyric_line_indices = {line.index for line in lines if not _is_instrumental_line(line)}
        high_confidence = sum(
            1
            for timing in timings
            if timing.line_index in lyric_line_indices and timing.confidence >= 0.45
        )
        fallback_error = ""
        lyric_line_count = len(lyric_line_indices)
        if lyric_line_count and high_confidence / lyric_line_count < MIN_CONFIDENT_ALIGNMENT_RATIO:
            fallback_error = (
                f"Sparse Whisper alignment; transcript-window fallback "
                f"({high_confidence}/{lyric_line_count} confident lyric lines)"
            )
            logger.info(
                "lyrics alignment too sparse; using transcript-window fallback project_id=%s high_confidence=%s lines=%s words=%s min_ratio=%.2f",
                project_id,
                high_confidence,
                lyric_line_count,
                len(words),
                MIN_CONFIDENT_ALIGNMENT_RATIO,
            )
            timings = _distribute_in_transcript_window(lines, duration, words)
            high_confidence = 0
        logger.info(
            "lyrics alignment done project_id=%s timings=%s high_confidence=%s low_confidence=%s elapsed_sec=%.3f",
            project_id,
            len(timings),
            high_confidence,
            len(timings) - high_confidence,
            time.monotonic() - started,
        )
        return timings, fallback_error

    def _store_alignment_timings(self, project_id: int, timings: list[LineTiming], fallback_error: str) -> None:
        self.store.set_timings(project_id, timings)
        logger.info("timings stored project_id=%s count=%s", project_id, len(timings))
        for timing in timings:
            if fallback_error:
                error = fallback_error
            else:
                error = "" if timing.confidence >= 0.45 else "Low confidence alignment; fallback timing"
            self.store.update_line(project_id, timing.line_index, error=error, last_action="align")

    def delete_project(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        self.clear_project(project_id)
        self._delete_project_upload_dir(project)
        self.store.delete_project(project_id)

    def _delete_project_upload_dir(self, project) -> None:
        app_root = self.workspace.resolve().parent
        uploads_root = (app_root / "uploads").resolve()
        candidates = [self._project_input_path(project["audio_path"]), self._project_input_path(project["lyrics_path"])]
        for raw_path in candidates:
            try:
                parent = raw_path.resolve().parent
                parent.relative_to(uploads_root)
            except (OSError, ValueError):
                continue
            if parent.exists():
                shutil.rmtree(parent)
            return

    def _selected_rows(self, project_id: int, selected_line_indices: list[int] | None):
        rows = self.store.list_lines(project_id)
        selected = set(selected_line_indices or [])
        if not selected:
            return rows
        return [row for row in rows if row["line_index"] in selected]

    def _selected_segments(self, project_id: int, selected_segment_indices: list[int] | None):
        rows = self.store.list_segments(project_id)
        selected = set(selected_segment_indices or [])
        if not selected:
            return rows
        return [row for row in rows if row["segment_index"] in selected]

    def _filter_timings(self, timings: list[LineTiming], selected_line_indices: list[int] | None) -> list[LineTiming]:
        selected = set(selected_line_indices or [])
        if not selected:
            return timings
        return [timing for timing in timings if timing.line_index in selected]

    def _line_timings_missing(self, project_id: int) -> bool:
        return any(row["start_sec"] is None or row["end_sec"] is None for row in self.store.list_lines(project_id))

    def _fill_missing_line_timings_evenly(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        rows = self.store.list_lines(project_id)
        lines = [
            LyricLine(
                index=row["line_index"],
                section=row["section"],
                raw_text=row["raw_text"],
                clean_text=row["clean_text"],
                is_chorus=bool(row["is_chorus"]),
                use_reference=bool(row["use_reference"]),
            )
            for row in rows
        ]
        duration = get_wav_duration_sec(self._project_input_path(project["audio_path"]))
        fallback_timings = distribute_evenly(lines, duration)
        missing = {int(row["line_index"]) for row in rows if row["start_sec"] is None or row["end_sec"] is None}
        self.store.set_timings(project_id, [timing for timing in fallback_timings if timing.line_index in missing])

    def _align_line_timings_with_fallback(self, project_id: int) -> None:
        project = self.store.get_project(project_id)
        lines = [
            LyricLine(
                index=row["line_index"],
                section=row["section"],
                raw_text=row["raw_text"],
                clean_text=row["clean_text"],
                is_chorus=bool(row["is_chorus"]),
                use_reference=bool(row["use_reference"]),
            )
            for row in self.store.list_lines(project_id)
        ]
        audio_path = self._project_input_path(project["audio_path"])
        duration = get_wav_duration_sec(audio_path)
        whisper_model_size = normalize_whisper_model_size(_row_value(project, "whisper_model_size", "small"))
        words = transcribe_words_with_fallback(
            audio_path,
            language=infer_language_from_lyrics(lines),
            model_size=whisper_model_size,
        )
        timings = align_lyrics_to_words(lines, words, duration)
        self.store.set_timings(project_id, timings)

    def _run_comfy_for_lines(self, project_id: int, workflow_path: Path, output_field: str) -> None:
        for row in self.store.list_lines(project_id):
            self._run_comfy_for_line(project_id, row, workflow_path, output_field)

    def _run_comfy_for_line(
        self,
        project_id: int,
        row,
        workflow_path: Path,
        output_field: str,
        prefer_avatar: bool = False,
        action: str | None = None,
    ) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row, prefer_avatar=prefer_avatar)
        prefix = f"musicvideogen/{self._project_folder_name(project)}/line-{row['line_index']}-{int(time.time() * 1000)}"
        if output_field == "clip_path":
            variables = _with_transition_handle_duration(project, variables)
            workflow = _inject_image_audio_video_inputs(workflow, variables)
            workflow = _randomize_workflow_seeds(workflow)
        elif output_field == "image_path":
            workflow = _randomize_workflow_seeds(workflow)
        workflow = with_output_prefix(workflow, prefix)
        self.store.update_line(project_id, row["line_index"], status="running", error="", last_action=action or output_field)
        result = client.run_workflow(workflow, variables)
        if result.ok and result.output_files:
            stored_output = self._localize_comfy_output(
                project,
                project_id=project_id,
                item_kind="line",
                item_index=int(row["line_index"]),
                output_field=output_field,
                output_path=result.output_files[0],
            )
            self.store.update_line(
                project_id,
                row["line_index"],
                **self._success_fields(output_field, self._project_storage_path(stored_output)),
            )
        elif result.ok and output_field == "prompt":
            self.store.update_line(project_id, row["line_index"], prompt=json.dumps(result.output_files), status="done", error="")
        else:
            self.store.update_line(project_id, row["line_index"], status="failed", error=result.error or "No output files")

    def _run_comfy_for_segment(
        self,
        project_id: int,
        row,
        workflow_path: Path,
        output_field: str,
        prefer_avatar: bool = False,
        action: str | None = None,
    ) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row, prefer_avatar=prefer_avatar)
        prefix = f"musicvideogen/{self._project_folder_name(project)}/segment-{row['segment_index']}-{int(time.time() * 1000)}"
        if output_field == "clip_path":
            variables = _with_transition_handle_duration(project, variables)
            workflow = _inject_image_audio_video_inputs(workflow, variables)
            workflow = _randomize_workflow_seeds(workflow)
        elif output_field == "image_path":
            workflow = _randomize_workflow_seeds(workflow)
        workflow = with_output_prefix(workflow, prefix)
        self.store.update_segment(project_id, row["segment_index"], status="running", error="", last_action=action or output_field)
        result = client.run_workflow(workflow, variables)
        if result.ok and result.output_files:
            stored_output = self._localize_comfy_output(
                project,
                project_id=project_id,
                item_kind="segment",
                item_index=int(row["segment_index"]),
                output_field=output_field,
                output_path=result.output_files[0],
            )
            self.store.update_segment(
                project_id,
                row["segment_index"],
                **self._success_fields(output_field, self._project_storage_path(stored_output)),
            )
        else:
            self.store.update_segment(project_id, row["segment_index"], status="failed", error=result.error or "No output files")

    def _run_comfy_for_avatar_line(self, project_id: int, row, workflow_path: Path) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row)
        workflow = _inject_avatar_load_images(workflow, variables)
        workflow = _inject_avatar_prompt(workflow, variables)
        workflow = _randomize_workflow_seeds(workflow)
        prefix = f"musicvideogen/{self._project_folder_name(project)}/avatar-line-{row['line_index']}-{int(time.time() * 1000)}"
        workflow = with_output_prefix(workflow, prefix)
        self.store.update_line(project_id, row["line_index"], status="running", error="", last_action="avatar-image")
        result = client.run_workflow(workflow, variables)
        if result.ok and result.output_files:
            stored_output = self._localize_comfy_output(
                project,
                project_id=project_id,
                item_kind="avatar-line",
                item_index=int(row["line_index"]),
                output_field="avatar_image_path",
                output_path=result.output_files[0],
            )
            self.store.update_line(project_id, row["line_index"], **self._success_fields("avatar_image_path", self._project_storage_path(stored_output)))
        else:
            self.store.update_line(project_id, row["line_index"], status="failed", error=result.error or "No output files")

    def _run_comfy_for_avatar_segment(self, project_id: int, row, workflow_path: Path) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row)
        workflow = _inject_avatar_load_images(workflow, variables)
        workflow = _inject_avatar_prompt(workflow, variables)
        workflow = _randomize_workflow_seeds(workflow)
        prefix = f"musicvideogen/{self._project_folder_name(project)}/avatar-segment-{row['segment_index']}-{int(time.time() * 1000)}"
        workflow = with_output_prefix(workflow, prefix)
        self.store.update_segment(project_id, row["segment_index"], status="running", error="", last_action="avatar-image")
        result = client.run_workflow(workflow, variables)
        if result.ok and result.output_files:
            stored_output = self._localize_comfy_output(
                project,
                project_id=project_id,
                item_kind="avatar-segment",
                item_index=int(row["segment_index"]),
                output_field="avatar_image_path",
                output_path=result.output_files[0],
            )
            self.store.update_segment(project_id, row["segment_index"], **self._success_fields("avatar_image_path", self._project_storage_path(stored_output)))
        else:
            self.store.update_segment(project_id, row["segment_index"], status="failed", error=result.error or "No output files")

    def _run_comfy_for_prompt(self, project_id: int, row, workflow_path: Path) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row)
        self.store.update_line(project_id, row["line_index"], status="running", error="", last_action="prompts")
        try:
            prompt_workflow = inject_promptgen_context(workflow, variables)
        except ValueError as exc:
            self.store.update_line(project_id, row["line_index"], status="failed", error=str(exc), last_action="prompts")
            return
        result = client.run_workflow(prompt_workflow, {})
        if result.ok and result.text_outputs:
            self.store.update_line(
                project_id,
                row["line_index"],
                prompt=result.text_outputs[0].strip(),
                status="prompted",
                error="",
            )
        elif result.ok and result.output_files:
            self.store.update_line(
                project_id,
                row["line_index"],
                prompt=json.dumps(result.output_files),
                status="prompted",
                error="",
            )
        else:
            self.store.update_line(project_id, row["line_index"], status="failed", error=result.error or "No text output")

    def _run_comfy_for_segment_prompt(self, project_id: int, row, workflow_path: Path) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row)
        self.store.update_segment(project_id, row["segment_index"], status="running", error="", last_action="prompts")
        try:
            prompt_workflow = inject_promptgen_context(workflow, variables)
        except ValueError as exc:
            self.store.update_segment(project_id, row["segment_index"], status="failed", error=str(exc), last_action="prompts")
            return
        result = client.run_workflow(prompt_workflow, {})
        if result.ok and result.text_outputs:
            self.store.update_segment(
                project_id,
                row["segment_index"],
                prompt=result.text_outputs[0].strip(),
                status="prompted",
                error="",
            )
        elif result.ok and result.output_files:
            self.store.update_segment(
                project_id,
                row["segment_index"],
                prompt=json.dumps(result.output_files),
                status="prompted",
                error="",
            )
        else:
            self.store.update_segment(project_id, row["segment_index"], status="failed", error=result.error or "No text output")

    def _run_comfy_for_line_video_prompt(self, project_id: int, row, workflow_path: Path) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row)
        self.store.update_line(project_id, row["line_index"], status="running", error="", last_action="video-prompts")
        try:
            prompt_workflow = inject_videoprompt_context(workflow, variables)
        except ValueError as exc:
            self.store.update_line(project_id, row["line_index"], status="failed", error=str(exc), last_action="video-prompts")
            return
        result = client.run_workflow(prompt_workflow, {})
        if result.ok and result.text_outputs:
            self.store.update_line(
                project_id,
                row["line_index"],
                video_prompt=result.text_outputs[0].strip(),
                clip_path=None,
                video_approved=0,
                status="video prompted",
                error="",
            )
        elif result.ok and result.output_files:
            self.store.update_line(
                project_id,
                row["line_index"],
                video_prompt=json.dumps(result.output_files),
                clip_path=None,
                video_approved=0,
                status="video prompted",
                error="",
            )
        else:
            self.store.update_line(project_id, row["line_index"], status="failed", error=result.error or "No text output")

    def _run_comfy_for_segment_video_prompt(self, project_id: int, row, workflow_path: Path) -> None:
        project = self.store.get_project(project_id)
        workflow = load_workflow(workflow_path)
        client = ComfyClient(project["comfy_base_url"])
        variables = self._variables(project, row)
        self.store.update_segment(project_id, row["segment_index"], status="running", error="", last_action="video-prompts")
        try:
            prompt_workflow = inject_videoprompt_context(workflow, variables)
        except ValueError as exc:
            self.store.update_segment(project_id, row["segment_index"], status="failed", error=str(exc), last_action="video-prompts")
            return
        result = client.run_workflow(prompt_workflow, {})
        if result.ok and result.text_outputs:
            self.store.update_segment(
                project_id,
                row["segment_index"],
                video_prompt=result.text_outputs[0].strip(),
                clip_path=None,
                video_approved=0,
                status="video prompted",
                error="",
            )
        elif result.ok and result.output_files:
            self.store.update_segment(
                project_id,
                row["segment_index"],
                video_prompt=json.dumps(result.output_files),
                clip_path=None,
                video_approved=0,
                status="video prompted",
                error="",
            )
        else:
            self.store.update_segment(project_id, row["segment_index"], status="failed", error=result.error or "No text output")

    def _localize_comfy_output(
        self,
        project,
        project_id: int,
        item_kind: str,
        item_index: int,
        output_field: str,
        output_path: str,
    ) -> Path:
        target_dir = self._project_dir(project, project_id) / _asset_folder(output_field)
        extension = Path(output_path.replace("\\", "/")).suffix or _default_extension(output_field)
        target = target_dir / f"{item_kind}-{item_index:03d}{extension}"
        target.parent.mkdir(parents=True, exist_ok=True)

        source = Path(output_path)
        if source.exists():
            shutil.copy2(source, target)
            return target

        self._download_file(_comfy_view_url(str(project["comfy_base_url"]), output_path), target)
        return target

    def _download_file(self, url: str, target: Path) -> None:
        urlretrieve(url, target)

    def _variables(self, project, row, prefer_avatar: bool = False) -> dict[str, str]:
        references = json.loads(project["reference_image_paths"] or "[]")
        resolved_references = [str(self._project_input_path(item)) for item in references]
        reference_image_path = resolved_references[0] if resolved_references else str(Path.cwd() / "images" / "avatar.jpeg")
        fullbody_reference_image_path = str(Path.cwd() / "images" / "avatar_fullbody.png")
        base_image_path = self._workflow_path_value(_row_value(row, "image_path", "") or "")
        avatar_image_path = self._workflow_path_value(_row_value(row, "avatar_image_path", "") or "")
        selected_image_source = _normalize_image_source(_row_value(row, "selected_image_source", "avatar"))
        use_avatar = prefer_avatar and avatar_image_path and selected_image_source != "image"
        source_image_path = avatar_image_path if use_avatar else base_image_path
        duration = 0.0
        if row["start_sec"] is not None and row["end_sec"] is not None:
            duration = float(row["end_sec"]) - float(row["start_sec"])
        return {
            "lyric_text": row["clean_text"],
            "section": row["section"],
            "is_chorus": str(bool(row["is_chorus"])).lower(),
            "use_reference_image": str(bool(row["use_reference"])).lower(),
            "global_style": project["global_style_prompt"],
            "duration": f"{duration:.3f}",
            "fps": str(project["fps"]),
            "output_resolution": project["output_resolution"],
            "reference_image_paths": json.dumps(resolved_references),
            "reference_image_path": reference_image_path,
            "reference_image_name": Path(reference_image_path).name if reference_image_path else "",
            "fullbody_reference_image_path": fullbody_reference_image_path,
            "fullbody_reference_image_name": Path(fullbody_reference_image_path).name,
            "base_image_path": base_image_path,
            "avatar_image_path": avatar_image_path,
            "source_image_path": source_image_path,
            "input_image_path": base_image_path,
            "image_path": source_image_path or base_image_path,
            "audio_path": self._workflow_path_value(_row_value(row, "audio_path", "") or ""),
            "prompt": row["prompt"] or "",
            "image_prompt": row["prompt"] or "",
            "video_prompt": _row_value(row, "video_prompt", "") or "",
            "scene_plan": _row_value(row, "scene_plan", "") or "",
            "genre": project["genre"] or "",
        }

    def _workflow_path_value(self, value: str) -> str:
        if not value:
            return ""
        return str(self._project_input_path(value))


def _row_value(row, key: str, default):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _format_scene_plan_text(plans: dict[int, str], fallback_reason: str) -> str:
    lines = [f"Fallback scene plan used: {fallback_reason}."]
    lines.extend(f"{index}: {plan}" for index, plan in plans.items())
    return "\n".join(lines)


def _format_successful_scene_plan_text(segment_plan: str, video_bible: str) -> str:
    if not video_bible.strip():
        return segment_plan
    return f"Video bible:\n{video_bible.strip()}\n\nSegment plan:\n{segment_plan}"


def _normalize_image_source(value: str) -> str:
    return "image" if str(value or "").lower() == "image" else "avatar"


def _distribute_in_transcript_window(lines: list[LyricLine], duration: float, words) -> list[LineTiming]:
    if not words:
        return distribute_evenly(lines, duration)
    first_word_start = max(0.0, min(float(word.start_sec) for word in words))
    last_word_end = min(duration, max(float(word.end_sec) for word in words))
    if last_word_end <= first_word_start:
        return distribute_evenly(lines, duration)

    first_lyric = _first_non_instrumental_index(lines)
    last_lyric = _last_non_instrumental_index(lines)
    if first_lyric is None or last_lyric is None:
        return distribute_evenly(lines, duration)

    timings: list[LineTiming] = []
    if first_lyric > 0:
        timings.extend(_distribute_line_slice(lines[:first_lyric], 0.0, first_word_start))
    timings.extend(_distribute_line_slice(lines[first_lyric : last_lyric + 1], first_word_start, last_word_end))
    if last_lyric + 1 < len(lines):
        timings.extend(_distribute_line_slice(lines[last_lyric + 1 :], last_word_end, duration))
    return sorted(timings, key=lambda timing: timing.line_index)


def _distribute_line_slice(lines: list[LyricLine], start_sec: float, end_sec: float) -> list[LineTiming]:
    if not lines:
        return []
    start_sec = max(0.0, float(start_sec))
    end_sec = max(start_sec, float(end_sec))
    span = end_sec - start_sec
    if span <= 0:
        return [LineTiming(line.index, start_sec, start_sec, 0.0) for line in lines]
    segment = span / len(lines)
    timings: list[LineTiming] = []
    for position, line in enumerate(lines):
        line_start = round(start_sec + position * segment, 6)
        line_end = round(end_sec if position == len(lines) - 1 else start_sec + (position + 1) * segment, 6)
        timings.append(LineTiming(line.index, line_start, line_end, 0.0))
    return timings


def _first_non_instrumental_index(lines: list[LyricLine]) -> int | None:
    for index, line in enumerate(lines):
        if not _is_instrumental_line(line):
            return index
    return None


def _last_non_instrumental_index(lines: list[LyricLine]) -> int | None:
    for index in range(len(lines) - 1, -1, -1):
        if not _is_instrumental_line(lines[index]):
            return index
    return None


def _is_instrumental_line(line: LyricLine) -> bool:
    return is_instrumental_section(line.clean_text) or is_instrumental_section(line.section)


def _with_transition_handle_duration(project, variables: dict[str, str]) -> dict[str, str]:
    updated = dict(variables)
    duration = float(updated.get("duration") or 0)
    handle = max(0.0, float(_row_value(project, "transition_handle_seconds", 0.5)))
    updated["duration"] = f"{duration + handle:.3f}"
    return updated


def _inject_avatar_load_images(workflow: dict, variables: dict[str, str]) -> dict:
    load_image_nodes = [
        node
        for node in workflow.values()
        if isinstance(node, dict)
        and str(node.get("class_type", "")).lower() == "loadimage"
        and isinstance(node.get("inputs"), dict)
        and "image" in node["inputs"]
    ]
    avatar_image = variables.get("reference_image_path", "") or variables.get("fullbody_reference_image_path", "")
    replacements = [
        variables.get("input_image_path", ""),
        avatar_image,
    ]
    for node, replacement in zip(load_image_nodes, replacements):
        if replacement:
            node["inputs"]["image"] = replacement
    return workflow


def _inject_avatar_prompt(workflow: dict, variables: dict[str, str]) -> dict:
    prompt = render_prompt_template(
        load_named_prompt_template("avatar_image.txt", DEFAULT_AVATAR_IMAGE_TEMPLATE),
        {
            "image_prompt": variables.get("image_prompt", ""),
            "IMAGE_PROMPT": variables.get("image_prompt", ""),
            "scene_plan": variables.get("scene_plan", ""),
            "SCENE_PLAN": variables.get("scene_plan", ""),
            "genre": variables.get("genre", ""),
            "GENRE": variables.get("genre", ""),
            "global_style": variables.get("global_style", ""),
            "GLOBAL_STYLE": variables.get("global_style", ""),
        },
    )
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        title = str(node.get("_meta", {}).get("title", "")).lower()
        class_type = str(node.get("class_type", "")).lower()
        if "positive" not in title:
            continue
        if "text" in inputs and "cliptextencode" in class_type:
            inputs["text"] = prompt
            break
        if "prompt" in inputs and ("textencode" in class_type or "qwen" in class_type):
            inputs["prompt"] = prompt
            break
    return workflow


def _inject_image_audio_video_inputs(workflow: dict, variables: dict[str, str]) -> dict:
    image_path = variables.get("image_path", "")
    audio_path = variables.get("audio_path", "")
    duration = variables.get("duration", "")
    video_prompt = variables.get("video_prompt", "")
    if image_path:
        for node in _nodes_by_class(workflow, "LoadImage"):
            inputs = node["inputs"]
            if "image" in inputs:
                inputs["image"] = image_path
                break
    if audio_path:
        for node in _nodes_by_class(workflow, "LoadAudio"):
            inputs = node["inputs"]
            if "audio" in inputs:
                inputs["audio"] = audio_path
                inputs.pop("audioUI", None)
                break
    if duration:
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict) or "value" not in inputs:
                continue
            title = str(node.get("_meta", {}).get("title", "")).lower()
            if node.get("class_type") == "PrimitiveFloat" and "duration" in title:
                inputs["value"] = float(duration)
                break
    if video_prompt:
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict) or "value" not in inputs:
                continue
            title = str(node.get("_meta", {}).get("title", "")).lower()
            if "prompt" in title:
                inputs["value"] = video_prompt
                break
    return workflow


def _randomize_workflow_seeds(workflow: dict) -> dict:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key, value in list(inputs.items()):
            if _is_seed_input(key, value):
                inputs[key] = _new_seed()
    return workflow


def _is_seed_input(key: str, value) -> bool:
    normalized = str(key).lower()
    return isinstance(value, int) and (
        normalized == "seed"
        or normalized.endswith("_seed")
        or normalized.endswith(".seed")
    )


def _new_seed() -> int:
    return secrets.randbelow(2**63 - 1) + 1


def _nodes_by_class(workflow: dict, class_type: str) -> list[dict]:
    return [
        node
        for node in workflow.values()
        if isinstance(node, dict)
        and str(node.get("class_type", "")).lower() == class_type.lower()
        and isinstance(node.get("inputs"), dict)
    ]


def _asset_folder(output_field: str) -> str:
    return "clips" if output_field == "clip_path" else "images"


def _default_extension(output_field: str) -> str:
    return ".mp4" if output_field == "clip_path" else ".png"


def _comfy_view_url(comfy_base_url: str, output_path: str) -> str:
    path = Path(output_path.replace("\\", "/"))
    filename = path.name
    subfolder = path.parent.as_posix()
    url = f"{comfy_base_url.rstrip('/')}/view?filename={quote(filename)}"
    if subfolder and subfolder != ".":
        url += f"&subfolder={quote(subfolder, safe='')}"
    return f"{url}&type=output"

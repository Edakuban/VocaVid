from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Callable
from urllib.parse import quote

try:
    from fastapi import FastAPI, File, Form, UploadFile
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as exc:  # pragma: no cover
    raise SystemExit("FastAPI is required. Install with: pip install -r requirements.txt") from exc

from .lyrics import parse_suno_lyrics
from .alignment import WHISPER_MODEL_SIZES, normalize_whisper_model_size
from .paths import is_internal_storage_path, resolve_storage_path, slug_folder_name, storage_relative_path
from .pipeline import Pipeline
from .store import Store
from .worker import JobQueue

APP_ROOT = Path.cwd() / ".musicvideogen"
UPLOADS = APP_ROOT / "uploads"
DB_PATH = APP_ROOT / "musicvideogen.sqlite3"
logger = logging.getLogger(__name__)
_SPLIT_ACTIONS = {"prompts", "video-prompts", "images", "avatar-image", "clips"}


@dataclass
class JobOptions:
    autodelete_finished: bool = False
    shutdown_after_queue: bool = False


class ShutdownController:
    def __init__(self, runner: Callable[[list[str]], object] | None = None):
        self._runner = runner or (lambda command: subprocess.run(command, check=False))
        self.enabled = False
        self.scheduled = False

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False
        self.cancel_pending()

    def schedule_after_queue_empty(self) -> None:
        if not self.enabled or self.scheduled:
            return
        self._runner(["shutdown", "/s", "/t", "900"])
        self.scheduled = True

    def cancel_pending(self) -> None:
        if not self.scheduled:
            return
        self._runner(["shutdown", "/a"])
        self.scheduled = False


def create_app() -> FastAPI:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    store = Store(DB_PATH)
    pipeline = Pipeline(store, APP_ROOT / "outputs")
    job_options = JobOptions()
    shutdown_controller = ShutdownController()

    def record_finished_job(job) -> None:
        if job.action and job.duration_seconds is not None:
            store.record_job_run(
                job.action,
                job.item_kind,
                max(1, len(job.selected_indices or [])),
                job.duration_seconds,
                job.status,
            )
        if job_options.autodelete_finished:
            jobs.delete_finished_jobs()
        if job_options.shutdown_after_queue and not jobs.active_jobs():
            shutdown_controller.schedule_after_queue_empty()

    jobs = JobQueue(max_workers=1, on_finish=record_finished_job)
    app = FastAPI(title="VocaVid")
    app.state.jobs = jobs
    app.state.job_options = job_options
    app.state.shutdown_controller = shutdown_controller
    app.mount("/assets", StaticFiles(directory=str(APP_ROOT)), name="assets")

    def mark_used(project_id: int, action: str) -> None:
        store.mark_project_action_used(project_id, action)

    def regroup_now(project_id: int, log_label: str, force_cpu: bool = False) -> None:
        try:
            if force_cpu:
                pipeline.regroup_project(project_id, force_cpu=True)
            else:
                pipeline.regroup_project(project_id)
        except Exception:
            logger.exception("%s failed project_id=%s", log_label, project_id)
            raise
        mark_used(project_id, "align")
        mark_used(project_id, "segments")
        logger.info("%s done project_id=%s", log_label, project_id)

    def submit_project_action(project_id: int, action: str, selected_indices: list[int] | None = None) -> bool:
        project = store.get_project(project_id)
        selected = list(selected_indices or [])
        actions = {
            "align": ("align", lambda: pipeline.align_with_whisper(project_id, selected)),
            "segments": ("build segments", lambda: pipeline.build_segments(project_id)),
            "scene-plan": ("generate scene plan", lambda: pipeline.generate_scene_plan(project_id, selected)),
            "prompts": ("generate prompts", lambda: pipeline.generate_prompts(project_id, selected)),
            "images": ("generate images", lambda: pipeline.generate_images(project_id, selected)),
            "avatar-image": ("generate avatar image", lambda: pipeline.generate_avatar_images(project_id, selected)),
            "video-prompts": ("generate video prompts", lambda: pipeline.generate_video_prompts(project_id, selected)),
            "clips": ("generate clips", lambda: pipeline.generate_clips(project_id, selected)),
            "assemble": ("assemble", lambda: pipeline.assemble(project_id, selected)),
        }
        if action not in actions:
            return False
        label, callback = actions[action]
        item_kind = _action_item_kind(action, bool(store.list_segments(project_id)))
        if action in _SPLIT_ACTIONS:
            indices = _selected_action_indices(project_id, item_kind, selected, store)
            if not indices:
                return False
            for index in indices:
                shutdown_controller.cancel_pending()
                jobs.submit(
                    _job_name(label, project["name"], [index], item_kind=item_kind),
                    lambda selected_index=index: _run_project_action(pipeline, project_id, action, [selected_index]),
                    project_id=project_id,
                    action=action,
                    item_kind=item_kind,
                    selected_indices=[index],
                )
            return True
        shutdown_controller.cancel_pending()
        jobs.submit(
            _job_name(label, project["name"], selected, item_kind=item_kind if selected else None),
            callback,
            project_id=project_id,
            action=action,
            item_kind=item_kind,
            selected_indices=selected,
        )
        return True

    @app.get("/", response_class=HTMLResponse)
    def index():
        active_jobs = jobs.active_jobs()
        average_durations = store.average_job_durations()
        return _page(
            "Projects",
            _projects_html(
                store.list_projects(),
                jobs.list_jobs(),
                average_durations,
                queue_estimate_seconds=_queue_estimate_seconds(active_jobs, average_durations),
                job_options=job_options,
            ),
            queue_count=len(active_jobs),
        )

    @app.get("/jobs/status")
    def jobs_status():
        active_jobs = jobs.active_jobs()
        average_durations = store.average_job_durations()
        queue_estimate_seconds = _queue_estimate_seconds(active_jobs, average_durations)
        listed_jobs = jobs.list_jobs()
        return {
            "jobs_html": _jobs_table_body_html(listed_jobs, average_durations),
            "queue_summary_html": _queue_summary_cards_html(listed_jobs, queue_estimate_seconds),
            "queue_estimate_seconds": queue_estimate_seconds,
            "queue_count": len(active_jobs),
            "autodelete_finished": job_options.autodelete_finished,
            "shutdown_after_queue": job_options.shutdown_after_queue,
        }

    @app.post("/jobs/options")
    def update_job_options(
        autodelete_finished: str | None = Form(None),
        shutdown_after_queue: str | None = Form(None),
    ):
        job_options.autodelete_finished = autodelete_finished == "on"
        job_options.shutdown_after_queue = shutdown_after_queue == "on"
        if job_options.autodelete_finished:
            jobs.delete_finished_jobs()
        if job_options.shutdown_after_queue:
            shutdown_controller.enable()
        else:
            shutdown_controller.disable()
        return RedirectResponse("/", status_code=303)

    @app.post("/jobs/{job_id}/delete")
    def delete_job(job_id: int):
        jobs.delete_job(job_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/jobs/delete-queued")
    def delete_queued_jobs():
        jobs.delete_queued_jobs()
        return RedirectResponse("/", status_code=303)

    @app.post("/jobs/delete-finished")
    def delete_finished_jobs():
        jobs.delete_finished_jobs()
        return RedirectResponse("/", status_code=303)

    @app.post("/projects")
    async def create_project(
        name: str = Form(...),
        global_style_prompt: str = Form(""),
        comfy_base_url: str = Form("http://127.0.0.1:8188"),
        output_resolution: str = Form("1280x720"),
        fps: int = Form(24),
        lyric_group_size: int = Form(2),
        chorus_group_size: int = Form(1),
        transition_handle_seconds: float = Form(0.5),
        whisper_model_size: str = Form("small"),
        audio: UploadFile = File(...),
        lyrics: UploadFile = File(...),
        references: list[UploadFile] = File(default=[]),
    ):
        project_dir = UPLOADS / _slug(name)
        project_dir.mkdir(parents=True, exist_ok=True)
        audio_path = await _save_upload(audio, project_dir)
        lyrics_path = await _save_upload(lyrics, project_dir)
        reference_paths = [
            _storage_path(await _save_upload(item, project_dir / "references"))
            for item in references
            if item.filename
        ]
        lines = parse_suno_lyrics(lyrics_path.read_text(encoding="utf-8"))
        project_id = store.create_project(
            {
                "name": name,
                "audio_path": _storage_path(audio_path),
                "lyrics_path": _storage_path(lyrics_path),
                "global_style_prompt": global_style_prompt,
                "genre": "",
                "reference_image_paths": reference_paths,
                "comfy_base_url": comfy_base_url,
                "output_resolution": output_resolution,
                "fps": fps,
                "lyric_group_size": max(1, int(lyric_group_size)),
                "chorus_group_size": max(1, int(chorus_group_size)),
                "transition_handle_seconds": max(0.0, float(transition_handle_seconds)),
                "whisper_model_size": normalize_whisper_model_size(whisper_model_size),
            },
            lines,
        )
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.get("/projects/{project_id}", response_class=HTMLResponse)
    def project_detail(project_id: int):
        project = store.get_project(project_id)
        projects = store.list_projects()
        previous_project_id, next_project_id = _project_navigation_ids(projects, project_id)
        lines = store.list_lines(project_id)
        segments = store.list_segments(project_id)
        used_actions = store.list_used_project_actions(project_id)
        active_jobs = jobs.active_project_jobs(project_id)
        queue_jobs = jobs.active_jobs()
        averages = store.average_job_durations()
        return _page(
            project["name"],
            _project_html(
                project,
                lines,
                segments,
                used_actions=used_actions,
                active_jobs=active_jobs,
                queue_estimate_seconds=_queue_estimate_seconds(queue_jobs, averages),
                previous_project_id=previous_project_id,
                next_project_id=next_project_id,
            ),
            queue_count=len(queue_jobs),
        )

    @app.get("/projects/{project_id}/status")
    def project_status(project_id: int):
        project = store.get_project(project_id)
        lines = store.list_lines(project_id)
        segments = store.list_segments(project_id)
        used_actions = store.list_used_project_actions(project_id)
        active = jobs.active_project_jobs(project_id)
        queue_jobs = jobs.active_jobs()
        return _project_status_payload(project, lines, segments, active, store.average_job_durations(), used_actions=used_actions, queue_jobs=queue_jobs)

    @app.post("/projects/{project_id}/align")
    def align(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "align", selected_lines):
            mark_used(project_id, "align")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/global-style-prompt")
    def generate_global_style_prompt(project_id: int):
        project = store.get_project(project_id)
        jobs.submit(
            f"generate global style prompt: {project['name']}",
            lambda: pipeline.generate_global_style_prompt(project_id),
            project_id=project_id,
            action="global-style-prompt",
        )
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/timing")
    def update_timing(project_id: int, line_index: int, start_sec: float = Form(...), end_sec: float = Form(...)):
        pipeline.update_timing(project_id, line_index, start_sec, end_sec)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/insert-after")
    def insert_line_after(project_id: int, line_index: int, text: str = Form(...), section: str = Form("")):
        pipeline.insert_line_after(project_id, line_index, text, section)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/delete")
    def delete_line(project_id: int, line_index: int):
        pipeline.delete_line(project_id, line_index)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/timing")
    def update_segment_timing(project_id: int, segment_index: int, start_sec: float = Form(...), end_sec: float = Form(...)):
        pipeline.update_segment_timing(project_id, segment_index, start_sec, end_sec)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/section")
    def update_segment_section(project_id: int, segment_index: int, section_type: str = Form("verse")):
        pipeline.update_segment_section(project_id, segment_index, section_type)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/settings")
    def update_settings(
        project_id: int,
        name: str = Form(...),
        audio_path: str = Form(...),
        lyrics_path: str = Form(...),
        global_style_prompt: str = Form(...),
        genre: str = Form(""),
        reference_image_paths: str = Form(""),
        comfy_base_url: str = Form("http://127.0.0.1:8188"),
        output_resolution: str = Form("1280x720"),
        fps: int = Form(24),
        lyric_group_size: int = Form(2),
        chorus_group_size: int = Form(1),
        transition_handle_seconds: float = Form(0.5),
        whisper_model_size: str = Form("small"),
    ):
        new_lyric_group_size = max(1, int(lyric_group_size))
        new_chorus_group_size = max(1, int(chorus_group_size))
        project_name = name.strip() or f"Project {project_id}"
        store.update_project(
            project_id,
            name=project_name,
            audio_path=_storage_path(audio_path.strip()),
            lyrics_path=_storage_path(lyrics_path.strip()),
            global_style_prompt=global_style_prompt,
            genre=genre.strip(),
            reference_image_paths=json.dumps([_storage_path(item) for item in _reference_paths_from_text(reference_image_paths)]),
            comfy_base_url=comfy_base_url.strip() or "http://127.0.0.1:8188",
            output_resolution=output_resolution.strip() or "1280x720",
            fps=max(1, int(fps)),
            lyric_group_size=new_lyric_group_size,
            chorus_group_size=new_chorus_group_size,
            transition_handle_seconds=max(0.0, float(transition_handle_seconds)),
            whisper_model_size=normalize_whisper_model_size(whisper_model_size),
        )
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/realign-lyrics")
    def realign_lyrics(project_id: int):
        logger.info("manual realign start project_id=%s", project_id)
        regroup_now(project_id, "manual realign")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/realign-lyrics-cpu")
    def realign_lyrics_cpu(project_id: int):
        logger.info("manual realign cpu start project_id=%s", project_id)
        regroup_now(project_id, "manual realign cpu", force_cpu=True)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments")
    def segments(project_id: int):
        if submit_project_action(project_id, "segments"):
            mark_used(project_id, "segments")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/scene-plan")
    def scene_plan(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "scene-plan", selected_lines):
            mark_used(project_id, "scene-plan")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/scene-plan/save")
    def save_scene_plan(project_id: int, scene_plan: str = Form("")):
        pipeline.save_scene_plan(project_id, scene_plan)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/prompts")
    def prompts(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "prompts", selected_lines):
            mark_used(project_id, "prompts")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/images")
    def images(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "images", selected_lines):
            mark_used(project_id, "images")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/avatar-image")
    def avatar_image(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "avatar-image", selected_lines):
            mark_used(project_id, "avatar-image")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/video-prompts")
    def video_prompts(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "video-prompts", selected_lines):
            mark_used(project_id, "video-prompts")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/clips")
    def clips(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "clips", selected_lines):
            mark_used(project_id, "clips")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/assemble")
    def assemble(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "assemble", selected_lines):
            mark_used(project_id, "assemble")
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/clear")
    def clear_project(project_id: int):
        pipeline.clear_project(project_id)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/delete")
    def delete_project(project_id: int):
        pipeline.delete_project(project_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/retry")
    def retry(project_id: int, line_index: int):
        pipeline.retry_line(project_id, line_index)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/redo")
    def redo_line(project_id: int, line_index: int):
        row = next(item for item in store.list_lines(project_id) if item["line_index"] == line_index)
        action = row["last_action"]
        if action and submit_project_action(project_id, action, [line_index]):
            mark_used(project_id, action)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/redo")
    def redo_segment(project_id: int, segment_index: int):
        row = next(item for item in store.list_segments(project_id) if item["segment_index"] == segment_index)
        action = row["last_action"]
        if action and submit_project_action(project_id, action, [segment_index]):
            mark_used(project_id, action)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/save")
    def save_line_prompts(project_id: int, line_index: int, prompt: str = Form(""), video_prompt: str = Form("")):
        pipeline.save_line_prompts(project_id, line_index, prompt, video_prompt)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/image/save")
    def save_line_image_prompt(project_id: int, line_index: int, prompt: str = Form("")):
        pipeline.save_line_prompt(project_id, line_index, prompt)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/video/save")
    def save_line_video_prompt(project_id: int, line_index: int, video_prompt: str = Form("")):
        pipeline.save_line_video_prompt(project_id, line_index, video_prompt)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/image/ai-fill")
    def ai_fill_line_image_prompt(project_id: int, line_index: int, prompt: str = Form("")):
        pipeline.save_line_prompt(project_id, line_index, prompt)
        project = store.get_project(project_id)
        jobs.submit(
            _job_name("ai fill image prompt", project["name"], [line_index], item_kind="lines"),
            lambda: pipeline.ai_fill_line_prompt(project_id, line_index, "image", prompt),
            project_id=project_id,
            action="ai-fill-image",
            item_kind="lines",
            selected_indices=[line_index],
        )
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/video/ai-fill")
    def ai_fill_line_video_prompt(project_id: int, line_index: int, video_prompt: str = Form("")):
        pipeline.save_line_video_prompt(project_id, line_index, video_prompt)
        project = store.get_project(project_id)
        jobs.submit(
            _job_name("ai fill video prompt", project["name"], [line_index], item_kind="lines"),
            lambda: pipeline.ai_fill_line_prompt(project_id, line_index, "video", video_prompt),
            project_id=project_id,
            action="ai-fill-video",
            item_kind="lines",
            selected_indices=[line_index],
        )
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/save")
    def save_segment_prompts(project_id: int, segment_index: int, prompt: str = Form(""), video_prompt: str = Form("")):
        pipeline.save_segment_prompts(project_id, segment_index, prompt, video_prompt)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/image/save")
    def save_segment_image_prompt(project_id: int, segment_index: int, prompt: str = Form("")):
        pipeline.save_segment_prompt(project_id, segment_index, prompt)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/video/save")
    def save_segment_video_prompt(project_id: int, segment_index: int, video_prompt: str = Form("")):
        pipeline.save_segment_video_prompt(project_id, segment_index, video_prompt)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/image/ai-fill")
    def ai_fill_segment_image_prompt(project_id: int, segment_index: int, prompt: str = Form("")):
        pipeline.save_segment_prompt(project_id, segment_index, prompt)
        project = store.get_project(project_id)
        jobs.submit(
            _job_name("ai fill image prompt", project["name"], [segment_index], item_kind="segments"),
            lambda: pipeline.ai_fill_segment_prompt(project_id, segment_index, "image", prompt),
            project_id=project_id,
            action="ai-fill-image",
            item_kind="segments",
            selected_indices=[segment_index],
        )
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/video/ai-fill")
    def ai_fill_segment_video_prompt(project_id: int, segment_index: int, video_prompt: str = Form("")):
        pipeline.save_segment_video_prompt(project_id, segment_index, video_prompt)
        project = store.get_project(project_id)
        jobs.submit(
            _job_name("ai fill video prompt", project["name"], [segment_index], item_kind="segments"),
            lambda: pipeline.ai_fill_segment_prompt(project_id, segment_index, "video", video_prompt),
            project_id=project_id,
            action="ai-fill-video",
            item_kind="segments",
            selected_indices=[segment_index],
        )
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/image-source")
    def select_line_image_source(project_id: int, line_index: int, selected_image_source: str = Form("avatar")):
        pipeline.select_line_image_source(project_id, line_index, selected_image_source)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/image-source")
    def select_segment_image_source(project_id: int, segment_index: int, selected_image_source: str = Form("avatar")):
        pipeline.select_segment_image_source(project_id, segment_index, selected_image_source)
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/approval")
    def approve_line_video(project_id: int, line_index: int, video_approved: int = Form(0)):
        pipeline.set_line_video_approved(project_id, line_index, bool(video_approved))
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    @app.post("/projects/{project_id}/segments/{segment_index}/approval")
    def approve_segment_video(project_id: int, segment_index: int, video_approved: int = Form(0)):
        pipeline.set_segment_video_approved(project_id, segment_index, bool(video_approved))
        return RedirectResponse(f"/projects/{project_id}", status_code=303)

    return app


async def _save_upload(upload: UploadFile, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / Path(upload.filename or "upload.bin").name
    with path.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return path


def _slug(value: str) -> str:
    return slug_folder_name(value)


def _storage_path(value: str | Path) -> str:
    return storage_relative_path(APP_ROOT, value)


def _page(title: str, body: str, queue_count: int = 0) -> str:
    browser_title = _browser_title(title, queue_count)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(browser_title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --studio-bg: #08090d;
      --studio-surface: #11151d;
      --studio-surface-2: #171d28;
      --studio-line: rgba(255,255,255,.12);
      --studio-text: #f6f7fb;
      --studio-muted: #9aa6b8;
      --studio-accent: #35e0b3;
      --studio-pink: #ff4f8b;
      --studio-amber: #f5b84b;
    }}
    body {{
      margin: 0;
      font-family: Inter, Segoe UI, Arial, sans-serif;
      background:
        radial-gradient(circle at 18% 0%, rgba(53,224,179,.14), transparent 26%),
        radial-gradient(circle at 78% 0%, rgba(255,79,139,.12), transparent 28%),
        linear-gradient(180deg, #0b0d12, #07080b);
      color: var(--studio-text);
    }}
    main {{ max-width: none; margin: 0; padding: 24px; }}
    .studio-topbar {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 18px;
      padding: 14px 16px;
      border: 1px solid var(--studio-line);
      border-radius: 20px;
      background: rgba(8,9,13,.74);
      backdrop-filter: blur(18px);
    }}
    .studio-brand {{ font-size: 23px; font-weight: 950; letter-spacing: 0; }}
    .studio-tagline {{ color: var(--studio-muted); font-weight: 750; }}
    .studio-spacer {{ flex: 1; }}
    .studio-panel {{
      border: 1px solid var(--studio-line);
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(255,255,255,.065), rgba(255,255,255,.026));
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(0,0,0,.24);
    }}
    .studio-panel-head {{
      padding: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--studio-line);
    }}
    .studio-chip {{
      border: 1px solid var(--studio-line);
      border-radius: 999px;
      padding: 8px 11px;
      background: rgba(255,255,255,.05);
      color: #cbd5e1;
      font-size: 12px;
      font-weight: 850;
      white-space: nowrap;
    }}
    .studio-chip-green {{
      border-color: rgba(53,224,179,.42);
      background: rgba(53,224,179,.1);
      color: #dcfff6;
    }}
    .studio-chip-pink {{
      border-color: rgba(255,79,139,.4);
      background: rgba(255,79,139,.1);
      color: #ffd7e5;
    }}
    .studio-button {{
      border: 0;
      border-radius: 12px;
      background: var(--studio-accent);
      color: #06100d;
      padding: 10px 13px;
      font-weight: 950;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
    }}
    .studio-button-secondary {{
      border: 1px solid var(--studio-line);
      background: rgba(255,255,255,.055);
      color: #e7edf7;
    }}
    .studio-button-danger, .danger-button {{
      border: 1px solid rgba(255,79,139,.42);
      background: rgba(255,79,139,.12);
      color: #ffd7e5;
    }}
    h1 {{ font-size: 28px; margin: 0; }}
    form, .panel {{ background: #fff; border: 1px solid #d8d3c8; color: #1c2526; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
    label {{ display: block; font-size: 13px; font-weight: 650; margin-top: 10px; }}
    input, textarea, select {{ box-sizing: border-box; width: 100%; border: 1px solid #b9c0bd; border-radius: 6px; padding: 8px; font: inherit; }}
    textarea {{ min-height: 80px; }}
    .prompt-textarea {{ min-width: 260px; min-height: 72px; resize: vertical; }}
    .prompt-actions {{ display: flex; gap: 8px; margin: 6px 0 10px; }}
    .hidden-action-form {{ display: none; }}
    .compact-form {{ padding: 0; margin: 0; border: 0; background: transparent; }}
    .jobs-heading {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .job-options {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 10px; align-items: center; }}
    .job-options label {{ display: inline-flex; gap: 6px; align-items: center; margin: 0; }}
    .job-options input {{ width: auto; }}
    .timing-column {{ width: 11rem; min-width: 11rem; }}
    .timing-form {{ display: grid; grid-template-columns: max-content max-content auto; gap: 4px; align-items: center; }}
    .timing-form input {{ width: 7ch; padding-left: 6px; padding-right: 6px; }}
    .section-form select {{ min-width: 104px; }}
    .approval-label {{ display: inline-flex; align-items: center; gap: 6px; margin: 0; font-weight: 650; }}
    .approval-label input {{ width: auto; }}
    button, .button {{ border: 0; border-radius: 12px; background: var(--studio-accent); color: #06100d; padding: 10px 13px; font-weight: 950; cursor: pointer; text-decoration: none; display: inline-block; }}
    .icon-button {{ width: 34px; height: 34px; padding: 0; border-radius: 50%; line-height: 34px; text-align: center; }}
    .wip-button {{ background: #e53d91; box-shadow: inset 0 -2px 0 rgba(0,0,0,.16); }}
    .wip-button:hover, .wip-button:focus {{ background: #c92878; }}
    .used-button {{ background: #555; box-shadow: inset 0 -2px 0 rgba(0,0,0,.18); }}
    .used-button:hover, .used-button:focus {{ background: #444; }}
    .danger-panel {{ border-color: #e2b1b1; background: #fff8f8; color: #1c2526; }}
    .danger-button {{ border: 1px solid rgba(255,79,139,.42); background: rgba(255,79,139,.12); color: #ffd7e5; }}
    .danger-button:hover, .danger-button:focus {{ background: rgba(255,79,139,.18); }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
    .actions form {{ padding: 0; margin: 0; border: 0; background: transparent; }}
    .start-dashboard {{ display: grid; gap: 18px; }}
    .start-hero {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); gap: 18px; align-items: stretch; }}
    .start-hero > div, .production-status {{
      border: 1px solid var(--studio-line);
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(255,255,255,.07), rgba(255,255,255,.028));
      padding: 22px;
      box-shadow: 0 24px 80px rgba(0,0,0,.22);
    }}
    .start-hero h1 {{ font-size: 42px; line-height: 1.02; margin: 0 0 12px; }}
    .start-hero p {{ max-width: 720px; margin: 0; color: var(--studio-muted); font-size: 17px; line-height: 1.5; }}
    .production-status h2 {{ margin: 0 0 14px; }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .stat {{ border: 1px solid var(--studio-line); border-radius: 12px; background: rgba(255,255,255,.055); padding: 12px; }}
    .stat strong {{ display: block; font-size: 24px; line-height: 1.1; }}
    .stat span {{ display: block; margin-top: 4px; color: var(--studio-muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    .start-layout {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }}
    .project-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; padding: 16px; }}
    .project-card {{ min-width: 0; border: 1px solid var(--studio-line); border-radius: 8px; background: rgba(255,255,255,.045); overflow: hidden; }}
    .project-card-link {{ display: grid; grid-template-columns: 86px minmax(0, 1fr); min-height: 112px; color: var(--studio-text); text-decoration: none; }}
    .project-card-art {{ background: linear-gradient(135deg, rgba(53,224,179,.42), rgba(255,79,139,.28)); }}
    .project-card-body {{ padding: 14px; min-width: 0; }}
    .project-card-body h3 {{ margin: 0 0 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .project-card-body p {{ margin: 0; color: var(--studio-muted); }}
    .project-card-done {{ border-color: rgba(53,224,179,.45); }}
    .project-card-done .project-card-art {{ background: linear-gradient(135deg, rgba(53,224,179,.72), rgba(53,224,179,.18)); }}
    .project-done-label {{ display: inline-flex; margin-top: 12px; padding: 4px 8px; border-radius: 999px; background: rgba(53,224,179,.12); color: #dcfff6; font-size: 12px; font-weight: 900; text-transform: uppercase; }}
    .queue-panel {{ display: grid; gap: 14px; }}
    .queue-panel-head {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: end; justify-content: space-between; padding: 16px 16px 0; }}
    .queue-panel-head h2 {{ margin: 0; }}
    .queue-panel-head p {{ margin: 4px 0 0; color: var(--studio-muted); }}
    .queue-summary-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; padding: 0 16px; }}
    .queue-summary-card {{ border: 1px solid var(--studio-line); border-radius: 8px; background: rgba(255,255,255,.045); padding: 12px; min-width: 0; }}
    .queue-summary-card-active {{ border-color: rgba(53,224,179,.42); background: rgba(53,224,179,.08); }}
    .queue-summary-card strong {{ display: block; color: var(--studio-text); font-size: 22px; line-height: 1.1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .queue-summary-card span {{ display: block; margin-top: 5px; color: var(--studio-muted); font-size: 11px; font-weight: 900; text-transform: uppercase; }}
    .jobs-table-wrap {{ overflow-x: auto; padding: 0 16px; }}
    .queue-admin-controls {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; padding: 0 16px 16px; }}
    .queue-admin-controls .compact-form {{ margin: 0; }}
    .queue-admin-controls .job-options {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }}
    .queue-admin-controls .job-options label {{ margin: 0; }}
    .modal-content {{ width: min(560px, 94vw); max-height: 88vh; overflow: auto; border-radius: 8px; background: #fff; color: #1c2526; box-shadow: 0 28px 90px rgba(0,0,0,.45); }}
    .modal-content .studio-panel-head {{ color: #1c2526; border-bottom: 1px solid #d8d3c8; }}
    .modal-content h2 {{ margin: 0; }}
    .new-project-form {{ margin: 0; border: 0; border-radius: 0; }}
    .project-list {{ display: grid; grid-template-columns: 1fr; gap: 6px 18px; padding: 8px 10px 4px 26px; }}
    .project-list-item {{ min-width: 0; padding: 4px 8px 4px 0; }}
    .project-list-item a {{ display: inline-block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: calc(100% - 44px); vertical-align: bottom; }}
    .project-list-item.project-done a {{ text-decoration: line-through; color: #66706d; }}
    @media (min-width: 820px) {{ .project-list {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
    @media (min-width: 1240px) {{ .project-list {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
    @media (max-width: 980px) {{
      .start-hero {{ grid-template-columns: 1fr; }}
      .project-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 680px) {{
      main {{ padding: 14px; }}
      .studio-topbar {{ align-items: stretch; flex-direction: column; }}
      .studio-spacer {{ display: none; }}
      .start-hero h1 {{ font-size: 32px; }}
      .stat-grid, .project-grid, .queue-summary-grid {{ grid-template-columns: 1fr; }}
      .project-card-link {{ grid-template-columns: 72px minmax(0, 1fr); }}
    }}
    .open-count-label {{ margin-left: auto; align-self: center; font-weight: 750; color: var(--studio-text); white-space: nowrap; }}
    .project-topbar {{ position: sticky; top: 0; z-index: 20; margin: -24px -24px 16px; padding: 14px 24px 0; background: rgba(12,18,20,.94); border-bottom: 1px solid var(--studio-line); color: var(--studio-text); backdrop-filter: blur(12px); box-shadow: 0 18px 50px rgba(0,0,0,.18); }}
    .project-title-row h1 {{ color: var(--studio-text); text-shadow: 0 1px 18px rgba(0,0,0,.35); }}
    .project-title-row {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 12px; }}
    .project-title-row .button {{ margin-left: 0; }}
    .project-icon-button {{ width: 42px; height: 42px; display: inline-flex; align-items: center; justify-content: center; padding: 0; border-radius: 12px; border: 1px solid var(--studio-line); background: rgba(255,255,255,.075); color: var(--studio-text); font-size: 18px; }}
    .project-icon-button:hover, .project-icon-button:focus {{ background: rgba(53,224,179,.16); border-color: rgba(53,224,179,.42); }}
    .project-nav-button {{ display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 6px; background: #555; color: white; font-size: 18px; font-weight: 900; line-height: 1; text-decoration: none; }}
    .project-nav-button:hover, .project-nav-button:focus {{ background: #444; }}
    .project-nav-disabled {{ opacity: .32; cursor: default; }}
    .project-nav-disabled:hover, .project-nav-disabled:focus {{ background: #555; }}
    .project-studio {{ display: grid; gap: 18px; }}
    .view-switch {{ display: inline-flex; gap: 4px; width: fit-content; padding: 4px; border: 1px solid #c7cdc9; border-radius: 8px; background: #eef1ed; }}
    .view-switch button {{ margin: 0; border-radius: 6px; background: transparent; color: #20302d; }}
    .view-switch button.active {{ background: #20302d; color: #fff; }}
    .project-storyboard {{ display: grid; gap: 12px; }}
    .storyboard-workspace {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 420px); gap: 14px; align-items: start; }}
    .storyboard-rail {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .storyboard-card {{ min-width: 0; border: 1px solid #d8d3c8; border-radius: 8px; background: #fff; color: #1c2526; overflow: hidden; cursor: pointer; transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease; }}
    .storyboard-card:hover, .storyboard-card:focus {{ border-color: rgba(53,224,179,.58); box-shadow: 0 0 0 3px rgba(53,224,179,.14); outline: none; }}
    .storyboard-card-active {{ border-color: var(--studio-accent); box-shadow: 0 0 0 3px rgba(53,224,179,.22), 0 18px 48px rgba(53,224,179,.16); transform: translateY(-1px); }}
    .storyboard-card-media {{ position: relative; display: flex; align-items: center; justify-content: center; min-height: 132px; aspect-ratio: 16 / 9; background: linear-gradient(135deg, #e9efe9, #f7f2e8); color: #5b6462; font-weight: 800; overflow: hidden; }}
    .storyboard-card-media button {{ width: 100%; height: 100%; margin: 0; padding: 0; border: 0; border-radius: 0; background: transparent; cursor: pointer; }}
    .storyboard-card-image {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
    .storyboard-card-media-clip {{ background: linear-gradient(135deg, #23312f, #53605b); color: #fff; }}
    .storyboard-card-video {{ display: block; width: 100%; height: 100%; object-fit: cover; background: #111; }}
    .storyboard-video-toggle {{ position: absolute; left: 8px; bottom: 8px; z-index: 2; display: inline-flex; align-items: center; justify-content: center; width: 30px !important; height: 30px !important; border-radius: 999px !important; background: rgba(11,18,20,.78) !important; color: #fff; box-shadow: 0 8px 18px rgba(0,0,0,.24); }}
    .storyboard-video-toggle:hover, .storyboard-video-toggle:focus {{ background: rgba(53,224,179,.88) !important; color: #10201c; outline: none; }}
    .storyboard-play-icon {{ font-size: 0; line-height: 1; }}
    .storyboard-video-toggle[aria-label="Play clip"] .storyboard-play-icon::before {{ content: "\\25b6"; font-size: 13px; }}
    .storyboard-video-toggle[aria-label="Pause clip"] .storyboard-play-icon::before {{ content: "II"; font-size: 12px; letter-spacing: -1px; }}
    .storyboard-card-media-empty {{ padding: 14px; text-align: center; }}
    .storyboard-empty-mark {{ display: grid; gap: 4px; }}
    .storyboard-empty-mark strong {{ color: #20302d; }}
    .storyboard-empty-mark span {{ color: #69736f; font-size: 12px; font-weight: 650; }}
    .storyboard-card-body {{ display: grid; gap: 8px; padding: 12px; }}
    .storyboard-card-title {{ display: flex; justify-content: space-between; gap: 8px; color: #44504d; font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    .storyboard-card-text {{ margin: 0; overflow-wrap: anywhere; }}
    .storyboard-card-status {{ color: #5b6462; font-size: 12px; }}
    .storyboard-progress-strip {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    .progress-step {{ border-radius: 999px; border: 1px solid #d8d3c8; padding: 3px 7px; color: #6a7470; background: #f2f4ef; font-size: 10px; font-weight: 850; text-transform: uppercase; }}
    .progress-step-done {{ border-color: rgba(53,224,179,.45); background: rgba(53,224,179,.14); color: #0c5d4a; }}
    .segment-inspector {{ position: sticky; top: 132px; display: grid; gap: 12px; min-width: 0; max-height: calc(100vh - 148px); overflow: auto; border: 1px solid #c7cdc9; border-radius: 8px; background: #fff; color: #1c2526; padding: 14px; }}
    .segment-inspector h3 {{ margin: 0; color: #20302d; }}
    .segment-inspector-section {{ display: grid; gap: 8px; min-width: 0; }}
    .segment-inspector-label {{ color: #5b6462; font-size: 12px; font-weight: 850; text-transform: uppercase; }}
    .segment-inspector-text {{ margin: 0; overflow-wrap: anywhere; }}
    .segment-inspector-actions {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .inspector-generation-actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .inspector-generation-actions .compact-form {{ margin: 0; }}
    .segment-inspector .storyboard-card-media {{ border-radius: 6px; border: 1px solid #d8d3c8; }}
    .segment-inspector .prompt-textarea {{ width: 100%; min-height: 76px; }}
    .project-modal-content {{ width: min(860px, 94vw); }}
    .project-modal-content form {{ margin: 0; border: 0; border-radius: 0; }}
    @media (max-width: 980px) {{ .storyboard-workspace {{ grid-template-columns: 1fr; }} .segment-inspector {{ position: static; max-height: none; }} }}
    .project-table-view[hidden] {{ display: none; }}
    .queue-estimate {{ margin-left: auto; padding: 6px 10px; border: 1px solid #b9c0bd; border-radius: 6px; background: #fff; color: #20302d; font-weight: 750; white-space: nowrap; }}
    .scroll-top-button {{ position: fixed; right: 18px; bottom: 18px; z-index: 30; box-shadow: 0 8px 22px rgba(0,0,0,.18); }}
    table {{ width: 100%; border-collapse: collapse; background: white; color: #1c2526; border: 1px solid #d8d3c8; }}
    th, td {{ padding: 8px; border-bottom: 1px solid #e7e1d6; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #e9efe9; }}
    .status {{ font-weight: 700; }}
    .status-error {{ margin-top: 4px; color: #9b1c1c; font-weight: 500; max-width: 260px; overflow-wrap: anywhere; }}
    .error {{ color: #9b1c1c; max-width: 220px; overflow-wrap: anywhere; }}
    .low-confidence {{ background: #ffe5f2; }}
    tr.section-gap {{ background: #eeeeee; }}
    tr.section-verse {{ background: lightyellow; }}
    tr.section-bridge {{ background: #eeeeee; }}
    tr.section-chorus {{ background: #e5f0ff; }}
    tr.approved-row {{ background: #7ed67e; box-shadow: inset 5px 0 0 #168a16; }}
    tr.low-confidence {{ box-shadow: inset 4px 0 0 #e53d91; }}
    tr.locked-row {{ position: relative; opacity: .58; pointer-events: none; }}
    .row-lock-overlay {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(128,128,128,.25); color: #17201e; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; pointer-events: none; }}
    .confidence {{ font-weight: 700; color: #9b1c64; }}
    .timing-confidence {{ margin-top: 4px; font-weight: 700; color: #9b1c64; }}
    .select-cell {{ width: 44px; text-align: center; }}
    .section-legend {{ display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin: 10px 0 18px; font-size: 13px; color: #44504d; }}
    .legend-swatch {{ width: 18px; height: 12px; border: 1px solid #ccd4d1; display: inline-block; margin-right: 6px; vertical-align: -2px; }}
    .legend-swatch.section-gap {{ background: #eeeeee; }}
    .legend-swatch.section-verse {{ background: lightyellow; }}
    .legend-swatch.section-bridge {{ background: #eeeeee; }}
    .legend-swatch.section-chorus {{ background: #e5f0ff; }}
    .preview-image {{ width: 292px; height: 164px; object-fit: cover; border-radius: 6px; border: 1px solid #d8d3c8; display: block; }}
    .preview-button {{ padding: 0; border: 0; background: transparent; color: inherit; }}
    .assets-column {{ min-width: 608px; }}
    .assets-stack {{ display: grid; gap: 8px; align-content: start; }}
    .asset-previews {{ display: flex; gap: 8px; align-items: flex-start; }}
    .image-choice {{ display: grid; gap: 6px; min-width: 90px; }}
    .image-choice label {{ display: flex; gap: 6px; align-items: center; margin: 0; font-weight: 500; }}
    .image-choice input {{ width: auto; }}
    .asset-path {{ display: block; max-width: 140px; margin-top: 4px; color: #5b6462; overflow-wrap: anywhere; font-size: 11px; }}
    .lyrics-lines div + div {{ margin-top: 4px; }}
    .redo-cell {{ text-align: center; min-width: 72px; }}
    .redo-action {{ margin-top: 4px; color: #44504d; font-size: 11px; overflow-wrap: anywhere; }}
    .inline-player {{ width: 180px; max-width: 100%; margin-left: 8px; vertical-align: middle; }}
    .lightbox {{ position: fixed; inset: 0; z-index: 50; display: none; align-items: center; justify-content: center; background: rgba(0,0,0,.78); padding: 24px; }}
    .lightbox.open {{ display: flex; }}
    .lightbox-content {{ width: min(960px, 94vw); }}
    .lightbox video, .lightbox img {{ width: 100%; max-height: 82vh; object-fit: contain; background: #000; border-radius: 8px; }}
    .lightbox-close {{ float: right; margin-bottom: 8px; }}
  </style>
  <script>
    const projectRowServerHtml = new Map();
    function rememberProjectRows() {{
      document.querySelectorAll('tr[id^="line-row-"], tr[id^="segment-row-"]').forEach((row) => {{
        projectRowServerHtml.set(row.id, row.outerHTML);
      }});
    }}
    function copySelectedLines(form) {{
      form.querySelectorAll('input[name="selected_lines"]').forEach((input) => input.remove());
      const selectedSegments = document.querySelectorAll('.segment-select:checked');
      const selectedLines = selectedSegments.length ? selectedSegments : document.querySelectorAll('.line-select:checked');
      if (!selectedLines.length) {{
        const hasSegments = document.querySelectorAll('.segment-select').length > 0;
        const itemLabel = hasSegments ? 'Segmente' : 'Zeilen';
        if (!confirm('Keine Checkbox markiert. Es werden alle(!) ' + itemLabel + ' verarbeitet. Fortfahren?')) {{
          return false;
        }}
      }}
      selectedLines.forEach((checkbox) => {{
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'selected_lines';
        input.value = checkbox.value;
        form.appendChild(input);
      }});
      return true;
    }}
    function currentProjectId() {{
      const match = window.location.pathname.match(/^\\/projects\\/(\\d+)/);
      return match ? Number(match[1]) : 0;
    }}
    function projectActionSubmitted(form) {{
      if (!copySelectedLines(form)) return false;
      const projectId = currentProjectId();
      if (projectId) {{
        window.setTimeout(() => refreshProjectStatus(projectId), 150);
      }}
      return true;
    }}
    function toggleRowSelection(event, row) {{
      const interactiveSelector = 'button, a, input, textarea, select, label, audio, video, img, form';
      if (event.target.closest(interactiveSelector)) return;
      const checkbox = row.querySelector('.segment-select, .line-select');
      if (!checkbox) return;
      checkbox.checked = !checkbox.checked;
    }}
    function projectRowChanged(row, replacement) {{
      const previousHtml = projectRowServerHtml.get(row.id) || row.outerHTML;
      return previousHtml !== replacement.outerHTML;
    }}
    function replaceProjectRow(row, html) {{
      const checkbox = row.querySelector('.segment-select, .line-select');
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (!replacement) return;
      if (!projectRowChanged(row, replacement)) return;
      const replacementCheckbox = replacement.querySelector('.segment-select, .line-select');
      if (checkbox && replacementCheckbox) {{
        replacementCheckbox.checked = checkbox.checked;
      }}
      row.replaceWith(replacement);
      projectRowServerHtml.set(replacement.id, replacement.outerHTML);
    }}
    const projectStoryboardFieldSelector = 'input, textarea, select';
    function projectStoryboardHasActiveEdit(storyboard) {{
      const active = document.activeElement;
      return !!(active && active.closest && storyboard.contains(active) && active.matches(projectStoryboardFieldSelector));
    }}
    function projectStoryboardFieldDirty(field) {{
      if (field.type === 'checkbox' || field.type === 'radio') {{
        return field.checked !== field.defaultChecked;
      }}
      if (field.tagName === 'SELECT') {{
        return Array.from(field.options).some((option) => option.selected !== option.defaultSelected);
      }}
      return field.value !== field.defaultValue;
    }}
    function projectStoryboardHasDirtyFields(storyboard) {{
      return Array.from(storyboard.querySelectorAll(projectStoryboardFieldSelector)).some(projectStoryboardFieldDirty);
    }}
    function projectStoryboardHasPlayingVideo(storyboard) {{
      return Array.from(storyboard.querySelectorAll('.storyboard-card-video')).some((video) => !video.paused && !video.ended);
    }}
    function shouldReplaceProjectStoryboard(storyboard) {{
      return !projectStoryboardHasActiveEdit(storyboard) && !projectStoryboardHasDirtyFields(storyboard) && !projectStoryboardHasPlayingVideo(storyboard);
    }}
    function activeProjectStoryboardTemplateId(storyboard) {{
      const activeCard = storyboard.querySelector('.storyboard-card-active');
      return activeCard ? activeCard.dataset.inspectorTemplate : '';
    }}
    function restoreProjectStoryboardSelection(storyboard, templateId) {{
      if (!templateId) return;
      const card = storyboard.querySelector('[data-inspector-template="' + templateId + '"]');
      if (!card) return;
      selectStoryboardCard(storyboard, card);
    }}
    function replaceProjectStoryboard(html) {{
      const storyboard = document.getElementById('project-storyboard');
      if (!storyboard || html === undefined) return;
      if (!shouldReplaceProjectStoryboard(storyboard)) return;
      const activeTemplateId = activeProjectStoryboardTemplateId(storyboard);
      const template = document.createElement('template');
      template.innerHTML = html.trim();
      const replacement = template.content.firstElementChild;
      if (!replacement) return;
      replacement.hidden = storyboard.hidden;
      storyboard.replaceWith(replacement);
      restoreProjectStoryboardSelection(replacement, activeTemplateId);
    }}
    const baseDocumentTitle = document.title.replace(/^\\(\\d+\\)\\s+/, '');
    function updateBrowserTitle(queueCount) {{
      if (queueCount === undefined || queueCount === null) return;
      const count = Math.max(0, Number(queueCount) || 0);
      document.title = count > 0 ? '(' + count + ') ' + baseDocumentTitle : baseDocumentTitle;
    }}
    function updateProjectStatus(data) {{
      updateQueueEstimate(data.queue_estimate_seconds);
      updateBrowserTitle(data.queue_count);
      Object.entries(data.rows || {{}}).forEach(([rowId, html]) => {{
        const row = document.getElementById(rowId);
        if (row) replaceProjectRow(row, html);
      }});
      if (data.storyboard_html !== undefined) replaceProjectStoryboard(data.storyboard_html);
    }}
    async function refreshProjectStatus(projectId) {{
      if (!projectId) return;
      const response = await fetch('/projects/' + projectId + '/status');
      if (!response.ok) return;
      const data = await response.json();
      updateProjectStatus(data);
    }}
    async function pollProjectStatus(projectId) {{
      try {{
        await refreshProjectStatus(projectId);
      }} catch (error) {{
        return;
      }} finally {{
        window.setTimeout(() => pollProjectStatus(projectId), 2500);
      }}
    }}
    function updateJobsStatus(data) {{
      updateQueueEstimate(data.queue_estimate_seconds);
      updateBrowserTitle(data.queue_count);
      const queueSummary = document.getElementById('queue-summary');
      if (queueSummary && data.queue_summary_html !== undefined) queueSummary.innerHTML = data.queue_summary_html;
      const jobsBody = document.getElementById('jobs-table-body');
      if (jobsBody && data.jobs_html !== undefined) jobsBody.innerHTML = data.jobs_html;
      const autodelete = document.querySelector('input[name="autodelete_finished"]');
      if (autodelete && data.autodelete_finished !== undefined) autodelete.checked = Boolean(data.autodelete_finished);
      const shutdown = document.querySelector('input[name="shutdown_after_queue"]');
      if (shutdown && data.shutdown_after_queue !== undefined) shutdown.checked = Boolean(data.shutdown_after_queue);
    }}
    async function refreshJobsStatus() {{
      const response = await fetch('/jobs/status');
      if (!response.ok) return;
      updateJobsStatus(await response.json());
    }}
    async function pollJobsStatus() {{
      try {{
        await refreshJobsStatus();
      }} catch (error) {{
        return;
      }} finally {{
        window.setTimeout(pollJobsStatus, 2500);
      }}
    }}
    function formatDuration(seconds) {{
      const total = Math.max(0, Math.round(Number(seconds) || 0));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const remaining = total % 60;
      if (hours) return hours + 'h ' + minutes + 'm';
      if (minutes) return minutes + 'm ' + remaining + 's';
      return remaining + 's';
    }}
    function updateQueueEstimate(seconds) {{
      const element = document.getElementById('queue-estimate');
      if (!element || seconds === undefined || seconds === null) return;
      const value = Math.max(0, Number(seconds) || 0);
      element.dataset.seconds = String(Math.round(value));
      element.textContent = value > 0 ? 'Queue ca. ' + formatDuration(value) : 'Queue frei';
    }}
    function setupQueueEstimateCountdown() {{
      window.setInterval(() => {{
        const element = document.getElementById('queue-estimate');
        if (!element) return;
        const value = Math.max(0, Number(element.dataset.seconds || 0) - 1);
        updateQueueEstimate(value);
      }}, 1000);
    }}
    function openNewProjectModal() {{
      const box = document.getElementById('new-project-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeNewProjectModal() {{
      const box = document.getElementById('new-project-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function openProjectSettingsModal() {{
      const box = document.getElementById('project-settings-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeProjectSettingsModal() {{
      const box = document.getElementById('project-settings-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function openScenePlanModal() {{
      const box = document.getElementById('scene-plan-modal');
      if (!box) return;
      box.classList.add('open');
    }}
    function closeScenePlanModal() {{
      const box = document.getElementById('scene-plan-modal');
      if (!box) return;
      box.classList.remove('open');
    }}
    function scrollToTop() {{
      const firstSegment = document.querySelector('tr[id^="segment-row-"]');
      const target = firstSegment || document.querySelector('tr[id^="line-row-"]');
      if (!target) {{
        window.scrollTo({{ top: 0, behavior: 'smooth' }});
        return;
      }}
      const topbar = document.querySelector('.project-topbar');
      const offset = topbar ? topbar.getBoundingClientRect().height : 0;
      const top = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({{ top: Math.max(0, top), behavior: 'smooth' }});
    }}
    function switchProjectView(view) {{
      const storyboard = document.getElementById('project-storyboard');
      const table = document.getElementById('project-table-view');
      if (!storyboard || !table) return;
      const showTable = view === 'table';
      storyboard.hidden = showTable;
      table.hidden = !showTable;
      document.querySelectorAll('[data-project-view]').forEach((button) => {{
        const active = button.dataset.projectView === view;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
      }});
    }}
    function selectStoryboardCard(storyboard, card) {{
      const templateId = card.dataset.inspectorTemplate;
      const template = templateId ? document.getElementById(templateId) : null;
      const current = storyboard.querySelector('#segment-inspector');
      if (!template || !current) return;
      storyboard.querySelectorAll('.storyboard-card-active').forEach((item) => item.classList.remove('storyboard-card-active'));
      card.classList.add('storyboard-card-active');
      const fragment = template.content.cloneNode(true);
      const replacement = fragment.querySelector('#segment-inspector');
      if (!replacement) return;
      current.replaceWith(replacement);
    }}
    function selectStoryboardItem(event, card) {{
      const interactiveSelector = 'button, a, input, textarea, select, label, audio, video, img, form';
      if (event && event.target && event.target.closest(interactiveSelector)) return;
      const storyboard = card.closest('#project-storyboard');
      if (!storyboard) return;
      selectStoryboardCard(storyboard, card);
    }}
    function scrollStorageKey() {{
      return 'musicvideogen-scroll:' + window.location.pathname;
    }}
    function rememberScrollPosition() {{
      sessionStorage.setItem(scrollStorageKey(), String(window.scrollY));
    }}
    function confirmProjectSettingsSave(form) {{
      rememberScrollPosition();
      return true;
    }}
    document.addEventListener('submit', rememberScrollPosition);
    document.addEventListener('DOMContentLoaded', () => {{
      rememberProjectRows();
      const stored = sessionStorage.getItem(scrollStorageKey());
      if (stored === null) return;
      const scrollY = Number(stored);
      if (!Number.isFinite(scrollY)) return;
      requestAnimationFrame(() => window.scrollTo(0, scrollY));
    }});
    function toggleAudio(button) {{
      const audio = button.nextElementSibling;
      if (!audio) return;
      if (audio.paused) {{
        audio.play();
        button.textContent = '||';
      }} else {{
        audio.pause();
        button.textContent = '▶';
      }}
      audio.onended = () => {{ button.textContent = '▶'; }};
    }}
    function toggleStoryboardVideo(event, target) {{
      if (event) event.stopPropagation();
      const media = target.closest('.storyboard-card-media-clip');
      if (!media) return;
      const video = media.querySelector('video');
      const button = media.querySelector('.storyboard-video-toggle');
      if (!video) return;
      if (video.paused) {{
        video.play();
        if (button) {{
          button.setAttribute('aria-label', 'Pause clip');
          button.querySelector('.storyboard-play-icon').textContent = 'Ⅱ';
        }}
      }} else {{
        video.pause();
        if (button) {{
          button.setAttribute('aria-label', 'Play clip');
          button.querySelector('.storyboard-play-icon').textContent = '▶';
        }}
      }}
      video.onended = () => {{
        if (!button) return;
        button.setAttribute('aria-label', 'Play clip');
        button.querySelector('.storyboard-play-icon').textContent = '▶';
      }};
    }}
    function openClipLightbox(src) {{
      const box = document.getElementById('clip-lightbox');
      const video = document.getElementById('clip-lightbox-video');
      video.src = src;
      box.classList.add('open');
      video.play();
    }}
    function closeClipLightbox() {{
      const box = document.getElementById('clip-lightbox');
      const video = document.getElementById('clip-lightbox-video');
      video.pause();
      video.removeAttribute('src');
      video.load();
      box.classList.remove('open');
    }}
    function openImageLightbox(src) {{
      const box = document.getElementById('image-lightbox');
      const image = document.getElementById('image-lightbox-image');
      image.src = src;
      box.classList.add('open');
    }}
    function closeImageLightbox() {{
      const box = document.getElementById('image-lightbox');
      const image = document.getElementById('image-lightbox-image');
      image.removeAttribute('src');
      box.classList.remove('open');
    }}
  </script>
</head>
<body><main>{body}</main></body>
</html>"""


def _browser_title(title: str, queue_count: int = 0) -> str:
    count = max(0, int(queue_count or 0))
    return f"({count}) {title}" if count else title


def _run_project_action(pipeline, project_id: int, action: str, selected_indices: list[int]) -> object:
    method_names = {
        "prompts": "generate_prompts",
        "video-prompts": "generate_video_prompts",
        "images": "generate_images",
        "avatar-image": "generate_avatar_images",
        "clips": "generate_clips",
    }
    return getattr(pipeline, method_names[action])(project_id, selected_indices)


def _selected_action_indices(project_id: int, item_kind: str, selected: list[int], store: Store) -> list[int]:
    if selected:
        selected_set = {int(index) for index in selected}
    else:
        selected_set = set()
    rows = store.list_segments(project_id) if item_kind == "segments" else store.list_lines(project_id)
    if selected_set:
        rows = [row for row in rows if _row_index(row, item_kind) in selected_set]
    rows = [row for row in rows if not bool(_row_value(row, "video_approved", 0))]
    return [_row_index(row, item_kind) for row in rows]


def _projects_html(
    projects,
    jobs,
    average_durations: dict[str, float] | None = None,
    queue_estimate_seconds: float | None = None,
    job_options: JobOptions | None = None,
) -> str:
    average_durations = average_durations or {}
    job_options = job_options or JobOptions()
    rows = "".join(_project_list_item_html(p) for p in projects)
    return f"""
<div class="start-dashboard">
{_start_topbar_html(queue_estimate_seconds)}
{_start_hero_html(projects, jobs, queue_estimate_seconds)}
<div class="start-layout">
<section class="studio-panel">
  <div class="studio-panel-head"><h2>Projects</h2></div>
  <div class="project-grid">{rows}</div>
</section>
{_queue_section_html(jobs, average_durations, queue_estimate_seconds, job_options)}
</div>
{_new_project_modal_html()}
</div>
<script>setupQueueEstimateCountdown(); pollJobsStatus();</script>
"""


def _start_topbar_html(queue_estimate_seconds: float | None) -> str:
    return f"""
<div class="studio-topbar">
  <div class="studio-brand">VocaVid</div>
  <div class="studio-tagline">Local AI music-video studio</div>
  <div class="studio-spacer"></div>
  {_queue_estimate_html(queue_estimate_seconds)}
  <button class="studio-button" type="button" onclick="openNewProjectModal()">New Project</button>
  <a class="studio-button studio-button-secondary" href="#jobs-panel">Jobs</a>
</div>
"""


def _new_project_modal_html() -> str:
    return f"""
<div id="new-project-modal" class="modal lightbox" onclick="if (event.target === this) closeNewProjectModal()">
  <div class="modal-content">
    <div class="studio-panel-head">
      <h2>New Project</h2>
      <button class="studio-button studio-button-secondary" type="button" onclick="closeNewProjectModal()">Close</button>
    </div>
    <form class="new-project-form" action="/projects" method="post" enctype="multipart/form-data">
      <label>Name</label><input name="name" required>
      <label>WAV</label><input name="audio" type="file" accept=".wav,audio/wav" required>
      <label>Lyrics</label><input name="lyrics" type="file" accept=".txt,.lyrics" required>
      <label>Lyrics-Zeilen pro Clip</label><input name="lyric_group_size" type="number" min="1" max="8" value="2">
      <label>Refrain-Zeilen pro Clip</label><input name="chorus_group_size" type="number" min="1" max="8" value="1">
      <label>Transition Handle hinten (Sek.)</label><input name="transition_handle_seconds" type="number" min="0" step="0.1" value="0.5">
      <label>Whisper Model</label>{_whisper_model_select_html("small")}
      <p><button>Create Project</button></p>
    </form>
  </div>
</div>
"""


def _start_hero_html(projects, jobs, queue_estimate_seconds: float | None) -> str:
    open_jobs = len([job for job in jobs if job.status in {"queued", "running"}])
    return f"""
<section class="start-hero">
  <div>
    <h1>Build, review, rerender.</h1>
    <p>Projects are the main act, queue health stays visible, and creating a new video opens as a focused modal.</p>
  </div>
  <div class="production-status">
    <h2>Production status</h2>
    <div class="stat-grid">
      <div class="stat"><strong>{len(projects)}</strong><span>projects</span></div>
      <div class="stat"><strong>{open_jobs}</strong><span>active jobs</span></div>
      <div class="stat"><strong>{_text(_format_duration(queue_estimate_seconds or 0))}</strong><span>queue estimate</span></div>
    </div>
  </div>
</section>
"""


def _queue_section_html(
    jobs,
    average_durations: dict[str, float],
    queue_estimate_seconds: float | None,
    job_options: JobOptions,
) -> str:
    job_rows = _jobs_table_body_html(jobs, average_durations)
    return f"""
<section id="jobs-panel" class="panel studio-panel queue-panel">
  <div class="queue-panel-head">
    <div>
      <h2 class="jobs-heading">Jobs</h2>
      <p>Live queue, recent results, and cleanup controls.</p>
    </div>
  </div>
  {_queue_summary_html(jobs, queue_estimate_seconds)}
  <div class="jobs-table-wrap">
    <table><thead><tr><th>#</th><th>Name</th><th>Status</th><th>Created</th><th>Error</th><th>Avg</th><th></th></tr></thead><tbody id="jobs-table-body">{job_rows}</tbody></table>
  </div>
  {_queue_admin_html(job_options)}
</section>
"""


def _queue_summary_html(jobs, queue_estimate_seconds: float | None) -> str:
    return f"""
  <div id="queue-summary" class="queue-summary-grid">
{_queue_summary_cards_html(jobs, queue_estimate_seconds)}
  </div>
"""


def _queue_summary_cards_html(jobs, queue_estimate_seconds: float | None) -> str:
    counts = {status: 0 for status in ("queued", "running", "done", "failed")}
    for job in jobs:
        if job.status in counts:
            counts[job.status] += 1
    estimate = _format_duration(queue_estimate_seconds or 0)
    return f"""
    <div class="queue-summary-card queue-summary-card-active"><strong>{counts["queued"]}</strong><span>queued</span></div>
    <div class="queue-summary-card queue-summary-card-active"><strong>{counts["running"]}</strong><span>running</span></div>
    <div class="queue-summary-card"><strong>{counts["done"]}</strong><span>done</span></div>
    <div class="queue-summary-card"><strong>{counts["failed"]}</strong><span>failed</span></div>
    <div class="queue-summary-card"><strong>{_text(estimate)}</strong><span>estimate</span></div>
"""


def _queue_admin_html(job_options: JobOptions) -> str:
    autodelete_checked = " checked" if job_options.autodelete_finished else ""
    shutdown_checked = " checked" if job_options.shutdown_after_queue else ""
    return f"""
  <div class="queue-admin-controls">
    <form class="compact-form" action="/jobs/delete-queued" method="post"><button>Delete queued</button></form>
    <form class="compact-form" action="/jobs/delete-finished" method="post"><button>Delete finished</button></form>
    <form class="compact-form job-options" action="/jobs/options" method="post">
      <label><input type="checkbox" name="autodelete_finished"{autodelete_checked} onchange="this.form.submit()"> Autodelete finished</label>
      <label><input type="checkbox" name="shutdown_after_queue"{shutdown_checked} onchange="this.form.submit()"> Shutdown computer 15mins after last queue</label>
    </form>
  </div>
"""


def _jobs_table_body_html(jobs, average_durations: dict[str, float]) -> str:
    return "".join(
        f"<tr><td>{job.id}</td><td>{_text(job.name)}</td><td>{_text(job.status)}</td><td>{_text(job.created_at)}</td><td class='error'>{_text(job.error)}</td><td>{_duration_html(_job_average_seconds(job, average_durations))}</td><td>{_job_delete_html(job)}</td></tr>"
        for job in jobs
    )


def _project_list_item_html(project) -> str:
    done = _is_kdenlive_project_done(project)
    css_class = "project-card project-card-done" if done else "project-card"
    done_label = '<span class="project-done-label">done</span>' if done else ""
    status = "Final assembled" if done else "Open project"
    return f"""
<article class="{css_class}">
  <a class="project-card-link" href="/projects/{project["id"]}">
    <div class="project-card-art"></div>
    <div class="project-card-body">
      <h3>{_text(project["name"])}</h3>
      <p>{_text(status)}</p>
      {done_label}
    </div>
  </a>
</article>
"""


def _is_kdenlive_project_done(project) -> bool:
    final_video_path = str(_row_value(project, "final_video_path", "") or "")
    return final_video_path.lower().endswith(".kdenlive")


def _job_name(label: str, project_name: str, selected_indices: list[int] | None = None, item_kind: str | None = None) -> str:
    selected = sorted(int(index) + 1 for index in (selected_indices or []))
    if not selected:
        return f"{label}: {project_name}"
    if item_kind and len(selected) == 1:
        item_label = "segment" if item_kind == "segments" else "line"
        return f"{label}: {project_name} ({item_label} {selected[0]})"
    indices = ", ".join(str(index) for index in selected)
    return f"{label}: {project_name} (segments {indices})"


def _action_item_kind(action: str, has_segments: bool) -> str:
    if action == "align" or action == "segments":
        return "lines"
    return "segments" if has_segments else "lines"


def _locked_indices(active_jobs, item_kind: str, rows) -> dict[int, str]:
    row_indices = [_row_index(row, item_kind) for row in rows]
    locked: dict[int, str] = {}
    for job in active_jobs:
        if job.item_kind != item_kind:
            continue
        selected = list(job.selected_indices or [])
        indices = selected if selected else row_indices
        for index in indices:
            locked[int(index)] = job.status
    return locked


def _row_index(row, item_kind: str) -> int:
    key = "segment_index" if item_kind == "segments" else "line_index"
    return int(row[key])


def _merge_row_class(row_class: str, extra_class: str) -> str:
    if not extra_class:
        return row_class
    if not row_class:
        return f' class="{extra_class}"'
    return row_class[:-1] + f" {extra_class}\""


def _project_html(
    project,
    lines,
    segments=None,
    used_actions=None,
    active_jobs=None,
    queue_estimate_seconds: float | None = None,
    previous_project_id: int | None = None,
    next_project_id: int | None = None,
) -> str:
    segments = segments or []
    used_actions = used_actions or set()
    active_jobs = active_jobs or []
    work_items = segments or lines
    item_kind = "segments" if segments else "lines"
    locked = _locked_indices(active_jobs, item_kind, work_items)
    assemble_enabled = _all_videos_approved(work_items)
    action_specs = [
        ("align", "Align", False),
        ("segments", "Segs + Audio", False),
        ("scene-plan", "Scene Plan", False),
        ("prompts", "Gen Image Prompts", False),
        ("video-prompts", "Gen Video Prompts", False),
        ("images", "Gen Images", False),
        ("avatar-image", "Gen Avatar Image", False),
        ("clips", "Gen Clips", False),
        ("assemble", "Assemble Final", True),
    ]
    actions = "".join(
        _action_button(
            project["id"],
            number,
            action,
            label,
            is_wip,
            action in used_actions,
            enabled=(action != "assemble" or not work_items or assemble_enabled),
        )
        for number, (action, label, is_wip) in enumerate(action_specs, start=1)
    )
    open_filter = _open_filter_html(work_items)
    queue_estimate = _queue_estimate_html(queue_estimate_seconds)
    previous_project_nav = _project_nav_html(previous_project_id, "previous")
    next_project_nav = _project_nav_html(next_project_id, "next")
    storyboard = _storyboard_html(project, work_items, item_kind)
    table = _work_items_html(project, lines, segments, locked, show_generation_columns="scene-plan" in used_actions)
    return f"""
<div class="project-studio">
  <div class="project-topbar">
    <div class="project-title-row">
      {previous_project_nav}
      <h1>{project['name']}</h1>
      {next_project_nav}
      {queue_estimate}
      <button class="project-icon-button" type="button" title="Project Settings" onclick="openProjectSettingsModal()">⚙</button>
      <button class="project-icon-button" type="button" title="Scene Plan" onclick="openScenePlanModal()">☰</button>
      <a class="button" href="/">Back</a>
    </div>
    <div class="actions">{actions}{open_filter}</div>
  </div>
  <div class="view-switch" role="group" aria-label="Project view">
    <button type="button" class="active" data-project-view="storyboard" aria-pressed="true" onclick="switchProjectView('storyboard')">Storyboard</button>
    <button type="button" data-project-view="table" aria-pressed="false" onclick="switchProjectView('table')">Advanced Table</button>
  </div>
  {storyboard}
  <section id="project-table-view" class="project-table-view" hidden>
    {table}
  </section>
{_project_settings_modal_html(project)}
{_scene_plan_modal_html(project)}
</div>
{_clip_lightbox_html()}
{_image_lightbox_html()}
{_clear_project_html(project)}
{_scroll_top_button_html()}
<script>rememberProjectRows(); setupQueueEstimateCountdown(); pollProjectStatus({project["id"]});</script>
"""


def _project_settings_modal_html(project) -> str:
    return f"""
<div id="project-settings-modal" class="modal lightbox" onclick="if (event.target === this) closeProjectSettingsModal()">
  <div class="modal-content project-modal-content">
    <div class="studio-panel-head">
      <h2>Project Settings</h2>
      <button class="studio-button studio-button-secondary" type="button" onclick="closeProjectSettingsModal()">Close</button>
    </div>
    {_segment_settings_html(project, show_heading=False)}
  </div>
</div>
"""


def _scene_plan_modal_html(project) -> str:
    return f"""
<div id="scene-plan-modal" class="modal lightbox" onclick="if (event.target === this) closeScenePlanModal()">
  <div class="modal-content project-modal-content">
    <div class="studio-panel-head">
      <h2>Scene Plan</h2>
      <button class="studio-button studio-button-secondary" type="button" onclick="closeScenePlanModal()">Close</button>
    </div>
    {_scene_plan_editor_html(project, show_heading=False)}
  </div>
</div>
"""


def _storyboard_html(project, work_items, item_kind: str) -> str:
    if not work_items:
        return """
  <section id="project-storyboard" class="project-storyboard">
    <h2>Storyboard</h2>
    <div class="storyboard-rail">
      <article class="storyboard-card storyboard-card-empty">
        <div class="storyboard-card-media">No items yet</div>
        <div class="storyboard-card-body">
          <p class="storyboard-card-text">Run alignment or segment generation to populate the storyboard.</p>
        </div>
      </article>
    </div>
  </section>
"""
    cards = "".join(_storyboard_card_html(project, row, item_kind, active=index == 0) for index, row in enumerate(work_items))
    templates = "".join(_storyboard_inspector_template_html(project, item_kind, row) for row in work_items)
    inspector = _segment_inspector_html(project, item_kind, work_items[0])
    return f"""
  <section id="project-storyboard" class="project-storyboard">
    <h2>Storyboard</h2>
    <div class="storyboard-workspace">
      <div class="storyboard-rail">{cards}</div>
      {inspector}
    </div>
    {templates}
  </section>
"""


def _storyboard_inspector_template_html(project, item_kind: str, row) -> str:
    item_index = _row_index(row, item_kind)
    return f"""
    <template id="segment-inspector-template-{item_kind}-{item_index}">
      {_segment_inspector_html(project, item_kind, row)}
    </template>
"""


def _segment_inspector_html(project, item_kind: str, row) -> str:
    index_key = "segment_index" if item_kind == "segments" else "line_index"
    label = "Segment" if item_kind == "segments" else "Line"
    item_index = int(_row_value(row, index_key, 0))
    text = _row_value(row, "clean_text", "") or "(empty)"
    timing = _timing_text(_row_value(row, "start_sec", None), _row_value(row, "end_sec", None))
    prompt = _row_value(row, "prompt", "") or ""
    video_prompt = _row_value(row, "video_prompt", "") or ""
    last_action = _row_value(row, "last_action", "")
    image_choice_html = _image_choice_html(project["id"], item_kind, item_index, row)
    redo_html = _redo_html(project["id"], item_kind, item_index, last_action)
    approval_html = _approval_html(project["id"], item_kind, item_index, row)
    status_html = _status_html(_row_value(row, "status", "") or "pending", _row_value(row, "error", "") or "")
    prompt_editor = _prompt_editor_html(f"/projects/{project['id']}/{item_kind}/{item_index}/prompts", prompt, video_prompt)
    media_html = _storyboard_card_media_html(project, row)
    text_html = _multiline_text_html(text) or _text(text)
    timing_html = f'<div class="storyboard-card-status">{_text(timing)}</div>' if timing else ""
    image_choice_section = f"""
      <div class="segment-inspector-section">
        <div class="segment-inspector-label">Image source</div>
        {image_choice_html}
      </div>""" if image_choice_html else ""
    redo_section = f"""
      <div class="segment-inspector-section">
        <div class="segment-inspector-label">Redo</div>
        {redo_html}
      </div>""" if redo_html else ""
    quick_actions = _inspector_generation_actions_html(project["id"], item_kind, item_index, row)
    return f"""
      <aside id="segment-inspector" class="segment-inspector" aria-label="Selected storyboard item">
        <h3>Selected {label} {_text(item_index)}</h3>
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Preview</div>
          {media_html}
        </div>
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Text</div>
          <div class="segment-inspector-text">{text_html}</div>
          {timing_html}
        </div>
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Prompts</div>
          {prompt_editor}
        </div>
        {image_choice_section}
        <div class="segment-inspector-actions">
          {approval_html}
        </div>
        {quick_actions}
        {redo_section}
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Status</div>
          {status_html}
        </div>
      </aside>
"""


def _storyboard_card_html(project, row, item_kind: str, active: bool = False) -> str:
    index_key = "segment_index" if item_kind == "segments" else "line_index"
    label = "Segment" if item_kind == "segments" else "Line"
    index = _row_value(row, index_key, 0)
    text = _row_value(row, "clean_text", "") or "(empty)"
    timing = _timing_text(_row_value(row, "start_sec", None), _row_value(row, "end_sec", None))
    status = _row_value(row, "status", "") or "pending"
    timing_html = f'<span>{_text(timing)}</span>' if timing else ""
    text_html = _multiline_text_html(text) or _text(text)
    media_html = _storyboard_card_media_html(project, row)
    active_class = " storyboard-card-active" if active else ""
    progress = _storyboard_progress_strip_html(row)
    return f"""
      <article class="storyboard-card{active_class}" tabindex="0" role="button" data-inspector-template="segment-inspector-template-{item_kind}-{_attr(index)}" onclick="selectStoryboardItem(event, this)" onkeydown="if (event.key === 'Enter' || event.key === ' ') selectStoryboardItem(event, this)">
        {media_html}
        <div class="storyboard-card-body">
          <div class="storyboard-card-title"><span>{label} {_text(index)}</span>{timing_html}</div>
          {progress}
          <div class="storyboard-card-text">{text_html}</div>
          <div class="storyboard-card-status">{_text(status)}</div>
        </div>
      </article>
"""


def _storyboard_progress_strip_html(row) -> str:
    steps = [
        ("Prompt", bool(_row_value(row, "prompt", "") or _row_value(row, "video_prompt", ""))),
        ("Image", bool(_row_value(row, "image_path", ""))),
        ("Avatar", bool(_row_value(row, "avatar_image_path", ""))),
        ("Clip", bool(_row_value(row, "clip_path", ""))),
        ("OK", bool(_row_value(row, "video_approved", 0))),
    ]
    chips = "".join(
        f'<span class="progress-step{" progress-step-done" if done else ""}">{_text(label)}</span>'
        for label, done in steps
    )
    return f'<div class="storyboard-progress-strip">{chips}</div>'


def _inspector_generation_actions_html(project_id: int, item_kind: str, item_index: int, row) -> str:
    if not (_row_value(row, "prompt", "") or _row_value(row, "video_prompt", "")):
        return ""
    return f"""
        <div class="segment-inspector-section">
          <div class="segment-inspector-label">Next renders</div>
          <div class="inspector-generation-actions">
            {_inspector_action_form_html(project_id, "images", item_index, "Gen Images")}
            {_inspector_action_form_html(project_id, "avatar-image", item_index, "Gen Avatar Image")}
            {_inspector_action_form_html(project_id, "clips", item_index, "Gen Clips")}
          </div>
        </div>
"""


def _inspector_action_form_html(project_id: int, action: str, item_index: int, label: str) -> str:
    return f"""
<form class="compact-form" action="/projects/{project_id}/{action}" method="post" onsubmit="rememberScrollPosition()">
  <input type="hidden" name="selected_lines" value="{_attr(item_index)}">
  <button>{_text(label)}</button>
</form>
"""


def _storyboard_card_media_html(project, row) -> str:
    clip_path = _row_value(row, "clip_path", "")
    if clip_path:
        url = _generated_asset_url(project, clip_path)
        poster_path = _storyboard_image_path(row)
        poster_attr = ""
        if poster_path:
            poster_url = _generated_asset_url(project, poster_path)
            poster_attr = f' poster="{_attr(_url_for_media_attribute(poster_url))}"'
        return f"""
        <div class="storyboard-card-media storyboard-card-media-clip" onclick="toggleStoryboardVideo(event, this)">
          <video class="storyboard-card-video" src="{_attr(_url_for_media_attribute(url))}"{poster_attr} preload="none" playsinline></video>
          <button class="storyboard-video-toggle" type="button" aria-label="Play clip" onclick="toggleStoryboardVideo(event, this)">
            <span class="storyboard-play-icon">▶</span>
          </button>
        </div>"""
        return f"""
        <div class="storyboard-card-media storyboard-card-media-clip">
          <button type="button" title="Play clip" onclick="openClipLightbox({_attr(_js_string_arg(_url_for_html_attribute(url)))})">
            <span class="storyboard-play-button"><span class="storyboard-play-icon">▶</span><span>Play clip</span></span>
          </button>
        </div>"""

    image_path = _storyboard_image_path(row)
    if image_path:
        url = _generated_asset_url(project, image_path)
        return f"""
        <div class="storyboard-card-media storyboard-card-media-image">
          <button type="button" title="Open image" onclick="openImageLightbox({_attr(_js_string_arg(_url_for_html_attribute(url)))})">
            <img class="storyboard-card-image" src="{_attr(_url_for_html_attribute(url))}" alt="Storyboard image">
          </button>
        </div>"""

    return """
        <div class="storyboard-card-media storyboard-card-media-empty">
          <span class="storyboard-empty-mark"><strong>Awaiting media</strong><span>Generate an image or clip to preview this item.</span></span>
        </div>"""


def _storyboard_image_path(row) -> str:
    image_path = _row_value(row, "image_path", "")
    avatar_image_path = _row_value(row, "avatar_image_path", "")
    if image_path and avatar_image_path:
        selected = _row_value(row, "selected_image_source", "avatar")
        return image_path if selected == "image" else avatar_image_path
    return avatar_image_path or image_path


def _url_for_html_attribute(url: str) -> str:
    return str(url).replace("&amp;", "&")


def _url_for_media_attribute(url: str) -> str:
    return json.dumps(_url_for_html_attribute(url))[1:-1]


def _project_navigation_ids(projects, project_id: int) -> tuple[int | None, int | None]:
    project_ids = [int(project["id"]) for project in projects]
    try:
        index = project_ids.index(int(project_id))
    except ValueError:
        return None, None
    previous_project_id = project_ids[index - 1] if index > 0 else None
    next_project_id = project_ids[index + 1] if index + 1 < len(project_ids) else None
    return previous_project_id, next_project_id


def _project_nav_html(project_id: int | None, direction: str) -> str:
    if direction == "previous":
        symbol = "◀"
        active_title = "Vorhergehendes Projekt"
        disabled_title = "Kein vorhergehendes Projekt"
    else:
        symbol = "▶"
        active_title = "Nachfolgendes Projekt"
        disabled_title = "Kein nachfolgendes Projekt"
    if project_id is None:
        return f'<span class="project-nav-button project-nav-disabled" title="{disabled_title}">{symbol}</span>'
    return f'<a class="project-nav-button" href="/projects/{project_id}" title="{active_title}">{symbol}</a>'


def _segment_settings_html(project, show_heading: bool = True) -> str:
    name = _row_value(project, "name", "")
    audio_path = _row_value(project, "audio_path", "")
    lyrics_path = _row_value(project, "lyrics_path", "")
    global_style_prompt = _row_value(project, "global_style_prompt", "")
    genre = _row_value(project, "genre", "")
    reference_paths = "\n".join(_reference_paths_from_json(_row_value(project, "reference_image_paths", "[]")))
    comfy_base_url = _row_value(project, "comfy_base_url", "http://127.0.0.1:8188")
    output_resolution = _row_value(project, "output_resolution", "1280x720")
    fps = _row_value(project, "fps", 24)
    lyric_group_size = _row_value(project, "lyric_group_size", 2)
    chorus_group_size = _row_value(project, "chorus_group_size", 1)
    transition_handle_seconds = _row_value(project, "transition_handle_seconds", 0.5)
    whisper_model_size = normalize_whisper_model_size(_row_value(project, "whisper_model_size", "small"))
    heading_html = "<h2>Project Settings</h2>" if show_heading else ""
    return f"""
<form class="hidden-action-form" id="global-style-prompt-form-{project['id']}" action="/projects/{project['id']}/global-style-prompt" method="post"></form>
<form class="hidden-action-form" id="realign-lyrics-form-{project['id']}" action="/projects/{project['id']}/realign-lyrics" method="post"></form>
<form class="hidden-action-form" id="realign-lyrics-cpu-form-{project['id']}" action="/projects/{project['id']}/realign-lyrics-cpu" method="post"></form>
<form action="/projects/{project['id']}/settings" method="post" onsubmit="return confirmProjectSettingsSave(this)" data-original-lyric-group-size="{_attr(lyric_group_size)}" data-original-chorus-group-size="{_attr(chorus_group_size)}">
  {heading_html}
  <label>Name</label><input name="name" value="{_attr(name)}" required>
  <label>WAV Path</label><input name="audio_path" value="{_attr(audio_path)}" required>
  <label>Lyrics Path</label><input name="lyrics_path" value="{_attr(lyrics_path)}" required>
  <label>Global Style Prompt</label><textarea name="global_style_prompt" required>{_text(global_style_prompt)}</textarea>
  <p><button type="submit" form="global-style-prompt-form-{project['id']}">KI-Vorschlag erstellen</button></p>
  <label>Genre</label><input name="genre" value="{_attr(genre)}">
  <label>Reference Image Paths</label><textarea name="reference_image_paths">{_text(reference_paths)}</textarea>
  <label>Comfy Base URL</label><input name="comfy_base_url" value="{_attr(comfy_base_url)}">
  <label>Resolution</label><input name="output_resolution" value="{_attr(output_resolution)}">
  <label>FPS</label><input name="fps" type="number" min="1" value="{_attr(fps)}">
  <label>Lyrics-Zeilen pro Clip</label><input name="lyric_group_size" type="number" min="1" max="8" value="{_attr(lyric_group_size)}">
  <label>Refrain-Zeilen pro Clip</label><input name="chorus_group_size" type="number" min="1" max="8" value="{_attr(chorus_group_size)}">
  <label>Transition Handle hinten (Sek.)</label><input name="transition_handle_seconds" type="number" min="0" step="0.1" value="{_attr(transition_handle_seconds)}">
  <label>Whisper Model</label>{_whisper_model_select_html(whisper_model_size)}
  <p>
    <button>Save Project Settings</button>
    <button type="submit" form="realign-lyrics-form-{project['id']}" onclick="return confirm('Lyrics neu alignen und Segmente neu erstellen? Generierte Dateien, Segmente, Timings, Prompts, OK-Status und Button-Status werden zurueckgesetzt.')">Realign Lyrics</button>
    <button type="submit" form="realign-lyrics-cpu-form-{project['id']}" onclick="return confirm('Lyrics per CPU neu alignen und Segmente neu erstellen? Generierte Dateien, Segmente, Timings, Prompts, OK-Status und Button-Status werden zurueckgesetzt.')">Realign Lyrics (CPU)</button>
  </p>
</form>
"""


def _scene_plan_editor_html(project, show_heading: bool = True) -> str:
    scene_plan = _row_value(project, "scene_plan", "") or ""
    heading_html = "<h2>Scene Plan</h2>" if show_heading else ""
    return f"""
<form action="/projects/{project['id']}/scene-plan/save" method="post">
  {heading_html}
  <textarea name="scene_plan">{_text(scene_plan)}</textarea>
  <p><button>Save Scene Plan</button></p>
</form>
"""


def _work_items_html(project, lines, segments, locked=None, show_generation_columns: bool = False) -> str:
    locked = locked or {}
    if segments:
        return _segments_html(project, lines, segments, locked, show_generation_columns=show_generation_columns)
    return _lyrics_html(project, lines, locked, show_generation_columns=show_generation_columns)


def _project_status_payload(
    project,
    lines,
    segments,
    active_jobs,
    average_durations: dict[str, float] | None = None,
    used_actions: set[str] | None = None,
    queue_jobs=None,
) -> dict[str, object]:
    average_durations = average_durations or {}
    used_actions = used_actions or set()
    counted_jobs = active_jobs if queue_jobs is None else queue_jobs
    item_kind = "segments" if segments else "lines"
    rows = segments or lines
    locked = _locked_indices(active_jobs, item_kind, rows)
    html = _work_items_html(project, lines, segments, locked, show_generation_columns="scene-plan" in used_actions)
    return {
        "locked": {
            "segments": sorted(locked) if item_kind == "segments" else [],
            "lines": sorted(locked) if item_kind == "lines" else [],
        },
        "queue_estimate_seconds": _queue_estimate_seconds(counted_jobs, average_durations),
        "queue_count": len(counted_jobs),
        "rows": _extract_row_snippets(html),
        "storyboard_html": _storyboard_html(project, rows, item_kind),
    }


def _extract_row_snippets(html: str) -> dict[str, str]:
    return {
        match.group(1): match.group(0)
        for match in re.finditer(r'<tr id="([^"]+)"[\s\S]*?</tr>', html)
    }


def _lyrics_html(project, lines, locked=None, show_generation_columns: bool = False) -> str:
    locked = locked or {}
    rows = ""
    for line in lines:
        confidence = _display_confidence(line)
        confidence_value = "" if confidence is None else f"{round(float(confidence) * 100)}%"
        row_class = _row_class(line["section"], bool(line["is_chorus"]), confidence, bool(_row_value(line, "video_approved", 0)))
        generation_cells = ""
        if show_generation_columns:
            image_choice_html = _image_choice_html(project["id"], "lines", line["line_index"], line)
            image_html = _assets_stack_html(
                _image_preview_html(project, line["image_path"]),
                _image_preview_html(project, _row_value(line, "avatar_image_path", "")),
                image_choice_html,
            )
            clip_html = _clip_play_html(project, line["clip_path"])
            approval_html = _approval_html(project["id"], "lines", line["line_index"], line)
            video_prompt = _row_value(line, "video_prompt", "")
            prompt_editor = _prompt_editor_html(
                f"/projects/{project['id']}/lines/{line['line_index']}/prompts",
                line["prompt"] or "",
                video_prompt or "",
            )
            redo_html = _redo_html(project["id"], "lines", line["line_index"], _row_value(line, "last_action", ""))
            generation_cells = f"""
  <td colspan="2">{prompt_editor}</td>
  <td class="assets-column">{image_html}</td>
  <td>{clip_html}</td>
  <td>{redo_html}</td>
  <td>{approval_html}</td>"""
        status_html = _status_html(line["status"], line["error"] or "")
        insert_html = _insert_line_html(project["id"], line["line_index"], line["section"])
        delete_html = _delete_line_html(project["id"], line["line_index"])
        timing = _timing_text(line["start_sec"], line["end_sec"])
        start_value = _time_value(line["start_sec"])
        end_value = _time_value(line["end_sec"])
        approved = "1" if bool(_row_value(line, "video_approved", 0)) else "0"
        locked_status = locked.get(int(line["line_index"]))
        tr_class = _merge_row_class(row_class, "locked-row" if locked_status else "")
        lock_overlay = f'<div class="row-lock-overlay">{_text(locked_status)}</div>' if locked_status else ""
        rows += f"""
<tr id="line-row-{line['line_index']}"{tr_class} data-work-item="1" data-video-approved="{approved}" data-locked="{'1' if locked_status else '0'}" onclick="toggleRowSelection(event, this)">
  <td class="select-cell"><input type="checkbox" class="line-select" name="selected_lines" value="{line['line_index']}"></td>
  <td>{_text(line['clean_text'])}</td>
  <td class="timing-column">
    <form class="compact-form timing-form" action="/projects/{project['id']}/lines/{line['line_index']}/timing" method="post">
      <input name="start_sec" value="{start_value}" placeholder="von">
      <input name="end_sec" value="{end_value}" placeholder="bis">
      <button>Save</button>
    </form>
    <div>{timing}</div>
  </td>
  <td class="confidence">{confidence_value}</td>
{generation_cells}
  <td>{status_html}</td>
  <td><form action="/projects/{project['id']}/lines/{line['line_index']}/retry" method="post"><button>Retry</button></form></td>
  <td>{insert_html}</td>
  <td>{delete_html}</td>
  <td>{lock_overlay}</td>
</tr>"""
    generation_headers = '<th colspan="2">Prompts</th><th>Images</th><th>Clip</th><th>Redo</th><th>OK</th>' if show_generation_columns else ""
    return f"""
<div class="panel"><h2>Lyrics / Timing</h2></div>
<table>
  <thead><tr><th>Select</th><th>Lyrics</th><th class="timing-column">Timing</th><th>Confidence</th>{generation_headers}<th>Status</th><th></th><th>Insert</th><th>Loeschen</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
{_section_legend_html()}
"""


def _segments_html(project, lines, segments, locked=None, show_generation_columns: bool = False) -> str:
    locked = locked or {}
    confidence_by_line = _line_confidence_by_index(lines)
    rows = ""
    for segment in segments:
        generation_cells = ""
        audio_html = _audio_play_html(segment["audio_path"])
        row_class = _row_class(
            segment["section"] if segment["kind"] != "gap" else segment["kind"],
            bool(segment["is_chorus"]),
            None,
            bool(_row_value(segment, "video_approved", 0)),
        )
        timing = _timing_text(segment["start_sec"], segment["end_sec"])
        confidence_html = _segment_confidence_html(segment, confidence_by_line)
        alignment_cells = ""
        if not show_generation_columns:
            timing_editor = _segment_timing_editor_html(project["id"], segment)
            section_editor = _segment_section_editor_html(project["id"], segment)
            alignment_cells = f"""
  <td>{section_editor}</td>
  <td class="timing-column">{timing_editor}<div>{timing}</div>{confidence_html}</td>
  <td>{audio_html}</td>"""
        text_html = _multiline_text_html(segment["clean_text"])
        if show_generation_columns:
            image_choice_html = _image_choice_html(project["id"], "segments", segment["segment_index"], segment)
            image_html = _assets_stack_html(
                _image_preview_html(project, segment["image_path"]),
                _image_preview_html(project, _row_value(segment, "avatar_image_path", "")),
                image_choice_html,
            )
            clip_html = _clip_play_html(project, segment["clip_path"])
            approval_html = _approval_html(project["id"], "segments", segment["segment_index"], segment)
            video_prompt = _row_value(segment, "video_prompt", "")
            prompt_editor = _prompt_editor_html(
                f"/projects/{project['id']}/segments/{segment['segment_index']}/prompts",
                segment["prompt"] or "",
                video_prompt or "",
            )
            redo_html = _redo_html(project["id"], "segments", segment["segment_index"], _row_value(segment, "last_action", ""))
            generation_cells = f"""
  <td colspan="2">{prompt_editor}</td>
  <td class="assets-column">{image_html}</td>
  <td>{clip_html}</td>
  <td>{redo_html}</td>
  <td>{approval_html}</td>"""
        status_html = _status_html(segment["status"], segment["error"] or "")
        approved = "1" if bool(_row_value(segment, "video_approved", 0)) else "0"
        locked_status = locked.get(int(segment["segment_index"]))
        tr_class = _merge_row_class(row_class, "locked-row" if locked_status else "")
        lock_overlay = f'<div class="row-lock-overlay">{_text(locked_status)}</div>' if locked_status else ""
        rows += f"""
<tr id="segment-row-{segment['segment_index']}"{tr_class} data-work-item="1" data-video-approved="{approved}" data-locked="{'1' if locked_status else '0'}" onclick="toggleRowSelection(event, this)">
  <td class="select-cell"><input type="checkbox" class="segment-select" name="selected_lines" value="{segment['segment_index']}"></td>
  <td>{segment['segment_index']}</td>
  <td>{text_html}</td>
{alignment_cells}
{generation_cells}
  <td>{status_html}</td>
  <td>{lock_overlay}</td>
</tr>"""
    alignment_headers = '<th>Typ</th><th class="timing-column">Timing</th><th>Audio</th>' if not show_generation_columns else ""
    generation_headers = '<th colspan="2">Prompts</th><th>Images</th><th>Clip</th><th>Redo</th><th>OK</th>' if show_generation_columns else ""
    return f"""
<div class="panel"><h2>Render Segments</h2></div>
<table>
  <thead><tr><th>Select</th><th>#</th><th>Text</th>{alignment_headers}{generation_headers}<th>Status</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
{_section_legend_html()}
"""


def _action_button(project_id: int, number: int, action: str, label: str, is_wip: bool, is_used: bool, enabled: bool = True) -> str:
    title = ""
    css_class = ""
    if is_used:
        css_class = "used-button"
        title = "Already used; click to run again"
    elif is_wip:
        css_class = "wip-button"
        title = "WIP: not fully clean yet"
    attrs = ""
    if css_class:
        attrs += f' class="{css_class}"'
    if not enabled:
        attrs += ' type="button" title="Alle Videos erst mit OK markieren" onclick="alert(\'Bitte erst alle Videos mit OK freigeben.\')"'
    elif title:
        attrs += f' title="{title}"'
    return f"""<form action="/projects/{project_id}/{action}" method="post" onsubmit="return projectActionSubmitted(this)"><button{attrs}>{number}. {label}</button></form>"""


def _open_filter_html(rows) -> str:
    total = len(rows)
    open_count = sum(1 for row in rows if not bool(_row_value(row, "video_approved", 0)))
    return f"""<span class="open-count-label">{open_count}/{total} offen</span>"""


def _queue_estimate_html(seconds: float | None) -> str:
    value = max(0.0, float(seconds or 0.0))
    label = "Queue frei" if value <= 0 else f"Queue ca. {_format_duration(value)}"
    return f'<span id="queue-estimate" class="queue-estimate" data-seconds="{int(round(value))}">{_text(label)}</span>'


def _scroll_top_button_html() -> str:
    return '<button class="scroll-top-button" type="button" onclick="scrollToTop()" title="Nach oben">Top</button>'


def _job_average_seconds(job, average_durations: dict[str, float]) -> float | None:
    action = job.action or _action_from_job_name(job.name)
    if not action:
        return None
    return average_durations.get(action)


def _action_from_job_name(name: str) -> str:
    label = str(name).split(":", 1)[0].strip()
    return {
        "generate prompts": "prompts",
        "generate video prompts": "video-prompts",
        "generate images": "images",
        "generate avatar image": "avatar-image",
        "generate clips": "clips",
        "align": "align",
        "build segments": "segments",
        "generate scene plan": "scene-plan",
        "assemble": "assemble",
    }.get(label, "")


def _duration_html(seconds: float | None) -> str:
    if seconds is None:
        return ""
    return _text(_format_duration(seconds))


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return ""
    total = max(0, int(round(float(seconds))))
    minutes, remaining = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {remaining}s"
    return f"{remaining}s"


def _queue_estimate_seconds(active_jobs, average_durations: dict[str, float]) -> float:
    total = 0.0
    now = datetime.now()
    for job in active_jobs:
        average = average_durations.get(job.action)
        if average is None:
            continue
        remaining = float(average)
        if job.status == "running" and job.started_at:
            try:
                elapsed = (now - datetime.fromisoformat(job.started_at)).total_seconds()
            except ValueError:
                elapsed = 0.0
            remaining = max(0.0, remaining - elapsed)
        total += remaining
    return total


def _job_delete_html(job) -> str:
    if job.status == "running":
        return ""
    return f"""
<form class="compact-form" action="/jobs/{job.id}/delete" method="post">
  <button>Delete</button>
</form>
"""


def _redo_html(project_id: int, item_kind: str, item_index: int, last_action: str | None) -> str:
    if not last_action:
        return ""
    action = _text(last_action)
    return f"""
<form class="compact-form redo-cell" action="/projects/{project_id}/{item_kind}/{item_index}/redo" method="post">
  <button class="icon-button" type="submit" title="Redo again">&#8635;</button>
  <div class="redo-action">{action}</div>
</form>
"""


def _insert_line_html(project_id: int, line_index: int, section: str) -> str:
    return f"""
<form class="compact-form insert-line-form" action="/projects/{project_id}/lines/{line_index}/insert-after" method="post">
  <input name="text" placeholder="Neue Zeile darunter" required>
  <input name="section" value="{_attr(section)}" placeholder="Section">
  <button>+</button>
</form>
"""


def _delete_line_html(project_id: int, line_index: int) -> str:
    return f"""
<form class="compact-form" action="/projects/{project_id}/lines/{line_index}/delete" method="post" onsubmit="return confirm('Lyrics-Zeile wirklich loeschen? Segmente und generierte Inhalte ab dieser Zeile werden zurueckgesetzt.')">
  <button class="danger-button">Loeschen</button>
</form>
"""


def _clear_project_html(project) -> str:
    return f"""
<details class="danger-panel">
  <summary>Danger Zone</summary>
  <div class="actions">
    <form class="compact-form" action="/projects/{project['id']}/clear" method="post" onsubmit="return confirm('Projekt wirklich leeren? Generierte Dateien, Segmente, Timings, Prompts und Button-Status werden zurueckgesetzt. Uploads und Settings bleiben erhalten.')">
      <button class="danger-button">Clear Project</button>
    </form>
    <form class="compact-form" action="/projects/{project['id']}/delete" method="post" onsubmit="return confirm('Projekt wirklich loeschen? Datenbankeintrag, Upload-Ordner und generierte Dateien werden entfernt.')">
      <button class="danger-button">Delete Project</button>
    </form>
  </div>
</details>
"""


def _image_preview_html(project, image_path: str | None) -> str:
    if not image_path:
        return ""
    url = _generated_asset_url(project, image_path)
    return (
        f'<button class="preview-button" type="button" onclick="openImageLightbox({_js_arg(url)})">'
        f'<img class="preview-image" src="{url}" alt="Generated image"></button>'
    )


def _assets_stack_html(*items: str) -> str:
    visible_items = [item for item in items if item]
    if not visible_items:
        return ""
    preview_items = [item for item in visible_items if 'class="preview-button"' in item]
    other_items = [item for item in visible_items if 'class="preview-button"' not in item]
    previews_html = '<div class="asset-previews">' + "".join(preview_items) + "</div>" if preview_items else ""
    return '<div class="assets-stack">' + previews_html + "".join(other_items) + "</div>"


def _image_choice_html(project_id: int, item_kind: str, item_index: int, row) -> str:
    image_path = _row_value(row, "image_path", "")
    avatar_image_path = _row_value(row, "avatar_image_path", "")
    if not image_path or not avatar_image_path:
        return ""
    selected = _row_value(row, "selected_image_source", "avatar")
    image_checked = " checked" if selected == "image" else ""
    avatar_checked = " checked" if selected != "image" else ""
    return f"""
<form class="compact-form image-choice" action="/projects/{project_id}/{item_kind}/{item_index}/image-source" method="post">
  <label><input type="radio" name="selected_image_source" value="image"{image_checked} onchange="rememberScrollPosition(); this.form.submit()"> Image</label>
  <label><input type="radio" name="selected_image_source" value="avatar"{avatar_checked} onchange="rememberScrollPosition(); this.form.submit()"> Avatar</label>
</form>
"""


def _approval_html(project_id: int, item_kind: str, item_index: int, row) -> str:
    checked = " checked" if bool(_row_value(row, "video_approved", 0)) else ""
    return f"""
<form class="compact-form" action="/projects/{project_id}/{item_kind}/{item_index}/approval" method="post">
  <input type="hidden" name="video_approved" value="0">
  <label class="approval-label"><input type="checkbox" name="video_approved" value="1"{checked} onchange="rememberScrollPosition(); this.form.submit()"> OK</label>
</form>
"""


def _prompt_editor_html(action: str, prompt: str, video_prompt: str) -> str:
    return f"""
<form class="compact-form" action="{action}/image/save" method="post">
  <label>Image</label><textarea class="prompt-textarea" name="prompt">{_text(prompt)}</textarea>
  <p class="prompt-actions"><button>Save</button><button type="submit" formaction="{action}/image/ai-fill">AI fill</button></p>
</form>
<form class="compact-form" action="{action}/video/save" method="post">
  <label>Video</label><textarea class="prompt-textarea" name="video_prompt">{_text(video_prompt)}</textarea>
  <p class="prompt-actions"><button>Save</button><button type="submit" formaction="{action}/video/ai-fill">AI fill</button></p>
</form>
"""


def _segment_section_editor_html(project_id: int, segment) -> str:
    section_type = _section_type(segment["section"], bool(segment["is_chorus"]))
    if section_type not in {"verse", "bridge", "refrain"}:
        section_type = "verse"
    verse_selected = " selected" if section_type == "verse" else ""
    bridge_selected = " selected" if section_type == "bridge" else ""
    refrain_selected = " selected" if section_type == "refrain" else ""
    return f"""
<form class="compact-form section-form" action="/projects/{project_id}/segments/{segment['segment_index']}/section" method="post">
  <select name="section_type" onchange="rememberScrollPosition(); this.form.submit()">
    <option value="verse"{verse_selected}>Verse</option>
    <option value="bridge"{bridge_selected}>Bridge</option>
    <option value="refrain"{refrain_selected}>Refrain</option>
  </select>
</form>
"""


def _whisper_model_select_html(selected: str) -> str:
    selected = normalize_whisper_model_size(selected)
    options = []
    for model_size in WHISPER_MODEL_SIZES:
        selected_attr = " selected" if model_size == selected else ""
        options.append(f'<option value="{_attr(model_size)}"{selected_attr}>{_text(model_size)}</option>')
    return f'<select name="whisper_model_size">{"".join(options)}</select>'


def _segment_timing_editor_html(project_id: int, segment) -> str:
    start_value = _time_value(segment["start_sec"])
    end_value = _time_value(segment["end_sec"])
    return f"""
<form class="compact-form timing-form" action="/projects/{project_id}/segments/{segment['segment_index']}/timing" method="post">
  <input name="start_sec" value="{start_value}" placeholder="von">
  <input name="end_sec" value="{end_value}" placeholder="bis">
  <button>Save</button>
</form>
"""


def _line_confidence_by_index(lines) -> dict[int, float]:
    values: dict[int, float] = {}
    for line in lines:
        confidence = _display_confidence(line)
        if confidence is None:
            continue
        try:
            values[int(line["line_index"])] = float(confidence)
        except (KeyError, TypeError, ValueError):
            continue
    return values


def _display_confidence(row):
    if _is_sparse_fallback_row(row):
        return None
    return _row_value(row, "confidence", None)


def _is_sparse_fallback_row(row) -> bool:
    return str(_row_value(row, "error", "") or "").startswith("Sparse Whisper alignment;")


def _segment_confidence_html(segment, confidence_by_line: dict[int, float]) -> str:
    values = [
        confidence_by_line[index]
        for index in _source_line_indices(segment)
        if index in confidence_by_line
    ]
    if not values:
        return ""
    confidence = min(values)
    return f'<div class="timing-confidence">Confidence {round(confidence * 100)}%</div>'


def _source_line_indices(segment) -> list[int]:
    value = _row_value(segment, "source_line_indices", [])
    if isinstance(value, str):
        try:
            value = json.loads(value or "[]")
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        return []
    indices: list[int] = []
    for item in value:
        try:
            indices.append(int(item))
        except (TypeError, ValueError):
            continue
    return indices


def _status_html(status: str, error: str) -> str:
    error_html = f'<div class="status-error">{_text(error)}</div>' if error else ""
    return f'<div class="status">{_text(status)}</div>{error_html}'


def _all_videos_approved(rows) -> bool:
    return bool(rows) and all(bool(_row_value(row, "video_approved", 0)) for row in rows)


def _audio_play_html(audio_path: str | None) -> str:
    if not audio_path:
        return ""
    url = _local_asset_url(audio_path)
    return (
        f'<button class="icon-button" type="button" title="Play audio" data-audio-src="{url}" onclick="toggleAudio(this)">▶</button>'
        f'<audio class="inline-player" preload="none" src="{url}"></audio>'
    )


def _clip_play_html(project, clip_path: str | None) -> str:
    if not clip_path:
        return ""
    url = _generated_asset_url(project, clip_path)
    return f'<button class="icon-button" type="button" title="Play clip" onclick="openClipLightbox(\'{url}\')">▶</button>'


def _clip_lightbox_html() -> str:
    return """
<div id="clip-lightbox" class="lightbox" onclick="if (event.target === this) closeClipLightbox()">
  <div class="lightbox-content">
    <button class="lightbox-close" type="button" onclick="closeClipLightbox()">Close</button>
    <video id="clip-lightbox-video" controls></video>
  </div>
</div>
"""


def _image_lightbox_html() -> str:
    return """
<div id="image-lightbox" class="lightbox" onclick="if (event.target === this) closeImageLightbox()">
  <div class="lightbox-content">
    <button class="lightbox-close" type="button" onclick="closeImageLightbox()">Close</button>
    <img id="image-lightbox-image" alt="Generated image">
  </div>
</div>
"""


def _row_class(section: str, is_chorus: bool, confidence, approved: bool = False) -> str:
    classes = [_section_class(section, is_chorus)]
    if approved:
        classes.append("approved-row")
    if confidence is not None and float(confidence) < 0.45:
        classes.append("low-confidence")
    return f' class="{" ".join(classes)}"'


def _section_class(section: str, is_chorus: bool) -> str:
    section_type = _section_type(section, is_chorus)
    if section_type == "refrain":
        return "section-chorus"
    if section_type == "bridge":
        return "section-bridge"
    if section_type == "verse":
        return "section-verse"
    return "section-gap"


def _section_type(section: str, is_chorus: bool) -> str:
    value = str(section or "").lower()
    if is_chorus or "chorus" in value or "refrain" in value:
        return "refrain"
    if "bridge" in value:
        return "bridge"
    if "verse" in value:
        return "verse"
    if "instrumental" in value or "break" in value or "gap" in value or value == "":
        return "gap"
    return "gap"


def _section_legend_html() -> str:
    return """
<div class="section-legend">
  <span><span class="legend-swatch section-gap"></span>Other</span>
  <span><span class="legend-swatch section-verse"></span>Verse</span>
  <span><span class="legend-swatch section-bridge"></span>Bridge</span>
  <span><span class="legend-swatch section-chorus"></span>Refrain</span>
</div>
"""


def _multiline_text_html(value: str) -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return '<div class="lyrics-lines">' + "".join(f"<div>{_text(line)}</div>" for line in lines) + "</div>"


def _timing_text(start, end) -> str:
    if start is None or end is None:
        return ""
    return f"{float(start):.1f} - {float(end):.1f}"


def _time_value(value) -> str:
    if value is None:
        return ""
    return f"{float(value):.1f}"


def _comfy_output_url(comfy_base_url: str, output_path: str) -> str:
    path = Path(output_path.replace("\\", "/"))
    filename = path.name
    subfolder = path.parent.as_posix()
    url = f"{comfy_base_url.rstrip('/')}/view?filename={quote(filename)}"
    if subfolder and subfolder != ".":
        url += f"&amp;subfolder={quote(subfolder, safe='')}"
    return f"{url}&amp;type=output"


def _generated_asset_url(project, path: str) -> str:
    if _is_local_project_asset(path):
        return _local_asset_url(path)
    return _comfy_output_url(_row_value(project, "comfy_base_url", "http://127.0.0.1:8188"), path)


def _is_local_project_asset(path: str) -> bool:
    if is_internal_storage_path(path):
        return True
    try:
        Path(path).resolve().relative_to(APP_ROOT.resolve())
        return True
    except (OSError, ValueError):
        return False


def _local_asset_url(path: str) -> str:
    candidate = resolve_storage_path(APP_ROOT, path)
    normalized = storage_relative_path(APP_ROOT, path)
    url = "/assets/" + quote(normalized.lstrip("/"), safe="/")
    version = _local_asset_version(candidate, normalized)
    return f"{url}?v={version}" if version else url


def _local_asset_version(candidate: Path, normalized: str) -> str:
    candidates = [candidate]
    normalized_path = normalized.lstrip("/").replace("/", "\\")
    if normalized_path:
        candidates.append(APP_ROOT / normalized_path)
    for item in candidates:
        try:
            stat = item.stat()
        except OSError:
            continue
        return f"{stat.st_mtime_ns}-{stat.st_size}"
    return ""


def _row_value(row, key: str, default):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _reference_paths_from_text(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _reference_paths_from_json(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return _reference_paths_from_text(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _attr(value) -> str:
    return escape(str(value), quote=True)


def _js_arg(value) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _js_string_arg(value) -> str:
    return json.dumps(str(value))


def _text(value) -> str:
    return escape(str(value), quote=False)


app = create_app()

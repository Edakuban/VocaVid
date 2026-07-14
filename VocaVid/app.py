from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from fastapi import FastAPI, File, Form, UploadFile
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as exc:  # pragma: no cover
    raise SystemExit("FastAPI is required. Install with: pip install -r requirements.txt") from exc

from .lyrics import parse_suno_lyrics
from .alignment import normalize_whisper_model_size
from .paths import slug_folder_name, storage_relative_path
from .pipeline import Pipeline
from .reels import ReelsPipeline
from .reels.storage import ensure_reels_dirs, project_finished_video_path, project_finished_video_path_candidates
from .store import Store
from .worker import JobQueue

APP_ROOT = Path.cwd() / ".VocaVid"
UPLOADS = APP_ROOT / "uploads"
DB_PATH = APP_ROOT / "VocaVid.sqlite3"
ICON_ROOT = Path.cwd() / "icon"
logger = logging.getLogger(__name__)
_SPLIT_ACTIONS = {"prompts", "video-prompts", "images", "avatar-image", "clips"}


def _project_redirect(project_id: int) -> RedirectResponse:
    return RedirectResponse(f"/projects/{int(project_id)}", status_code=303)


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
    interrupted_items = store.mark_interrupted_running_items()
    if interrupted_items:
        logger.warning("marked %s interrupted running project items as failed", interrupted_items)
    pipeline = Pipeline(store, APP_ROOT / "outputs")
    reels_pipeline = ReelsPipeline(store, APP_ROOT)
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
    app.state.reels_pipeline = reels_pipeline
    app.state.job_options = job_options
    app.state.shutdown_controller = shutdown_controller
    app.mount("/assets", StaticFiles(directory=str(APP_ROOT)), name="assets")
    app.mount("/icon", StaticFiles(directory=str(ICON_ROOT)), name="icon")

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
            "render-mp4": ("render MP4", lambda: pipeline.render_final_mp4(project_id)),
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

    def submit_prompt_actions(project_id: int, selected_indices: list[int] | None = None) -> bool:
        selected = list(selected_indices or [])
        item_kind = _action_item_kind("prompts", bool(store.list_segments(project_id)))
        indices = _selected_action_indices(project_id, item_kind, selected, store)
        if not indices:
            return False
        submitted = False
        for index in indices:
            submitted_prompts = submit_project_action(project_id, "prompts", [index])
            submitted_video_prompts = submit_project_action(project_id, "video-prompts", [index])
            submitted = submitted or submitted_prompts or submitted_video_prompts
        return submitted

    def submit_global_style_prompt(project_id: int) -> None:
        project = store.get_project(project_id)
        shutdown_controller.cancel_pending()
        jobs.submit(
            f"generate global style prompt: {project['name']}",
            lambda: pipeline.generate_global_style_prompt(project_id),
            project_id=project_id,
            action="global-style-prompt",
        )

    def submit_initial_project_jobs(project_id: int, *, describe_avatar: bool = False) -> None:
        if describe_avatar:
            project = store.get_project(project_id)
            jobs.submit(
                _job_name("describe avatar", project["name"], []),
                lambda: pipeline.describe_avatar_face(project_id),
                project_id=project_id,
                action="avatar-description",
            )
        submit_global_style_prompt(project_id)
        if submit_project_action(project_id, "align"):
            mark_used(project_id, "align")
        if submit_project_action(project_id, "segments"):
            mark_used(project_id, "segments")
        if submit_project_action(project_id, "scene-plan"):
            mark_used(project_id, "scene-plan")

    @app.get("/", response_class=HTMLResponse)
    def index():
        active_jobs = jobs.active_jobs()
        average_durations = store.average_job_durations()
        projects = store.list_projects()
        project_previews = {int(project["id"]): store.list_segments(int(project["id"])) for project in projects}
        return _page(
            "Projects",
            _projects_html(
                projects,
                jobs.list_jobs(),
                average_durations,
                queue_estimate_seconds=_queue_estimate_seconds(active_jobs, average_durations),
                job_options=job_options,
                project_previews=project_previews,
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
        genre: str = Form(...),
        avatar_gender: str = Form(""),
        avatar_face_description: str = Form(""),
        global_style_prompt: str = Form(""),
        comfy_base_url: str = Form("http://127.0.0.1:8188"),
        output_resolution: str = Form("1280x720"),
        fps: int = Form(24),
        lyric_group_size: int = Form(2),
        chorus_group_size: int = Form(1),
        transition_handle_seconds: float = Form(0.5),
        whisper_model_size: str = Form("large-v3"),
        audio: UploadFile = File(...),
        lyrics: UploadFile = File(...),
        avatar: UploadFile | None = File(None),
        references: list[UploadFile] = File(default=[]),
    ):
        project_dir = UPLOADS / _slug(name)
        project_dir.mkdir(parents=True, exist_ok=True)
        audio_path = await _save_upload(audio, project_dir)
        lyrics_path = await _save_upload(lyrics, project_dir)
        reference_paths = []
        if avatar is not None and avatar.filename:
            reference_paths.append(_storage_path(await _save_upload(avatar, project_dir / "references")))
        for item in references:
            if item.filename:
                reference_paths.append(_storage_path(await _save_upload(item, project_dir / "references")))
        lines = parse_suno_lyrics(lyrics_path.read_text(encoding="utf-8"))
        project_id = store.create_project(
            {
                "name": name,
                "audio_path": _storage_path(audio_path),
                "lyrics_path": _storage_path(lyrics_path),
                "global_style_prompt": global_style_prompt,
                "genre": genre.strip(),
                "avatar_gender": _normalize_avatar_gender(avatar_gender),
                "avatar_face_description": avatar_face_description.strip(),
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
        submit_initial_project_jobs(project_id, describe_avatar=not avatar_face_description.strip())
        return _project_redirect(project_id)

    @app.get("/projects/{project_id}", response_class=HTMLResponse)
    def project_detail(project_id: int):
        project = store.get_project(project_id)
        projects = store.list_projects()
        previous_project_id, next_project_id = _project_navigation_ids(projects, project_id)
        lines = store.list_lines(project_id)
        segments = store.list_segments(project_id)
        used_actions = store.list_used_project_actions(project_id)
        reel_analyses = store.list_reel_analyses(project_id)
        reel_candidates_by_analysis = {
            int(analysis["id"]): store.list_reel_candidates(int(analysis["id"]))
            for analysis in reel_analyses
        }
        active_jobs = jobs.active_project_jobs(project_id)
        queue_jobs = jobs.active_jobs()
        listed_jobs = jobs.list_jobs()
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
                queue_count=len(queue_jobs),
                queue_jobs=listed_jobs,
                average_durations=averages,
                job_options=job_options,
                previous_project_id=previous_project_id,
                next_project_id=next_project_id,
                reel_analyses=reel_analyses,
                reel_candidates_by_analysis=reel_candidates_by_analysis,
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

    @app.get("/projects/{project_id}/reels/status")
    def reels_status(project_id: int):
        project = store.get_project(project_id)
        analyses = store.list_reel_analyses(project_id)
        candidates_by_analysis = {
            int(analysis["id"]): store.list_reel_candidates(int(analysis["id"]))
            for analysis in analyses
        }
        return {
            "reels_html": _reels_status_html(project, analyses, candidates_by_analysis),
        }

    @app.post("/projects/{project_id}/reels/analyze")
    async def analyze_reels(
        project_id: int,
        source_video_path: str = Form(""),
        source_video: UploadFile | None = File(None),
    ):
        project = store.get_project(project_id)
        _ = source_video_path
        video_path = ""
        if source_video is not None and source_video.filename:
            source_dir = ensure_reels_dirs(APP_ROOT, project)["root"] / "source"
            video_path = storage_relative_path(APP_ROOT, await _save_upload(source_video, source_dir))
        else:
            default_video_path = next((path for path in project_finished_video_path_candidates(APP_ROOT, project) if path.exists()), None)
            video_path = storage_relative_path(APP_ROOT, default_video_path) if default_video_path else ""
        if not video_path:
            analysis_id = store.create_reel_analysis(project_id, "")
            expected = storage_relative_path(APP_ROOT, project_finished_video_path(APP_ROOT, project))
            store.update_reel_analysis(analysis_id, status="failed", error=f"Add {expected} to the project output folder or upload a source video")
            return _project_redirect(project_id)
        analysis_id = store.create_reel_analysis(project_id, video_path)
        shutdown_controller.cancel_pending()
        jobs.submit(
            f"analyze reels: {project['name']}",
            lambda: reels_pipeline.analyze(project_id, video_path),
            project_id=project_id,
            action="reels-analyze",
            item_kind="reels",
            selected_indices=[analysis_id],
        )
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/reels/{analysis_id}/candidates/{candidate_id}/preview")
    def preview_reel(project_id: int, analysis_id: int, candidate_id: int):
        project = store.get_project(project_id)
        jobs.submit(
            f"preview reel: {project['name']} (candidate {candidate_id})",
            lambda: reels_pipeline.render_preview(project_id, analysis_id, candidate_id),
            project_id=project_id,
            action="reels-preview",
            item_kind="reels",
            selected_indices=[candidate_id],
        )
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/reels/{analysis_id}/candidates/{candidate_id}/export")
    def export_reel(project_id: int, analysis_id: int, candidate_id: int):
        project = store.get_project(project_id)
        jobs.submit(
            f"export reel: {project['name']} (candidate {candidate_id})",
            lambda: reels_pipeline.export(project_id, analysis_id, candidate_id),
            project_id=project_id,
            action="reels-export",
            item_kind="reels",
            selected_indices=[candidate_id],
        )
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/reels/{analysis_id}/candidates/{candidate_id}/clear")
    def clear_reel_candidate(project_id: int, analysis_id: int, candidate_id: int):
        reels_pipeline.clear_candidate_outputs(project_id, analysis_id, candidate_id)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/reels/{analysis_id}/candidates/{candidate_id}/delete")
    def delete_reel_candidate(project_id: int, analysis_id: int, candidate_id: int):
        reels_pipeline.delete_candidate(project_id, analysis_id, candidate_id)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/align")
    def align(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "align", selected_lines):
            mark_used(project_id, "align")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/global-style-prompt")
    def generate_global_style_prompt(project_id: int):
        submit_global_style_prompt(project_id)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/avatar-description")
    def describe_avatar(project_id: int):
        project = store.get_project(project_id)
        jobs.submit(
            _job_name("describe avatar", project["name"], []),
            lambda: pipeline.describe_avatar_face(project_id),
            project_id=project_id,
            action="avatar-description",
        )
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/timing")
    def update_timing(project_id: int, line_index: int, start_sec: float = Form(...), end_sec: float = Form(...)):
        pipeline.update_timing(project_id, line_index, start_sec, end_sec)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/insert-after")
    def insert_line_after(project_id: int, line_index: int, text: str = Form(...), section: str = Form("")):
        pipeline.insert_line_after(project_id, line_index, text, section)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/delete")
    def delete_line(project_id: int, line_index: int):
        pipeline.delete_line(project_id, line_index)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/timing")
    def update_segment_timing(project_id: int, segment_index: int, start_sec: float = Form(...), end_sec: float = Form(...)):
        pipeline.update_segment_timing(project_id, segment_index, start_sec, end_sec)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/section")
    def update_segment_section(project_id: int, segment_index: int, section_type: str = Form("verse")):
        pipeline.update_segment_section(project_id, segment_index, section_type)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/settings")
    def update_settings(
        project_id: int,
        name: str = Form(...),
        audio_path: str = Form(...),
        lyrics_path: str = Form(...),
        global_style_prompt: str = Form(...),
        genre: str = Form(""),
        avatar_gender: str = Form(""),
        avatar_face_description: str = Form(""),
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
            avatar_gender=_normalize_avatar_gender(avatar_gender),
            avatar_face_description=avatar_face_description.strip(),
            reference_image_paths=json.dumps([_storage_path(item) for item in _reference_paths_from_text(reference_image_paths)]),
            comfy_base_url=comfy_base_url.strip() or "http://127.0.0.1:8188",
            output_resolution=output_resolution.strip() or "1280x720",
            fps=max(1, int(fps)),
            lyric_group_size=new_lyric_group_size,
            chorus_group_size=new_chorus_group_size,
            transition_handle_seconds=max(0.0, float(transition_handle_seconds)),
            whisper_model_size=normalize_whisper_model_size(whisper_model_size),
        )
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/realign-lyrics")
    def realign_lyrics(project_id: int):
        logger.info("manual realign start project_id=%s", project_id)
        regroup_now(project_id, "manual realign")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/realign-lyrics-cpu")
    def realign_lyrics_cpu(project_id: int):
        logger.info("manual realign cpu start project_id=%s", project_id)
        regroup_now(project_id, "manual realign cpu", force_cpu=True)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/manual-timing")
    def save_manual_timing(
        project_id: int,
        line_indices: list[int] = Form(...),
        clean_texts: list[str] = Form(...),
        sections: list[str] = Form(...),
        start_secs: list[str] = Form(...),
        end_secs: list[str] = Form(...),
        manual_segment_starts: list[int] = Form(default=[]),
    ):
        starts = {int(index) for index in manual_segment_starts}
        row_count = len(line_indices)
        if not all(len(values) == row_count for values in (clean_texts, sections, start_secs, end_secs)):
            raise ValueError("Manual timing form fields must have matching row counts")
        rows = [
            {
                "line_index": line_indices[index],
                "clean_text": clean_texts[index],
                "section": sections[index],
                "start_sec": start_secs[index],
                "end_sec": end_secs[index],
                "manual_segment_start": int(line_indices[index]) in starts,
            }
            for index in range(row_count)
        ]
        pipeline.save_manual_timing(project_id, rows)
        mark_used(project_id, "align")
        mark_used(project_id, "segments")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments")
    def segments(project_id: int):
        if submit_project_action(project_id, "segments"):
            mark_used(project_id, "segments")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/scene-plan")
    def scene_plan(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "scene-plan", selected_lines):
            mark_used(project_id, "scene-plan")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/scene-plan/save")
    def save_scene_plan(project_id: int, scene_plan: str = Form("")):
        pipeline.save_scene_plan(project_id, scene_plan)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/prompts")
    def prompts(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "prompts", selected_lines):
            mark_used(project_id, "prompts")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/generate-prompts")
    def generate_prompts(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_prompt_actions(project_id, selected_lines):
            mark_used(project_id, "prompts")
            mark_used(project_id, "video-prompts")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/images")
    def images(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "images", selected_lines):
            mark_used(project_id, "images")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/avatar-image")
    def avatar_image(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "avatar-image", selected_lines):
            mark_used(project_id, "avatar-image")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/video-prompts")
    def video_prompts(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "video-prompts", selected_lines):
            mark_used(project_id, "video-prompts")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/clips")
    def clips(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "clips", selected_lines):
            mark_used(project_id, "clips")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/assemble")
    def assemble(project_id: int, selected_lines: list[int] = Form(default=[])):
        if submit_project_action(project_id, "assemble", selected_lines):
            mark_used(project_id, "assemble")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/render-mp4")
    def render_mp4(project_id: int):
        if submit_project_action(project_id, "render-mp4", []):
            mark_used(project_id, "render-mp4")
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/clear")
    def clear_project(project_id: int):
        pipeline.clear_project(project_id)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/delete")
    def delete_project(project_id: int):
        pipeline.delete_project(project_id)
        return RedirectResponse("/", status_code=303)

    @app.post("/projects/{project_id}/lines/{line_index}/retry")
    def retry(project_id: int, line_index: int):
        pipeline.retry_line(project_id, line_index)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/redo")
    def redo_line(project_id: int, line_index: int):
        row = next(item for item in store.list_lines(project_id) if item["line_index"] == line_index)
        action = row["last_action"]
        if action and submit_project_action(project_id, action, [line_index]):
            mark_used(project_id, action)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/redo")
    def redo_segment(project_id: int, segment_index: int):
        row = next(item for item in store.list_segments(project_id) if item["segment_index"] == segment_index)
        action = row["last_action"]
        if action and submit_project_action(project_id, action, [segment_index]):
            mark_used(project_id, action)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/save")
    def save_line_prompts(project_id: int, line_index: int, prompt: str = Form(""), video_prompt: str = Form("")):
        pipeline.save_line_prompts(project_id, line_index, prompt, video_prompt)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/image/save")
    def save_line_image_prompt(project_id: int, line_index: int, prompt: str = Form("")):
        pipeline.save_line_prompt(project_id, line_index, prompt)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/prompts/video/save")
    def save_line_video_prompt(project_id: int, line_index: int, video_prompt: str = Form("")):
        pipeline.save_line_video_prompt(project_id, line_index, video_prompt)
        return _project_redirect(project_id)

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
        return _project_redirect(project_id)

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
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/save")
    def save_segment_prompts(project_id: int, segment_index: int, prompt: str = Form(""), video_prompt: str = Form("")):
        pipeline.save_segment_prompts(project_id, segment_index, prompt, video_prompt)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/image/save")
    def save_segment_image_prompt(project_id: int, segment_index: int, prompt: str = Form("")):
        pipeline.save_segment_prompt(project_id, segment_index, prompt)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/prompts/video/save")
    def save_segment_video_prompt(project_id: int, segment_index: int, video_prompt: str = Form("")):
        pipeline.save_segment_video_prompt(project_id, segment_index, video_prompt)
        return _project_redirect(project_id)

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
        return _project_redirect(project_id)

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
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/image-source")
    def select_line_image_source(project_id: int, line_index: int, selected_image_source: str = Form("avatar")):
        pipeline.select_line_image_source(project_id, line_index, selected_image_source)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/image-source")
    def select_segment_image_source(project_id: int, segment_index: int, selected_image_source: str = Form("avatar")):
        pipeline.select_segment_image_source(project_id, segment_index, selected_image_source)
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/lines/{line_index}/approval")
    def approve_line_video(project_id: int, line_index: int, video_approved: int = Form(0)):
        pipeline.set_line_video_approved(project_id, line_index, bool(video_approved))
        return _project_redirect(project_id)

    @app.post("/projects/{project_id}/segments/{segment_index}/approval")
    def approve_segment_video(project_id: int, segment_index: int, video_approved: int = Form(0)):
        pipeline.set_segment_video_approved(project_id, segment_index, bool(video_approved))
        return _project_redirect(project_id)

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

from .ui import assets as _ui_assets
from .ui import rendering as _ui_rendering


# Compatibility bridge for older tests and callers that import private UI
# helpers from VocaVid.app. New UI code should import from
# VocaVid.ui.* modules directly.
def _sync_ui_rendering_roots() -> None:
    _ui_rendering.set_app_root(APP_ROOT)


def _wrap_ui_rendering_function(name: str):
    def _wrapped(*args, **kwargs):
        _sync_ui_rendering_roots()
        return getattr(_ui_rendering, name)(*args, **kwargs)

    _wrapped.__name__ = name
    _wrapped.__doc__ = getattr(getattr(_ui_rendering, name), "__doc__", None)
    return _wrapped


def _page(title: str, body: str, queue_count: int = 0) -> str:
    return _ui_assets._page(title, body, queue_count)


def _browser_title(title: str, queue_count: int = 0) -> str:
    return _ui_assets._browser_title(title, queue_count)


for _ui_name in _ui_rendering.__all__:
    globals()[_ui_name] = _wrap_ui_rendering_function(_ui_name)

del _ui_name

app = create_app()

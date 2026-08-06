from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from itertools import count
from threading import Lock
from time import perf_counter
from typing import Callable


class RetryableJobError(RuntimeError):
    """A failed job that is safe to place at the end of the queue once."""


@dataclass
class Job:
    id: int
    name: str
    status: str
    created_at: str
    error: str = ""
    project_id: int | None = None
    action: str = ""
    item_kind: str = ""
    text_model_profile: str = ""
    generation_profile: str = ""
    video_seconds: float = 0.0
    selected_indices: list[int] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    retry_count: int = 0
    callback: Callable[[], object] | None = None


class JobQueue:
    def __init__(self, max_workers: int = 1, on_finish: Callable[[Job], object] | None = None):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._ids = count(1)
        self._lock = Lock()
        self._jobs: dict[int, Job] = {}
        self._started_perf: dict[int, float] = {}
        self._on_finish = on_finish

    def submit(
        self,
        name: str,
        func: Callable[[], object],
        project_id: int | None = None,
        action: str = "",
        item_kind: str = "",
        text_model_profile: str = "",
        generation_profile: str = "",
        video_seconds: float = 0.0,
        selected_indices: list[int] | None = None,
        retry_count: int = 0,
    ) -> int:
        job_id = next(self._ids)
        with self._lock:
            self._jobs[job_id] = Job(
                id=job_id,
                name=name,
                status="queued",
                created_at=datetime.now().isoformat(timespec="seconds"),
                project_id=project_id,
                action=action,
                item_kind=item_kind,
                text_model_profile=text_model_profile,
                generation_profile=generation_profile,
                video_seconds=max(0.0, float(video_seconds)),
                selected_indices=list(selected_indices or []),
                retry_count=retry_count,
                callback=func,
            )
        future = self.executor.submit(self._run, job_id, func)
        future.add_done_callback(lambda item: self._finish(job_id, item))
        return job_id

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.id, reverse=True)

    def active_project_jobs(self, project_id: int) -> list[Job]:
        with self._lock:
            return sorted(
                [
                    job
                    for job in self._jobs.values()
                    if job.project_id == project_id and job.status in {"queued", "running"}
                ],
                key=lambda job: job.id,
                reverse=True,
            )

    def active_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(
                [job for job in self._jobs.values() if job.status in {"queued", "running"}],
                key=lambda job: job.id,
                reverse=True,
            )

    def delete_job(self, job_id: int) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status == "running":
                return False
            del self._jobs[job_id]
            return True

    def delete_queued_jobs(self) -> int:
        with self._lock:
            job_ids = [job.id for job in self._jobs.values() if job.status == "queued"]
            for job_id in job_ids:
                del self._jobs[job_id]
            return len(job_ids)

    def delete_finished_jobs(self) -> int:
        with self._lock:
            job_ids = [job.id for job in self._jobs.values() if job.status in {"done", "failed"}]
            for job_id in job_ids:
                del self._jobs[job_id]
            return len(job_ids)

    def _run(self, job_id: int, func: Callable[[], object]) -> object:
        with self._lock:
            if job_id not in self._jobs:
                return None
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = datetime.now().isoformat(timespec="seconds")
            self._started_perf[job_id] = perf_counter()
        return func()

    def _finish(self, job_id: int, future: Future) -> None:
        finished_job = None
        retry_args = None
        with self._lock:
            if job_id not in self._jobs:
                return
            job = self._jobs[job_id]
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            started_perf = self._started_perf.pop(job_id, None)
            if started_perf is not None:
                job.duration_seconds = max(0.0, perf_counter() - started_perf)
            if future.exception() is None:
                job.status = "done"
                job.error = ""
            else:
                job.status = "failed"
                job.error = str(future.exception())
            finished_job = Job(
                id=job.id,
                name=job.name,
                status=job.status,
                created_at=job.created_at,
                error=job.error,
                project_id=job.project_id,
                action=job.action,
                item_kind=job.item_kind,
                text_model_profile=job.text_model_profile,
                generation_profile=job.generation_profile,
                video_seconds=job.video_seconds,
                selected_indices=list(job.selected_indices or []),
                started_at=job.started_at,
                finished_at=job.finished_at,
                duration_seconds=job.duration_seconds,
                retry_count=job.retry_count,
            )
            retry = isinstance(future.exception(), RetryableJobError) and job.retry_count < 1 and job.callback is not None
            if retry:
                retry_args = {
                    "name": f"{job.name} (retry {job.retry_count + 1}/1)",
                    "func": job.callback,
                    "project_id": job.project_id,
                    "action": job.action,
                    "item_kind": job.item_kind,
                    "text_model_profile": job.text_model_profile,
                    "generation_profile": job.generation_profile,
                    "video_seconds": job.video_seconds,
                    "selected_indices": job.selected_indices,
                    "retry_count": job.retry_count + 1,
                }
        if retry_args is not None:
            self.submit(**retry_args)
        if self._on_finish is not None and finished_job is not None:
            self._on_finish(finished_job)

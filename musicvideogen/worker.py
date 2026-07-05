from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from itertools import count
from threading import Lock
from typing import Callable


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
    selected_indices: list[int] | None = None


class JobQueue:
    def __init__(self, max_workers: int = 1):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._ids = count(1)
        self._lock = Lock()
        self._jobs: dict[int, Job] = {}

    def submit(
        self,
        name: str,
        func: Callable[[], object],
        project_id: int | None = None,
        action: str = "",
        item_kind: str = "",
        selected_indices: list[int] | None = None,
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
                selected_indices=list(selected_indices or []),
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

    def _run(self, job_id: int, func: Callable[[], object]) -> object:
        with self._lock:
            if job_id not in self._jobs:
                return None
            self._jobs[job_id].status = "running"
        return func()

    def _finish(self, job_id: int, future: Future) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            job = self._jobs[job_id]
            if future.exception() is None:
                job.status = "done"
                job.error = ""
            else:
                job.status = "failed"
                job.error = str(future.exception())

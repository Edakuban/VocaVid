import unittest
from datetime import datetime

from musicvideogen.worker import JobQueue


class WorkerTests(unittest.TestCase):
    def test_job_queue_marks_successful_jobs_done(self):
        queue = JobQueue(max_workers=1)

        job_id = queue.submit("example", lambda: "ok")
        queue.executor.shutdown(wait=True)

        jobs = queue.list_jobs()
        self.assertEqual(jobs[0].id, job_id)
        self.assertEqual(jobs[0].status, "done")
        self.assertEqual(jobs[0].error, "")

    def test_job_queue_records_failed_job_error(self):
        def fail():
            raise RuntimeError("boom")

        queue = JobQueue(max_workers=1)

        queue.submit("example", fail)
        queue.executor.shutdown(wait=True)

        jobs = queue.list_jobs()
        self.assertEqual(jobs[0].status, "failed")
        self.assertIn("boom", jobs[0].error)

    def test_delete_job_removes_non_running_jobs_only(self):
        queue = JobQueue(max_workers=1)
        queued_id = queue.submit("queued", lambda: "ok")

        self.assertTrue(queue.delete_job(queued_id))
        self.assertEqual(queue.list_jobs(), [])
        queue.executor.shutdown(wait=True)

    def test_delete_queued_jobs_keeps_running_done_and_failed_jobs(self):
        gate = queue_gate()
        queue = JobQueue(max_workers=1)
        running_id = queue.submit("running", gate.wait)
        queued_id = queue.submit("queued", lambda: "ok")
        gate.started.wait(timeout=2)

        deleted = queue.delete_queued_jobs()

        self.assertEqual(deleted, 1)
        self.assertEqual([job.id for job in queue.list_jobs()], [running_id])
        gate.release()
        queue.executor.shutdown(wait=True)

    def test_delete_finished_jobs_keeps_queued_and_running_jobs(self):
        gate = queue_gate()
        queue = JobQueue(max_workers=1)
        done_id = queue.submit("done", lambda: "ok")
        failed_id = queue.submit("failed", failing_job)
        running_id = queue.submit("running", gate.wait)
        queued_id = queue.submit("queued", lambda: "ok")
        gate.started.wait(timeout=2)

        deleted = queue.delete_finished_jobs()

        self.assertEqual(deleted, 2)
        self.assertEqual([job.id for job in queue.list_jobs()], [queued_id, running_id])
        gate.release()
        queue.executor.shutdown(wait=True)

    def test_jobs_store_project_item_metadata_and_list_active_project_jobs(self):
        gate = queue_gate()
        queue = JobQueue(max_workers=1)
        running_id = queue.submit(
            "generate images",
            gate.wait,
            project_id=7,
            action="images",
            item_kind="segments",
            selected_indices=[0, 2],
        )
        queued_id = queue.submit(
            "generate clips",
            lambda: "ok",
            project_id=7,
            action="clips",
            item_kind="segments",
            selected_indices=[],
        )
        queue.submit("other project", lambda: "ok", project_id=8, action="images", item_kind="segments", selected_indices=[1])
        gate.started.wait(timeout=2)

        active = queue.active_project_jobs(7)

        self.assertEqual([job.id for job in active], [queued_id, running_id])
        self.assertEqual(active[0].item_kind, "segments")
        self.assertEqual(active[0].selected_indices, [])
        self.assertEqual(active[1].selected_indices, [0, 2])
        gate.release()
        queue.executor.shutdown(wait=True)

    def test_job_queue_records_runtime_and_notifies_on_finish(self):
        finished = []
        queue = JobQueue(max_workers=1, on_finish=finished.append)

        queue.submit("example", lambda: "ok", project_id=7, action="images", item_kind="segments", selected_indices=[2])
        queue.executor.shutdown(wait=True)

        jobs = queue.list_jobs()
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0].id, jobs[0].id)
        self.assertEqual(finished[0].duration_seconds, jobs[0].duration_seconds)
        self.assertIsNotNone(jobs[0].started_at)
        self.assertIsNotNone(jobs[0].finished_at)
        self.assertGreaterEqual(jobs[0].duration_seconds, 0.0)
        datetime.fromisoformat(jobs[0].started_at)
        datetime.fromisoformat(jobs[0].finished_at)


class queue_gate:
    def __init__(self):
        from threading import Event

        self.started = Event()
        self.released = Event()

    def wait(self):
        self.started.set()
        self.released.wait(timeout=2)

    def release(self):
        self.released.set()


def failing_job():
    raise RuntimeError("boom")

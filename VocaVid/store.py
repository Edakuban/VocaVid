from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import LyricLine, LineTiming, RenderSegment


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    lyrics_path TEXT NOT NULL,
    global_style_prompt TEXT NOT NULL,
    genre TEXT NOT NULL DEFAULT '',
    reference_image_paths TEXT NOT NULL DEFAULT '[]',
    avatar_gender TEXT NOT NULL DEFAULT '',
    avatar_face_description TEXT NOT NULL DEFAULT '',
    comfy_base_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:8188',
    output_resolution TEXT NOT NULL DEFAULT '1280x720',
    fps INTEGER NOT NULL DEFAULT 24,
    lyric_group_size INTEGER NOT NULL DEFAULT 2,
    chorus_group_size INTEGER NOT NULL DEFAULT 1,
    transition_handle_seconds REAL NOT NULL DEFAULT 0.5,
    whisper_model_size TEXT NOT NULL DEFAULT 'small',
    final_video_path TEXT,
    scene_plan TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lyric_lines (
    project_id INTEGER NOT NULL,
    line_index INTEGER NOT NULL,
    section TEXT NOT NULL,
    is_chorus INTEGER NOT NULL,
    use_reference INTEGER NOT NULL DEFAULT 0,
    raw_text TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    start_sec REAL,
    end_sec REAL,
    confidence REAL,
    manual_segment_start INTEGER NOT NULL DEFAULT 0,
    prompt TEXT,
    video_prompt TEXT,
    image_path TEXT,
    avatar_image_path TEXT,
    selected_image_source TEXT NOT NULL DEFAULT 'avatar',
    clip_path TEXT,
    video_approved INTEGER NOT NULL DEFAULT 0,
    last_action TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(project_id, line_index)
);

CREATE TABLE IF NOT EXISTS render_segments (
    project_id INTEGER NOT NULL,
    segment_index INTEGER NOT NULL,
    kind TEXT NOT NULL,
    section TEXT NOT NULL,
    is_chorus INTEGER NOT NULL,
    use_reference INTEGER NOT NULL DEFAULT 0,
    source_line_indices TEXT NOT NULL DEFAULT '[]',
    clean_text TEXT NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    prompt TEXT,
    video_prompt TEXT,
    image_path TEXT,
    avatar_image_path TEXT,
    selected_image_source TEXT NOT NULL DEFAULT 'avatar',
    clip_path TEXT,
    video_approved INTEGER NOT NULL DEFAULT 0,
    audio_path TEXT,
    scene_plan TEXT,
    last_action TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(project_id, segment_index)
);

CREATE TABLE IF NOT EXISTS manual_timing_interludes (
    project_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    after_line_index INTEGER NOT NULL,
    clean_text TEXT NOT NULL DEFAULT '[Instrumental]',
    section TEXT NOT NULL DEFAULT 'Instrumental',
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    PRIMARY KEY(project_id, position)
);

CREATE TABLE IF NOT EXISTS project_actions (
    project_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(project_id, action)
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    item_kind TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 1,
    duration_seconds REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reel_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    source_video_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    transcript_json TEXT NOT NULL DEFAULT '{}',
    lyric_alignment_json TEXT NOT NULL DEFAULT '[]',
    audio_features_json TEXT NOT NULL DEFAULT '[]',
    scene_json TEXT NOT NULL DEFAULT '[]',
    detections_json TEXT NOT NULL DEFAULT '[]',
    focus_tracks_json TEXT NOT NULL DEFAULT '[]',
    manual_keyframes_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reel_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    preview_path TEXT,
    export_path TEXT,
    crop_json TEXT NOT NULL DEFAULT '{}',
    selected INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT ''
);
"""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(lyric_lines)")}
        if "use_reference" not in columns:
            conn.execute("ALTER TABLE lyric_lines ADD COLUMN use_reference INTEGER NOT NULL DEFAULT 0")
        if "video_prompt" not in columns:
            conn.execute("ALTER TABLE lyric_lines ADD COLUMN video_prompt TEXT")
        if "avatar_image_path" not in columns:
            conn.execute("ALTER TABLE lyric_lines ADD COLUMN avatar_image_path TEXT")
        if "selected_image_source" not in columns:
            conn.execute("ALTER TABLE lyric_lines ADD COLUMN selected_image_source TEXT NOT NULL DEFAULT 'avatar'")
        if "video_approved" not in columns:
            conn.execute("ALTER TABLE lyric_lines ADD COLUMN video_approved INTEGER NOT NULL DEFAULT 0")
        if "last_action" not in columns:
            conn.execute("ALTER TABLE lyric_lines ADD COLUMN last_action TEXT")
        if "manual_segment_start" not in columns:
            conn.execute("ALTER TABLE lyric_lines ADD COLUMN manual_segment_start INTEGER NOT NULL DEFAULT 0")
        project_columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)")}
        if "genre" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN genre TEXT NOT NULL DEFAULT ''")
        if "lyric_group_size" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN lyric_group_size INTEGER NOT NULL DEFAULT 2")
        if "chorus_group_size" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN chorus_group_size INTEGER NOT NULL DEFAULT 1")
        if "transition_handle_seconds" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN transition_handle_seconds REAL NOT NULL DEFAULT 0.5")
        if "whisper_model_size" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN whisper_model_size TEXT NOT NULL DEFAULT 'small'")
        if "scene_plan" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN scene_plan TEXT")
        if "avatar_gender" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN avatar_gender TEXT NOT NULL DEFAULT ''")
        if "avatar_face_description" not in project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN avatar_face_description TEXT NOT NULL DEFAULT ''")
        segment_columns = {row["name"] for row in conn.execute("PRAGMA table_info(render_segments)")}
        if "scene_plan" not in segment_columns:
            conn.execute("ALTER TABLE render_segments ADD COLUMN scene_plan TEXT")
        if "video_prompt" not in segment_columns:
            conn.execute("ALTER TABLE render_segments ADD COLUMN video_prompt TEXT")
        if "avatar_image_path" not in segment_columns:
            conn.execute("ALTER TABLE render_segments ADD COLUMN avatar_image_path TEXT")
        if "selected_image_source" not in segment_columns:
            conn.execute("ALTER TABLE render_segments ADD COLUMN selected_image_source TEXT NOT NULL DEFAULT 'avatar'")
        if "video_approved" not in segment_columns:
            conn.execute("ALTER TABLE render_segments ADD COLUMN video_approved INTEGER NOT NULL DEFAULT 0")
        if "last_action" not in segment_columns:
            conn.execute("ALTER TABLE render_segments ADD COLUMN last_action TEXT")

    def create_project(self, data: dict[str, Any], lines: list[LyricLine]) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (
                    name, audio_path, lyrics_path, global_style_prompt, genre, reference_image_paths,
                    avatar_gender, avatar_face_description,
                    comfy_base_url, output_resolution, fps, lyric_group_size, chorus_group_size,
                    transition_handle_seconds, whisper_model_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["name"],
                    data["audio_path"],
                    data["lyrics_path"],
                    data["global_style_prompt"],
                    data.get("genre", ""),
                    json.dumps(data.get("reference_image_paths", [])),
                    data.get("avatar_gender", ""),
                    data.get("avatar_face_description", ""),
                    data.get("comfy_base_url", "http://127.0.0.1:8188"),
                    data.get("output_resolution", "1280x720"),
                    int(data.get("fps", 24)),
                    int(data.get("lyric_group_size", 2)),
                    int(data.get("chorus_group_size", 1)),
                    max(0.0, float(data.get("transition_handle_seconds", 0.5))),
                    data.get("whisper_model_size", "small"),
                ),
            )
            project_id = int(cursor.lastrowid)
            self.replace_lines(project_id, lines, conn=conn)
            return project_id

    def replace_lines(self, project_id: int, lines: list[LyricLine], conn: sqlite3.Connection | None = None) -> None:
        close = conn is None
        conn = conn or self._connect()
        try:
            conn.execute("DELETE FROM lyric_lines WHERE project_id = ?", (project_id,))
            conn.executemany(
                """
                INSERT INTO lyric_lines (
                    project_id, line_index, section, is_chorus, use_reference, raw_text, clean_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        project_id,
                        line.index,
                        line.section,
                        int(line.is_chorus),
                        int(line.use_reference),
                        line.raw_text,
                        line.clean_text,
                    )
                    for line in lines
                ],
            )
            conn.commit()
        finally:
            if close:
                conn.close()

    def list_projects(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute("SELECT * FROM projects ORDER BY id DESC"))

    def get_project(self, project_id: int) -> sqlite3.Row:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row is None:
                raise KeyError(f"Project {project_id} not found")
            return row

    def list_lines(self, project_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute("SELECT * FROM lyric_lines WHERE project_id = ? ORDER BY line_index", (project_id,)))

    def insert_line_after(
        self,
        project_id: int,
        after_line_index: int,
        section: str,
        raw_text: str,
        clean_text: str,
        is_chorus: bool,
        use_reference: bool,
    ) -> None:
        insert_index = int(after_line_index) + 1
        with self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM lyric_lines WHERE project_id = ? AND line_index = ?",
                (project_id, after_line_index),
            ).fetchone() is None:
                raise KeyError(f"Line {after_line_index} not found")
            conn.execute(
                "UPDATE lyric_lines SET line_index = line_index + 100000 WHERE project_id = ? AND line_index >= ?",
                (project_id, insert_index),
            )
            conn.execute(
                "UPDATE lyric_lines SET line_index = line_index - 99999 WHERE project_id = ? AND line_index >= 100000",
                (project_id,),
            )
            conn.execute(
                """
                INSERT INTO lyric_lines (
                    project_id, line_index, section, is_chorus, use_reference, raw_text, clean_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, insert_index, section, int(is_chorus), int(use_reference), raw_text, clean_text),
            )
            self._clear_structure_dependent_state(conn, project_id, from_line_index=insert_index)

    def delete_line(self, project_id: int, line_index: int) -> None:
        line_index = int(line_index)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM lyric_lines WHERE project_id = ? AND line_index = ?",
                (project_id, line_index),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Line {line_index} not found")
            conn.execute(
                "UPDATE lyric_lines SET line_index = line_index - 100000 WHERE project_id = ? AND line_index > ?",
                (project_id, line_index),
            )
            conn.execute(
                "UPDATE lyric_lines SET line_index = line_index + 99999 WHERE project_id = ? AND line_index < 0",
                (project_id,),
            )
            self._clear_structure_dependent_state(conn, project_id, from_line_index=line_index)

    def replace_segments(self, project_id: int, segments: list[RenderSegment]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM render_segments WHERE project_id = ?", (project_id,))
            conn.executemany(
                """
                INSERT INTO render_segments (
                    project_id, segment_index, kind, section, is_chorus, use_reference,
                    source_line_indices, clean_text, start_sec, end_sec, prompt, video_prompt,
                    image_path, avatar_image_path, clip_path, audio_path, scene_plan, status, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        project_id,
                        segment.index,
                        segment.kind,
                        segment.section,
                        int(segment.is_chorus),
                        int(segment.use_reference),
                        json.dumps(segment.source_line_indices),
                        segment.clean_text,
                        segment.start_sec,
                        segment.end_sec,
                        segment.prompt,
                        segment.video_prompt,
                        segment.image_path,
                        segment.avatar_image_path,
                        segment.clip_path,
                        segment.audio_path,
                        segment.scene_plan,
                        segment.status,
                        segment.error,
                    )
                    for segment in segments
                ],
            )

    def list_manual_timing_interludes(self, project_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM manual_timing_interludes WHERE project_id = ? ORDER BY position",
                    (project_id,),
                )
            )

    def replace_manual_timing_interludes(self, project_id: int, interludes: list[dict[str, object]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM manual_timing_interludes WHERE project_id = ?", (project_id,))
            conn.executemany(
                """
                INSERT INTO manual_timing_interludes (
                    project_id, position, after_line_index, clean_text, section, start_sec, end_sec
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        project_id,
                        position,
                        int(interlude["after_line_index"]),
                        str(interlude["clean_text"]),
                        str(interlude["section"]),
                        float(interlude["start_sec"]),
                        float(interlude["end_sec"]),
                    )
                    for position, interlude in enumerate(interludes)
                ],
            )

    def list_segments(self, project_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute("SELECT * FROM render_segments WHERE project_id = ? ORDER BY segment_index", (project_id,)))

    def update_segment(self, project_id: int, segment_index: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [project_id, segment_index]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE render_segments SET {assignments} WHERE project_id = ? AND segment_index = ?",
                values,
            )

    def mark_interrupted_running_items(self, error: str = "Job interrupted by app restart or queue reset") -> int:
        with self._connect() as conn:
            line_result = conn.execute(
                """
                UPDATE lyric_lines
                SET status = 'failed', error = ?
                WHERE status = 'running'
                """,
                (error,),
            )
            segment_result = conn.execute(
                """
                UPDATE render_segments
                SET status = 'failed', error = ?
                WHERE status = 'running'
                """,
                (error,),
            )
            return int(line_result.rowcount or 0) + int(segment_result.rowcount or 0)

    def update_project(self, project_id: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [project_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE projects SET {assignments} WHERE id = ?", values)

    def mark_project_action_used(self, project_id: int, action: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO project_actions (project_id, action, used_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(project_id, action) DO UPDATE SET used_at = CURRENT_TIMESTAMP
                """,
                (project_id, action),
            )

    def list_used_project_actions(self, project_id: int) -> set[str]:
        with self._connect() as conn:
            return {
                str(row["action"])
                for row in conn.execute("SELECT action FROM project_actions WHERE project_id = ?", (project_id,))
            }

    def record_job_run(self, action: str, item_kind: str, item_count: int, duration_seconds: float, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO job_runs (action, item_kind, item_count, duration_seconds, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action, item_kind, max(1, int(item_count)), max(0.0, float(duration_seconds)), status),
            )

    def average_job_durations(self) -> dict[str, float]:
        with self._connect() as conn:
            return {
                str(row["action"]): float(row["average_duration"])
                for row in conn.execute(
                    """
                    SELECT action, AVG(duration_seconds / item_count) AS average_duration
                    FROM job_runs
                    WHERE status = 'done' AND item_count > 0
                    GROUP BY action
                    ORDER BY action
                    """
                )
            }

    def delete_project(self, project_id: int) -> None:
        with self._connect() as conn:
            analysis_ids = [row["id"] for row in conn.execute("SELECT id FROM reel_analyses WHERE project_id = ?", (project_id,))]
            if analysis_ids:
                placeholders = ",".join("?" for _ in analysis_ids)
                conn.execute(f"DELETE FROM reel_candidates WHERE analysis_id IN ({placeholders})", analysis_ids)
            conn.execute("DELETE FROM reel_analyses WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM render_segments WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM lyric_lines WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM project_actions WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def clear_project_generated_state(self, project_id: int, preserve_line_timings: bool = False) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM render_segments WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM project_actions WHERE project_id = ?", (project_id,))
            timing_reset = "" if preserve_line_timings else "start_sec = NULL, end_sec = NULL, confidence = NULL,"
            conn.execute(
                f"""
                UPDATE lyric_lines
                SET {timing_reset}
                    prompt = NULL,
                    video_prompt = NULL,
                    image_path = NULL,
                    avatar_image_path = NULL,
                    clip_path = NULL,
                    video_approved = 0,
                    last_action = NULL,
                    status = 'pending',
                    error = ''
                WHERE project_id = ?
                """,
                (project_id,),
            )
            conn.execute("UPDATE projects SET final_video_path = NULL, scene_plan = NULL WHERE id = ?", (project_id,))

    def _clear_structure_dependent_state(self, conn: sqlite3.Connection, project_id: int, from_line_index: int) -> None:
        conn.execute("DELETE FROM render_segments WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_actions WHERE project_id = ?", (project_id,))
        conn.execute(
            """
            UPDATE lyric_lines
            SET start_sec = NULL,
                end_sec = NULL,
                confidence = NULL,
                prompt = NULL,
                video_prompt = NULL,
                image_path = NULL,
                avatar_image_path = NULL,
                clip_path = NULL,
                video_approved = 0,
                last_action = NULL,
                status = 'pending',
                error = ''
            WHERE project_id = ? AND line_index >= ?
            """,
            (project_id, from_line_index),
        )
        conn.execute("UPDATE projects SET final_video_path = NULL, scene_plan = NULL WHERE id = ?", (project_id,))

    def set_timings(self, project_id: int, timings: list[LineTiming]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                UPDATE lyric_lines
                SET start_sec = ?, end_sec = ?, confidence = ?
                WHERE project_id = ? AND line_index = ?
                """,
                [(t.start_sec, t.end_sec, t.confidence, project_id, t.line_index) for t in timings],
            )

    def update_line(self, project_id: int, line_index: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [project_id, line_index]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE lyric_lines SET {assignments} WHERE project_id = ? AND line_index = ?",
                values,
            )

    def set_final_video(self, project_id: int, path: Path) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE projects SET final_video_path = ? WHERE id = ?", (str(path), project_id))

    def create_reel_analysis(self, project_id: int, source_video_path: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reel_analyses (project_id, source_video_path)
                VALUES (?, ?)
                """,
                (project_id, source_video_path),
            )
            return int(cursor.lastrowid)

    def get_reel_analysis(self, analysis_id: int) -> sqlite3.Row:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reel_analyses WHERE id = ?", (analysis_id,)).fetchone()
            if row is None:
                raise KeyError(f"Reel analysis {analysis_id} not found")
            return row

    def latest_reel_analysis(self, project_id: int) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM reel_analyses WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                (project_id,),
            ).fetchone()

    def list_reel_analyses(self, project_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute("SELECT * FROM reel_analyses WHERE project_id = ? ORDER BY id DESC", (project_id,)))

    def update_reel_analysis(self, analysis_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields = dict(fields)
        fields["updated_at"] = _current_timestamp()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [analysis_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE reel_analyses SET {assignments} WHERE id = ?", values)

    def replace_reel_candidates(self, analysis_id: int, candidates) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reel_candidates WHERE analysis_id = ?", (analysis_id,))
            conn.executemany(
                """
                INSERT INTO reel_candidates (
                    analysis_id, label, start_sec, end_sec, score, reasons_json, crop_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        analysis_id,
                        candidate.label,
                        candidate.start_sec,
                        candidate.end_sec,
                        candidate.score,
                        json.dumps(candidate.reasons),
                        json.dumps(candidate.crop),
                    )
                    for candidate in candidates
                ],
            )

    def list_reel_candidates(self, analysis_id: int) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute("SELECT * FROM reel_candidates WHERE analysis_id = ? ORDER BY score DESC, id", (analysis_id,)))

    def get_reel_candidate(self, candidate_id: int) -> sqlite3.Row:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reel_candidates WHERE id = ?", (candidate_id,)).fetchone()
            if row is None:
                raise KeyError(f"Reel candidate {candidate_id} not found")
            return row

    def update_reel_candidate(self, candidate_id: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [candidate_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE reel_candidates SET {assignments} WHERE id = ?", values)

    def delete_reel_candidate(self, candidate_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reel_candidates WHERE id = ?", (candidate_id,))


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

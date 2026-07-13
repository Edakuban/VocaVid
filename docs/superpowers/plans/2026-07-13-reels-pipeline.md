# Reels Pipeline Implementation Plan

> Source context: GitHub issue #7 asks for a new reels/shorts module. The attached `reels_pipeline_spec.md` is still useful as the product and technical direction, but it predates the completed UI redesign and the later UI module split.

## Current Repo Fit

The current app is no longer a mostly single-file UI in `VocaVid/app.py`.

- `VocaVid/app.py` owns FastAPI routes, queue wiring, and pipeline submission.
- `VocaVid/ui/projects.py` owns the start dashboard and project detail shell.
- `VocaVid/ui/storyboard.py` owns storyboard cards and the segment inspector.
- `VocaVid/ui/forms.py`, `VocaVid/ui/queue.py`, and `VocaVid/ui/styles.py` own shared controls, queue UI, modals, lightboxes, and CSS.
- `VocaVid/store.py` persists projects, lyric lines, render segments, project actions, and historical job durations.
- `VocaVid/pipeline.py` owns long-running generation/assembly work and already uses FFmpeg, Whisper alignment, project-relative storage paths, and status updates.

Therefore the Reels feature should be implemented as a new project-level workflow that plugs into the redesigned project page, rather than as direct additions to the old table flow.

## What Remains Valid From The Spec

- Reels are generated from the current project plus an explicitly selected finished MP4.
- Lyrics come from the current project data; the user should not upload lyrics again.
- Output lives under the project folder in `reels/`.
- Cache analysis data so expensive steps do not rerun unnecessarily.
- Generate multiple candidates up to 60 seconds.
- Prefer candidate-first analysis: audio/lyrics -> top candidates -> scene/focus analysis only for selected candidate ranges.
- The whole workflow should remain in a lightbox/modal on the project page.

## What Needs Updating

- The button should be a project action in the current project topbar, near `Assemble Final`, using the existing redesigned action-button style.
- The lightbox should use the existing `.modal.lightbox`, `.studio-panel-head`, `.lightbox-close`, and project UI conventions from `VocaVid/ui/*`.
- The UI should not be built inside `app.py`; add a dedicated `VocaVid/ui/reels.py`.
- The backend should not be a nested `reels_module/` package from the spec. Use a VocaVid-native package/module set, likely `VocaVid/reels/`.
- The Store needs explicit Reels persistence instead of relying only on one loose `analysis.json`.
- Heavy steps should be submitted through the existing `JobQueue`, with action names such as `reels-analyze`, `reels-preview`, and `reels-export`.
- Dependencies need to be staged. The current `requirements.txt` does not include Librosa, PySceneDetect, MediaPipe, OpenCV/PyAV, or NumPy.

## Proposed File Structure

- Add `VocaVid/reels/__init__.py`
- Add `VocaVid/reels/models.py`
- Add `VocaVid/reels/storage.py`
- Add `VocaVid/reels/media.py`
- Add `VocaVid/reels/lyrics.py`
- Add `VocaVid/reels/candidates.py`
- Add `VocaVid/reels/render.py`
- Add `VocaVid/ui/reels.py`
- Modify `VocaVid/app.py`
- Modify `VocaVid/store.py`
- Modify `VocaVid/ui/projects.py`
- Modify `VocaVid/ui/rendering.py`
- Modify `VocaVid/ui/styles.py`
- Add focused tests in `tests/test_reels_*.py`
- Extend existing app HTML and endpoint tests where routes/UI are touched

## Data Model

Add tables rather than storing only unindexed JSON:

```sql
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
```

Still write a readable `reels/analysis.json` snapshot for debugging/export portability, but treat SQLite as the app source of truth.

## MVP Scope

The MVP should be useful before MediaPipe and a full keyframe editor exist.

1. Add `Make reels` button after `Assemble Final`.
2. Open a Reels lightbox on the project page.
3. Select or drag-drop an MP4.
4. Validate video with FFprobe.
5. Create `<project>/reels/`.
6. Extract audio for analysis.
7. Transcribe with the existing faster-whisper path where practical.
8. Parse current project lyrics from stored lines/segments.
9. Align lyric sections to transcript approximately.
10. Generate scored candidates up to 60 seconds.
11. Render simple static-center 9:16 previews.
12. Let the user export selected candidates to 1080x1920 MP4.

MediaPipe focus tracking, manual keyframes, blur background, subtitles, and dynamic crop smoothing should be later phases.

## Task 1: Backend Models And Store Persistence

- Add dataclasses for `ReelAnalysis`, `ReelCandidate`, `ReelVideoMetadata`, and `ReelJobStatus`.
- Add Store migrations for `reel_analyses` and `reel_candidates`.
- Add Store methods:
  - `create_reel_analysis`
  - `get_reel_analysis`
  - `list_reel_analyses`
  - `update_reel_analysis`
  - `replace_reel_candidates`
  - `list_reel_candidates`
  - `update_reel_candidate`
- Add tests for migration and CRUD behavior.

## Task 2: Video Validation And Project Storage

- Add `VocaVid/reels/storage.py` for resolving project `reels/`, `cache/`, `previews/`, and `exports/` folders.
- Add `VocaVid/reels/media.py` with FFprobe metadata validation.
- Validate:
  - path exists
  - suffix/container is MP4 or readable video
  - video stream exists
  - audio stream exists
  - duration > 0
  - width/height/fps can be read
- Store an absolute source path in the analysis record; do not copy source MP4 by default.
- Add tests with mocked subprocess output.

## Task 3: Project Lyrics To Reel Sections

- Add `VocaVid/reels/lyrics.py`.
- Build section records from existing project lines or render segments.
- Preserve section order and repeated occurrences.
- Include start/end hints from existing line/segment timing when available.
- Treat lyrics/project data as ground truth and transcript as timing evidence.
- Add tests for repeated chorus/pre-chorus/bridge parsing.

## Task 4: Candidate Generation

- Add `VocaVid/reels/candidates.py`.
- Implement deterministic MVP scoring:
  - section type score
  - duration fit score
  - boundary cleanliness from existing timings
  - preference for chorus and final chorus
  - simple audio/transcript confidence hook where available
- Generate candidates:
  - chorus
  - pre-chorus + chorus
  - bridge + final chorus
  - strongest verse excerpt if data supports it
  - 15/30/45/60 second variants clipped to phrase boundaries
- Add tests for max duration, repeated chorus handling, and score ordering.

## Task 5: Preview And Export Rendering

- Add `VocaVid/reels/render.py`.
- MVP render mode: static 9:16 center crop from the source video.
- Use FFmpeg for:
  - extracting analysis WAV
  - preview render at 540x960
  - final export at 1080x1920, H.264/AAC/yuv420p
- Add crop math tests for 16:9 and non-16:9 inputs.
- Add command construction tests; avoid requiring real FFmpeg in unit tests.

## Task 6: JobQueue Integration

- Add `Pipeline` methods or a dedicated `ReelsPipeline` collaborator:
  - `analyze_reels(project_id, source_video_path)`
  - `render_reel_preview(project_id, analysis_id, candidate_id)`
  - `export_reel(project_id, analysis_id, candidate_id)`
- Submit these through `JobQueue` from app routes.
- Use job action names:
  - `reels-analyze`
  - `reels-preview`
  - `reels-export`
- Persist status on analyses/candidates and expose progress in the Reels lightbox.
- Add endpoint tests for queue submission and status payloads.

## Task 7: Redesigned Reels UI

- Add `VocaVid/ui/reels.py`.
- Expose helpers through `VocaVid/ui/rendering.py`.
- Add a `Make reels` button in `VocaVid/ui/projects.py` immediately after `Assemble Final`.
- Add a modal/lightbox using existing classes:
  - upload/drop zone
  - metadata summary
  - analysis progress
  - candidate list
  - 9:16 preview player
  - export action/results
- Keep it visually consistent with storyboard/project controls.
- Add HTML tests that assert:
  - project page includes the Reels button
  - the Reels modal is present
  - lyrics are not re-uploaded
  - the MP4 picker accepts video files
  - candidate/export actions point to project-scoped routes

## Task 8: Routes

Add routes in `VocaVid/app.py`:

- `POST /projects/{project_id}/reels/analyze`
- `GET /projects/{project_id}/reels/status`
- `POST /projects/{project_id}/reels/{analysis_id}/candidates/{candidate_id}/preview`
- `POST /projects/{project_id}/reels/{analysis_id}/candidates/{candidate_id}/export`

The status endpoint should return HTML snippets for the modal, similar to the existing project/queue polling pattern.

## Task 9: Later Focus Tracking Phase

After the MVP works:

- Add PySceneDetect for candidate ranges.
- Add MediaPipe face/person detection for candidate ranges.
- Add per-scene focus tracks.
- Add smoothing and manual keyframes.
- Render dynamic crop previews.
- Add mode selection per scene: `static_crop`, `follow_face`, `center_crop`, `blur_background`, `manual`.

## Open Decisions

- Whether `faster-whisper` should reuse the existing alignment code or have a Reels-specific transcript cache.
- Whether to add heavy dependencies directly to `requirements.txt` or split optional reels dependencies into another file.
- Whether source MP4 paths outside the project should be allowed permanently, or whether the app should offer an optional "copy into project" action.
- Whether MVP previews should be generated immediately for all candidates or lazily per selected candidate.

## Definition Of Done For MVP

- The project page shows `Make reels` after `Assemble Final`.
- Reels opens in a lightbox without leaving the redesigned project page.
- The user selects a finished MP4 and the app validates it.
- The app uses current project lyrics automatically.
- Analysis creates candidates and caches results under `reels/`.
- The user can preview 9:16 candidates.
- The user can export one or more 1080x1920 MP4 files.
- Tests cover storage, validation, candidate scoring, crop math, routes, and generated HTML.

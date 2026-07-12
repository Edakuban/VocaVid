# UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved VocaVid studio-dashboard and storyboard-review redesign while preserving all existing render, queue, prompt, rerun, approval, and table workflows.

**Architecture:** Keep the current FastAPI server-rendered HTML architecture. Refactor `VocaVid/app.py` just enough to introduce shared UI helpers, a modern start dashboard, a storyboard-first project view, and a retained advanced table view. Existing endpoints stay intact; view choice is controlled by a query parameter on the project detail route.

**Tech Stack:** Python 3.11+, FastAPI, server-rendered HTML/CSS/JavaScript in `VocaVid/app.py`, SQLite-backed project/job data via `VocaVid/store.py`, `unittest` test suite.

---

## File Structure

- Modify `VocaVid/app.py`
  - Shared CSS in `_page`.
  - Start dashboard helpers.
  - New Project modal helper.
  - Queue summary/admin helpers.
  - Project header/view toggle helpers.
  - Storyboard card and inspector helpers.
  - Existing table helpers remain as advanced view.
  - Existing lightbox helpers remain and are reused.
- Modify `tests/test_app_html.py`
  - Update start-page expectations.
  - Add modal, queue admin, storyboard, inspector, and view-toggle tests.
  - Keep existing endpoint/action coverage expectations.
- Modify `tests/test_app_endpoints.py`
  - Add a small endpoint/view-mode smoke test for the new `view` query parameter.
- Do not modify `VocaVid/store.py` unless a test proves helper data cannot be derived from existing rows.
- Do not modify runtime data under `.VocaVid/`.

## Scope

This plan covers the first implementation pass:

- Modern start page.
- New Project modal markup.
- Queue summary and queue admin presentation.
- Project detail page with storyboard default and advanced/table mode.
- Smart segment card state rendering.
- Segment inspector markup using existing actions.
- Tests and screenshots/manual verification.

Video first-frame generation is out of scope for this first pass. The first pass should use the clip path with a play overlay and fall back visually to the selected image/avatar where an actual frame thumbnail does not exist yet.

---

### Task 1: Add Shared Studio UI Shell Styles

**Files:**
- Modify: `VocaVid/app.py`
- Test: `tests/test_app_html.py`

- [ ] **Step 1: Add a failing test for the dark studio shell CSS**

Add this test to `AppHtmlTests` in `tests/test_app_html.py`:

```python
def test_page_uses_dark_studio_shell_styles(self):
    html = _page("Projects", "")

    self.assertIn(":root", html)
    self.assertIn("--studio-bg", html)
    self.assertIn("background:", html)
    self.assertIn(".studio-topbar", html)
    self.assertIn(".studio-panel", html)
    self.assertIn(".studio-button", html)
    self.assertIn(".studio-chip", html)
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_page_uses_dark_studio_shell_styles
```

Expected: FAIL because the CSS variables and classes do not exist yet.

- [ ] **Step 3: Replace the top of `_page` CSS with studio tokens and shared classes**

In `VocaVid/app.py`, update the `<style>` block inside `_page`. Keep existing functional classes such as `.compact-form`, `.project-topbar`, table classes, lightboxes, polling scripts, and selection scripts. Add these shared tokens/classes near the top of the style block:

```css
:root {
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
}
body {
  margin: 0;
  font-family: Inter, Segoe UI, Arial, sans-serif;
  background:
    radial-gradient(circle at 18% 0%, rgba(53,224,179,.14), transparent 26%),
    radial-gradient(circle at 78% 0%, rgba(255,79,139,.12), transparent 28%),
    linear-gradient(180deg, #0b0d12, #07080b);
  color: var(--studio-text);
}
main { max-width: none; margin: 0; padding: 24px; }
.studio-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
  padding: 14px 16px;
  border: 1px solid var(--studio-line);
  border-radius: 20px;
  background: rgba(8,9,13,.74);
  backdrop-filter: blur(18px);
}
.studio-brand { font-size: 23px; font-weight: 950; letter-spacing: 0; }
.studio-tagline { color: var(--studio-muted); font-weight: 750; }
.studio-spacer { flex: 1; }
.studio-panel {
  border: 1px solid var(--studio-line);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(255,255,255,.065), rgba(255,255,255,.026));
  overflow: hidden;
  box-shadow: 0 24px 80px rgba(0,0,0,.24);
}
.studio-panel-head {
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--studio-line);
}
.studio-chip {
  border: 1px solid var(--studio-line);
  border-radius: 999px;
  padding: 8px 11px;
  background: rgba(255,255,255,.05);
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 850;
  white-space: nowrap;
}
.studio-chip-green {
  border-color: rgba(53,224,179,.42);
  background: rgba(53,224,179,.1);
  color: #dcfff6;
}
.studio-chip-pink {
  border-color: rgba(255,79,139,.4);
  background: rgba(255,79,139,.1);
  color: #ffd7e5;
}
.studio-button, button, .button {
  border: 0;
  border-radius: 12px;
  background: var(--studio-accent);
  color: #06100d;
  padding: 10px 13px;
  font-weight: 950;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.studio-button-secondary {
  border: 1px solid var(--studio-line);
  background: rgba(255,255,255,.055);
  color: #e7edf7;
}
.studio-button-danger, .danger-button {
  border: 1px solid rgba(255,79,139,.42);
  background: rgba(255,79,139,.12);
  color: #ffd7e5;
}
```

When updating `.danger-panel`, tables, rows, and form styles, keep class names stable so existing tests continue to find them.

- [ ] **Step 4: Run the focused shell test**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_page_uses_dark_studio_shell_styles
```

Expected: PASS.

- [ ] **Step 5: Run current HTML tests to catch CSS selector regressions**

Run:

```powershell
python -m unittest tests.test_app_html
```

Expected: Some existing tests may fail because they assert old beige/list CSS. Update those tests in later tasks, not in this task unless they fail only because of renamed shared button classes.

- [ ] **Step 6: Commit**

```powershell
git add VocaVid/app.py tests/test_app_html.py
git commit -m "Add studio UI shell styles"
```

---

### Task 2: Redesign Start Page With New Project Modal

**Files:**
- Modify: `VocaVid/app.py`
- Modify: `tests/test_app_html.py`

- [ ] **Step 1: Replace old start-form tests with modal/dashboard tests**

Update `test_project_form_is_minimal_import_form` so it expects a modal instead of a permanent form:

```python
def test_start_page_has_new_project_modal_trigger_and_form(self):
    html = _projects_html([], [])

    self.assertIn('class="start-dashboard"', html)
    self.assertIn('class="studio-button" type="button" onclick="openNewProjectModal()"', html)
    self.assertIn('id="new-project-modal"', html)
    self.assertIn('action="/projects"', html)
    self.assertIn('method="post" enctype="multipart/form-data"', html)
    self.assertIn('<label>Name</label><input name="name" required>', html)
    self.assertIn('<label>WAV</label><input name="audio" type="file" accept=".wav,audio/wav" required>', html)
    self.assertIn('<label>Lyrics</label><input name="lyrics" type="file" accept=".txt,.lyrics" required>', html)
    self.assertIn('name="lyric_group_size" type="number" min="1" max="8" value="2"', html)
    self.assertIn('name="chorus_group_size" type="number" min="1" max="8" value="1"', html)
    self.assertIn('name="transition_handle_seconds" type="number" min="0" step="0.1" value="0.5"', html)
    self.assertIn('name="whisper_model_size"', html)
```

Keep `test_project_form_includes_clip_group_defaults`, but update its final ordering assertion to search inside the modal form and expect `Create Project` in a studio button:

```python
self.assertLess(html.index('name="whisper_model_size"'), html.index("<button>Create Project</button>"))
```

- [ ] **Step 2: Add project-card tests**

Replace `test_projects_list_is_responsive_and_marks_kdenlive_projects_done` with:

```python
def test_start_page_renders_project_cards_and_marks_done_projects(self):
    projects = [
        {"id": 2, "name": "Finished Song", "final_video_path": "outputs/finished/final.kdenlive"},
        {"id": 1, "name": "Open Song", "final_video_path": None},
    ]

    body = _projects_html(projects, [])
    html = _page("Projects", body)

    self.assertIn('class="project-card project-card-done"', body)
    self.assertIn('<a class="project-card-link" href="/projects/2">', body)
    self.assertIn("Finished Song", body)
    self.assertIn('<span class="project-done-label">done</span>', body)
    self.assertIn('<a class="project-card-link" href="/projects/1">', body)
    self.assertIn(".project-grid", html)
    self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", html)
```

- [ ] **Step 3: Run the start-page tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_start_page_has_new_project_modal_trigger_and_form tests.test_app_html.AppHtmlTests.test_start_page_renders_project_cards_and_marks_done_projects
```

Expected: FAIL because `_projects_html` still renders the old form and list.

- [ ] **Step 4: Add start page helper functions**

In `VocaVid/app.py`, add these helpers before `_projects_html`:

```python
def _start_topbar_html(queue_estimate_seconds: float | None) -> str:
    return f"""
<div class="studio-topbar">
  <div class="studio-brand">VocaVid</div>
  <div class="studio-tagline">Local AI music-video studio</div>
  <div class="studio-spacer"></div>
  {_queue_estimate_html(queue_estimate_seconds)}
  <button class="studio-button" type="button" onclick="openNewProjectModal()">New Project</button>
  <a class="studio-button studio-button-secondary" href="#queue-admin">Jobs</a>
</div>
"""
```

```python
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
```

```python
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
```

- [ ] **Step 5: Replace `_project_list_item_html` with card rendering**

Replace `_project_list_item_html` with:

```python
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
```

- [ ] **Step 6: Rewrite `_projects_html` around dashboard sections**

Replace the return value of `_projects_html` with:

```python
project_cards = "".join(_project_list_item_html(p) for p in projects)
if not project_cards:
    project_cards = '<p class="empty-state">No projects yet. Create one to start rendering.</p>'
return f"""
<div class="start-dashboard">
  {_start_topbar_html(queue_estimate_seconds)}
  {_start_hero_html(projects, jobs, queue_estimate_seconds)}
  <section class="start-layout">
    <section class="studio-panel">
      <div class="studio-panel-head">
        <h2>Projects</h2>
        <span class="studio-chip">Recent first</span>
      </div>
      <div class="project-grid">{project_cards}</div>
    </section>
    {_queue_summary_html(jobs, average_durations)}
  </section>
  {_queue_admin_html(job_options)}
  {_new_project_modal_html()}
</div>
<script>setupQueueEstimateCountdown(); pollJobsStatus();</script>
"""
```

`_queue_summary_html` and `_queue_admin_html` are added in Task 3.

- [ ] **Step 7: Add New Project modal JavaScript**

Inside `_page` `<script>`, add:

```javascript
function openNewProjectModal() {
  const box = document.getElementById('new-project-modal');
  if (!box) return;
  box.classList.add('open');
}
function closeNewProjectModal() {
  const box = document.getElementById('new-project-modal');
  if (!box) return;
  box.classList.remove('open');
}
```

- [ ] **Step 8: Add start dashboard CSS**

Add CSS in `_page`:

```css
.start-dashboard { display: grid; gap: 18px; }
.start-hero {
  min-height: 250px;
  border: 1px solid var(--studio-line);
  border-radius: 24px;
  padding: 28px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 24px;
  align-items: end;
  background:
    linear-gradient(90deg, rgba(0,0,0,.76), rgba(0,0,0,.16)),
    linear-gradient(135deg, #111827, #f97316 58%, #171923);
  box-shadow: 0 24px 90px rgba(0,0,0,.26);
}
.start-hero h1 { font-size: clamp(42px, 6vw, 76px); line-height: .94; margin: 0; }
.start-hero p { margin-top: 12px; color: #dce3ef; max-width: 700px; font-size: 17px; }
.production-status {
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 18px;
  background: rgba(8,10,14,.72);
  padding: 16px;
  display: grid;
  gap: 12px;
  backdrop-filter: blur(12px);
}
.stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.stat { border: 1px solid var(--studio-line); border-radius: 14px; padding: 13px; background: rgba(255,255,255,.045); }
.stat strong { display: block; font-size: 26px; }
.stat span { color: var(--studio-muted); font-size: 12px; font-weight: 800; }
.start-layout { display: grid; grid-template-columns: minmax(0, 1fr) 390px; gap: 18px; align-items: start; }
.project-grid { padding: 16px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.project-card { min-height: 176px; border: 1px solid var(--studio-line); border-radius: 16px; background: rgba(0,0,0,.16); overflow: hidden; }
.project-card-link { color: inherit; text-decoration: none; display: block; height: 100%; }
.project-card-art { height: 96px; background: linear-gradient(135deg, #111827, #fb713f); }
.project-card-body { padding: 12px; }
.project-card-body h3 { margin: 0 0 7px; font-size: 14px; }
.project-card-body p { margin: 0; color: var(--studio-muted); font-size: 12px; }
.project-card-done .project-card-body h3 { text-decoration: line-through; color: #a5adba; }
.project-done-label { display: inline-flex; margin-top: 10px; border: 1px solid rgba(53,224,179,.36); color: #dffff6; background: rgba(53,224,179,.09); border-radius: 999px; padding: 5px 7px; font-size: 11px; font-weight: 850; }
.modal-content { width: min(760px, calc(100vw - 48px)); border: 1px solid rgba(53,224,179,.35); border-radius: 24px; background: #0f131a; box-shadow: 0 40px 120px rgba(0,0,0,.55); overflow: hidden; }
.new-project-form { padding: 18px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: transparent; border: 0; margin: 0; }
.new-project-form p { grid-column: 1 / -1; margin: 0; }
@media (max-width: 1180px) { .start-hero, .start-layout { grid-template-columns: 1fr; } .project-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .project-grid, .new-project-form { grid-template-columns: 1fr; } }
```

- [ ] **Step 9: Run start page tests**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_start_page_has_new_project_modal_trigger_and_form tests.test_app_html.AppHtmlTests.test_project_form_includes_clip_group_defaults tests.test_app_html.AppHtmlTests.test_start_page_renders_project_cards_and_marks_done_projects
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add VocaVid/app.py tests/test_app_html.py
git commit -m "Redesign start page dashboard"
```

---

### Task 3: Redesign Queue Summary And Admin Sections

**Files:**
- Modify: `VocaVid/app.py`
- Modify: `tests/test_app_html.py`

- [ ] **Step 1: Update queue tests**

Replace `test_jobs_table_has_delete_actions_except_running_and_clear_queued_button` with:

```python
def test_start_page_has_queue_summary_and_admin_actions(self):
    jobs = [
        Job(id=4, name="generate prompts: Demo Song", status="queued", created_at="2026-06-27T19:15:24", action="prompts"),
        Job(id=3, name="generate clips: Demo Song", status="running", created_at="2026-06-27T19:03:22", action="clips"),
        Job(id=2, name="align: Demo Song", status="done", created_at="2026-06-27T18:00:00", action="align"),
        Job(id=1, name="old job", status="failed", created_at="2026-06-27T17:00:00", error="boom"),
    ]

    html = _projects_html([], jobs, {"prompts": 12.4, "clips": 126.0})

    self.assertIn('class="queue-summary studio-panel"', html)
    self.assertIn('id="jobs-table-body"', html)
    self.assertIn("generate prompts: Demo Song", html)
    self.assertIn("2m 6s", html)
    self.assertIn('id="queue-admin"', html)
    self.assertIn('action="/jobs/delete-queued"', html)
    self.assertIn("<button>Delete queued</button>", html)
    self.assertIn('action="/jobs/delete-finished"', html)
    self.assertIn("<button>Delete finished</button>", html)
    self.assertIn('name="autodelete_finished"', html)
    self.assertIn('name="shutdown_after_queue"', html)
```

Keep `test_start_page_has_queue_polling_and_queue_options`, but update the visible labels to match the new card labels if they change.

- [ ] **Step 2: Run queue tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_start_page_has_queue_summary_and_admin_actions tests.test_app_html.AppHtmlTests.test_start_page_has_queue_polling_and_queue_options
```

Expected: FAIL until helpers exist.

- [ ] **Step 3: Add `_queue_summary_html`**

In `VocaVid/app.py`, add:

```python
def _queue_summary_html(jobs, average_durations: dict[str, float]) -> str:
    job_rows = _jobs_table_body_html(jobs, average_durations)
    return f"""
<aside class="queue-summary studio-panel">
  <div class="studio-panel-head">
    <h2>Queue Now</h2>
    <span class="studio-chip studio-chip-green">running</span>
  </div>
  <table class="queue-table">
    <thead><tr><th>#</th><th>Name</th><th>Status</th><th>Avg</th><th></th></tr></thead>
    <tbody id="jobs-table-body">{job_rows}</tbody>
  </table>
</aside>
"""
```

- [ ] **Step 4: Add `_queue_admin_html`**

In `VocaVid/app.py`, add:

```python
def _queue_admin_html(job_options: JobOptions) -> str:
    autodelete_checked = " checked" if job_options.autodelete_finished else ""
    shutdown_checked = " checked" if job_options.shutdown_after_queue else ""
    return f"""
<section id="queue-admin" class="queue-admin studio-panel">
  <div class="studio-panel-head">
    <h2>Queue Admin</h2>
    <span class="studio-chip">destructive and automation controls</span>
  </div>
  <div class="queue-admin-grid">
    <form class="queue-admin-card compact-form" action="/jobs/delete-queued" method="post">
      <h3>Delete queued</h3>
      <p>Clear waiting render jobs when a batch was wrong.</p>
      <button class="studio-button-danger">Delete queued</button>
    </form>
    <form class="queue-admin-card compact-form" action="/jobs/delete-finished" method="post">
      <h3>Delete finished</h3>
      <p>Clean successful and failed job history.</p>
      <button class="studio-button-secondary">Delete finished</button>
    </form>
    <form class="queue-admin-card compact-form job-options" action="/jobs/options" method="post">
      <h3>Auto-delete</h3>
      <p>Automatically remove finished jobs.</p>
      <label><input type="checkbox" name="autodelete_finished"{autodelete_checked} onchange="this.form.submit()"> Autodelete finished</label>
    </form>
    <form class="queue-admin-card compact-form job-options" action="/jobs/options" method="post">
      <h3>Computer shutdown</h3>
      <p>Optional shutdown after queue drains.</p>
      <label><input type="checkbox" name="shutdown_after_queue"{shutdown_checked} onchange="this.form.submit()"> Shutdown computer 15mins after last queue</label>
    </form>
  </div>
</section>
"""
```

- [ ] **Step 5: Narrow `_jobs_table_body_html` columns for queue summary**

Keep `_jobs_table_body_html` as-is if old table tests still need Created/Error columns. If the queue summary needs fewer columns, add a second helper instead:

```python
def _jobs_compact_table_body_html(jobs, average_durations: dict[str, float]) -> str:
    return "".join(
        f"<tr><td>{job.id}</td><td>{_text(job.name)}{_job_error_inline_html(job.error)}</td><td>{_text(job.status)}</td><td>{_duration_html(_job_average_seconds(job, average_durations))}</td><td>{_job_delete_html(job)}</td></tr>"
        for job in jobs
    )

def _job_error_inline_html(error: str) -> str:
    return f'<div class="status-error">{_text(error)}</div>' if error else ""
```

If this compact helper is used, update `_queue_summary_html` to call `_jobs_compact_table_body_html`.

- [ ] **Step 6: Add queue admin CSS**

Add:

```css
.queue-summary .queue-table { border: 0; background: transparent; }
.queue-summary th, .queue-summary td { border-bottom: 1px solid var(--studio-line); }
.queue-admin { margin-top: 18px; }
.queue-admin-grid { padding: 16px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.queue-admin-card {
  border: 1px solid var(--studio-line);
  border-radius: 16px;
  background: rgba(0,0,0,.16);
  padding: 14px;
  min-height: 128px;
  display: grid;
  align-content: space-between;
  gap: 12px;
}
.queue-admin-card h3 { margin: 0; font-size: 15px; }
.queue-admin-card p { margin: 0; color: var(--studio-muted); font-size: 12px; }
@media (max-width: 1180px) { .queue-admin-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .queue-admin-grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 7: Run queue tests**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_start_page_has_queue_summary_and_admin_actions tests.test_app_html.AppHtmlTests.test_start_page_has_queue_polling_and_queue_options tests.test_app_endpoints.AppEndpointTests.test_job_options_endpoint_toggles_autodelete_and_shutdown
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add VocaVid/app.py tests/test_app_html.py
git commit -m "Redesign queue dashboard sections"
```

---

### Task 4: Add Project View Mode And Storyboard Default

**Files:**
- Modify: `VocaVid/app.py`
- Modify: `tests/test_app_html.py`
- Modify: `tests/test_app_endpoints.py`

- [ ] **Step 1: Add failing tests for project view controls**

Add to `tests/test_app_html.py`:

```python
def test_project_page_defaults_to_storyboard_view_with_table_toggle(self):
    project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
    segments = [
        {
            "segment_index": 0,
            "kind": "lyrics",
            "section": "Verse",
            "is_chorus": 0,
            "clean_text": "Hello world",
            "start_sec": 0.0,
            "end_sec": 3.0,
            "prompt": None,
            "video_prompt": None,
            "image_path": None,
            "avatar_image_path": None,
            "clip_path": None,
            "audio_path": None,
            "scene_plan": "",
            "video_approved": 0,
            "status": "pending",
            "error": "",
        }
    ]

    html = _project_html(project, [], segments, used_actions={"scene-plan"})

    self.assertIn('class="project-workspace"', html)
    self.assertIn('class="storyboard-grid"', html)
    self.assertIn('class="segment-inspector studio-panel"', html)
    self.assertIn('href="/projects/7?view=table"', html)
    self.assertNotIn("<table>", html.split('class="project-workspace"')[1])
```

Add:

```python
def test_project_page_table_view_keeps_advanced_table(self):
    project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
    segments = [
        {
            "segment_index": 0,
            "kind": "lyrics",
            "section": "Verse",
            "is_chorus": 0,
            "clean_text": "Hello world",
            "start_sec": 0.0,
            "end_sec": 3.0,
            "prompt": None,
            "video_prompt": None,
            "image_path": None,
            "avatar_image_path": None,
            "clip_path": None,
            "audio_path": None,
            "scene_plan": "",
            "video_approved": 0,
            "status": "pending",
            "error": "",
        }
    ]

    html = _project_html(project, [], segments, used_actions={"scene-plan"}, view="table")

    self.assertIn("<h2>Render Segments</h2>", html)
    self.assertIn("<table>", html)
    self.assertIn('href="/projects/7?view=storyboard"', html)
```

- [ ] **Step 2: Update endpoint to accept `view` query parameter**

In `VocaVid/app.py`, change project detail route signature:

```python
@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail(project_id: int, view: str = "storyboard"):
```

Pass `view=view` to `_project_html`.

- [ ] **Step 3: Update `_project_html` signature and view dispatch**

Change signature:

```python
def _project_html(
    project,
    lines,
    segments=None,
    used_actions=None,
    active_jobs=None,
    queue_estimate_seconds: float | None = None,
    previous_project_id: int | None = None,
    next_project_id: int | None = None,
    view: str = "storyboard",
) -> str:
```

Inside `_project_html`, normalize:

```python
view = "table" if view == "table" else "storyboard"
show_generation_columns = "scene-plan" in used_actions
work_items_html = (
    _work_items_html(project, lines, segments, locked, show_generation_columns=show_generation_columns)
    if view == "table"
    else _storyboard_view_html(project, lines, segments, locked, show_generation_columns=show_generation_columns)
)
```

Replace direct `_work_items_html(...)` in the return string with `{work_items_html}`.

- [ ] **Step 4: Add `_project_view_toggle_html`**

Add:

```python
def _project_view_toggle_html(project_id: int, view: str) -> str:
    storyboard_active = " active" if view != "table" else ""
    table_active = " active" if view == "table" else ""
    return f"""
<nav class="project-view-toggle" aria-label="Project view">
  <a class="view-pill{storyboard_active}" href="/projects/{project_id}?view=storyboard">Storyboard</a>
  <a class="view-pill{table_active}" href="/projects/{project_id}?view=table">Table</a>
</nav>
"""
```

Add `{_project_view_toggle_html(project["id"], view)}` to the project topbar actions area.

- [ ] **Step 5: Add placeholder `_storyboard_view_html`**

Add a minimal implementation that will be expanded in Task 5:

```python
def _storyboard_view_html(project, lines, segments, locked=None, show_generation_columns: bool = False) -> str:
    rows = segments or lines
    item_kind = "segments" if segments else "lines"
    cards = "".join(_segment_card_html(project, item_kind, row, locked or {}) for row in rows)
    selected = rows[0] if rows else None
    return f"""
<section class="project-workspace">
  <section class="studio-panel storyboard-panel">
    <div class="studio-panel-head">
      <h2>Storyboard Review</h2>
      <span class="studio-chip">Shot control</span>
    </div>
    <div class="storyboard-grid">{cards}</div>
  </section>
  {_segment_inspector_html(project, item_kind, selected) if selected else ""}
</section>
"""
```

Add minimal stub helpers:

```python
def _segment_card_html(project, item_kind: str, row, locked: dict[int, str]) -> str:
    index = _row_index(row, item_kind)
    return f'<article class="segment-card" data-segment-card="{index}"><h3>{index + 1}</h3><p>{_text(_row_value(row, "clean_text", ""))}</p></article>'

def _segment_inspector_html(project, item_kind: str, row) -> str:
    return '<aside class="segment-inspector studio-panel"><div class="studio-panel-head"><h2>Segment Inspector</h2></div></aside>'
```

- [ ] **Step 6: Add project workspace CSS**

Add:

```css
.project-view-toggle { display: inline-flex; border: 1px solid var(--studio-line); border-radius: 12px; overflow: hidden; background: rgba(0,0,0,.16); }
.view-pill { padding: 8px 10px; color: var(--studio-muted); font-size: 12px; font-weight: 850; text-decoration: none; }
.view-pill.active { color: #06100d; background: var(--studio-accent); }
.project-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 430px; gap: 18px; align-items: start; }
.storyboard-grid { padding: 16px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.segment-card { border: 1px solid var(--studio-line); border-radius: 16px; background: rgba(0,0,0,.16); padding: 12px; min-height: 180px; }
.segment-inspector { position: sticky; top: 120px; }
@media (max-width: 1200px) { .project-workspace { grid-template-columns: 1fr; } .segment-inspector { position: static; } }
@media (max-width: 820px) { .storyboard-grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 7: Run view tests**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_project_page_defaults_to_storyboard_view_with_table_toggle tests.test_app_html.AppHtmlTests.test_project_page_table_view_keeps_advanced_table
```

Expected: PASS.

- [ ] **Step 8: Add endpoint smoke test**

Add to `tests/test_app_endpoints.py`:

```python
def test_project_detail_table_view_query_renders_advanced_table(self):
    old_app_root = app_module.APP_ROOT
    old_uploads = app_module.UPLOADS
    old_db_path = app_module.DB_PATH
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            app_module.APP_ROOT = root / ".VocaVid"
            app_module.UPLOADS = app_module.APP_ROOT / "uploads"
            app_module.DB_PATH = app_module.APP_ROOT / "VocaVid.sqlite3"
            store = Store(app_module.DB_PATH)
            lyrics = root / "lyrics.txt"
            audio = root / "song.wav"
            lyrics.write_text("[Verse]\nOne\n", encoding="utf-8")
            _write_wav(audio)
            project_id = store.create_project(
                {"name": "Demo", "audio_path": str(audio), "lyrics_path": str(lyrics), "global_style_prompt": "cinematic"},
                parse_suno_lyrics(lyrics.read_text(encoding="utf-8")),
            )

            client = TestClient(app_module.create_app())
            page = client.get(f"/projects/{project_id}?view=table").text

            self.assertIn("<table>", page)
            self.assertIn("Lyrics / Timing", page)
            self.assertIn('href="/projects/1?view=storyboard"', page)
    finally:
        app_module.APP_ROOT = old_app_root
        app_module.UPLOADS = old_uploads
        app_module.DB_PATH = old_db_path
```

- [ ] **Step 9: Run endpoint smoke test**

Run:

```powershell
python -m unittest tests.test_app_endpoints.AppEndpointTests.test_project_detail_table_view_query_renders_advanced_table
```

Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add VocaVid/app.py tests/test_app_html.py tests/test_app_endpoints.py
git commit -m "Add storyboard project view mode"
```

---

### Task 5: Implement Smart Segment Cards

**Files:**
- Modify: `VocaVid/app.py`
- Modify: `tests/test_app_html.py`

- [ ] **Step 1: Add media priority tests**

Add:

```python
def test_segment_card_media_priority_prefers_clip_avatar_image_fallback(self):
    project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
    base = {
        "segment_index": 0,
        "kind": "lyrics",
        "section": "Verse",
        "is_chorus": 0,
        "clean_text": "Hello world",
        "start_sec": 0.0,
        "end_sec": 3.0,
        "prompt": None,
        "video_prompt": None,
        "image_path": None,
        "avatar_image_path": None,
        "selected_image_source": "avatar",
        "clip_path": None,
        "audio_path": None,
        "scene_plan": "",
        "video_approved": 0,
        "status": "pending",
        "error": "",
    }

    fallback_html = _segment_card_html(project, "segments", base, {})
    self.assertIn("segment-card-fallback", fallback_html)
    self.assertIn("No media yet", fallback_html)

    image_row = dict(base, image_path="outputs/project-7/images/segment-000.png")
    image_html = _segment_card_html(project, "segments", image_row, {})
    self.assertIn("segment-card-image", image_html)
    self.assertIn('src="/assets/outputs/project-7/images/segment-000.png', image_html)

    avatar_row = dict(image_row, avatar_image_path="outputs/project-7/images/avatar-segment-000.png")
    avatar_html = _segment_card_html(project, "segments", avatar_row, {})
    self.assertIn("segment-card-avatar", avatar_html)
    self.assertIn('src="/assets/outputs/project-7/images/avatar-segment-000.png', avatar_html)

    clip_row = dict(avatar_row, clip_path="outputs/project-7/clips/segment-000.mp4")
    clip_html = _segment_card_html(project, "segments", clip_row, {})
    self.assertIn("segment-card-video", clip_html)
    self.assertIn("openClipLightbox('/assets/outputs/project-7/clips/segment-000.mp4", clip_html)
    self.assertIn("segment-card-play", clip_html)
```

- [ ] **Step 2: Run media priority test**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_segment_card_media_priority_prefers_clip_avatar_image_fallback
```

Expected: FAIL because `_segment_card_html` is still a placeholder.

- [ ] **Step 3: Add segment card media helpers**

In `VocaVid/app.py`, add:

```python
def _segment_card_media(project, row) -> tuple[str, str, str]:
    clip_path = _row_value(row, "clip_path", "")
    avatar_path = _row_value(row, "avatar_image_path", "")
    image_path = _row_value(row, "image_path", "")
    if clip_path:
        clip_url = _generated_asset_url(project, clip_path)
        fallback_image = avatar_path or image_path
        preview = _segment_card_image_tag(project, fallback_image, "Clip preview frame") if fallback_image else '<div class="segment-card-fallback-mark">▶</div>'
        return (
            "segment-card-video",
            f'<button class="segment-card-media-button" type="button" onclick="openClipLightbox({_js_arg(clip_url)})">{preview}<span class="segment-card-play">▶</span></button>',
            "final clip",
        )
    if avatar_path:
        return ("segment-card-avatar", _segment_card_image_button(project, avatar_path, "Avatar image"), "avatar image")
    if image_path:
        return ("segment-card-image", _segment_card_image_button(project, image_path, "Generated image"), "AI image")
    return (
        "segment-card-fallback",
        '<div class="segment-card-fallback-mark">No media yet</div>',
        "fallback",
    )

def _segment_card_image_tag(project, image_path: str | None, alt: str) -> str:
    if not image_path:
        return ""
    url = _generated_asset_url(project, image_path)
    return f'<img class="segment-card-image" src="{url}" alt="{_attr(alt)}">'

def _segment_card_image_button(project, image_path: str, alt: str) -> str:
    url = _generated_asset_url(project, image_path)
    return f'<button class="segment-card-media-button" type="button" onclick="openImageLightbox({_js_arg(url)})"><img class="segment-card-image" src="{url}" alt="{_attr(alt)}"></button>'
```

- [ ] **Step 4: Replace `_segment_card_html`**

Use:

```python
def _segment_card_html(project, item_kind: str, row, locked: dict[int, str]) -> str:
    index = _row_index(row, item_kind)
    approved = bool(_row_value(row, "video_approved", 0))
    locked_status = locked.get(index)
    media_class, media_html, media_label = _segment_card_media(project, row)
    status = _row_value(row, "status", "pending")
    source = _row_value(row, "selected_image_source", "avatar")
    approved_badge = '<span class="segment-badge segment-badge-ok">OK</span>' if approved else ""
    locked_badge = f'<span class="segment-badge segment-badge-warn">{_text(locked_status)}</span>' if locked_status else ""
    return f"""
<article class="segment-card {media_class}{' segment-card-approved' if approved else ''}" data-segment-card="{index}" onclick="selectSegmentCard({index})">
  <div class="segment-card-media">
    {media_html}
    <div class="segment-card-badges">
      <span class="segment-badge">{index + 1}</span>
      <span class="segment-badge">{_text(media_label)}</span>
      {approved_badge}
      {locked_badge}
    </div>
  </div>
  <div class="segment-card-body">
    <h3>{_text(_row_value(row, "clean_text", ""))}</h3>
    <p>{_text(status)}</p>
    <div class="segment-card-actions">
      {_segment_card_quick_action_html(project["id"], item_kind, index, row)}
      <span class="segment-badge">source: {_text(source)}</span>
    </div>
  </div>
</article>
"""
```

Add quick action helper:

```python
def _segment_card_quick_action_html(project_id: int, item_kind: str, index: int, row) -> str:
    if _row_value(row, "clip_path", ""):
        return _redo_html(project_id, item_kind, index, _row_value(row, "last_action", "clips")) or ""
    if _row_value(row, "image_path", "") or _row_value(row, "avatar_image_path", ""):
        return '<span class="segment-badge segment-badge-ok">ready for clip</span>'
    return '<span class="segment-badge segment-badge-warn">needs image</span>'
```

- [ ] **Step 5: Add card CSS**

Add:

```css
.segment-card { min-height: 280px; padding: 0; overflow: hidden; cursor: pointer; }
.segment-card-media { height: 156px; position: relative; background: #151923; overflow: hidden; }
.segment-card-media-button { width: 100%; height: 100%; padding: 0; border: 0; border-radius: 0; background: transparent; display: block; }
.segment-card-image { width: 100%; height: 100%; object-fit: cover; display: block; }
.segment-card-fallback .segment-card-media {
  background:
    repeating-linear-gradient(45deg, rgba(255,255,255,.055) 0 10px, transparent 10px 20px),
    radial-gradient(circle at 50% 35%, rgba(110,168,255,.2), transparent 34%),
    #141923;
}
.segment-card-fallback-mark { height: 100%; display: grid; place-items: center; color: rgba(255,255,255,.58); font-weight: 950; }
.segment-card-play { position: absolute; left: 50%; top: 50%; translate: -50% -50%; width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; background: rgba(53,224,179,.92); color: #06100d; font-size: 21px; font-weight: 950; }
.segment-card-badges { position: absolute; left: 10px; right: 10px; top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
.segment-badge { border: 1px solid rgba(255,255,255,.18); border-radius: 999px; padding: 5px 7px; background: rgba(0,0,0,.42); color: #eaf0f8; font-size: 11px; font-weight: 900; }
.segment-badge-ok { border-color: rgba(53,224,179,.5); color: #dffff6; background: rgba(53,224,179,.12); }
.segment-badge-warn { border-color: rgba(245,184,75,.55); color: #ffe6ad; background: rgba(245,184,75,.12); }
.segment-card-body { padding: 12px; }
.segment-card-body h3 { margin: 0; min-height: 42px; font-size: 14px; line-height: 1.35; }
.segment-card-body p { margin: 8px 0 0; color: var(--studio-muted); font-size: 12px; }
.segment-card-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
.segment-card-approved { border-color: rgba(53,224,179,.55); box-shadow: inset 0 0 0 1px rgba(53,224,179,.22); }
```

- [ ] **Step 6: Add harmless selection JavaScript**

Add:

```javascript
function selectSegmentCard(index) {
  document.querySelectorAll('.segment-card').forEach((card) => card.classList.remove('selected'));
  const card = document.querySelector('[data-segment-card="' + index + '"]');
  if (card) card.classList.add('selected');
}
```

- [ ] **Step 7: Run card tests**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_segment_card_media_priority_prefers_clip_avatar_image_fallback
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add VocaVid/app.py tests/test_app_html.py
git commit -m "Add smart storyboard segment cards"
```

---

### Task 6: Implement Segment Inspector With Existing Actions

**Files:**
- Modify: `VocaVid/app.py`
- Modify: `tests/test_app_html.py`

- [ ] **Step 1: Add inspector action test**

Add:

```python
def test_segment_inspector_exposes_prompt_source_redo_and_approval_actions(self):
    project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
    segment = {
        "segment_index": 3,
        "kind": "lyrics",
        "section": "Verse",
        "is_chorus": 0,
        "clean_text": "Hallo Welt",
        "start_sec": 0.0,
        "end_sec": 3.0,
        "prompt": "image prompt",
        "video_prompt": "video prompt",
        "image_path": "outputs/project-7/images/segment-003.png",
        "avatar_image_path": "outputs/project-7/images/avatar-segment-003.png",
        "selected_image_source": "avatar",
        "clip_path": "outputs/project-7/clips/segment-003.mp4",
        "audio_path": None,
        "scene_plan": "",
        "last_action": "clips",
        "video_approved": 1,
        "status": "done",
        "error": "",
    }

    html = _segment_inspector_html(project, "segments", segment)

    self.assertIn("Segment Inspector", html)
    self.assertIn("Hallo Welt", html)
    self.assertIn('action="/projects/7/segments/3/prompts/image/save"', html)
    self.assertIn('formaction="/projects/7/segments/3/prompts/image/ai-fill"', html)
    self.assertIn('action="/projects/7/segments/3/prompts/video/save"', html)
    self.assertIn('formaction="/projects/7/segments/3/prompts/video/ai-fill"', html)
    self.assertIn('action="/projects/7/segments/3/image-source"', html)
    self.assertIn('action="/projects/7/segments/3/redo"', html)
    self.assertIn('action="/projects/7/segments/3/approval"', html)
    self.assertIn('name="video_approved" value="1" checked', html)
```

- [ ] **Step 2: Run inspector test**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_segment_inspector_exposes_prompt_source_redo_and_approval_actions
```

Expected: FAIL because the inspector is still a stub.

- [ ] **Step 3: Replace `_segment_inspector_html`**

Use:

```python
def _segment_inspector_html(project, item_kind: str, row) -> str:
    index = _row_index(row, item_kind)
    prompt_editor = _prompt_editor_html(
        f"/projects/{project['id']}/{item_kind}/{index}/prompts",
        _row_value(row, "prompt", "") or "",
        _row_value(row, "video_prompt", "") or "",
    )
    image_choice = _image_choice_html(project["id"], item_kind, index, row)
    redo = _redo_html(project["id"], item_kind, index, _row_value(row, "last_action", ""))
    approval = _approval_html(project["id"], item_kind, index, row)
    status = _status_html(_row_value(row, "status", "pending"), _row_value(row, "error", "") or "")
    media_class, media_html, media_label = _segment_card_media(project, row)
    return f"""
<aside class="segment-inspector studio-panel">
  <div class="studio-panel-head">
    <div>
      <h2>Segment Inspector</h2>
      <p class="inspector-subtitle">{_text(item_kind[:-1].title())} {index + 1} · {_text(media_label)}</p>
    </div>
    <span class="studio-chip">{index + 1}</span>
  </div>
  <div class="segment-inspector-body">
    <div class="inspector-preview {media_class}">{media_html}</div>
    <div class="inspector-lyric">{_multiline_text_html(_row_value(row, "clean_text", ""))}</div>
    <div class="inspector-field">{prompt_editor}</div>
    <div class="inspector-field">
      <h3>Source</h3>
      {image_choice or '<p class="muted">Image/avatar source becomes available after both assets exist.</p>'}
    </div>
    <div class="inspector-actions">
      {redo}
      {approval}
    </div>
    <div class="inspector-status">{status}</div>
  </div>
</aside>
"""
```

- [ ] **Step 4: Add inspector CSS**

Add:

```css
.segment-inspector-body { padding: 16px; display: grid; gap: 14px; align-content: start; }
.inspector-preview { height: 220px; border-radius: 16px; overflow: hidden; border: 1px solid var(--studio-line); background: #111827; }
.inspector-preview .segment-card-media-button, .inspector-preview .segment-card-fallback-mark { height: 100%; }
.inspector-subtitle { margin: 4px 0 0; color: var(--studio-muted); font-size: 12px; }
.inspector-lyric { border: 1px solid var(--studio-line); border-radius: 14px; padding: 12px; background: rgba(0,0,0,.16); font-weight: 850; }
.inspector-field { border: 1px solid var(--studio-line); border-radius: 14px; background: rgba(0,0,0,.18); padding: 12px; }
.inspector-field h3 { margin: 0 0 8px; font-size: 14px; }
.inspector-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.inspector-status { border-top: 1px solid var(--studio-line); padding-top: 12px; }
.muted { color: var(--studio-muted); }
```

- [ ] **Step 5: Run inspector tests**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_segment_inspector_exposes_prompt_source_redo_and_approval_actions
```

Expected: PASS.

- [ ] **Step 6: Run project HTML tests affected by inspector/table**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_prompts_are_editable_and_status_combines_error tests.test_app_html.AppHtmlTests.test_rows_show_image_choice_radios_only_when_both_images_exist tests.test_app_html.AppHtmlTests.test_rows_show_autosave_video_approval_before_status
```

Expected: PASS. If old table expectations fail because default view is storyboard, update those tests to call `_project_html(..., view="table")` when they are specifically table tests.

- [ ] **Step 7: Commit**

```powershell
git add VocaVid/app.py tests/test_app_html.py
git commit -m "Add storyboard segment inspector"
```

---

### Task 7: Preserve Table Mode And Polling Behavior

**Files:**
- Modify: `VocaVid/app.py`
- Modify: `tests/test_app_html.py`
- Modify: `tests/test_app_endpoints.py`

- [ ] **Step 1: Add status payload test for table rows**

The current `/projects/{id}/status` endpoint extracts `<tr>` snippets from `_work_items_html`. Keep it table-only for now so polling can still update advanced rows.

Add to `tests/test_app_html.py`:

```python
def test_project_status_payload_still_returns_table_row_snippets(self):
    project = {"id": 7, "name": "Demo", "audio_path": "song.wav", "final_video_path": None}
    segments = [
        {
            "segment_index": 0,
            "kind": "lyrics",
            "section": "Verse",
            "is_chorus": 0,
            "clean_text": "Updated row",
            "start_sec": 0.0,
            "end_sec": 3.0,
            "prompt": None,
            "image_path": None,
            "clip_path": None,
            "audio_path": None,
            "scene_plan": "",
            "status": "done",
            "error": "",
        }
    ]

    payload = _project_status_payload(project, [], segments, [])

    self.assertIn("segment-row-0", payload["rows"])
    self.assertIn("Updated row", payload["rows"]["segment-row-0"])
```

- [ ] **Step 2: Run the status payload test**

Run:

```powershell
python -m unittest tests.test_app_html.AppHtmlTests.test_project_status_payload_still_returns_table_row_snippets
```

Expected: PASS if `_project_status_payload` still calls `_work_items_html`.

- [ ] **Step 3: Update old table-specific tests to request table mode**

For tests that assert `<th>`, `<table>`, row classes, prompt columns, or table order, update calls from:

```python
html = _project_html(project, lines, segments, used_actions={"scene-plan"})
```

to:

```python
html = _project_html(project, lines, segments, used_actions={"scene-plan"}, view="table")
```

Do this for tests whose purpose is specifically table structure. Do not update tests that validate project header, view toggle, lightboxes, or default storyboard behavior.

- [ ] **Step 4: Run all app HTML tests**

Run:

```powershell
python -m unittest tests.test_app_html
```

Expected: PASS.

- [ ] **Step 5: Run endpoint tests for polling**

Run:

```powershell
python -m unittest tests.test_app_endpoints.AppEndpointTests.test_project_status_endpoint_returns_current_segment_row_html tests.test_app_endpoints.AppEndpointTests.test_jobs_status_endpoint_returns_current_queue_payload
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add VocaVid/app.py tests/test_app_html.py tests/test_app_endpoints.py
git commit -m "Preserve advanced table mode"
```

---

### Task 8: Full Verification And Screenshots

**Files:**
- Modify only if verification exposes defects:
  - `VocaVid/app.py`
  - `tests/test_app_html.py`
  - `tests/test_app_endpoints.py`

- [ ] **Step 1: Run the full test suite**

Run:

```powershell
python -m unittest discover -s tests
```

Expected: PASS.

- [ ] **Step 2: Start the app locally**

Use an approved local server command if available, or run:

```powershell
python -m VocaVid serve --host 127.0.0.1 --port 8001
```

Expected: app serves at `http://127.0.0.1:8001`.

- [ ] **Step 3: Verify start dashboard manually**

Open:

```text
http://127.0.0.1:8001/
```

Expected:

- Dark studio dashboard appears.
- New Project opens in a modal/lightbox.
- Project cards are visible.
- Queue summary is visible in the first page.
- Queue admin controls are below the dashboard.

- [ ] **Step 4: Verify project storyboard manually**

Open an existing project:

```text
http://127.0.0.1:8001/projects/1
```

Expected:

- Project header has previous/next arrows around the project name.
- Storyboard is the default view.
- Segment cards show fallback/image/avatar/clip state according to available data.
- Segment inspector appears on the right or below on narrower viewport.
- Image and video lightboxes open.

- [ ] **Step 5: Verify table mode manually**

Open:

```text
http://127.0.0.1:8001/projects/1?view=table
```

Expected:

- Existing table workflow is available.
- Selection checkboxes still work.
- Batch action forms still copy selected rows.
- Prompt save, AI fill, image source, redo, and OK forms are still present.

- [ ] **Step 6: Capture screenshots**

Capture and update README screenshots only if the user asks during execution. For this first implementation branch, keep screenshots as manual QA artifacts unless requested.

- [ ] **Step 7: Final status**

Run:

```powershell
git status --short --branch
```

Expected: only intentional files are modified. The existing local note file may still be present as an unrelated user change and should not be staged unless the user asks.

- [ ] **Step 8: Commit verification fixes if needed**

If any fixes were needed:

```powershell
git add VocaVid/app.py tests/test_app_html.py tests/test_app_endpoints.py
git commit -m "Polish UI redesign verification"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage:
  - Start dashboard: Tasks 2 and 3.
  - New Project modal: Task 2.
  - Project-only arrows/header and view toggle: Task 4.
  - Storyboard default and table mode: Tasks 4 and 7.
  - Smart segment card media priority: Task 5.
  - Inspector controls: Task 6.
  - Queue admin below dashboard: Task 3.
  - Tests and visual verification: Tasks 1 through 8.
- Placeholder scan: no unresolved placeholder markers are intentionally left.
- Type consistency:
  - `view` is a string with values `"storyboard"` and `"table"`.
  - `item_kind` remains `"segments"` or `"lines"` to match existing routes.
  - Existing helper names such as `_prompt_editor_html`, `_image_choice_html`,
    `_redo_html`, `_approval_html`, `_generated_asset_url`, and `_js_arg` are reused.

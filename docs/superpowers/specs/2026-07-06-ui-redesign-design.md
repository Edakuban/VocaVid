# VocaVid UI Redesign Design

## Goal

Redesign VocaVid so it feels like a modern local AI music-video studio instead
of a coder/admin interface, without hiding the segment-level control that makes
the project useful.

The target feel is "Suno-like ease over a precise local render workstation":
fast to understand, visually driven, and still explicit about prompts, assets,
queue state, reruns, approvals, and final assembly.

## Chosen Direction

Use the "Studio Dashboard + Storyboard Review" approach.

- The start page becomes a compact studio dashboard.
- The project detail page becomes storyboard-first.
- The existing table-style detail view remains available as an advanced/table
  mode.
- The UI keeps all existing power features, but moves detailed controls into
  focused inspectors, lightboxes, and lower-priority admin sections.

Rejected alternatives:

- A conservative reskin would be safer but would not change the "nerdy table"
  feeling enough.
- A full magic-app flow would look slick, but it would risk hiding the main
  value: precise rerender and prompt control per segment.

## Visual System

Use one consistent dark studio theme across the app.

- Background: dark neutral studio surface with subtle cinematic color accents.
- Accent colors: teal/green for ready/OK/primary actions, pink for active or
  high-energy states, amber for warnings and queued/admin states.
- Media should lead the layout wherever available.
- Cards should be visually clear and modern, but not oversized marketing cards.
- Controls should feel like production tools: compact, scannable, and explicit.

Avoid a split personality where the start page is bright and the project page is
dark. VocaVid should feel like one app.

## Start Page

The start page is the studio dashboard.

Primary content:

- Top app bar with VocaVid, short app context, queue estimate/status chips, a
  New Project button, and a Jobs button.
- Project cards as the main visible surface.
- Queue summary in the first viewport.
- Queue admin actions below the primary dashboard.

New Project should open in a modal/lightbox rather than occupying permanent page
space. The modal should contain the existing project creation fields:

- Name
- WAV file
- Lyrics file
- Genre/style prompt
- Reference images
- Resolution/FPS and other existing settings
- Whisper model and segment settings

Project cards should show generated or representative cover imagery when
available, then project title and key status such as:

- OK/open clip counts
- queue estimate
- final assembled/done state
- next likely stage such as prompts, images, review, or rendering

Queue admin actions should live below the primary dashboard because they are
less frequent and potentially destructive:

- Delete queued
- Delete finished
- Auto-delete finished jobs
- Computer shutdown after queue drains

Scrolling is acceptable for these admin controls. The first viewport should
prioritize current work and status, not every possible action.

## Project Header

Project navigation belongs only on the project detail page, not on the start
page.

The sticky project header should include:

- Back/home navigation
- Previous project arrow
- Project name/title
- Next project arrow
- Queue estimate/status
- Open/total count
- Primary final action when available, such as Assemble Final

The project arrows should stay near the project title because they are a
project-to-project browsing affordance, not a global app control.

## Project Detail Page

The default project view should be storyboard-first.

Main layout:

- Sticky project header.
- Pipeline/stage strip for major project phases.
- Storyboard grid/list of segment cards.
- Segment inspector for the selected card.
- Toggle to table/advanced view for dense editing and fallback workflows.

The storyboard should make the music video feel tangible. A user should see
shots, state, approval progress, and obvious rerender paths without scanning a
large table first.

The old table should not disappear. It remains important for dense timing,
debugging, and advanced batch workflows.

## Segment Cards

Segment cards are smart status objects.

Media display priority:

1. Final clip preview frame, with a play overlay.
2. Avatar/reference image.
3. AI-generated image.
4. Fallback placeholder based on segment index, section, lyric, and project
   style.

The final clip should not be an embedded video player inside the grid. Use a
still preview frame and open the video in a lightbox on click. This keeps the
grid calm and prevents many active players from making the page noisy or heavy.

Each card should show:

- Segment index.
- Lyric/segment text.
- Current media state.
- OK/locked status.
- Source choice state when relevant.
- Small status badges for available assets.

Card interactions:

- Clicking the media opens image or video lightbox.
- Clicking the card selects the segment and fills the inspector.
- Quick actions should stay minimal on the card, focused on the most likely
  next action.
- Detailed actions move to the inspector.

Recommended quick card actions:

- Gen image or Gen clip, depending on state.
- OK/locked state.
- Redo, when a clip exists or failed.

## Segment Inspector

The inspector keeps detail control without making every card heavy.

It should expose the full controls for the selected segment:

- Image prompt editor.
- Video prompt editor.
- Save prompt actions.
- AI fill actions.
- Generate or redo image.
- Generate or redo avatar image.
- Generate or redo clip.
- Image/avatar source choice.
- OK approval toggle.
- Status and error details.
- Timing/source metadata when relevant.

The inspector should make the existing "if the clip is bad, go back to image"
workflow obvious. That workflow is a core product feature, not an edge case.

## Lightboxes

Use lightboxes for focused media and create/edit flows:

- New Project modal on the start page.
- Image preview lightbox.
- Video clip lightbox/player.

Lightboxes should not replace the main workflow. They should focus attention for
actions that need space or playback.

## Queue

Queue state appears at multiple levels:

- Global chips in the top app/start page.
- Project header queue estimate.
- Start page queue summary.
- Queue admin area below the start dashboard.
- Jobs page or expanded queue view for full history/details.

Queue admin actions should be visually separated from ordinary render actions,
especially destructive actions like deleting queued jobs.

## Responsiveness

The design must work on desktop first, with responsive fallback:

- Start page cards collapse from dashboard columns to stacked sections.
- Project storyboard collapses from grid plus inspector to stacked card then
  inspector.
- Sticky headers must not cover content.
- Text must wrap rather than clip.
- Media cards should keep stable aspect ratios.

## Implementation Boundaries

Keep the current FastAPI/server-rendered HTML approach for the initial redesign.
Do not introduce a frontend framework unless a later plan explicitly justifies
it.

Refactor HTML rendering only as needed to make the redesign maintainable:

- Shared layout helpers for app shell, buttons, chips, panels, cards, and
  lightboxes.
- Separate helpers for start dashboard, project header, storyboard cards,
  inspector, queue summary, and queue admin.
- Preserve existing endpoints and actions where practical.

## Testing

The redesign should update or add tests around generated HTML:

- Start page contains New Project modal trigger and queue summary/admin areas.
- Project page contains project navigation arrows only on project detail pages.
- Segment card media priority renders correctly for fallback, image, avatar,
  and clip states.
- Existing form actions remain present for prompt save, AI fill, generation,
  redo, approval, queue cleanup, and project creation.
- Existing tests should continue passing.

Visual verification should include screenshots of:

- Start dashboard.
- New Project modal.
- Project storyboard view.
- Segment inspector.
- Image/video lightbox.
- Queue admin area.

## Open Decisions

The implementation plan should decide:

- Whether the storyboard view and table view are separate routes or a query/view
  mode on the existing project route.
- How to generate or cache first-frame previews for videos.
- Which exact card quick actions stay visible by default.
- Whether project cards use the latest final clip frame, latest generated image,
  or a deterministic fallback when no media exists.


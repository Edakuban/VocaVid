# VocaVid

Local orchestration app for turning a WAV file, SUNO-style lyrics, a genre/style idea, ComfyUI workflow templates, and reference images into a resumable music-video render.

VocaVid runs as a small local FastAPI web app. It keeps project state in a local SQLite database, sends generation jobs to a local ComfyUI server, stores generated assets under `.musicvideogen/`, and can assemble the final video from the rendered clips.

This project has grown through a lot of Codex-assisted vibe coding: most of the app was shaped in close human/AI collaboration, with quick iteration, local tests, and a healthy amount of "what if we made this nicer?" energy.

## Features

- Create reusable projects from a WAV file, lyrics file, genre, global style prompt, and one or more reference images.
- Align lyric lines with `faster-whisper` word timestamps, with an even-timing fallback when transcription is unavailable or uncertain.
- Group lyric lines into render segments, with separate group sizes for normal sections and chorus/refrain sections.
- Generate or edit a full scene plan before rendering.
- Generate image prompts, still images, avatar/reference-person image variants, image-to-video motion prompts, video clips, and the final assembled output.
- Retry or rerun individual lines/segments instead of restarting the whole render.
- Edit image/video prompts per row, save each field independently, or use `AI fill` to turn a rough draft into a production-ready scene prompt.
- Mark generated videos as approved with `OK`; approved rows are protected and skipped by later batch, selected-row, and redo generation actions.
- Track the global render queue in the project header and browser tab title, so other tabs show how many queued/running jobs remain.
- Choose whether clips use the base image or avatar image source.
- Keep uploads, generated files, database state, logs, and Python bytecode out of Git via `.gitignore`.

## Requirements

- Python 3.11+ recommended.
- A running ComfyUI instance, usually at `http://127.0.0.1:8188`.
- ComfyUI workflows exported into the local `workflows/` folder.
- `ffmpeg` available on `PATH` for audio splitting and final assembly.
- Optional but recommended: CUDA-capable GPU for faster Whisper alignment.

Python dependencies are listed in `requirements.txt`:

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python -m musicvideogen serve
```

Then open:

```text
http://127.0.0.1:8000
```

The server also accepts custom host/port values:

```powershell
python -m musicvideogen serve --host 127.0.0.1 --port 8001
```

There is also a batch file for this local machine:

```powershell
start.bat
```

## Quick Workflow

1. Start ComfyUI.
2. Put the required ComfyUI workflow JSON files into `workflows/`.
3. Start VocaVid with `python -m musicvideogen serve`.
4. Create a project with:
   - WAV audio file
   - SUNO-style lyrics file
   - genre
   - global style prompt, or use the UI button to generate one
   - reference image paths
   - resolution, FPS, and segment grouping settings
5. Click `Align` to align lyrics and build render segments.
6. Review and adjust line/segment timing where needed.
7. Click `Scene Plan` and edit/save the result if needed.
8. Click `Gen Prompts`.
9. Review prompts; use per-field `Save` or `AI fill` under the Image/Video text boxes for manual prompt refinement.
10. Click `Gen Images`.
11. Click `Gen Avatar Image` when you want reference-person variants.
12. Choose `Image` or `Avatar` as the clip source per row when both exist.
13. Click `Gen Video Prompts`.
14. Click `Gen Clips`.
15. Mark usable clips with `OK`.
16. Click `Assemble Final`.

Most actions can be run on selected rows only, so failed or weak segments can be rerendered without losing the whole project. Rows marked `OK` are treated as locked and are skipped even when selected or when processing the whole project.

## Workflow Files

Default workflow lookup is handled by `musicvideogen/workflows.py`.

| Purpose | Preferred file | Fallback/alias | Required |
| --- | --- | --- | --- |
| Text generation for global style, scene plan, image prompts, and video prompts | `workflows/promptgen.json` | none | No |
| Still image generation | `workflows/image.json` | `workflows/image_z_image_turbo.json` | Yes |
| Reference-image still generation | `workflows/image_reference.json` | falls back to image workflow | No |
| Avatar/reference-person image edit | `workflows/avatartoimage_flux.json` | none | Yes for `Gen Avatar Image` |
| Image/audio-to-video generation | `workflows/video.json` | `workflows/imageaudiotovideo.json` | Yes for `Gen Clips` |
| Chorus-specific workflow | `workflows/chorus.json` | none | Present in code, not part of the main UI path yet |

The repository includes example workflow files for the current local setup:

- `workflows/promptgen.json`
- `workflows/image_z_image_turbo.json`
- `workflows/avatartoimage_flux.json`
- `workflows/imageaudiotovideo.json`

Exported ComfyUI UI-format workflows are accepted; VocaVid converts them to API prompt format internally.

## Prompt Templates

Prompt instructions live in `prompts/` and can be edited without touching code:

- `prompts/global_style.txt`
- `prompts/sceneplan_concept.txt`
- `prompts/sceneplan.txt`
- `prompts/promptgen.txt`
- `prompts/scenefill.txt`
- `prompts/videoprompt.txt`
- `prompts/avatar_image.txt`

`prompts/scenefill.txt` powers the row-level `AI fill` buttons. If `workflows/promptgen.json` is missing, VocaVid falls back to deterministic local prompt text for image and video prompts where possible. Scene plans also have a local fallback.

## Template Variables

Workflow JSON and prompt templates can use either `{{ name }}` or `{NAME}` style placeholders.

Common variables:

- `lyric_text` / `LYRIC_TEXT`
- `lyrics` / `LYRICS`
- `section` / `SECTION`
- `is_chorus` / `IS_CHORUS`
- `use_reference_image`
- `mode` / `MODE`
- `global_style` / `GLOBAL_STYLE`
- `genre` / `GENRE`
- `duration` / `DURATION`
- `fps`
- `output_resolution`
- `scene_plan` / `SCENE_PLAN`

Image and video workflow variables:

- `prompt`
- `image_prompt` / `IMAGE_PROMPT`
- `video_prompt`
- `reference_image_paths`
- `reference_image_path`
- `reference_image_name`
- `fullbody_reference_image_path`
- `fullbody_reference_image_name`
- `base_image_path`
- `avatar_image_path`
- `source_image_path`
- `input_image_path`
- `image_path`
- `audio_path`

Scene-plan prompt variables:

- `total_segments` / `TOTAL_SEGMENTS`
- `lyric_group_size` / `LYRIC_GROUP_SIZE`
- `chorus_group_size` / `CHORUS_GROUP_SIZE`
- `first_index` / `FIRST_INDEX`
- `last_index` / `LAST_INDEX`
- `segments` / `SEGMENTS`
- `video_bible_context` / `VIDEO_BIBLE_CONTEXT`

## Reference Images and Chorus Shots

Lyrics are parsed from SUNO-style section tags such as `[Verse]`, `[Bridge]`, `[Chorus]`, and `[Refrain]`.

Chorus/refrain sections are treated as reference-capable performance shots by default. Individual lyric lines can also force reference-image use with an inline tag:

```text
[me] I stand in the smoke
```

The `[me]` tag is removed from the renderable lyric text. The first uploaded reference image is exposed as `reference_image_path`, and the bundled fallback images under `images/` are used when no project reference image is available.

## Local State and Outputs

Runtime files are intentionally local-only:

- `.musicvideogen/` contains uploads, generated outputs, and per-project assets.
- `musicvideogen.sqlite3` contains project state.
- `.musicvideogen-server*.log` files contain local server logs.
- `__pycache__/` contains Python bytecode.

These paths are ignored by Git. Do not commit generated media or local databases unless you explicitly intend to publish them.

## CLI Batch Render

After a project exists, this command runs the full pipeline for that project ID:

```powershell
python -m musicvideogen run --project 1
```

It performs even alignment, builds segments, generates a scene plan, prompts, images, clips, and then assembles the final output. The web UI is usually safer for real projects because it lets you inspect, correct, rerun, and approve intermediate results.

## Tests

Run the test suite with:

```powershell
python -m unittest discover -s tests
```

The tests cover workflow conversion, prompt/template behavior, alignment logic, UI HTML generation, project actions, segment planning, and assembly helpers.

## Troubleshooting

### ComfyUI connection fails

Check that ComfyUI is running and that the project setting points to the right base URL. The default is:

```text
http://127.0.0.1:8188
```

### Missing workflow error

Put the expected workflow JSON into `workflows/`. For image and video generation, aliases are accepted:

- image: `image.json` or `image_z_image_turbo.json`
- video: `video.json` or `imageaudiotovideo.json`

### Whisper alignment is slow or falls back

`faster-whisper` uses CUDA when available, then retries on CPU when CUDA fails or times out. Low-confidence rows are highlighted in the UI and can be corrected manually.

### Clips do not assemble

Make sure `ffmpeg` is available on `PATH` and that `templates/kdenlivetemplate.kdenlive` exists. Generated project media is stored under `.musicvideogen/outputs/`.

### Push/commit hygiene

Before committing changes:

```powershell
git status
git diff
```

The `.gitignore` is set up to keep local runtime data, generated outputs, logs, SQLite files, and Python caches out of commits.

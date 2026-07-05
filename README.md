# VocaVid

Local orchestration app for turning a WAV file, SUNO-style lyrics, a global style prompt, ComfyUI workflow templates, and reference images into a resumable music-video render.

## Run

```powershell
pip install -r requirements.txt
python -m musicvideogen serve
```

Then open `http://127.0.0.1:8000`.

## Workflow

1. Export your ComfyUI workflow templates into the local `workflows` folder:
   - `workflows/promptgen.json` optional; falls back to `lyrics + global style` when missing
   - `workflows/image.json`
   - `workflows/image_z_image_turbo.json` is also accepted as an image workflow alias
   - `workflows/image_reference.json` optional; used for lines marked as reference shots
   - `workflows/video.json`
   - `workflows/chorus.json`
2. Create a project with WAV, lyrics, style prompt, and reference images.
3. Click `Align` to create initial line timings. The first version distributes lines evenly over the WAV duration so you can correct timings manually in the UI.
4. Click `Generate Prompts`, `Generate Images`, `Generate Clips`, and `Assemble Final`.
5. Retry individual failed lines from the project detail table.

ComfyUI is expected at `http://127.0.0.1:8188` by default.

## Alignment

`Align` now uses local `faster-whisper` word timestamps on CUDA when available, then matches the transcript words against the SUNO lyric lines in order with fuzzy matching. The UI shows a confidence percentage per line.

If Whisper fails or a line cannot be matched confidently, the app falls back to evenly distributed timings and marks the row with low confidence.

## Promptgen Prompt

The instruction prompt sent into `workflows/promptgen.json` is editable here:

```text
prompts/promptgen.txt
```

Available placeholders:

- `{{ lyric_text }}`
- `{{ section }}`
- `{{ is_chorus }}`
- `{{ mode }}`
- `{{ duration }}`
- `{{ global_style }}`

## Image Reference Shots

Normal image generation uses `workflows/image.json`.

For shots that should include the uploaded reference image, either use a `[Chorus]`/`[Refrain]` section or mark an individual lyric line with an inline tag:

```text
[me] I stand in the smoke
```

The app strips `[me]` from the renderable lyric text and sets:

- `{{ use_reference_image }}` to `true`
- `{{ reference_image_path }}` to the first uploaded reference image path
- `{{ reference_image_name }}` to its filename

If `workflows/image_reference.json` exists, reference shots use that workflow. Otherwise they fall back to `workflows/image.json`.

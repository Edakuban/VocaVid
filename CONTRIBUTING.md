# Contributing to VocaVid

Thanks for your interest in improving VocaVid.

This is a small local-first project for orchestrating music-video generation
with ComfyUI. Contributions are welcome, especially when they keep the app
practical, resumable, and easy to run on a local machine.

## Before You Start

- Check existing issues and pull requests to avoid duplicate work.
- Open an issue first for larger changes, workflow changes, or behavior that
  could affect existing projects.
- Keep pull requests focused. Small, reviewable changes are much easier to
  merge.

## Development Setup

Use Python 3.11 or newer if possible.

```powershell
pip install -r requirements.txt
```

Run the app locally with:

```powershell
python -m VocaVid serve
```

Then open:

```text
http://127.0.0.1:8000
```

VocaVid expects a local ComfyUI instance for generation features, usually at:

```text
http://127.0.0.1:8188
```

Some features also require `ffmpeg` to be available on `PATH`.

## Tests

Please run the test suite before opening a pull request:

```powershell
pytest
```

If your change touches only documentation, tests are usually not necessary.

For changes involving ComfyUI workflows, file paths, prompt generation, project
state, or final video assembly, add or update focused tests where practical.

## Pull Request Guidelines

- Describe what changed and why.
- Mention any manual testing you performed.
- Include screenshots for visible UI changes when useful.
- Avoid committing local project outputs, generated assets, logs, caches, or
  machine-specific files.
- Keep generated media and large binary files out of the repository unless they
  are intentionally small fixtures.

## Coding Style

- Follow the style of the surrounding code.
- Prefer simple, explicit code over broad abstractions.
- Keep local workflows resumable; avoid changes that force users to restart a
  full render when only one segment failed.
- Treat user project files and generated assets carefully. Path handling should
  be predictable and should not write outside the intended project/output
  locations.

## Reporting Bugs

When reporting a bug, please include:

- what you expected to happen
- what actually happened
- steps to reproduce the issue
- relevant logs or traceback output
- your Python version
- whether ComfyUI and `ffmpeg` were available
- any workflow file names involved, if relevant

Please avoid attaching private audio, lyrics, images, or generated media unless
they are necessary and safe to share.

## Security Issues

Please do not report security vulnerabilities in public issues. See
`SECURITY.md` for the private reporting process.

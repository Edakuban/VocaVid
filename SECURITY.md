# Security Policy

## Supported Versions

VocaVid is a local-first project. Security updates are provided for the current
`main` branch only.

Older commits, forks, and local modifications are not actively supported.

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

If you believe you found a security issue, please report it privately using
GitHub's private vulnerability reporting feature, if available for this
repository.

If private vulnerability reporting is not available, contact the maintainer
directly through GitHub and include:

- a clear description of the issue
- steps to reproduce it
- the affected files, endpoints, or workflows
- any relevant logs or screenshots
- whether the issue requires local access, network access, or a malicious input
  file

Please avoid sharing exploit details publicly until the issue has been reviewed.

## Scope

Security issues may include, but are not limited to:

- unintended file access outside the project workspace
- unsafe handling of uploaded or referenced local files
- command execution risks
- exposure of local secrets, paths, logs, or generated assets
- unsafe network behavior in the local FastAPI app

The following are usually not considered security vulnerabilities:

- prompt quality problems
- failed ComfyUI generations
- local dependency installation issues
- unsupported custom ComfyUI workflows
- issues caused by modified forks or local changes

## Response Expectations

This is a small personal/open-source project, so response times may vary. I will
try to acknowledge valid reports as soon as practical and will prioritize fixes
based on severity and reproducibility.

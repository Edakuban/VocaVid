from __future__ import annotations

from pathlib import Path


DEFAULT_PROMPTGEN_TEMPLATE = """Create one concise image-generation prompt for a music video shot.

Lyric line: {{ lyric_text }}
Song section: {{ section }}
Mode: {{ mode }}
Clip duration seconds: {{ duration }}
Global visual style: {{ global_style }}
Genre: {{ genre }}
Avatar identity: {{ avatar_identity_context }}
Scene plan for this clip: {{ scene_plan }}

Focus on concrete subject, setting, mood, lighting, camera framing, and motion potential.
Do not quote the lyric as visible text.
Do not mention that this is a prompt.
Return only the image prompt, one paragraph, no markdown."""


def default_promptgen_path(project_root: Path | None = None) -> Path:
    return (project_root or Path.cwd()) / "prompts" / "promptgen.txt"


def default_named_prompt_path(name: str, project_root: Path | None = None) -> Path:
    return (project_root or Path.cwd()) / "prompts" / name


def load_prompt_template(path: Path | None = None) -> str:
    template_path = path or default_promptgen_path()
    if template_path.exists():
        return template_path.read_text(encoding="utf-8").strip()
    return DEFAULT_PROMPTGEN_TEMPLATE


def load_named_prompt_template(name: str, default: str = "", project_root: Path | None = None) -> str:
    template_path = default_named_prompt_path(name, project_root)
    if template_path.exists():
        return template_path.read_text(encoding="utf-8").strip()
    return default.strip()


def render_prompt_template(template: str, variables: dict[str, object]) -> str:
    rendered = template
    for key, value in variables.items():
        replacement = str(value)
        rendered = rendered.replace("{{ " + key + " }}", replacement)
        rendered = rendered.replace("{{" + key + "}}", replacement)
        rendered = rendered.replace("{" + key + "}", replacement)
        rendered = rendered.replace("{" + key.upper() + "}", replacement)
    return rendered

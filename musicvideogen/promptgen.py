from __future__ import annotations

from copy import deepcopy
from typing import Any

from .comfy import render_template
from .prompt_templates import load_named_prompt_template, load_prompt_template, render_prompt_template


DEFAULT_VIDEOPROMPT_TEMPLATE = """Create one concise image-to-video motion prompt for a music video segment.

Return only the video prompt. Do not include labels, markdown, quotes, or explanations.

Goal:
Generate a controlled image-to-video motion prompt that starts from the existing still image and preserves visual continuity.
Keep the same identity, face, wardrobe, setting, lighting, objects, pose, framing, and composition from the image prompt.
Animate only what is already visible or explicitly described in the image prompt or scene plan.

Mode: {MODE}
Section: {SECTION}
Duration seconds: {DURATION}
Genre: {GENRE}
Global visual style: {GLOBAL_STYLE}
Scene plan: {SCENE_PLAN}
Lyrics:
{LYRICS}

Image prompt:
{IMAGE_PROMPT}

Motion selection:

* Choose one motion approach that fits this specific scene, section, duration, and energy.
* Do not default to a slow push-in. Use it only when the scene plan or emotion clearly benefits from that choice.
* Prefer varied controlled motion across segments: lateral tracking, gentle crane rise, rack focus, foreground wipes, slow reveal, parallax drift, subtle handheld tension, locked-off rhythmic environment motion, or a small motivated pan or tilt.
* For story or atmosphere shots, motion may come from the subject, camera, foreground, weather, light, particles, props already present, or the environment.
* For performance shots, keep the singer lip-sync stable while making the frame feel alive through expression, light, atmosphere, and motivated camera movement.
* If any character, singer, performer, face, or person is visible, show visible singing or lip-sync with clear but natural mouth movement matched to the lyric emotion.
* Visible characters should not be silent posing, silently staring, or acting out unrelated business while the lyric plays.

Performance shot rules:

* The singer stays in the same physical position throughout the shot.
* The singer does not walk, run, step forward, approach the camera, dance, jump, or make large body movements.
* Motion should come from facial expression, mouth movement, breath, eye contact, slight head movement, small shoulder tension, hair, clothing, and the environment.
* Keep the face and head stable enough for later lip-sync.
* Describe singing intensity through the mouth, eyes, jaw, breath, and expression, not through body travel.
* The singer should remain centered and recognizable, with stable facial features.

Camera rules:

* Use controlled camera movement only.
* Good options: locked-off shot with active environment motion, lateral tracking, gentle crane rise, rack focus, foreground wipe, slow reveal, parallax drift, subtle zoom, gentle handheld micro-drift, small tilt, minimal pan, or a restrained push-in.
* If using a push-in or zoom, clearly state that the camera moves while the singer remains fixed in place.
* Avoid strong orbit, fast dolly, shaky handheld, whip pan, or aggressive reframing unless explicitly required.

Environment motion:

* Add subtle believable movement in the scene: smoke drifting, embers floating, rain falling, lights flickering, shadows moving, fabric shifting, hair moving, dust in the air.
* Environment motion should support the rhythm and emotion without changing the scene layout.

Forbidden:
walking, running, stepping forward, moving toward camera, lunging, dancing, jumping, large gestures, full-body travel, camera chasing the subject, unstable framing, face leaving frame, identity change, warped face, wardrobe change, setting change.
Do not invent new props, furniture, vehicles, food, drinks, weapons, or everyday actions not already present or requested. No coffee cup, no mug, no drinking, no sitting down, no standing up, no picking up objects, and no entering or leaving the scene unless explicitly described.

Output:
Write one concise cinematic motion prompt in 2-4 sentences.
Clearly separate subject motion, camera motion, and environment motion."""


DEFAULT_GLOBAL_STYLE_TEMPLATE = """Ich will ein KI-Musikvideo zu dem Song erstellen. Welchen 'Global Style Prompt' sollte ich nutzen?

Genre: {GENRE}
Lyrics: {LYRICS}

Return only the Global Style Prompt. Do not include labels, markdown, quotes, or explanations."""


DEFAULT_SCENEFILL_TEMPLATE = """Transform the user's draft into one concise, production-ready scene prompt for this music video segment.

Return only the rewritten prompt. Do not include labels, markdown, quotes, or explanations.

Target field: {TARGET_FIELD}
Mode: {MODE}
Section: {SECTION}
Duration seconds: {DURATION}
Genre: {GENRE}
Global visual style: {GLOBAL_STYLE}
Scene plan: {SCENE_PLAN}
Lyrics:
{LYRICS}

Current image prompt:
{IMAGE_PROMPT}

Current video prompt:
{VIDEO_PROMPT}

User draft:
{DRAFT_TEXT}

Rules:
* Preserve the user's intent, subject, setting, mood, and any concrete visual details.
* Convert vague wording into a specific cinematic scene with subject, setting, lighting, framing, atmosphere, and production design.
* If target field is image, write a still-image scene prompt with strong visual composition and no motion instructions.
* If target field is video, write an image-to-video motion prompt that preserves the existing image prompt and adds controlled subject, camera, and environment motion.
* Do not quote the lyric as visible text.
* Do not invent unrelated everyday props or actions.
* Keep it concise and directly usable."""


def make_promptgen_prompt(
    lyric_text: str,
    section: str = "",
    is_chorus: bool = False,
    global_style: str = "",
    duration: str = "",
    genre: str = "",
    scene_plan: str = "",
) -> str:
    mode = "chorus/refrain featuring the singer" if is_chorus else "non-chorus story visual"
    return render_prompt_template(
        load_prompt_template(),
        _prompt_variables(
            lyric_text=lyric_text,
            section=section,
            is_chorus=is_chorus,
            mode=mode,
            global_style=global_style,
            duration=duration,
            genre=genre,
            scene_plan=scene_plan,
        ),
    )


def make_videoprompt_prompt(
    lyric_text: str,
    image_prompt: str = "",
    section: str = "",
    is_chorus: bool = False,
    global_style: str = "",
    duration: str = "",
    genre: str = "",
    scene_plan: str = "",
) -> str:
    mode = "performance shot featuring the singer" if is_chorus else "story or atmosphere shot"
    return render_prompt_template(
        load_named_prompt_template("videoprompt.txt", DEFAULT_VIDEOPROMPT_TEMPLATE),
        _prompt_variables(
            lyric_text=lyric_text,
            image_prompt=image_prompt,
            section=section,
            is_chorus=is_chorus,
            mode=mode,
            global_style=global_style,
            duration=duration,
            genre=genre,
            scene_plan=scene_plan,
        ),
    )


def make_global_style_prompt(genre: str, lyrics: str) -> str:
    return render_prompt_template(
        load_named_prompt_template("global_style.txt", DEFAULT_GLOBAL_STYLE_TEMPLATE),
        _prompt_variables(lyric_text=lyrics, genre=genre),
    )


def make_scenefill_prompt(
    draft_text: str,
    target_field: str,
    lyric_text: str,
    image_prompt: str = "",
    video_prompt: str = "",
    section: str = "",
    is_chorus: bool = False,
    global_style: str = "",
    duration: str = "",
    genre: str = "",
    scene_plan: str = "",
) -> str:
    mode = "performance shot featuring the singer" if is_chorus else "story or atmosphere shot"
    return render_prompt_template(
        load_named_prompt_template("scenefill.txt", DEFAULT_SCENEFILL_TEMPLATE),
        {
            **_prompt_variables(
                lyric_text=lyric_text,
                image_prompt=image_prompt,
                section=section,
                is_chorus=is_chorus,
                mode=mode,
                global_style=global_style,
                duration=duration,
                genre=genre,
                scene_plan=scene_plan,
            ),
            "draft_text": draft_text,
            "DRAFT_TEXT": draft_text,
            "target_field": target_field,
            "TARGET_FIELD": target_field,
            "video_prompt": video_prompt,
            "VIDEO_PROMPT": video_prompt,
        },
    )


def _prompt_variables(
    lyric_text: str = "",
    image_prompt: str = "",
    section: str = "",
    is_chorus: bool = False,
    mode: str = "",
    global_style: str = "",
    duration: str = "",
    genre: str = "",
    scene_plan: str = "",
) -> dict[str, object]:
    return {
        "lyric_text": lyric_text,
        "LYRIC_TEXT": lyric_text,
        "lyrics": lyric_text,
        "LYRICS": lyric_text,
        "image_prompt": image_prompt,
        "IMAGE_PROMPT": image_prompt,
        "section": section,
        "SECTION": section,
        "is_chorus": str(is_chorus).lower(),
        "IS_CHORUS": str(is_chorus).lower(),
        "mode": mode,
        "MODE": mode,
        "global_style": global_style,
        "GLOBAL_STYLE": global_style,
        "duration": duration,
        "DURATION": duration,
        "genre": genre,
        "GENRE": genre,
        "scene_plan": scene_plan,
        "SCENE_PLAN": scene_plan,
    }


def inject_promptgen_context(workflow_template: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    if _has_placeholder(workflow_template):
        return render_template(workflow_template, variables)

    workflow = deepcopy(workflow_template)
    prompt = make_promptgen_prompt(
        lyric_text=str(variables.get("lyric_text", "")),
        section=str(variables.get("section", "")),
        is_chorus=str(variables.get("is_chorus", "")).lower() == "true",
        global_style=str(variables.get("global_style", "")),
        duration=str(variables.get("duration", "")),
        genre=str(variables.get("genre", "")),
        scene_plan=str(variables.get("scene_plan", "")),
    )
    node = _find_text_prompt_node(workflow)
    if node is None:
        raise ValueError("promptgen.json needs a TextGenerate node with inputs.prompt, or {{ lyric_text }} placeholders")
    node["inputs"]["prompt"] = prompt
    return workflow


def inject_videoprompt_context(workflow_template: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    if _has_placeholder(workflow_template):
        return render_template(workflow_template, variables)

    workflow = deepcopy(workflow_template)
    prompt = make_videoprompt_prompt(
        lyric_text=str(variables.get("lyric_text", "")),
        image_prompt=str(variables.get("image_prompt", variables.get("prompt", ""))),
        section=str(variables.get("section", "")),
        is_chorus=str(variables.get("is_chorus", "")).lower() == "true",
        global_style=str(variables.get("global_style", "")),
        duration=str(variables.get("duration", "")),
        genre=str(variables.get("genre", "")),
        scene_plan=str(variables.get("scene_plan", "")),
    )
    node = _find_text_prompt_node(workflow)
    if node is None:
        raise ValueError("promptgen.json needs a TextGenerate node with inputs.prompt, or {{ lyric_text }} placeholders")
    node["inputs"]["prompt"] = prompt
    return workflow


def inject_scenefill_context(workflow_template: dict[str, Any], variables: dict[str, Any], target_field: str, draft_text: str) -> dict[str, Any]:
    workflow = deepcopy(workflow_template)
    prompt = make_scenefill_prompt(
        draft_text=draft_text,
        target_field=target_field,
        lyric_text=str(variables.get("lyric_text", "")),
        image_prompt=str(variables.get("image_prompt", variables.get("prompt", ""))),
        video_prompt=str(variables.get("video_prompt", "")),
        section=str(variables.get("section", "")),
        is_chorus=str(variables.get("is_chorus", "")).lower() == "true",
        global_style=str(variables.get("global_style", "")),
        duration=str(variables.get("duration", "")),
        genre=str(variables.get("genre", "")),
        scene_plan=str(variables.get("scene_plan", "")),
    )
    node = _find_text_prompt_node(workflow)
    if node is None:
        raise ValueError("promptgen.json needs a TextGenerate node with inputs.prompt")
    node["inputs"]["prompt"] = prompt
    return workflow


def inject_raw_text_prompt(workflow_template: dict[str, Any], prompt: str) -> dict[str, Any]:
    workflow = deepcopy(workflow_template)
    node = _find_text_prompt_node(workflow)
    if node is None:
        raise ValueError("Workflow needs a text prompt node")
    node["inputs"]["prompt"] = prompt
    return workflow


def _has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "{{" in value and "}}" in value
    if isinstance(value, list):
        return any(_has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(_has_placeholder(item) for item in value.values())
    return False


def _find_text_prompt_node(workflow: dict[str, Any]) -> dict[str, Any] | None:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or "prompt" not in inputs:
            continue
        class_type = str(node.get("class_type", "")).lower()
        title = str(node.get("_meta", {}).get("title", "")).lower()
        if "textgenerate" in class_type or "generate text" in title or "gemma" in class_type:
            return node
    for node in workflow.values():
        if isinstance(node, dict) and isinstance(node.get("inputs"), dict) and "prompt" in node["inputs"]:
            return node
    return None

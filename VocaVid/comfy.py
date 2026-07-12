from __future__ import annotations

import json
import copy
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .models import ComfyResult


class JsonTransport(Protocol):
    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def get_json(self, url: str) -> dict[str, Any]:
        ...


class UrlLibTransport:
    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_json(self, url: str) -> dict[str, Any]:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", transport: JsonTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.transport = transport or UrlLibTransport()

    def run_workflow(
        self,
        workflow_template: dict[str, Any],
        variables: dict[str, Any],
        poll_interval_sec: float = 1.0,
        timeout_sec: float = 900.0,
    ) -> ComfyResult:
        prompt = render_template(workflow_template, variables)
        try:
            submit = self.transport.post_json(f"{self.base_url}/prompt", {"prompt": prompt})
        except urllib.error.HTTPError as exc:
            return ComfyResult(prompt_id="", ok=False, output_files=[], error=self.http_error_message(exc))
        except (OSError, urllib.error.URLError) as exc:
            return ComfyResult(prompt_id="", ok=False, output_files=[], error=str(exc))

        prompt_id = str(submit.get("prompt_id", ""))
        if not prompt_id:
            return ComfyResult(prompt_id="", ok=False, output_files=[], error="ComfyUI did not return a prompt_id")

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() <= deadline:
            history = self.transport.get_json(f"{self.base_url}/history/{prompt_id}")
            entry = history.get(prompt_id, {})
            status = entry.get("status", {})
            if status.get("completed") is True:
                return ComfyResult(
                    prompt_id=prompt_id,
                    ok=True,
                    output_files=extract_output_files(entry),
                    text_outputs=extract_text_outputs(entry),
                )
            if status.get("status_str") == "error":
                return ComfyResult(prompt_id=prompt_id, ok=False, output_files=[], error=_status_error(status))
            if poll_interval_sec:
                time.sleep(poll_interval_sec)

        return ComfyResult(prompt_id=prompt_id, ok=False, output_files=[], error="Timed out waiting for ComfyUI job")

    @staticmethod
    def http_error_message(exc: urllib.error.HTTPError) -> str:
        body = exc.read().decode("utf-8", errors="replace")
        return f"HTTP Error {exc.code}: {exc.reason}. {body}".strip()


def load_workflow(path: Path) -> dict[str, Any]:
    return load_workflow_from_data(json.loads(path.read_text(encoding="utf-8")))


def load_workflow_from_data(data: dict[str, Any]) -> dict[str, Any]:
    if "nodes" not in data or not isinstance(data.get("nodes"), list):
        return data
    return _ui_workflow_to_api_prompt(data)


def _ui_workflow_to_api_prompt(data: dict[str, Any]) -> dict[str, Any]:
    link_lookup = _ui_link_lookup(data.get("links", []))
    subgraphs = {item.get("id"): item for item in data.get("definitions", {}).get("subgraphs", [])}
    subgraph_outputs: dict[tuple[int, int], tuple[str, int]] = {}
    prompt: dict[str, Any] = {}
    for node in data.get("nodes", []):
        if node.get("type") in subgraphs:
            subgraph_outputs.update(_expand_subgraph_instance(prompt, node, subgraphs[node.get("type")]))

    for node in data.get("nodes", []):
        if _is_ui_only_node(node):
            continue
        if node.get("type") in subgraphs:
            continue
        node_id = str(node["id"])
        inputs: dict[str, Any] = {}
        widget_values = list(node.get("widgets_values") or [])
        widget_index = 0
        for item in node.get("inputs", []) or []:
            name = item.get("name")
            if not name:
                continue
            link = item.get("link")
            if link is not None and link in link_lookup:
                source_id, source_slot = link_lookup[link]
                source = subgraph_outputs.get((source_id, source_slot), (str(source_id), source_slot))
                inputs[name] = [source[0], source[1]]
            elif item.get("widget") is not None:
                if widget_index < len(widget_values):
                    inputs[name] = widget_values[widget_index]
                    widget_index += 1
                elif item.get("type") == "STRING":
                    inputs[name] = "{{ prompt }}"
            elif item.get("type") == "STRING":
                inputs[name] = "{{ prompt }}"
        if node.get("type") == "SaveImage" and widget_values and "filename_prefix" not in inputs:
            inputs["filename_prefix"] = widget_values[0]
        _apply_widget_defaults(str(node.get("type", "")), widget_values, inputs)
        prompt[node_id] = {"class_type": node.get("type"), "inputs": inputs}
    return prompt


def _expand_subgraph_instance(
    prompt: dict[str, Any],
    instance: dict[str, Any],
    subgraph: dict[str, Any],
) -> dict[tuple[int, int], tuple[str, int]]:
    instance_id = int(instance["id"])
    prefix = f"{instance_id}_"
    external_inputs = _subgraph_external_inputs(instance, subgraph)
    output_map = _subgraph_output_map(instance_id, prefix, subgraph)
    link_lookup = _ui_link_lookup(subgraph.get("links", []))

    for node in subgraph.get("nodes", []):
        if _is_ui_only_node(node):
            continue
        node_id = int(node["id"])
        if node_id < 0:
            continue
        api_id = f"{prefix}{node_id}"
        inputs: dict[str, Any] = {}
        widget_values = list(node.get("widgets_values") or [])
        widget_index = 0
        for item in node.get("inputs", []) or []:
            name = item.get("name")
            if not name:
                continue
            link = item.get("link")
            if link is not None and link in external_inputs:
                inputs[name] = external_inputs[link]
            elif link is not None and link in link_lookup:
                source_id, source_slot = link_lookup[link]
                if source_id >= 0:
                    inputs[name] = [f"{prefix}{source_id}", source_slot]
                elif item.get("widget") is not None:
                    if widget_index < len(widget_values):
                        inputs[name] = widget_values[widget_index]
                        widget_index += 1
                    elif item.get("type") == "STRING":
                        inputs[name] = "{{ prompt }}"
            elif item.get("widget") is not None:
                if widget_index < len(widget_values):
                    inputs[name] = widget_values[widget_index]
                    widget_index += 1
                elif item.get("type") == "STRING":
                    inputs[name] = "{{ prompt }}"
            elif item.get("type") == "STRING":
                inputs[name] = "{{ prompt }}"
        _apply_widget_defaults(str(node.get("type", "")), widget_values, inputs)
        prompt[api_id] = {"class_type": node.get("type"), "inputs": inputs}
    return output_map


def _subgraph_external_inputs(instance: dict[str, Any], subgraph: dict[str, Any]) -> dict[int, Any]:
    instance_inputs = {item.get("name"): item for item in instance.get("inputs", []) or []}
    values: dict[int, Any] = {}
    for item in subgraph.get("inputs", []) or []:
        name = item.get("name")
        input_def = instance_inputs.get(name, {})
        if not input_def:
            continue
        value = "{{ prompt }}" if input_def.get("type") == "STRING" else None
        for link_id in item.get("linkIds", []) or []:
            values[int(link_id)] = value
    return values


def _subgraph_output_map(instance_id: int, prefix: str, subgraph: dict[str, Any]) -> dict[tuple[int, int], tuple[str, int]]:
    output_links: dict[int, int] = {}
    for slot, item in enumerate(subgraph.get("outputs", []) or []):
        for link_id in item.get("linkIds", []) or []:
            output_links[int(link_id)] = slot

    result: dict[tuple[int, int], tuple[str, int]] = {}
    for link in subgraph.get("links", []) or []:
        if isinstance(link, dict):
            link_id = int(link["id"])
            if link_id in output_links:
                result[(instance_id, output_links[link_id])] = (f"{prefix}{int(link['origin_id'])}", int(link["origin_slot"]))
        elif isinstance(link, list) and len(link) >= 4:
            link_id = int(link[0])
            if link_id in output_links:
                result[(instance_id, output_links[link_id])] = (f"{prefix}{int(link[1])}", int(link[2]))
    return result


def _apply_widget_defaults(class_type: str, widget_values: list[Any], inputs: dict[str, Any]) -> None:
    mappings = {
        "CLIPLoader": {"clip_name": 0, "type": 1, "device": 2},
        "UNETLoader": {"unet_name": 0, "weight_dtype": 1},
        "VAELoader": {"vae_name": 0},
        "EmptySD3LatentImage": {"width": 0, "height": 1, "batch_size": 2},
        "KSampler": {
            "seed": 0,
            "steps": 2,
            "cfg": 3,
            "sampler_name": 4,
            "scheduler": 5,
            "denoise": 6,
        },
        "ModelSamplingAuraFlow": {"shift": 0},
        "SaveImage": {"filename_prefix": 0},
    }
    for name, index in mappings.get(class_type, {}).items():
        if index < len(widget_values):
            inputs[name] = widget_values[index]


def _is_ui_only_node(node: dict[str, Any]) -> bool:
    return str(node.get("type", "")).lower() in {"markdownnote", "note", "reroute"}


def _ui_link_lookup(links: list[Any]) -> dict[int, tuple[int, int]]:
    lookup: dict[int, tuple[int, int]] = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 4:
            link_id, origin_id, origin_slot = int(link[0]), int(link[1]), int(link[2])
            lookup[link_id] = (origin_id, origin_slot)
        elif isinstance(link, dict):
            lookup[int(link["id"])] = (int(link["origin_id"]), int(link["origin_slot"]))
    return lookup


def render_template(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        rendered = value
        for key, replacement in variables.items():
            rendered = rendered.replace("{{ " + key + " }}", str(replacement))
            rendered = rendered.replace("{{" + key + "}}", str(replacement))
        return rendered
    if isinstance(value, list):
        return [render_template(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render_template(item, variables) for key, item in value.items()}
    return value


def with_output_prefix(workflow_template: dict[str, Any], prefix: str) -> dict[str, Any]:
    workflow = copy.deepcopy(workflow_template)
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if node.get("class_type") == "SaveImage" or "filename_prefix" in inputs:
            inputs["filename_prefix"] = prefix
    return workflow


def extract_output_files(history_entry: dict[str, Any]) -> list[str]:
    files: list[str] = []
    outputs = history_entry.get("outputs", {})
    for output in outputs.values():
        for key in ("images", "videos", "gifs"):
            for item in output.get(key, []):
                filename = item.get("filename")
                if not filename:
                    continue
                subfolder = item.get("subfolder") or ""
                files.append((Path(subfolder) / filename).as_posix() if subfolder else filename)
    return files


def extract_text_outputs(history_entry: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    outputs = history_entry.get("outputs", {})
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        for key in ("text", "texts", "string", "strings", "result", "results"):
            value = output.get(key)
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, list):
                texts.extend(str(item) for item in value if item is not None)
    return texts


def _status_error(status: dict[str, Any]) -> str:
    messages = status.get("messages", [])
    if isinstance(messages, list) and messages:
        return " ".join(str(message) for message in messages)
    return str(status)

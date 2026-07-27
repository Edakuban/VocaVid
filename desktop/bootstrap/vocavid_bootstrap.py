from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable

USER_AGENT = "VocaVid-Desktop/1.0"
MARKER_NAME = "install-state.json"
SEVEN_ZIP_NAME = "7zr.exe"


class BootstrapError(RuntimeError):
    pass


def emit(kind: str, message: str, **data: Any) -> None:
    print(json.dumps({"kind": kind, "message": message, **data}, ensure_ascii=True), flush=True)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"Manifest kann nicht gelesen werden: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise BootstrapError("Nicht unterstützte Manifest-Version")
    return manifest


def default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "VocaVid"


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _request(url: str, headers: dict[str, str] | None = None) -> urllib.request.Request:
    merged = {"User-Agent": USER_AGENT}
    merged.update(headers or {})
    return urllib.request.Request(url, headers=merged)


def github_release_asset(runtime: dict[str, Any]) -> tuple[str, str | None, str]:
    repository = runtime["repository"]
    tag = runtime["tag"]
    pattern = re.compile(runtime["asset_pattern"], re.IGNORECASE)
    api_url = f"https://api.github.com/repos/{repository}/releases/tags/{tag}"
    try:
        with urllib.request.urlopen(_request(api_url), timeout=30) as response:
            release = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"ComfyUI-Release konnte nicht aufgelöst werden: {exc}") from exc
    matches = [asset for asset in release.get("assets", []) if pattern.search(asset.get("name", ""))]
    if not matches:
        raise BootstrapError(f"Kein passendes ComfyUI-Archiv in {repository} {tag} gefunden")
    preferred = sorted(matches, key=lambda item: ("cu" not in item["name"].lower(), item["name"]))[0]
    digest = preferred.get("digest") or ""
    expected = digest.removeprefix("sha256:") if digest.startswith("sha256:") else None
    return preferred["browser_download_url"], expected, preferred["name"]


def resolve_archive(runtime: dict[str, Any]) -> tuple[str, str | None, str]:
    if runtime.get("kind") == "github_release_asset":
        return github_release_asset(runtime)
    url = runtime.get("url")
    if not url:
        raise BootstrapError("Runtime-Download ist im Manifest nicht definiert")
    return url, runtime.get("sha256"), Path(urllib.parse.urlparse(url).path).name


def download(
    url: str,
    target: Path,
    expected_sha256: str | None = None,
    request_headers: dict[str, str] | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    existing = partial.stat().st_size if partial.exists() else 0
    headers = dict(request_headers or {})
    if existing:
        headers["Range"] = f"bytes={existing}-"
    emit(
        "download",
        f"Lade {target.name}",
        file=target.name,
        current=existing,
        initial=True,
    )
    try:
        response = urllib.request.urlopen(_request(url, headers), timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise BootstrapError(
                f"Download nicht autorisiert ({target.name}). "
                "Bitte Modelllizenz auf Hugging Face akzeptieren und einen gültigen Read-Token verwenden."
            ) from exc
        raise BootstrapError(f"Download fehlgeschlagen ({target.name}): HTTP {exc.code}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise BootstrapError(f"Download fehlgeschlagen ({target.name}): {exc}") from exc
    status = getattr(response, "status", 200)
    if existing and status != 206:
        existing = 0
        partial.unlink(missing_ok=True)
    total_header = response.headers.get("Content-Length")
    total = existing + int(total_header) if total_header else None
    mode = "ab" if existing else "wb"
    downloaded = existing
    last_update = 0.0
    with response, partial.open(mode) as output:
        while chunk := response.read(4 * 1024 * 1024):
            output.write(chunk)
            downloaded += len(chunk)
            now = time.monotonic()
            if now - last_update >= 0.5:
                emit(
                    "download",
                    f"Lade {target.name}",
                    file=target.name,
                    current=downloaded,
                    total=total,
                )
                last_update = now
    if expected_sha256:
        emit("verify", f"Prüfe {target.name}")
        actual = sha256_file(partial)
        if actual.lower() != expected_sha256.lower():
            partial.unlink(missing_ok=True)
            raise BootstrapError(f"SHA-256 stimmt nicht für {target.name}: {actual}")
    partial.replace(target)
    emit(
        "downloaded",
        f"{target.name} vollständig",
        file=target.name,
        current=downloaded,
        total=total,
    )


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_remove(path: Path, root: Path) -> None:
    if not _within(path, root) or path.resolve() == root.resolve():
        raise BootstrapError(f"Unsicheres Löschziel verweigert: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def seven_zip_executable() -> Path:
    candidates: list[Path] = []
    override = os.environ.get("VOCAVID_7ZR")
    if override:
        candidates.append(Path(override))
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / SEVEN_ZIP_NAME)
    candidates.extend(
        [
            Path(sys.executable).resolve().parent / SEVEN_ZIP_NAME,
            Path(__file__).resolve().parent / SEVEN_ZIP_NAME,
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for command in ("7zr.exe", "7z.exe", "7zr", "7z"):
        located = shutil.which(command)
        if located:
            return Path(located)
    raise BootstrapError("Der gebündelte 7-Zip-Entpacker fehlt")


def extract_archive(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    emit("extract", f"Entpacke {archive.name}")
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(target)
        return
    if archive.suffix.lower() == ".7z":
        run_checked(
            [
                str(seven_zip_executable()),
                "x",
                str(archive),
                f"-o{target}",
                "-y",
                "-bso0",
                "-bsp0",
            ]
        )
        return
    raise BootstrapError(f"Unbekanntes Archivformat: {archive.suffix}")


def find_portable_root(directory: Path, runtime: dict[str, Any]) -> Path:
    python_rel = Path(runtime["python"])
    comfy_rel = Path(runtime["comfy_main"])
    candidates = [directory, *[item for item in directory.rglob("*") if item.is_dir()]]
    for candidate in candidates:
        if (candidate / python_rel).is_file() and (candidate / comfy_rel).is_file():
            return candidate
    raise BootstrapError("Das ComfyUI-Portable-Verzeichnis wurde im Archiv nicht gefunden")


def runtime_paths(root: Path, manifest: dict[str, Any]) -> tuple[Path, Path, Path]:
    runtime_root = root / "runtime"
    runtime = manifest["runtime"]
    return runtime_root, runtime_root / runtime["python"], runtime_root / runtime["comfy_main"]


def read_state(root: Path) -> dict[str, Any]:
    marker = root / MARKER_NAME
    if not marker.is_file():
        return {}
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(root: Path, state: dict[str, Any]) -> None:
    marker = root / MARKER_NAME
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(marker)


def normalize_local_comfy_url(value: str) -> str:
    candidate = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise BootstrapError("Die vorhandene ComfyUI muss über eine lokale http(s)-Adresse erreichbar sein")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise BootstrapError("Die ComfyUI-Adresse darf keinen Pfad, Query oder Fragment enthalten")
    try:
        port = parsed.port
    except ValueError as exc:
        raise BootstrapError("Die ComfyUI-Adresse enthält einen ungültigen Port") from exc
    if port is None:
        candidate = f"{parsed.scheme}://{parsed.hostname}:{443 if parsed.scheme == 'https' else 80}"
    return candidate


def resolve_shared_models_root(value: str | None) -> Path | None:
    if not value:
        return None
    candidate = Path(value).expanduser().resolve()
    options = [candidate]
    if candidate.name.lower() != "models":
        options.extend([candidate / "models", candidate / "ComfyUI" / "models"])
    for option in options:
        if option.is_dir() and option.name.lower() == "models":
            return option
    raise BootstrapError(
        "Der angegebene Pfad enthält keinen ComfyUI-models-Ordner. "
        "Bitte den ComfyUI-, ComfyUI/models- oder Portable-Hauptordner angeben."
    )


def configure_shared_models(runtime_root: Path, models_root: Path | None) -> None:
    config = runtime_root / "ComfyUI" / "extra_model_paths.yaml"
    if models_root is None:
        config.unlink(missing_ok=True)
        return
    escaped = str(models_root).replace("'", "''")
    categories = (
        "checkpoints",
        "diffusion_models",
        "text_encoders",
        "vae",
        "loras",
        "latent_upscale_models",
    )
    lines = ["vocavid_shared:", f"  base_path: '{escaped}'"]
    lines.extend(f"  {category}: {category}" for category in categories)
    config.write_text("\n".join(lines) + "\n", encoding="utf-8")


def deploy_runtime(root: Path, manifest: dict[str, Any]) -> None:
    runtime_root, python, comfy_main = runtime_paths(root, manifest)
    if python.is_file() and comfy_main.is_file():
        data: dict[str, Any] = {}
        asset_pattern = manifest["runtime"].get("asset_pattern")
        downloads = root / "downloads"
        if asset_pattern and downloads.is_dir():
            archive = next(
                (
                    item
                    for item in downloads.iterdir()
                    if item.is_file() and re.search(asset_pattern, item.name, re.IGNORECASE)
                ),
                None,
            )
            if archive:
                data = {"file": archive.name, "current": archive.stat().st_size, "initial": True}
        emit("skip", "ComfyUI-Runtime ist bereits vorhanden", **data)
        return
    url, expected, filename = resolve_archive(manifest["runtime"])
    archive = root / "downloads" / filename
    if not archive.is_file() or (expected and sha256_file(archive).lower() != expected.lower()):
        download(url, archive, expected)
    staging = root / ".runtime-staging"
    if staging.exists():
        safe_remove(staging, root)
    extract_archive(archive, staging)
    portable_root = find_portable_root(staging, manifest["runtime"])
    if runtime_root.exists():
        safe_remove(runtime_root, root)
    shutil.move(str(portable_root), str(runtime_root))
    if staging.exists():
        safe_remove(staging, root)


def deploy_application(root: Path, payload: Path) -> Path:
    if not payload.is_file():
        raise BootstrapError(f"VocaVid-Payload fehlt: {payload}")
    workspace = root / "workspace"
    staging = root / ".workspace-staging"
    if staging.exists():
        safe_remove(staging, root)
    extract_archive(payload, staging)
    if workspace.exists():
        state = workspace / ".VocaVid"
        preserved = root / ".preserved-state"
        if preserved.exists():
            safe_remove(preserved, root)
        if state.exists():
            shutil.move(str(state), str(preserved))
        safe_remove(workspace, root)
        shutil.move(str(staging), str(workspace))
        if preserved.exists():
            shutil.move(str(preserved), str(workspace / ".VocaVid"))
    else:
        shutil.move(str(staging), str(workspace))
    return workspace


def run_checked(command: list[str], cwd: Path | None = None) -> None:
    display = Path(command[0]).name
    emit("command", f"Führe {display} aus")
    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        emit("command-output", line.rstrip())
    if process.wait() != 0:
        raise BootstrapError(f"{display} ist mit Code {process.returncode} fehlgeschlagen")


def install_python_dependencies(root: Path, manifest: dict[str, Any], workspace: Path) -> None:
    _, python, _ = runtime_paths(root, manifest)
    app = manifest["application"]
    requirements = workspace / app["requirements"]
    if requirements.is_file():
        run_checked([str(python), "-s", "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)])
    packages = list(app.get("pip_packages", []))
    if packages:
        run_checked([str(python), "-s", "-m", "pip", "install", "--disable-pip-version-check", *packages])
    tools = workspace / "bin"
    tools.mkdir(exist_ok=True)
    locator = "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
    located = subprocess.run([str(python), "-s", "-c", locator], check=True, capture_output=True, text=True)
    ffmpeg_source = Path(located.stdout.strip())
    if ffmpeg_source.is_file():
        shutil.copy2(ffmpeg_source, tools / "ffmpeg.exe")


def selected_entries(manifest: dict[str, Any], profiles: Iterable[str], key: str) -> list[str]:
    result: list[str] = []
    for profile in profiles:
        definition = manifest.get("profiles", {}).get(profile)
        if not definition:
            raise BootstrapError(f"Unbekanntes Installationsprofil: {profile}")
        for entry in definition.get(key, []):
            if entry not in result:
                result.append(entry)
    return result


def install_models(
    root: Path,
    manifest: dict[str, Any],
    profiles: list[str],
    *,
    huggingface_token: str | None = None,
    flux_license_accepted: bool = False,
    shared_models_root: Path | None = None,
) -> None:
    runtime_root, _, _ = runtime_paths(root, manifest)
    comfy_root = runtime_root / "ComfyUI"
    for model_id in selected_entries(manifest, profiles, "models"):
        model = manifest.get("models", {}).get(model_id)
        if not model:
            raise BootstrapError(f"Modelleintrag fehlt: {model_id}")
        target = comfy_root / model["target"]
        expected = model["sha256"]
        if target.is_file() and sha256_file(target).lower() == expected.lower():
            emit(
                "skip",
                f"Modell bereits vorhanden: {target.name}",
                file=target.name,
                current=target.stat().st_size,
                initial=True,
            )
            continue
        if shared_models_root is not None:
            relative = Path(model["target"])
            parts = relative.parts[1:] if relative.parts and relative.parts[0].lower() == "models" else relative.parts
            shared_target = shared_models_root.joinpath(*parts)
            if shared_target.is_file() and sha256_file(shared_target).lower() == expected.lower():
                emit(
                    "skip",
                    f"Modell aus vorhandenem Ordner eingebunden: {target.name}",
                    file=target.name,
                    current=shared_target.stat().st_size,
                    initial=True,
                )
                continue
        headers: dict[str, str] = {}
        if model.get("gated"):
            if not flux_license_accepted:
                raise BootstrapError("Die FLUX.2-Lizenz muss vor dem Download ausdrücklich akzeptiert werden")
            if not huggingface_token:
                raise BootstrapError("Für das gated FLUX.2-Modell wird ein Hugging-Face-Read-Token benötigt")
            headers["Authorization"] = f"Bearer {huggingface_token}"
        download(model["url"], target, expected, headers)


def install_custom_nodes(root: Path, manifest: dict[str, Any], profiles: list[str]) -> None:
    runtime_root, python, _ = runtime_paths(root, manifest)
    custom_root = runtime_root / "ComfyUI" / "custom_nodes"
    custom_root.mkdir(parents=True, exist_ok=True)
    for node_id in selected_entries(manifest, profiles, "custom_nodes"):
        node = manifest.get("custom_nodes", {}).get(node_id)
        if not node:
            raise BootstrapError(f"Custom-Node-Eintrag fehlt: {node_id}")
        repository = node["repository"].removesuffix("/")
        ref = node["ref"]
        archive = root / "downloads" / f"node-{node_id}-{ref}.zip"
        download(f"{repository}/archive/{ref}.zip", archive, node.get("sha256"))
        staging = root / f".node-{node_id}"
        if staging.exists():
            safe_remove(staging, root)
        extract_archive(archive, staging)
        children = list(staging.iterdir())
        source = children[0] if len(children) == 1 and children[0].is_dir() else staging
        target = custom_root / node.get("directory", node_id)
        if target.exists():
            safe_remove(target, root)
        shutil.move(str(source), str(target))
        if staging.exists():
            safe_remove(staging, root)
        requirements = target / "requirements.txt"
        if requirements.is_file():
            run_checked([str(python), "-s", "-m", "pip", "install", "-r", str(requirements)])


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", str(value))
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def probe_comfy(
    base_url: str,
    manifest: dict[str, Any],
    profiles: list[str],
) -> dict[str, Any]:
    normalized = normalize_local_comfy_url(base_url)
    try:
        with urllib.request.urlopen(_request(f"{normalized}/system_stats"), timeout=8) as response:
            system_stats = json.load(response)
        with urllib.request.urlopen(_request(f"{normalized}/object_info"), timeout=20) as response:
            object_info = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"ComfyUI ist unter {normalized} nicht erreichbar: {exc}") from exc

    required_nodes: set[str] = set()
    default_required_nodes = set(manifest.get("comfyui", {}).get("required_nodes", []))
    for profile_id in profiles:
        profile = manifest.get("profiles", {}).get(profile_id, {})
        required_nodes.update(profile.get("required_nodes", default_required_nodes))
    available_nodes = set(object_info) if isinstance(object_info, dict) else set()
    missing_nodes = sorted(required_nodes - available_nodes)

    required_models = {
        Path(manifest["models"][model_id]["target"]).name.casefold()
        for model_id in selected_entries(manifest, profiles, "models")
    }
    available_models = {
        Path(value).name.casefold()
        for value in _string_values(object_info)
        if value.lower().endswith((".safetensors", ".ckpt", ".pt", ".pth"))
    }
    missing_models = sorted(required_models - available_models)
    version = ""
    if isinstance(system_stats, dict):
        system = system_stats.get("system", {})
        if isinstance(system, dict):
            version = str(system.get("comfyui_version") or system.get("version") or "")
    required_version = str(manifest.get("runtime", {}).get("tag") or "").lstrip("v")
    detected_tuple = _version_tuple(version)
    required_tuple = _version_tuple(required_version)
    version_compatible = not detected_tuple or not required_tuple or detected_tuple >= required_tuple
    return {
        "ok": version_compatible and not missing_nodes and not missing_models,
        "url": normalized,
        "version": version,
        "required_version": required_version,
        "version_compatible": version_compatible,
        "missing_nodes": missing_nodes,
        "missing_models": missing_models,
    }


def install(
    root: Path,
    manifest: dict[str, Any],
    payload: Path,
    profiles: list[str],
    skip_models: bool,
    *,
    comfy_mode: str = "managed",
    external_comfy_url: str | None = None,
    shared_model_root: str | None = None,
    huggingface_token: str | None = None,
    flux_license_accepted: bool = False,
) -> None:
    if comfy_mode not in {"managed", "external"}:
        raise BootstrapError("Unbekannter ComfyUI-Modus")
    external_url = normalize_local_comfy_url(external_comfy_url or "") if comfy_mode == "external" else None
    shared_models = resolve_shared_models_root(shared_model_root)
    root.mkdir(parents=True, exist_ok=True)
    if comfy_mode == "managed" and not skip_models:
        profile_download_gb = sum(
            manifest.get("profiles", {}).get(profile, {}).get("estimated_download_gb", 0)
            for profile in profiles
        )
        runtime_download_gb = manifest.get("runtime", {}).get("estimated_download_gb", 0)
        estimated_download_bytes = int((profile_download_gb + runtime_download_gb) * 1024**3)
        emit(
            "download-plan",
            "Gesamtdownload wird vorbereitet",
            total=estimated_download_bytes,
            approximate=True,
        )
    if not (root / MARKER_NAME).is_file() and not skip_models and comfy_mode == "managed":
        profile_definitions = []
        for profile in profiles:
            definition = manifest.get("profiles", {}).get(profile)
            if not definition:
                raise BootstrapError(f"Unbekanntes Installationsprofil: {profile}")
            profile_definitions.append(definition)
        profile_gb = sum(definition["estimated_download_gb"] for definition in profile_definitions)
        required_gb = profile_gb + manifest["runtime"].get("estimated_download_gb", 0) + 8
        free_gb = shutil.disk_usage(root).free / (1024**3)
        if free_gb < required_gb:
            raise BootstrapError(
                f"Zu wenig freier Speicher: {free_gb:.1f} GB frei, ungefähr {required_gb:.0f} GB benötigt"
            )
    emit("phase", "Installiere ComfyUI")
    deploy_runtime(root, manifest)
    emit("phase", "Installiere VocaVid")
    workspace = deploy_application(root, payload)
    install_python_dependencies(root, manifest, workspace)
    runtime_root, _, _ = runtime_paths(root, manifest)
    if comfy_mode == "managed":
        configure_shared_models(runtime_root, shared_models)
        emit("phase", "Installiere Custom Nodes")
        install_custom_nodes(root, manifest, profiles)
        if not skip_models:
            emit("phase", "Lade Modelle")
            install_models(
                root,
                manifest,
                profiles,
                huggingface_token=huggingface_token,
                flux_license_accepted=flux_license_accepted,
                shared_models_root=shared_models,
            )
    else:
        emit("phase", "Prüfe vorhandene ComfyUI")
        probe = probe_comfy(external_url or "", manifest, profiles)
        if not probe["ok"]:
            details = []
            if not probe["version_compatible"]:
                details.append(
                    f"ComfyUI {probe['version']} ist älter als die benötigte Version {probe['required_version']}"
                )
            if probe["missing_nodes"]:
                details.append("fehlende Nodes: " + ", ".join(probe["missing_nodes"]))
            if probe["missing_models"]:
                details.append("fehlende Modelle: " + ", ".join(probe["missing_models"]))
            raise BootstrapError("Vorhandene ComfyUI ist nicht kompatibel; " + "; ".join(details))
    state = {
        "schema_version": 1,
        "stack_version": manifest["stack_version"],
        "profiles": profiles,
        "models_skipped": skip_models or comfy_mode == "external",
        "comfy_mode": comfy_mode,
        "external_comfy_url": external_url,
        "shared_models_root": str(shared_models) if shared_models else None,
        "flux_license_accepted": bool(flux_license_accepted),
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_state(root, state)
    emit("complete", "VocaVid wurde installiert")


def detect_nvidia_gpus() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    gpus: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        name, separator, memory = line.rpartition(",")
        if not separator:
            continue
        try:
            memory_mb = int(memory.strip())
        except ValueError:
            memory_mb = 0
        gpus.append({"name": name.strip(), "memory_mb": memory_mb})
    return gpus


def status(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    marker = root / MARKER_NAME
    runtime_root, python, comfy_main = runtime_paths(root, manifest)
    workspace = root / "workspace"
    installed = marker.is_file() and python.is_file() and comfy_main.is_file() and (workspace / "VocaVid").is_dir()
    state = read_state(root)
    if marker.is_file() and not state:
        installed = False
    free_gb = 0.0
    probe = root if root.exists() else root.parent
    try:
        free_gb = shutil.disk_usage(probe).free / (1024**3)
    except OSError:
        pass
    return {
        "installed": installed,
        "current": installed and state.get("stack_version") == manifest.get("stack_version"),
        "stack_version": state.get("stack_version"),
        "target_version": manifest.get("stack_version"),
        "profiles": state.get("profiles", []),
        "root": str(root),
        "free_gb": round(free_gb, 1),
        "gpus": detect_nvidia_gpus(),
        "runtime": str(runtime_root),
        "comfy_mode": state.get("comfy_mode", "managed"),
        "external_comfy_url": state.get("external_comfy_url"),
        "shared_models_root": state.get("shared_models_root"),
    }


def available_port(host: str, preferred: int, excluded: Iterable[int] = ()) -> int:
    excluded_ports = {int(port) for port in excluded if port}
    for port in range(int(preferred), min(65535, int(preferred) + 100)):
        if port in excluded_ports:
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE if os.name == "nt" else socket.SO_REUSEADDR, 1)
                probe.bind((host, port))
                return port
        except OSError:
            continue
    raise BootstrapError(f"Kein freier lokaler Port ab {preferred} gefunden")


def update_workspace_comfy_url(workspace: Path, current_url: str, previous_url: str | None) -> None:
    database = workspace / ".VocaVid" / "VocaVid.sqlite3"
    if not database.is_file():
        return
    candidates = {"http://127.0.0.1:8188"}
    if previous_url:
        candidates.add(previous_url.rstrip("/"))
    placeholders = ",".join("?" for _ in candidates)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(database)
        with connection:
            table_names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            values = [current_url, *sorted(candidates)]
            if "global_settings" in table_names:
                connection.execute(
                    f"UPDATE global_settings SET comfy_base_url = ? WHERE comfy_base_url IN ({placeholders})",
                    values,
                )
            if "projects" in table_names:
                connection.execute(
                    f"UPDATE projects SET comfy_base_url = ? WHERE comfy_base_url IN ({placeholders})",
                    values,
                )
    except sqlite3.Error as exc:
        raise BootstrapError(f"Gespeicherte ComfyUI-Adresse konnte nicht aktualisiert werden: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def acquire_service_lock(root: Path):
    lock_path = root / "service.lock"
    handle = lock_path.open("a+b")
    try:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"1")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as exc:
        handle.close()
        raise BootstrapError("VocaVid läuft bereits in einem anderen Fenster") from exc
    return handle


def wait_http(url: str, timeout: float, processes: list[subprocess.Popen[Any]]) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise BootstrapError(f"Hintergrundprozess wurde unerwartet beendet (Code {process.returncode})")
        try:
            with urllib.request.urlopen(_request(url), timeout=2) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)
    raise BootstrapError(f"Server antwortet nicht: {url}")


def parent_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def terminate(processes: Iterable[subprocess.Popen[Any]]) -> None:
    active = [process for process in processes if process.poll() is None]
    for process in active:
        process.terminate()
    deadline = time.monotonic() + 8
    while active and time.monotonic() < deadline:
        active = [process for process in active if process.poll() is None]
        time.sleep(0.2)
    for process in active:
        process.kill()


def serve(root: Path, manifest: dict[str, Any], parent_pid: int) -> None:
    state = status(root, manifest)
    if not state["installed"]:
        raise BootstrapError("VocaVid ist noch nicht installiert")
    install_state = read_state(root)
    runtime_root, python, comfy_main = runtime_paths(root, manifest)
    workspace = root / "workspace"
    app = manifest["application"]
    comfy = manifest["comfyui"]
    comfy_mode = str(install_state.get("comfy_mode") or "managed")
    previous_comfy_url = str(install_state.get("last_comfy_url") or "") or None
    if comfy_mode == "external":
        comfy_url = normalize_local_comfy_url(str(install_state.get("external_comfy_url") or ""))
        probe = probe_comfy(comfy_url, manifest, list(install_state.get("profiles") or ["starter"]))
        if not probe["ok"]:
            details = []
            if not probe["version_compatible"]:
                details.append(
                    f"ComfyUI {probe['version']} ist älter als die benötigte Version {probe['required_version']}"
                )
            if probe["missing_nodes"]:
                details.append("fehlende Nodes: " + ", ".join(probe["missing_nodes"]))
            if probe["missing_models"]:
                details.append("fehlende Modelle: " + ", ".join(probe["missing_models"]))
            raise BootstrapError("Vorhandene ComfyUI ist nicht startbereit; " + "; ".join(details))
    else:
        preferred_comfy_port = int(install_state.get("service_ports", {}).get("comfyui") or comfy["port"])
        comfy_port = available_port(comfy["host"], preferred_comfy_port)
        comfy_url = f"http://{comfy['host']}:{comfy_port}"
    preferred_app_port = int(install_state.get("service_ports", {}).get("application") or app["port"])
    app_port = available_port(
        app["host"],
        preferred_app_port,
        excluded=[urllib.parse.urlparse(comfy_url).port or 0],
    )
    update_workspace_comfy_url(workspace, comfy_url, previous_comfy_url)
    install_state["last_comfy_url"] = comfy_url
    install_state["service_ports"] = {
        "application": app_port,
        "comfyui": urllib.parse.urlparse(comfy_url).port,
    }
    write_state(root, install_state)
    service_lock = acquire_service_lock(root)
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(workspace)
    env["HF_HOME"] = str(root / "cache" / "huggingface")
    env["TORCH_HOME"] = str(root / "cache" / "torch")
    env["VOCAVID_COMFY_BASE_URL"] = comfy_url
    env["PATH"] = str(workspace / "bin") + os.pathsep + env.get("PATH", "")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    comfy_log = (log_dir / "comfyui.log").open("a", encoding="utf-8")
    app_log = (log_dir / "vocavid.log").open("a", encoding="utf-8")
    processes: list[subprocess.Popen[Any]] = []
    try:
        if comfy_mode == "managed":
            comfy_command = [
                str(python),
                "-s",
                str(comfy_main),
                "--listen",
                comfy["host"],
                "--port",
                str(urllib.parse.urlparse(comfy_url).port),
                *comfy.get("extra_args", []),
            ]
            emit("service", f"Starte verwaltete ComfyUI auf {comfy_url}")
            processes.append(
                subprocess.Popen(
                    comfy_command,
                    cwd=str(runtime_root / "ComfyUI"),
                    env=env,
                    stdout=comfy_log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            )
            wait_http(f"{comfy_url}/system_stats", 180, processes)
        else:
            emit("service", f"Verwende vorhandene ComfyUI auf {comfy_url}")
        emit("service", "Starte VocaVid")
        app_command = [
            str(python),
            "-s",
            "-m",
            app["module"],
            "serve",
            "--host",
            app["host"],
            "--port",
            str(app_port),
        ]
        processes.append(
            subprocess.Popen(
                app_command,
                cwd=str(workspace),
                env=env,
                stdout=app_log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        )
        url = f"http://{app['host']}:{app_port}"
        wait_http(url, 120, processes)
        emit("ready", "VocaVid ist bereit", url=url)
        while all(process.poll() is None for process in processes) and parent_alive(parent_pid):
            time.sleep(1)
    finally:
        emit("service", "Beende Hintergrundprozesse")
        terminate(reversed(processes))
        comfy_log.close()
        app_log.close()
        service_lock.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="vocavid-bootstrap")
    result.add_argument("command", choices=("status", "install", "probe", "serve"))
    result.add_argument("--root", type=Path, default=default_root())
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--payload", type=Path)
    result.add_argument("--profile", action="append", dest="profiles")
    result.add_argument("--skip-models", action="store_true")
    result.add_argument("--parent-pid", type=int, default=0)
    result.add_argument("--comfy-mode", choices=("managed", "external"), default="managed")
    result.add_argument("--external-comfy-url")
    result.add_argument("--shared-model-root")
    result.add_argument("--flux-license-accepted", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        root = args.root.resolve()
        if args.command == "status":
            print(json.dumps(status(root, manifest), ensure_ascii=True))
        elif args.command == "install":
            if not args.payload:
                raise BootstrapError("--payload wird für install benötigt")
            install(
                root,
                manifest,
                args.payload.resolve(),
                args.profiles or ["starter"],
                args.skip_models,
                comfy_mode=args.comfy_mode,
                external_comfy_url=args.external_comfy_url,
                shared_model_root=args.shared_model_root,
                huggingface_token=os.environ.get("VOCAVID_HF_TOKEN"),
                flux_license_accepted=args.flux_license_accepted,
            )
        elif args.command == "probe":
            if not args.external_comfy_url:
                raise BootstrapError("--external-comfy-url fehlt")
            print(
                json.dumps(
                    probe_comfy(args.external_comfy_url, manifest, args.profiles or ["creator"]),
                    ensure_ascii=True,
                )
            )
        else:
            serve(root, manifest, args.parent_pid)
        return 0
    except (BootstrapError, OSError, subprocess.SubprocessError) as exc:
        emit("error", str(exc))
        return 1
    except Exception as exc:
        emit("error", f"Unerwarteter Installerfehler ({type(exc).__name__}): {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

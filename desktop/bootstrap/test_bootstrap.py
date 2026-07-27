from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import vocavid_bootstrap as bootstrap


class BootstrapTests(unittest.TestCase):
    @patch("builtins.print")
    def test_emit_uses_ascii_safe_json_transport(self, print_mock) -> None:
        bootstrap.emit("command", "Führe python.exe aus")

        serialized = print_mock.call_args.args[0]
        self.assertEqual(serialized.encode("ascii").decode("ascii"), serialized)
        self.assertIn(r"F\u00fchre", serialized)
        self.assertEqual(json.loads(serialized)["message"], "Führe python.exe aus")

    def test_sha256_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "value.bin"
            path.write_bytes(b"vocavid")
            self.assertEqual(bootstrap.sha256_file(path), hashlib.sha256(b"vocavid").hexdigest())

    def test_deploy_application_preserves_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "payload.zip"
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("VocaVid/__init__.py", "")
                archive.writestr("requirements.txt", "")
            workspace = bootstrap.deploy_application(root, payload)
            state = workspace / ".VocaVid" / "state.txt"
            state.parent.mkdir()
            state.write_text("keep", encoding="utf-8")
            workspace = bootstrap.deploy_application(root, payload)
            self.assertEqual((workspace / ".VocaVid" / "state.txt").read_text(encoding="utf-8"), "keep")

    def test_status_requires_runtime_and_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {
                "stack_version": "1",
                "runtime": {
                    "python": "python_embeded/python.exe",
                    "comfy_main": "ComfyUI/main.py",
                },
            }
            (root / bootstrap.MARKER_NAME).write_text(
                json.dumps({"stack_version": "1", "profiles": ["starter"]}), encoding="utf-8"
            )
            self.assertFalse(bootstrap.status(root, manifest)["installed"])
            (root / "runtime/python_embeded").mkdir(parents=True)
            (root / "runtime/python_embeded/python.exe").touch()
            (root / "runtime/ComfyUI").mkdir()
            (root / "runtime/ComfyUI/main.py").touch()
            (root / "workspace/VocaVid").mkdir(parents=True)
            self.assertTrue(bootstrap.status(root, manifest)["installed"])

    def test_safe_remove_rejects_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(bootstrap.BootstrapError):
                bootstrap.safe_remove(root, root)

    def test_seven_zip_executable_uses_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "7zr.exe"
            executable.touch()
            with patch.dict(os.environ, {"VOCAVID_7ZR": str(executable)}):
                self.assertEqual(bootstrap.seven_zip_executable(), executable)

    @patch("vocavid_bootstrap.run_checked")
    @patch("vocavid_bootstrap.seven_zip_executable", return_value=Path("C:/tools/7zr.exe"))
    def test_extract_7z_uses_native_seven_zip(self, _executable, run_checked) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "runtime.7z"
            archive.touch()
            target = root / "runtime"
            bootstrap.extract_archive(archive, target)
            run_checked.assert_called_once_with(
                [
                    "C:\\tools\\7zr.exe",
                    "x",
                    str(archive),
                    f"-o{target}",
                    "-y",
                    "-bso0",
                    "-bsp0",
                ]
            )

    def test_normalize_local_comfy_url_rejects_remote_hosts(self) -> None:
        self.assertEqual(
            bootstrap.normalize_local_comfy_url("http://localhost:8188/"),
            "http://localhost:8188",
        )
        with self.assertRaises(bootstrap.BootstrapError):
            bootstrap.normalize_local_comfy_url("https://example.com:8188")

    def test_version_tuple_accepts_prefixed_versions(self) -> None:
        self.assertEqual(bootstrap._version_tuple("v0.20.1"), (0, 20, 1))
        self.assertGreater(bootstrap._version_tuple("0.21.0"), bootstrap._version_tuple("v0.20.1"))

    def test_available_port_skips_an_occupied_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            occupied = listener.getsockname()[1]
            listener.listen()
            selected = bootstrap.available_port("127.0.0.1", occupied)
            self.assertGreater(selected, occupied)

    def test_configure_shared_models_writes_extra_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            (runtime / "ComfyUI").mkdir(parents=True)
            models = Path(directory) / "shared" / "models"
            models.mkdir(parents=True)
            bootstrap.configure_shared_models(runtime, models)
            config = (runtime / "ComfyUI" / "extra_model_paths.yaml").read_text(encoding="utf-8")
            self.assertIn(str(models), config)
            self.assertIn("diffusion_models: diffusion_models", config)

    def test_install_models_requires_credentials_for_gated_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "runtime" / "ComfyUI").mkdir(parents=True)
            manifest = {
                "runtime": {
                    "python": "python_embeded/python.exe",
                    "comfy_main": "ComfyUI/main.py",
                },
                "profiles": {
                    "creator": {
                        "models": ["flux"],
                    }
                },
                "models": {
                    "flux": {
                        "url": "https://example.invalid/flux.safetensors",
                        "target": "models/diffusion_models/flux.safetensors",
                        "sha256": "0" * 64,
                        "gated": True,
                    }
                },
            }
            with self.assertRaisesRegex(bootstrap.BootstrapError, "Lizenz"):
                bootstrap.install_models(root, manifest, ["creator"])
            with self.assertRaisesRegex(bootstrap.BootstrapError, "Read-Token"):
                bootstrap.install_models(
                    root,
                    manifest,
                    ["creator"],
                    flux_license_accepted=True,
                )

    def test_update_workspace_comfy_url_updates_managed_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            database = workspace / ".VocaVid" / "VocaVid.sqlite3"
            database.parent.mkdir()
            connection = sqlite3.connect(database)
            try:
                connection.executescript(
                    """
                    CREATE TABLE global_settings (id INTEGER PRIMARY KEY, comfy_base_url TEXT);
                    CREATE TABLE projects (id INTEGER PRIMARY KEY, comfy_base_url TEXT);
                    INSERT INTO global_settings VALUES (1, 'http://127.0.0.1:8188');
                    INSERT INTO projects VALUES (1, 'http://127.0.0.1:8188');
                    INSERT INTO projects VALUES (2, 'http://127.0.0.1:9999');
                    """
                )
                connection.commit()
            finally:
                connection.close()
            bootstrap.update_workspace_comfy_url(
                workspace,
                "http://127.0.0.1:8189",
                "http://127.0.0.1:8188",
            )
            connection = sqlite3.connect(database)
            try:
                values = [row[0] for row in connection.execute("SELECT comfy_base_url FROM projects ORDER BY id")]
            finally:
                connection.close()
            self.assertEqual(values, ["http://127.0.0.1:8189", "http://127.0.0.1:9999"])

    @patch("vocavid_bootstrap.shutil.which", return_value="nvidia-smi.exe")
    @patch("vocavid_bootstrap.subprocess.run")
    def test_detect_nvidia_gpus(self, run, _which) -> None:
        run.return_value.stdout = "NVIDIA GeForce RTX 4090, 24564\n"
        self.assertEqual(
            bootstrap.detect_nvidia_gpus(),
            [{"name": "NVIDIA GeForce RTX 4090", "memory_mb": 24564}],
        )


if __name__ == "__main__":
    unittest.main()

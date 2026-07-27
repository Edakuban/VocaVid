use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::Mutex;
use tauri::{Emitter, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct ServiceState(Mutex<Option<CommandChild>>);
const FLUX_LICENSE_URL: &str =
    "https://huggingface.co/black-forest-labs/FLUX.2-klein-base-9b-fp8";

fn bundled_resource(resources: &Path, name: &str) -> Result<PathBuf, String> {
    let candidates = [resources.join("resources").join(name), resources.join(name)];
    candidates
        .into_iter()
        .find(|candidate| candidate.is_file())
        .ok_or_else(|| {
            format!(
                "Installer-Ressource fehlt: {name} (gesucht unter {})",
                resources.display()
            )
        })
}

fn resource_args(app: &tauri::AppHandle, command: &str) -> Result<Vec<String>, String> {
    let resources = app.path().resource_dir().map_err(|error| error.to_string())?;
    let manifest = bundled_resource(&resources, "stack.lock.json")?;
    let mut args = vec![
        command.to_string(),
        "--manifest".to_string(),
        manifest.to_string_lossy().to_string(),
    ];
    if command == "install" {
        let payload = bundled_resource(&resources, "vocavid-app.zip")?;
        args.push("--payload".to_string());
        args.push(payload.to_string_lossy().to_string());
    }
    Ok(args)
}

fn sidecar_path() -> Result<PathBuf, String> {
    let executable = std::env::current_exe().map_err(|error| error.to_string())?;
    let directory = executable
        .parent()
        .ok_or_else(|| "Installationsverzeichnis konnte nicht bestimmt werden".to_string())?;
    let sidecar = directory.join("vocavid-bootstrap.exe");
    if !sidecar.is_file() {
        return Err(format!("Bootstrapper fehlt: {}", sidecar.display()));
    }
    Ok(sidecar)
}

fn last_nonempty_line(bytes: &[u8]) -> Option<String> {
    String::from_utf8_lossy(bytes)
        .lines()
        .rev()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .map(ToOwned::to_owned)
}

fn parse_bootstrap_output(output: &Output, context: &str) -> Result<Value, String> {
    let stdout_line = last_nonempty_line(&output.stdout);
    if !output.status.success() {
        if let Some(line) = stdout_line.as_deref() {
            if let Ok(payload) = serde_json::from_str::<Value>(line) {
                if let Some(message) = payload.get("message").and_then(Value::as_str) {
                    return Err(message.to_string());
                }
            }
        }
        let detail = last_nonempty_line(&output.stderr)
            .or(stdout_line)
            .unwrap_or_else(|| "keine Ausgabe".to_string());
        return Err(format!(
            "{context} ist mit Code {} fehlgeschlagen: {detail}",
            output.status.code().unwrap_or(-1)
        ));
    }
    let line = stdout_line.ok_or_else(|| format!("{context} lieferte keine Ausgabe"))?;
    serde_json::from_str(&line)
        .map_err(|error| format!("{context} lieferte ungültiges JSON: {error}; Ausgabe: {line}"))
}

async fn run_sidecar_output(args: Vec<String>, context: &'static str) -> Result<Value, String> {
    let sidecar = sidecar_path()?;
    let output =
        tauri::async_runtime::spawn_blocking(move || Command::new(sidecar).args(args).output())
            .await
            .map_err(|error| format!("{context} konnte nicht ausgeführt werden: {error}"))?
            .map_err(|error| format!("{context} konnte nicht gestartet werden: {error}"))?;
    parse_bootstrap_output(&output, context)
}

#[tauri::command]
async fn runtime_status(app: tauri::AppHandle) -> Result<Value, String> {
    run_sidecar_output(resource_args(&app, "status")?, "Systemprüfung").await
}

#[tauri::command]
async fn install_runtime(
    app: tauri::AppHandle,
    profile: String,
    comfy_mode: String,
    external_comfy_url: Option<String>,
    shared_model_root: Option<String>,
    huggingface_token: Option<String>,
    flux_license_accepted: bool,
) -> Result<(), String> {
    let allowed = ["starter", "creator"];
    if !allowed.contains(&profile.as_str()) {
        return Err("Unbekanntes Installationsprofil".to_string());
    }
    if !["managed", "external"].contains(&comfy_mode.as_str()) {
        return Err("Unbekannter ComfyUI-Modus".to_string());
    }
    let mut args = resource_args(&app, "install")?;
    args.push("--profile".to_string());
    args.push(profile);
    args.push("--comfy-mode".to_string());
    args.push(comfy_mode.clone());
    if comfy_mode == "external" {
        let url = external_comfy_url
            .filter(|value| !value.trim().is_empty())
            .ok_or("Für eine vorhandene ComfyUI wird die lokale URL benötigt")?;
        args.push("--external-comfy-url".to_string());
        args.push(url);
    }
    if let Some(root) = shared_model_root.filter(|value| !value.trim().is_empty()) {
        args.push("--shared-model-root".to_string());
        args.push(root);
    }
    if flux_license_accepted {
        args.push("--flux-license-accepted".to_string());
    }
    let mut command = app
        .shell()
        .sidecar("vocavid-bootstrap")
        .map_err(|error| error.to_string())?
        .args(args);
    if let Some(token) = huggingface_token.filter(|value| !value.trim().is_empty()) {
        command = command.env("VOCAVID_HF_TOKEN", token);
    }
    let (mut receiver, child) = command
        .spawn()
        .map_err(|error| error.to_string())?;
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    let line = String::from_utf8_lossy(&bytes).trim().to_string();
                    if !line.is_empty() {
                        let payload = serde_json::from_str::<Value>(&line)
                            .unwrap_or_else(|_| serde_json::json!({"kind":"log","message":line}));
                        let _ = app_handle.emit("bootstrap-progress", payload);
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    let line = String::from_utf8_lossy(&bytes).trim().to_string();
                    let _ = app_handle.emit(
                        "bootstrap-progress",
                        serde_json::json!({"kind":"error","message":line}),
                    );
                }
                CommandEvent::Terminated(status) => {
                    let _ = app_handle.emit(
                        "bootstrap-finished",
                        serde_json::json!({"code":status.code}),
                    );
                    break;
                }
                _ => {}
            }
        }
        drop(child);
    });
    Ok(())
}

#[tauri::command]
async fn validate_external_comfy(
    app: tauri::AppHandle,
    url: String,
    profile: String,
) -> Result<Value, String> {
    let allowed = ["starter", "creator"];
    if !allowed.contains(&profile.as_str()) {
        return Err("Unbekanntes Installationsprofil".to_string());
    }
    let mut args = resource_args(&app, "probe")?;
    args.push("--external-comfy-url".to_string());
    args.push(url);
    args.push("--profile".to_string());
    args.push(profile);
    run_sidecar_output(args, "ComfyUI-Prüfung").await
}

#[tauri::command]
fn open_flux_license(app: tauri::AppHandle) -> Result<(), String> {
    #[allow(deprecated)]
    app.shell()
        .open(FLUX_LICENSE_URL, None)
        .map_err(|error| error.to_string())
}

#[tauri::command]
async fn start_services(app: tauri::AppHandle, state: tauri::State<'_, ServiceState>) -> Result<(), String> {
    if state.0.lock().map_err(|_| "Service lock poisoned")?.is_some() {
        return Ok(());
    }
    let mut args = resource_args(&app, "serve")?;
    args.push("--parent-pid".to_string());
    args.push(std::process::id().to_string());
    let (mut receiver, child) = app
        .shell()
        .sidecar("vocavid-bootstrap")
        .map_err(|error| error.to_string())?
        .args(args)
        .spawn()
        .map_err(|error| error.to_string())?;
    *state.0.lock().map_err(|_| "Service lock poisoned")? = Some(child);
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            if let CommandEvent::Stdout(bytes) = event {
                let line = String::from_utf8_lossy(&bytes).trim().to_string();
                let payload = serde_json::from_str::<Value>(&line)
                    .unwrap_or_else(|_| serde_json::json!({"kind":"log","message":line}));
                let _ = app_handle.emit("service-progress", payload.clone());
                if payload.get("kind").and_then(Value::as_str) == Some("ready") {
                    if let Some(url) = payload.get("url").and_then(Value::as_str) {
                        if let Ok(parsed) = url.parse() {
                            if let Some(window) = app_handle.get_webview_window("main") {
                                let _ = window.navigate(parsed);
                            }
                        }
                    }
                }
            }
        }
        if let Ok(mut service) = app_handle.state::<ServiceState>().0.lock() {
            *service = None;
        }
    });
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(ServiceState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            runtime_status,
            install_runtime,
            validate_external_comfy,
            open_flux_license,
            start_services
        ])
        .run(tauri::generate_context!())
        .expect("error while running VocaVid");
}

#[cfg(test)]
mod tests {
    use super::{bundled_resource, last_nonempty_line};
    use std::fs;

    #[test]
    fn last_nonempty_line_ignores_trailing_blank_lines() {
        let output = b"diagnostic\r\n{\"ok\":true}\r\n  \r\n";
        assert_eq!(last_nonempty_line(output).as_deref(), Some("{\"ok\":true}"));
    }

    #[test]
    fn bundled_resource_accepts_nested_layout() {
        let root =
            std::env::temp_dir().join(format!("vocavid-resource-test-{}", std::process::id()));
        let nested = root.join("resources");
        fs::create_dir_all(&nested).unwrap();
        fs::write(nested.join("stack.lock.json"), b"{}").unwrap();
        assert_eq!(
            bundled_resource(&root, "stack.lock.json").unwrap(),
            nested.join("stack.lock.json")
        );
        fs::remove_dir_all(root).unwrap();
    }
}

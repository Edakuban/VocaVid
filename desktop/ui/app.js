const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const title = document.querySelector("#status-title");
const detail = document.querySelector("#status-detail");
const dot = document.querySelector("#status-dot");
const installInfo = document.querySelector("#install-info");
const installButton = document.querySelector("#install-button");
const profile = document.querySelector("#profile");
const profileName = document.querySelector("#profile-name");
const profileSize = document.querySelector("#profile-size");
const gpuName = document.querySelector("#gpu-name");
const progressArea = document.querySelector("#progress-area");
const progressBar = document.querySelector("#progress-bar");
const log = document.querySelector("#log");
const comfyMode = document.querySelector("#comfy-mode");
const managedOptions = document.querySelector("#managed-options");
const sharedModelRoot = document.querySelector("#shared-model-root");
const externalOptions = document.querySelector("#external-options");
const externalComfyUrl = document.querySelector("#external-comfy-url");
const validateExternalButton = document.querySelector("#validate-external-button");
const externalResult = document.querySelector("#external-result");
const fluxOptions = document.querySelector("#flux-options");
const fluxLicenseAccepted = document.querySelector("#flux-license-accepted");
const huggingfaceToken = document.querySelector("#huggingface-token");
const openFluxLicense = document.querySelector("#open-flux-license");

let phaseProgress = 8;
let freeGb = 0;
let externalValidated = false;

function setStatus(nextTitle, nextDetail, state = "working") {
  title.textContent = nextTitle;
  detail.textContent = nextDetail;
  dot.className = `dot ${state === "working" ? "pulse" : state}`;
}

function appendLog(message) {
  if (!message) return;
  log.textContent += `${message}\n`;
  log.scrollTop = log.scrollHeight;
}

function handleProgress(payload) {
  appendLog(payload.message);
  if (payload.kind === "phase") {
    phaseProgress = Math.min(88, phaseProgress + 16);
    progressBar.style.width = `${phaseProgress}%`;
    setStatus(payload.message, "Die Installation läuft. Das kann beim ersten Mal länger dauern.");
  } else if (payload.kind === "download" && payload.total) {
    const withinPhase = Math.min(14, (payload.current / payload.total) * 14);
    progressBar.style.width = `${Math.min(96, phaseProgress + withinPhase)}%`;
  } else if (payload.kind === "error") {
    setStatus("Installation fehlgeschlagen", payload.message, "error");
    installButton.disabled = false;
  } else if (payload.kind === "complete") {
    progressBar.style.width = "100%";
  }
}

function creatorNeedsFluxCredentials() {
  return comfyMode.value === "managed" && profile.value === "creator";
}

function updateInstallButton() {
  const selected = profile.selectedOptions[0];
  const required = comfyMode.value === "external" ? 10 : Number(selected.dataset.required);
  const enoughSpace = !freeGb || freeGb >= required;
  const fluxReady = !creatorNeedsFluxCredentials()
    || (fluxLicenseAccepted.checked && huggingfaceToken.value.trim().startsWith("hf_"));
  const externalReady = comfyMode.value !== "external" || externalValidated;
  installButton.disabled = !(enoughSpace && fluxReady && externalReady);

  if (!enoughSpace) {
    setStatus(
      "Zu wenig Speicherplatz",
      `${freeGb} GB frei, mindestens ungefähr ${required} GB benötigt.`,
      "error",
    );
  }
}

function resetExternalValidation() {
  externalValidated = false;
  externalResult.textContent = "ComfyUI muss laufen. Nodes und Modelle werden vor der Installation geprüft.";
  externalResult.className = "";
  updateInstallButton();
}

function updateOptions() {
  const selected = profile.selectedOptions[0];
  const external = comfyMode.value === "external";
  profileName.textContent = selected.textContent.split("–")[0].trim();
  profileSize.textContent = external ? "ca. 2 GB" : selected.dataset.size;
  managedOptions.classList.toggle("hidden", external);
  externalOptions.classList.toggle("hidden", !external);
  fluxOptions.classList.toggle("hidden", external || profile.value !== "creator");
  if (!external) {
    externalValidated = false;
  }
  updateInstallButton();
}

async function start() {
  installInfo.classList.add("hidden");
  progressArea.classList.remove("hidden");
  setStatus("Starte VocaVid", "ComfyUI und VocaVid werden im Hintergrund gestartet.");
  try {
    await invoke("start_services");
  } catch (error) {
    setStatus("Start fehlgeschlagen", String(error), "error");
  }
}

async function check() {
  try {
    const status = await invoke("runtime_status");
    if (status.installed && status.current) {
      appendLog(`Runtime: ${status.runtime}`);
      await start();
      return;
    }
    freeGb = status.free_gb;
    gpuName.textContent = status.gpus?.length
      ? `${status.gpus[0].name} · ${Math.round(status.gpus[0].memory_mb / 1024)} GB`
      : "Keine NVIDIA GPU erkannt";
    setStatus(
      status.installed ? "Aktualisierung erforderlich" : "Bereit zur Installation",
      `${status.free_gb} GB freier Speicher auf dem Ziellaufwerk.`,
      "success",
    );
    installInfo.classList.remove("hidden");
    updateOptions();
  } catch (error) {
    setStatus("Systemprüfung fehlgeschlagen", String(error), "error");
  }
}

installButton.addEventListener("click", async () => {
  updateInstallButton();
  if (installButton.disabled) return;
  installButton.disabled = true;
  installInfo.classList.add("hidden");
  progressArea.classList.remove("hidden");
  setStatus("Installation wird vorbereitet", "Bitte VocaVid während des Downloads geöffnet lassen.");
  try {
    await invoke("install_runtime", {
      profile: profile.value,
      comfyMode: comfyMode.value,
      externalComfyUrl: comfyMode.value === "external" ? externalComfyUrl.value.trim() : null,
      sharedModelRoot: comfyMode.value === "managed" ? sharedModelRoot.value.trim() || null : null,
      huggingfaceToken: creatorNeedsFluxCredentials() ? huggingfaceToken.value.trim() : null,
      fluxLicenseAccepted: creatorNeedsFluxCredentials() && fluxLicenseAccepted.checked,
    });
    huggingfaceToken.value = "";
  } catch (error) {
    huggingfaceToken.value = "";
    setStatus("Installation fehlgeschlagen", String(error), "error");
    installInfo.classList.remove("hidden");
    progressArea.classList.add("hidden");
    updateInstallButton();
  }
});

validateExternalButton.addEventListener("click", async () => {
  validateExternalButton.disabled = true;
  externalResult.textContent = "Prüfe Verbindung, Nodes und Modelle …";
  externalResult.className = "";
  try {
    const result = await invoke("validate_external_comfy", {
      url: externalComfyUrl.value.trim(),
      profile: profile.value,
    });
    externalValidated = Boolean(result.ok);
    if (externalValidated) {
      externalResult.textContent = `Kompatibel${result.version ? ` · ComfyUI ${result.version}` : ""}`;
      externalResult.className = "validation-success";
    } else {
      const parts = [];
      if (result.version_compatible === false) {
        parts.push(`Version ${result.version || "unbekannt"} < ${result.required_version}`);
      }
      if (result.missing_nodes?.length) parts.push(`Nodes: ${result.missing_nodes.join(", ")}`);
      if (result.missing_models?.length) parts.push(`Modelle: ${result.missing_models.join(", ")}`);
      externalResult.textContent = `Nicht vollständig · ${parts.join(" · ")}`;
      externalResult.className = "validation-error";
    }
  } catch (error) {
    externalValidated = false;
    externalResult.textContent = String(error);
    externalResult.className = "validation-error";
  } finally {
    validateExternalButton.disabled = false;
    updateInstallButton();
  }
});

openFluxLicense.addEventListener("click", () => invoke("open_flux_license"));
profile.addEventListener("change", () => {
  resetExternalValidation();
  updateOptions();
});
comfyMode.addEventListener("change", updateOptions);
externalComfyUrl.addEventListener("input", resetExternalValidation);
fluxLicenseAccepted.addEventListener("change", updateInstallButton);
huggingfaceToken.addEventListener("input", updateInstallButton);

listen("bootstrap-progress", (event) => handleProgress(event.payload));
listen("bootstrap-finished", async (event) => {
  if (event.payload.code === 0) {
    await start();
  } else {
    huggingfaceToken.value = "";
    setStatus("Installation fehlgeschlagen", "Details stehen im Installationsprotokoll.", "error");
    installInfo.classList.remove("hidden");
    updateInstallButton();
  }
});
listen("service-progress", (event) => {
  const payload = event.payload;
  appendLog(payload.message);
  if (payload.kind === "ready") {
    setStatus("VocaVid ist bereit", "Die Benutzeroberfläche wird geöffnet.", "success");
  } else if (payload.kind === "error") {
    setStatus("Start fehlgeschlagen", payload.message, "error");
  } else if (payload.kind === "service") {
    setStatus(payload.message, "Die lokalen Dienste werden vorbereitet.");
  }
});

check();

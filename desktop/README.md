# VocaVid Desktop

`desktop/` erzeugt eine eigenständige Windows-App mit integriertem WebView. Die
App startet VocaVid und ComfyUI lokal im Hintergrund; Python, Node, Git oder
Docker werden auf dem Zielrechner nicht benötigt.

## Nutzerablauf

1. `VocaVid_*_x64-setup.exe` installieren.
2. VocaVid öffnen.
3. Beim ersten Start das verwaltete Runtime- und Modellpaket installieren.
4. Danach startet die App ComfyUI und VocaVid auf freien lokalen Ports und
   zeigt VocaVid im eigenen Fenster.

Die Laufzeit liegt unter `%LOCALAPPDATA%\VocaVid`. Projektzustand und Downloads
bleiben bei App-Updates erhalten.

## Lokaler Build

Benötigt werden Node.js, Rust mit dem MSVC-Target, Python 3.11+ und die
Windows-C++-Buildtools.

```powershell
cd desktop
npm install
npm run build:installer
```

Der NSIS-Installer liegt anschließend unter
`desktop/src-tauri/target/release/bundle/nsis/`.

## Abhängigkeitsmanifest

`stack.lock.json` ist die einzige Quelle für ComfyUI-, Modell- und
Custom-Node-Abhängigkeiten. Downloads unterstützen Fortsetzung und werden mit
SHA-256 geprüft. Es gibt zwei Pakete:

- `starter`: Z-Image Turbo.
- `creator`: alle Abhängigkeiten der aktiven Workflows für
  Promptgenerierung, Z-Image, FLUX-Avatarbilder und LTX-2.3-Video.

Die verwendeten Node-Typen sind in der festgeschriebenen ComfyUI-Version
enthalten; aktuell sind daher keine separaten Custom Nodes erforderlich.
`avatartoimage_flux.json` benötigt zusätzlich das gated FLUX.2-Basismodell.
Der Launcher öffnet dafür die Lizenzseite und lädt das Modell erst nach
expliziter Bestätigung mit einem nur für den Downloadprozess übergebenen
Hugging-Face-Read-Token.

Standardmäßig verwendet VocaVid eine isolierte ComfyUI unter
`%LOCALAPPDATA%\VocaVid\runtime`. Eine vorhandene Installation bleibt
unverändert. Im Expertenmodus kann stattdessen eine laufende lokale ComfyUI
verwendet werden; `/system_stats` und `/object_info` werden vorab auf benötigte
Nodes und Modelle geprüft. Ein vorhandener `models`-Ordner kann im verwalteten
Modus über `extra_model_paths.yaml` eingebunden werden.

Weitere Pakete werden ergänzt, indem unter `models` bzw. `custom_nodes` feste
Downloads eingetragen und einem Profil zugeordnet werden. Gated Modelle dürfen
nicht ohne explizite Lizenzannahme automatisiert heruntergeladen werden.

## Bootstrapper testen

```powershell
cd desktop/bootstrap
python -m unittest -v
```

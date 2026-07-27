# VocaVid website draft

Der Ordner enthält einen bewusst frameworkfreien Entwurf für die öffentliche
VocaVid-Website. Er kann mit jedem statischen Hoster ausgeliefert werden.

## Lokale Vorschau

Vom Repository-Stamm einen lokalen Webserver starten, zum Beispiel:

```powershell
python -m http.server 8080
```

Danach `http://localhost:8080/website/` öffnen. Alle auf der Website verwendeten
Icons, Screenshots und Videos liegen relativ unter `website/assets/`.

## Vor dem Livegang

- Ausgewählte Videodateien für das Hosting optimieren; der finale
  Systemfehler-Export ist derzeit rund 400 MB groß und sollte für die Website
  als Streaming-Version bereitgestellt werden.
- Impressum und Datenschutz mit echten Angaben sowie dem finalen Hosting- und
  Dienstesetup vervollständigen und prüfen lassen.
- Rechte an Musik, Bildern, Stimmen und dargestellten Personen bestätigen.

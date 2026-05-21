# K23 Audioarchiv – Browser

Statische Oberfläche für https://audioarchiv.k23.in/ mit Suche, Tags, Player, Favoriten und gespeicherter Hörposition.

## Lokal testen

```bash
python3 crawl_k23.py
python3 -m http.server 8000
```

Dann öffnen:

```text
http://localhost:8000
```

## GitHub Pages

Die Website braucht nur diese Dateien:

- `index.html`
- `style.css`
- `app.js`
- `audio-index.json`

`audio-index.json` wird durch `crawl_k23.py` erzeugt.

## GitHub Action

`.github/workflows/update-index.yml`:

```yaml
name: Update audio index

on:
  workflow_dispatch:
  schedule:
    - cron: "0 */6 * * *"

permissions:
  contents: write

jobs:
  update-index:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.x"

      - name: Run crawler
        run: python crawl_k23.py

      - name: Commit updated audio-index.json
        run: |
          git config user.name "github-actions"
          git config user.email "github-actions@github.com"
          git add audio-index.json
          git commit -m "Update audio index" || echo "No changes"
          git push
```

## Tags erweitern

In `crawl_k23.py` die Liste `TAG_RULES` bearbeiten. Danach GitHub Action erneut starten.

## YouTube-Beschreibungen

Für YouTube-Metadaten braucht man den konkreten Kanal-Link. Technisch wäre der nächste Schritt: per `yt-dlp` Videotitel/Beschreibungen ziehen, fuzzy mit den Archivtiteln abgleichen und als `description` / `youtubeUrl` in `audio-index.json` eintragen.

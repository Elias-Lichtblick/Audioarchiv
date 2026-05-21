# K23 Audioarchiv – Browser mit Tags und YouTube-Abgleich

Statische Oberfläche für https://audioarchiv.k23.in/ mit Suche, Tags, Player, Favoriten, gespeicherter Hörposition und optionalem Abgleich mit dem YouTube-Kanal **The Nokturnal Times**.

## Lokal testen

```bash
python3 crawl_k23.py
python3 -m pip install yt-dlp
python3 crawl_youtube.py --audio-index audio-index.json --out audio-index.json
python3 -m http.server 8000
```

Dann öffnen:

```text
http://localhost:8000
```

## Was die YouTube-Erweiterung macht

`crawl_youtube.py` lädt öffentlich sichtbare Videometadaten des Kanals:

```text
https://www.youtube.com/channel/UCgj0uCW9VR8p3PUJ91oDz9g/videos
```

Danach gleicht das Skript YouTube-Titel mit den Audioarchiv-Titeln ab. Bei hinreichend sicherem Treffer ergänzt es:

- YouTube-Link
- YouTube-Titel
- Beschreibung aus der Videobeschreibung
- optional besseren Titel, wenn der Dateiname im Audioarchiv sehr roh/generisch ist

Der Abgleich ist absichtlich vorsichtig. Die Schwelle kannst du ändern:

```bash
python3 crawl_youtube.py --threshold 0.80
```

Höher = weniger falsche Treffer, aber auch weniger Matches.

## GitHub Action

Die Datei liegt bereits in:

```text
.github/workflows/update-index.yml
```

Sie macht automatisch:

1. K23-Index crawlen
2. `yt-dlp` installieren
3. YouTube-Metadaten holen
4. `audio-index.json` anreichern
5. `audio-index.json` und `youtube-index.json` committen

Manuell starten:

```text
GitHub → Actions → Update audio index → Run workflow
```

## GitHub Pages

Die Website braucht für GitHub Pages:

- `index.html`
- `style.css`
- `app.js`
- `audio-index.json`

`youtube-index.json` ist nur zusätzlich nützlich, falls man später die YouTube-Daten separat ansehen oder debuggen will.

## Tags erweitern

In `crawl_k23.py` die Liste `TAG_RULES` bearbeiten. Danach GitHub Action erneut starten.

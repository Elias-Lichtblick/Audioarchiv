# Audioarchiv Browser

Statische Website für das K23-Audioarchiv mit Suche, Tags, Audio-Player, Fortschrittsspeicherung und optionaler Ergänzung durch YouTube-Beschreibungen des Kanals **The Nokturnal Times**.

## Dateien

```text
index.html
style.css
app.js
crawl_k23.py
crawl_youtube.py
.nojekyll
.github/workflows/update-index.yml
README.md
```

## Was diese Version macht

- crawlt `https://audioarchiv.k23.in/` rekursiv
- erzeugt `audio-index.json`
- bereinigt Titel und Pfade
- korrigiert häufige Schreibweisen, z.B. `Jean Am Ery` → `Jean Améry`
- wandelt Unterstriche und Punkte in Leerzeichen um
- zieht vollständige Datumsangaben aus Titeln heraus und speichert sie separat als `dateLabel`
- erzeugt Tags aus Titeln, Namen, Ordnern und YouTube-Beschreibungen
- lädt mit `yt-dlp` Metadaten vom YouTube-Kanal `The Nokturnal Times`
- ergänzt passende Audioeinträge um YouTube-Link, YouTube-Titel und Videobeschreibung
- speichert Abspielpositionen und Favoriten im Browser per `localStorage`

## Upload zu GitHub

Alle Dateien aus diesem Ordner in das GitHub-Repository hochladen. Die Datei

```text
.github/workflows/update-index.yml
```

muss genau in diesem Pfad liegen. GitHub erstellt die Ordner automatisch, wenn du beim Anlegen einer neuen Datei den kompletten Pfad einträgst.

## GitHub Action starten

1. Repository öffnen.
2. Oben auf **Actions** klicken.
3. **Update audio index** auswählen.
4. **Run workflow** klicken.
5. Warten, bis der Lauf grün ist.
6. GitHub-Pages-Seite mit `Cmd + Shift + R` hart neu laden.

## Lokaler Test

```bash
python3 crawl_k23.py
python3 -m pip install yt-dlp
python3 crawl_youtube.py
python3 -m http.server 8000
```

Dann öffnen:

```text
http://localhost:8000
```

## Begriffe / Schreibweisen ergänzen

Korrekturen stehen in `crawl_k23.py` in diesen Blöcken:

```python
TEXT_FIXES
TAG_RULES
ACRONYMS
```

Wenn ein Name oder Begriff noch falsch dargestellt wird, dort eine neue Regel ergänzen und danach die GitHub Action erneut starten.

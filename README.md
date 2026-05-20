# K23 Audioarchiv Browser

Statische Oberfläche für `https://audioarchiv.k23.in/` mit Suche, Ordnernavigation, Player, Favoriten und gespeicherter Hörposition.

## Start

```bash
cd k23-audio-archiv
python3 crawl_k23.py
python3 -m http.server 8000
```

Dann öffnen:

```text
http://localhost:8000
```

## Was gespeichert wird

Die Hörpositionen und Favoriten werden lokal im Browser per `localStorage` gespeichert. Das bedeutet: keine Accounts, keine Datenbank, aber auch keine Synchronisierung zwischen Geräten.

## Dateien

- `crawl_k23.py` crawlt das vorhandene Index-of-Archiv und erzeugt `audio-index.json`
- `index.html` ist die Oberfläche
- `app.js` enthält Suche, Filter, Player und Fortschrittsspeicherung
- `style.css` enthält das Layout

## Hosting

Du kannst den Ordner nach dem Crawlen auf jeden statischen Webspace legen. Wichtig ist nur, dass `audio-index.json` neben `index.html` liegt.

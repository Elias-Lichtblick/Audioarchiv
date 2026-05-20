#!/usr/bin/env python3
"""
Crawlt https://audioarchiv.k23.in/ rekursiv und erzeugt audio-index.json.

Nutzung:
  python3 crawl_k23.py
  python3 -m http.server 8000
  # dann http://localhost:8000 öffnen
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Iterable
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen

BASE = "https://audioarchiv.k23.in/"
AUDIO_EXT = (".mp3", ".m4a", ".ogg", ".oga", ".wav", ".flac", ".aac")
SKIP_NAMES = {"Parent directory/", "../"}

@dataclass
class Track:
    title: str
    name: str
    url: str
    folder: str
    path: str
    size: str = ""
    sizeBytes: int = 0
    date: str = ""

class IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._in_a = False
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            self._href = attrs_dict.get("href") or ""
            self._text = []
            self._in_a = True

    def handle_data(self, data: str) -> None:
        if self._in_a:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._in_a:
            text = "".join(self._text).strip()
            if self._href:
                self.links.append((self._href, text))
            self._in_a = False


def fetch(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "k23-audio-browser-crawler/1.0"})
    with urlopen(req, timeout=timeout) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, errors="replace")


def guess_title(name: str) -> str:
    name = unquote(name)

    # Dateiendung entfernen
    name = re.sub(r"\.(mp3|m4a|ogg|oga|wav|flac|aac)$", "", name, flags=re.I)

    # URL-/Dateizeichen lesbar machen
    name = name.replace("_", " ")
    name = name.replace("%20", " ")
    name = name.replace(".", " ")

    # CamelCase trennen: DerKommendeAufstand -> Der Kommende Aufstand
    name = re.sub(r"([a-zäöüß])([A-ZÄÖÜ])", r"\1 \2", name)

    # Teil1 -> Teil 1, Vortrag2 -> Vortrag 2
    name = re.sub(r"([A-Za-zÄÖÜäöüß])(\d)", r"\1 \2", name)
    name = re.sub(r"(\d)([A-Za-zÄÖÜäöüß])", r"\1 \2", name)

    # Häufige Begriffe schöner absetzen
    name = re.sub(r"\bDiskussion\b", "– Diskussion", name)
    name = re.sub(r"\bTeil\s*(\d+)\b", r"Teil \1", name, flags=re.I)

    # Mehrfachstriche/Leerzeichen bereinigen
    name = re.sub(r"\s*-\s*", " – ", name)
    name = re.sub(r"\s*–\s*", " – ", name)
    name = re.sub(r"\s+", " ", name).strip()

    # Falls durch Regel am Anfang ein Strich entsteht
    name = re.sub(r"^–\s*", "", name)

    return name

def parse_listing_meta(html: str) -> dict[str, tuple[str, str]]:
    """Best effort: extrahiert Größe/Datum aus einfachem Index-of-Text."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    meta: dict[str, tuple[str, str]] = {}
    # Viele Server schneiden lange Namen visuell ab; deshalb wird später nur best effort gematcht.
    return meta


def size_to_bytes(size: str) -> int:
    m = re.match(r"^([0-9.]+)\s*([KMGT]?i?B|B)$", size.strip(), re.I)
    if not m:
        return 0
    n = float(m.group(1))
    unit = m.group(2).lower()
    mult = {"b": 1, "kb": 1000, "kib": 1024, "mb": 1000**2, "mib": 1024**2,
            "gb": 1000**3, "gib": 1024**3, "tb": 1000**4, "tib": 1024**4}.get(unit, 1)
    return int(n * mult)


def folder_from_url(file_url: str, base: str) -> str:
    rel = urlparse(file_url).path.removeprefix(urlparse(base).path)
    parent = str(PurePosixPath(unquote(rel)).parent)
    return "" if parent == "." else parent


def crawl(start_url: str, delay: float = 0.05, max_pages: int = 10000) -> list[Track]:
    seen_pages: set[str] = set()
    queue = [start_url]
    tracks: list[Track] = []

    while queue:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        if len(seen_pages) >= max_pages:
            print(f"Abbruch: max_pages={max_pages} erreicht", file=sys.stderr)
            break
        seen_pages.add(url)
        print(f"Crawl: {url}", file=sys.stderr)
        try:
            html = fetch(url)
        except Exception as e:
            print(f"WARN: konnte {url} nicht laden: {e}", file=sys.stderr)
            continue

        parser = IndexParser()
        parser.feed(html)
        for href, text in parser.links:
            if text in SKIP_NAMES or href in ("../", "/"):
                continue
            abs_url = urljoin(url, href)
            parsed = urlparse(abs_url)
            if not parsed.scheme.startswith("http"):
                continue
            if not abs_url.startswith(start_url):
                # Bleibt innerhalb des Archivs/Startzweigs.
                continue
            name = unquote(parsed.path.rstrip("/").split("/")[-1])
            if href.endswith("/"):
                if abs_url not in seen_pages:
                    queue.append(abs_url)
            elif name.lower().endswith(AUDIO_EXT):
                folder = folder_from_url(abs_url, start_url)
                tracks.append(Track(
                    title=guess_title(name),
                    name=name,
                    url=abs_url,
                    folder=folder,
                    path=f"{folder}/{name}" if folder else name,
                ))
        time.sleep(delay)

    return tracks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE, help="Start-URL, Standard: https://audioarchiv.k23.in/")
    ap.add_argument("--out", default="audio-index.json", help="Ausgabedatei")
    ap.add_argument("--delay", type=float, default=0.05, help="Pause zwischen Requests")
    ap.add_argument("--max-pages", type=int, default=10000)
    args = ap.parse_args()

    base = args.base if args.base.endswith("/") else args.base + "/"
    tracks = crawl(base, delay=args.delay, max_pages=args.max_pages)
    tracks.sort(key=lambda t: (t.folder.lower(), t.title.lower()))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([asdict(t) for t in tracks], f, ensure_ascii=False, indent=2)
    print(f"Fertig: {len(tracks)} Audio-Dateien in {args.out}")

if __name__ == "__main__":
    main()

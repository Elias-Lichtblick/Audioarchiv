#!/usr/bin/env python3
"""
Crawlt https://audioarchiv.k23.in/ rekursiv und erzeugt audio-index.json.

Die erzeugte JSON-Datei enthält neben URL und Originaldateiname auch:
- lesbare Titel
- lesbare Pfadangaben
- automatisch erkannte Tags aus Titel, Dateiname und Ordnern

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
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen

BASE = "https://audioarchiv.k23.in/"
AUDIO_EXT = (".mp3", ".m4a", ".ogg", ".oga", ".wav", ".flac", ".aac")
SKIP_NAMES = {"Parent directory/", "../"}

# Diese Liste ist absichtlich kuratiert: nicht jeder Ordnername soll ein Tag werden.
# Ergänze hier später einfach weitere Begriffe/Namen.
TAG_RULES: dict[str, list[str]] = {
    # Theorie / Personen
    "Adorno": ["adorno", "theodor w adorno", "theodor adorno"],
    "Horkheimer": ["horkheimer", "max horkheimer"],
    "Marcuse": ["marcuse", "herbert marcuse"],
    "Benjamin": ["benjamin", "walter benjamin"],
    "Freud": ["freud", "sigmund freud"],
    "Marx": ["marx", "karl marx"],
    "Engels": ["engels", "friedrich engels"],
    "Hegel": ["hegel", "g w f hegel"],
    "Nietzsche": ["nietzsche", "friedrich nietzsche"],
    "Postone": ["postone", "moishe postone"],
    "Agnoli": ["agnoli", "johannes agnoli"],
    "Roger Behrens": ["roger behrens", "behrens"],
    "Thomas Ebermann": ["thomas ebermann", "ebermann"],
    "Peter Weiss": ["peter weiss"],
    "Paul Celan": ["paul celan", "celan"],

    # Themen
    "Kritische Theorie": ["kritische theorie", "frankfurter schule", "negative dialektik"],
    "Dialektik": ["dialektik", "dialektisch"],
    "Ideologiekritik": ["ideologiekritik", "ideologie", "falsches bewusstsein"],
    "Kulturindustrie": ["kulturindustrie", "kultur industrie"],
    "Kapitalismus": ["kapitalismus", "kapital", "warenform", "wertkritik", "wert-abspaltung", "arbeitskritik", "arbeitskritische"],
    "Antisemitismus": ["antisemitismus", "antisemitisch", "antisemitische", "judenhass", "israelbezogener antisemitismus"],
    "Rassismus": ["rassismus", "rassistisch", "rassistische", "postkolonial", "kolonialismus"],
    "Nationalsozialismus": ["nationalsozialismus", "nationalsozialist", "nazismus", "ns", "shoah", "auschwitz"],
    "Faschismus": ["faschismus", "faschistisch", "faschistische"],
    "Israel": ["israel", "zionismus", "zionistisch", "nahost", "palästina", "palaestina"],
    "Islamismus": ["islamismus", "islamistisch", "jihad", "dschihad"],
    "Psychoanalyse": ["psychoanalyse", "psychoanalytisch", "unbewusst", "trieb", "verdrängung", "verdraengung"],
    "Sexualität": ["sexualität", "sexualitaet", "sexuelle", "pornografie", "prostitution", "begehren"],
    "Feminismus": ["feminismus", "feministisch", "patriarchat", "geschlecht", "gender"],
    "Anarchismus": ["anarchismus", "anarchie", "kommende aufstand", "tiqqun"],
    "Radio": ["radio", "rundfunk", "feature", "freie radios"],
    "Literatur": ["literatur", "roman", "lesung", "celan", "peter weiss"],
}

ACRONYMS = {
    "ag": "AG", "br": "BR", "dlf": "DLF", "ndr": "NDR", "swr": "SWR", "wdr": "WDR",
    "hr": "HR", "rbb": "RBB", "frn": "FRN", "xxi": "XXI", "ns": "NS", "usa": "USA",
    "eu": "EU", "raf": "RAF", "ddr": "DDR", "brd": "BRD", "mp3": "MP3",
}

WORD_REPLACEMENTS = [
    (r"\bbegruessung\b", "Begrüßung"),
    (r"\babschliessend\b", "abschließend"),
    (r"\babschied\b", "Abschied"),
    (r"\bueber\b", "über"),
    (r"\bfuer\b", "für"),
    (r"\bgegenwaert\b", "Gegenwart"),
    (r"\bgegenwaertigkeit\b", "Gegenwärtigkeit"),
    (r"\baktualitaet\b", "Aktualität"),
    (r"\btraditionalitaet\b", "Traditionalität"),
    (r"\bgeschichte\b", "Geschichte"),
    (r"\bkommende\b", "kommende"),
]

@dataclass
class Track:
    title: str
    name: str
    url: str
    folder: str
    path: str
    displayPath: str
    source: str
    tags: list[str]
    size: str = ""
    sizeBytes: int = 0
    date: str = ""
    description: str = ""
    youtubeUrl: str = ""

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
    req = Request(url, headers={"User-Agent": "k23-audio-browser-crawler/1.1"})
    with urlopen(req, timeout=timeout) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, errors="replace")


def normalize(text: str) -> str:
    text = unquote(text).lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_audio_ext(name: str) -> str:
    return re.sub(r"\.(mp3|m4a|ogg|oga|wav|flac|aac)$", "", name, flags=re.I)


def fix_acronyms(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        word = m.group(0)
        return ACRONYMS.get(word.lower(), word)
    return re.sub(r"\b[a-zA-Z]{2,4}\b", repl, text)


def humanize_text(text: str, remove_leading_number: bool = False) -> str:
    text = unquote(text)
    text = strip_audio_ext(text)
    text = text.replace("%20", " ")
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"[.]+", " ", text)
    text = re.sub(r"\s*[-–—]+\s*", " – ", text)

    # CamelCase / angeklebte Wörter auftrennen.
    text = re.sub(r"([a-zäöüß])([A-ZÄÖÜ])", r"\1 \2", text)
    text = re.sub(r"([A-Za-zÄÖÜäöüß])([0-9])", r"\1 \2", text)
    text = re.sub(r"([0-9])([A-Za-zÄÖÜäöüß])", r"\1 \2", text)

    if remove_leading_number:
        text = re.sub(r"^\s*\d{1,3}\s+", "", text)

    # Häufige angehängte Angaben absetzen.
    text = re.sub(r"^(.+?)\s+(Diskussion|Gespräch|Gespraech|Interview|Vortrag|Lesung|Workshop|Mitschnitt)$", r"\1 – \2", text, flags=re.I)
    text = re.sub(r"\bTeil\s*(\d+)\b", r"Teil \1", text, flags=re.I)

    for pattern, replacement in WORD_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.I)

    text = re.sub(r"\s+", " ", text).strip(" –\t\n")
    text = fix_acronyms(text)

    # Wenn alles kleingeschrieben war: wenigstens den Anfang anheben.
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text or "Ohne Titel"


def guess_title(name: str) -> str:
    return humanize_text(name, remove_leading_number=True)


def pretty_folder(folder: str) -> str:
    if not folder:
        return "Archiv"
    parts = [humanize_text(p, remove_leading_number=False) for p in folder.split("/") if p]
    return " / ".join(parts) if parts else "Archiv"


def detect_person_tag(title: str) -> str | None:
    # Beispiele: "Thomas Ebermann – Die Pogrome ..." oder "Interview mit Roger Behrens".
    m = re.match(r"^([A-ZÄÖÜ][\wÄÖÜäöüß-]+(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüß-]+){1,2})\s+–\s+", title)
    if m:
        candidate = m.group(1).strip()
        if len(candidate) <= 40 and not candidate.lower().startswith(("der ", "die ", "das ", "eine ", "ein ")):
            return candidate
    m = re.search(r"\bmit\s+([A-ZÄÖÜ][\wÄÖÜäöüß-]+\s+[A-ZÄÖÜ][\wÄÖÜäöüß-]+)\b", title)
    if m:
        return m.group(1).strip()
    return None


def detect_tags(title: str, name: str, folder: str) -> list[str]:
    haystack = normalize(" ".join([title, name, folder, pretty_folder(folder)]))
    tags: list[str] = []
    for tag, aliases in TAG_RULES.items():
        for alias in aliases:
            a = normalize(alias)
            if a and re.search(rf"(^|\s){re.escape(a)}($|\s)", haystack):
                tags.append(tag)
                break

    person = detect_person_tag(title)
    if person and person not in tags:
        tags.append(person)

    source = folder.split("/", 1)[0] if folder else "Archiv"
    if source in ("Radio", "Referate") and source not in tags:
        tags.append(source)

    return sorted(tags, key=lambda x: normalize(x))


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
                continue
            name = unquote(parsed.path.rstrip("/").split("/")[-1])
            if href.endswith("/"):
                if abs_url not in seen_pages:
                    queue.append(abs_url)
            elif name.lower().endswith(AUDIO_EXT):
                folder = folder_from_url(abs_url, start_url)
                title = guess_title(name)
                display_path = pretty_folder(folder)
                source = folder.split("/", 1)[0] if folder else "Archiv"
                tracks.append(Track(
                    title=title,
                    name=name,
                    url=abs_url,
                    folder=folder,
                    path=f"{folder}/{name}" if folder else name,
                    displayPath=display_path,
                    source=source,
                    tags=detect_tags(title, name, folder),
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
    tracks.sort(key=lambda t: (t.title.lower(), t.displayPath.lower()))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([asdict(t) for t in tracks], f, ensure_ascii=False, indent=2)
    print(f"Fertig: {len(tracks)} Audio-Dateien in {args.out}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Crawlt https://audioarchiv.k23.in/ und erzeugt audio-index.json.

Schwerpunkte:
- keine rohen Dateinamen in der Website anzeigen
- Unterstriche/Punkte/CamelCase bereinigen
- häufige falsche Schreibweisen und fehlende Umlaute korrigieren
- Datumsangaben aus Titeln entfernen und separat als dateLabel speichern
- Tags aus Namen, Themen, Ordnern und Titeln erzeugen
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://audioarchiv.k23.in/"
AUDIO_EXT = (".mp3", ".m4a", ".ogg", ".oga", ".wav", ".flac", ".aac")
SKIP_NAMES = {"Parent Directory", "Parent directory", "../", ".."}

TAG_RULES: dict[str, list[str]] = {
    # Personen / Theorie
    "Adorno": ["adorno", "theodor w adorno", "theodor adorno", "t w adorno"],
    "Horkheimer": ["horkheimer", "max horkheimer"],
    "Marcuse": ["marcuse", "herbert marcuse"],
    "Benjamin": ["benjamin", "walter benjamin"],
    "Freud": ["freud", "sigmund freud"],
    "Marx": ["marx", "karl marx"],
    "Engels": ["engels", "friedrich engels"],
    "Hegel": ["hegel", "g w f hegel"],
    "Nietzsche": ["nietzsche", "friedrich nietzsche"],
    "Jean Améry": ["jean amery", "jean am ery", "amery", "améry"],
    "Hannah Arendt": ["hannah arendt", "arendt"],
    "Günther Anders": ["gunther anders", "guenther anders", "günther anders"],
    "Moishe Postone": ["moishe postone", "postone"],
    "Leo Löwenthal": ["leo lowenthal", "leo loewenthal", "löwenthal", "loewenthal"],
    "Franz Neumann": ["franz neumann"],
    "Johannes Agnoli": ["johannes agnoli", "agnoli"],
    "Roger Behrens": ["roger behrens", "behrens"],
    "Thomas Ebermann": ["thomas ebermann", "ebermann"],
    "Peter Weiss": ["peter weiss"],
    "Paul Celan": ["paul celan", "celan"],
    "Gisela Elsner": ["gisela elsner", "elsner"],
    "Klaus Theweleit": ["klaus theweleit", "theweleit"],

    # Themen
    "Kritische Theorie": ["kritische theorie", "frankfurter schule", "negative dialektik", "dialektik der aufklaerung", "dialektik der aufklärung"],
    "Dialektik": ["dialektik", "dialektisch"],
    "Ideologiekritik": ["ideologiekritik", "ideologie", "falsches bewusstsein"],
    "Kulturindustrie": ["kulturindustrie", "kultur industrie"],
    "Kapitalismus": ["kapitalismus", "kapital", "warenform", "wertkritik", "wert-abspaltung", "arbeitskritik", "arbeitskritische"],
    "Antisemitismus": ["antisemitismus", "antisemitisch", "antisemitische", "judenhass", "israelbezogener antisemitismus"],
    "Rassismus": ["rassismus", "rassistisch", "rassistische", "postkolonial", "kolonialismus"],
    "Nationalsozialismus": ["nationalsozialismus", "nationalsozialist", "nazismus", "shoah", "auschwitz", "ns-vergangenheit"],
    "Faschismus": ["faschismus", "faschistisch", "faschistische"],
    "Israel": ["israel", "zionismus", "zionistisch", "nahost", "palaestina", "palästina"],
    "Islamismus": ["islamismus", "islamistisch", "jihad", "dschihad"],
    "Psychoanalyse": ["psychoanalyse", "psychoanalytisch", "unbewusst", "trieb", "verdrängung", "verdraengung"],
    "Sexualität": ["sexualitaet", "sexualität", "sexuelle", "pornografie", "prostitution", "begehren"],
    "Feminismus": ["feminismus", "feministisch", "patriarchat", "geschlecht", "gender"],
    "Anarchismus": ["anarchismus", "anarchie", "kommende aufstand", "tiqqun"],
    "Literatur": ["literatur", "roman", "lesung", "celan", "peter weiss"],
    "Radio": ["radio", "rundfunk", "feature", "freie radios"],
}

ACRONYMS = {
    "ag": "AG", "br": "BR", "dlf": "DLF", "ndr": "NDR", "swr": "SWR", "wdr": "WDR",
    "hr": "HR", "rbb": "RBB", "frn": "FRN", "xxi": "XXI", "ns": "NS", "usa": "USA",
    "eu": "EU", "raf": "RAF", "ddr": "DDR", "brd": "BRD", "mp3": "MP3", "fm": "FM",
}

# Regex-Korrekturen werden nach der groben Bereinigung angewendet.
TEXT_FIXES: list[tuple[str, str]] = [
    (r"\bJean\s+Am\s+Ery\b", "Jean Améry"),
    (r"\bJean\s+Amery\b", "Jean Améry"),
    (r"\bAmery\b", "Améry"),
    (r"\bGuenther\s+Anders\b", "Günther Anders"),
    (r"\bGunther\s+Anders\b", "Günther Anders"),
    (r"\bG\.W\.F\.\s*Hegel\b", "G. W. F. Hegel"),
    (r"\bTheodor\s+W\s+Adorno\b", "Theodor W. Adorno"),
    (r"\bMax\s+Horkheimer\b", "Max Horkheimer"),
    (r"\bWalter\s+Benjamin\b", "Walter Benjamin"),
    (r"\bLeo\s+Loewenthal\b", "Leo Löwenthal"),
    (r"\bLeo\s+Lowenthal\b", "Leo Löwenthal"),
    (r"\bMoishe\s+Postone\b", "Moishe Postone"),
    (r"\bPalaestina\b", "Palästina"),
    (r"\bZionismus\b", "Zionismus"),
    (r"\bAntisemitismus\b", "Antisemitismus"),
    (r"\bRassismus\b", "Rassismus"),
    (r"\bKritische\s+Theorie\b", "Kritische Theorie"),
    (r"\bNegative\s+Dialektik\b", "Negative Dialektik"),
    (r"\bDialektik\s+der\s+Aufklaerung\b", "Dialektik der Aufklärung"),
    (r"\bAufklaerung\b", "Aufklärung"),
    (r"\bBegruessung\b", "Begrüßung"),
    (r"\bGrusswort\b", "Grußwort"),
    (r"\bGespraech\b", "Gespräch"),
    (r"\bGespraeche\b", "Gespräche"),
    (r"\bUeber\b", "Über"),
    (r"\bueber\b", "über"),
    (r"\bFuer\b", "Für"),
    (r"\bfuer\b", "für"),
    (r"\bGegenwaertigkeit\b", "Gegenwärtigkeit"),
    (r"\bGegenwaertige\b", "Gegenwärtige"),
    (r"\bGegenwart\b", "Gegenwart"),
    (r"\bAktualitaet\b", "Aktualität"),
    (r"\bTraditionalitaet\b", "Traditionalität"),
    (r"\bOekonomie\b", "Ökonomie"),
    (r"\boekonomie\b", "Ökonomie"),
    (r"\bAesthetik\b", "Ästhetik"),
    (r"\baesthetik\b", "Ästhetik"),
    (r"\bSexualitaet\b", "Sexualität"),
    (r"\bOeffentlichkeit\b", "Öffentlichkeit"),
    (r"\boeffentlichkeit\b", "Öffentlichkeit"),
    (r"\bNationalsozialismus\b", "Nationalsozialismus"),
    (r"\bFaschismus\b", "Faschismus"),
    (r"\bKapitalismus\b", "Kapitalismus"),
]

DATE_PATTERNS = [
    re.compile(r"(?P<all>\b(?P<y>19\d{2}|20\d{2})[-_. ](?P<m>0?[1-9]|1[0-2])[-_. ](?P<d>0?[1-9]|[12]\d|3[01])\b)"),
    re.compile(r"(?P<all>\b(?P<d>0?[1-9]|[12]\d|3[01])[-_. ](?P<m>0?[1-9]|1[0-2])[-_. ](?P<y>19\d{2}|20\d{2})\b)"),
]

@dataclass
class Track:
    id: str
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
    dateLabel: str = ""
    dateIso: str = ""
    sortDate: str = ""
    description: str = ""
    youtubeUrl: str = ""
    youtubeTitle: str = ""
    matchScore: float = 0.0

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
    req = Request(url, headers={"User-Agent": "k23-audio-browser-crawler/2.0"})
    with urlopen(req, timeout=timeout) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, errors="replace")


def strip_audio_ext(name: str) -> str:
    return re.sub(r"\.(mp3|m4a|ogg|oga|wav|flac|aac)$", "", name, flags=re.I)


def normalize(value: str) -> str:
    s = unquote(str(value)).lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def apply_text_fixes(text: str) -> str:
    for pattern, replacement in TEXT_FIXES:
        text = re.sub(pattern, replacement, text, flags=re.I)
    def acronym(m: re.Match[str]) -> str:
        word = m.group(0)
        return ACRONYMS.get(word.lower(), word)
    text = re.sub(r"\b[a-zA-Z]{2,4}\b", acronym, text)
    return text


def extract_date(text: str) -> tuple[str, str, str]:
    """Return text_without_date, date_label, date_iso."""
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        date_label = f"{d:02d}.{mo:02d}.{y:04d}"
        date_iso = f"{y:04d}-{mo:02d}-{d:02d}"
        before = text[:m.start()]
        after = text[m.end():]
        cleaned = (before + " " + after).strip()
        cleaned = re.sub(r"\b(am|vom|v\.?)\s*$", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"\s*[()\[\]_-]+\s*", " ", cleaned).strip()
        return cleaned, date_label, date_iso
    return text, "", ""


def humanize_text(text: str, *, remove_leading_number: bool = False) -> str:
    text = unquote(str(text))
    text = strip_audio_ext(text)
    text = text.replace("%20", " ")
    text = text.replace("+", " ")
    text = re.sub(r"[_]+", " ", text)
    text = re.sub(r"[.]+", " ", text)
    text = re.sub(r"\s*[-–—]+\s*", " – ", text)
    text = re.sub(r"([a-zäöüß])([A-ZÄÖÜ])", r"\1 \2", text)
    text = re.sub(r"([A-Za-zÄÖÜäöüß])([0-9])", r"\1 \2", text)
    text = re.sub(r"([0-9])([A-Za-zÄÖÜäöüß])", r"\1 \2", text)
    if remove_leading_number:
        text = re.sub(r"^\s*\d{1,3}\s+", "", text)
    text = re.sub(r"^(.+?)\s+(Diskussion|Gespraech|Gespräch|Interview|Vortrag|Lesung|Workshop|Mitschnitt)$", r"\1 – \2", text, flags=re.I)
    text = re.sub(r"\bTeil\s*(\d+)\b", r"Teil \1", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" –\t\n")
    text = apply_text_fixes(text)
    text = re.sub(r"\s+", " ", text).strip(" –\t\n")
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text or "Ohne Titel"


def title_from_filename(name: str) -> tuple[str, str, str]:
    rough = humanize_text(name, remove_leading_number=True)
    without_date, date_label, date_iso = extract_date(rough)
    title = humanize_text(without_date, remove_leading_number=True)
    return title, date_label, date_iso


def pretty_folder(folder: str) -> str:
    if not folder:
        return "Archiv"
    parts = [humanize_text(p, remove_leading_number=False) for p in folder.split("/") if p]
    return " / ".join(parts) if parts else "Archiv"


def detect_person_tag(title: str) -> str | None:
    m = re.match(r"^([A-ZÄÖÜ][\wÄÖÜäöüßéÉèÈ-]+(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüßéÉèÈ.-]+){1,3})\s+–\s+", title)
    if m:
        candidate = apply_text_fixes(m.group(1).strip())
        if len(candidate) <= 48 and not candidate.lower().startswith(("der ", "die ", "das ", "eine ", "ein ")):
            return candidate
    m = re.search(r"\bmit\s+([A-ZÄÖÜ][\wÄÖÜäöüßéÉèÈ.-]+\s+[A-ZÄÖÜ][\wÄÖÜäöüßéÉèÈ.-]+)\b", title)
    if m:
        return apply_text_fixes(m.group(1).strip())
    return None


def detect_tags(*texts: str) -> list[str]:
    haystack = normalize(" ".join(t for t in texts if t))
    tags: list[str] = []
    for tag, aliases in TAG_RULES.items():
        for alias in aliases:
            if normalize(alias) in haystack:
                tags.append(tag)
                break
    person = detect_person_tag(texts[0] if texts else "")
    if person and person not in tags:
        tags.insert(0, person)
    return sorted(set(tags), key=lambda t: (t.lower() not in {"adorno", "kritische theorie"}, t.lower()))


def is_audio_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(AUDIO_EXT)


def should_skip(href: str, text: str) -> bool:
    label = unquote(text or href).strip().strip("/")
    if label in SKIP_NAMES or href.startswith("?") or href.startswith("#"):
        return True
    return False


def stable_id(url: str) -> str:
    import hashlib
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def crawl(base: str, max_pages: int = 1200, delay: float = 0.05) -> list[Track]:
    base = base.rstrip("/") + "/"
    seen_pages: set[str] = set()
    queue = [base]
    tracks: dict[str, Track] = {}

    while queue and len(seen_pages) < max_pages:
        page = queue.pop(0)
        if page in seen_pages:
            continue
        seen_pages.add(page)
        print(f"[crawl] {page}", file=sys.stderr)
        try:
            html = fetch(page)
        except Exception as exc:
            print(f"[warn] {page}: {exc}", file=sys.stderr)
            continue
        parser = IndexParser()
        parser.feed(html)
        for href, text in parser.links:
            if should_skip(href, text):
                continue
            absolute = urljoin(page, href)
            if not absolute.startswith(base):
                continue
            parsed = urlparse(absolute)
            if is_audio_url(absolute):
                rel = parsed.path[len(urlparse(base).path):].lstrip("/")
                path = PurePosixPath(unquote(rel))
                name = path.name
                folder = str(path.parent) if str(path.parent) != "." else ""
                title, date_label, date_iso = title_from_filename(name)
                display_path = pretty_folder(folder)
                tags = detect_tags(title, name, folder, display_path)
                tracks[absolute] = Track(
                    id=stable_id(absolute),
                    title=title,
                    name=name,
                    url=absolute,
                    folder=folder,
                    path=unquote(rel),
                    displayPath=display_path,
                    source="K23 Audioarchiv",
                    tags=tags,
                    dateLabel=date_label,
                    dateIso=date_iso,
                    sortDate=date_iso,
                )
            elif href.endswith("/"):
                # Verzeichnisse rekursiv aufnehmen.
                if absolute not in seen_pages and absolute not in queue:
                    queue.append(absolute)
        if delay:
            time.sleep(delay)
    return sorted(tracks.values(), key=lambda t: (t.displayPath.lower(), t.title.lower()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--out", default="audio-index.json")
    ap.add_argument("--max-pages", type=int, default=1200)
    ap.add_argument("--delay", type=float, default=0.05)
    args = ap.parse_args()
    tracks = crawl(args.base, max_pages=args.max_pages, delay=args.delay)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([asdict(t) for t in tracks], f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(tracks)} tracks to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Lädt öffentliche YouTube-Metadaten des Kanals „The Nokturnal Times" per yt-dlp,
gleicht sie vorsichtig mit audio-index.json ab und ergänzt passende Einträge um:
- youtubeUrl
- youtubeTitle
- description
- youtubeMatchScore

Nutzung lokal:
  python3 -m pip install yt-dlp
  python3 crawl_k23.py
  python3 crawl_youtube.py --audio-index audio-index.json --out audio-index.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

DEFAULT_CHANNEL = "https://www.youtube.com/channel/UCgj0uCW9VR8p3PUJ91oDz9g/videos"

STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "und", "oder",
    "zur", "zum", "von", "vom", "mit", "im", "in", "am", "an", "auf", "fuer", "für", "ueber", "über",
    "the", "a", "an", "of", "and", "or", "to", "for", "with",
}

GENERIC_TITLES = {
    "begruessung", "begrussung", "begrüßung", "diskussion", "abschlussdiskussion",
    "einleitung", "intro", "teil", "vortrag", "interview", "gespraech", "gespräch",
}

@dataclass
class Video:
    title: str
    url: str
    description: str = ""
    uploadDate: str = ""
    duration: int = 0
    channel: str = ""


def normalize(text: str) -> str:
    text = str(text or "").lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b(the\s+)?nokturnal\s+times\b", " ", text)
    text = re.sub(r"\b(audioarchiv|k23|radio|referate)\b", " ", text)
    text = re.sub(r"\.(mp3|m4a|ogg|oga|wav|flac|aac)\b", " ", text)
    text = re.sub(r"[_./|]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) > 2 and t not in STOPWORDS}


def score_titles(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = tokens(na), tokens(nb)
    if not ta or not tb:
        return ratio
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    return max(ratio, 0.55 * ratio + 0.35 * overlap + 0.10 * jaccard)


def clean_description(description: str, limit: int = 1800) -> str:
    description = str(description or "")
    description = description.replace("\r\n", "\n").replace("\r", "\n")
    # Überlange Link-Sammlungen und Hashtag-Blöcke unten stören in der Kartenansicht oft mehr, als sie helfen.
    lines = []
    for line in description.split("\n"):
        stripped = line.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if stripped.startswith("#") and len(stripped.split()) <= 8:
            continue
        lines.append(stripped)
    out = "\n".join(lines).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].strip() + "…"
    return out


def run_ytdlp(channel_url: str, max_videos: int = 0) -> list[Video]:
    cmd = [
        "yt-dlp",
        "--ignore-errors",
        "--no-warnings",
        "--skip-download",
        "--dump-json",
    ]
    if max_videos and max_videos > 0:
        cmd += ["--playlist-end", str(max_videos)]
    cmd.append(channel_url)

    print("YouTube: lade Metadaten mit yt-dlp …", file=sys.stderr)
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except FileNotFoundError:
        print("WARN: yt-dlp ist nicht installiert. Überspringe YouTube-Abgleich.", file=sys.stderr)
        return []

    if proc.returncode not in (0, 1):
        print(proc.stderr[-2000:], file=sys.stderr)
        print(f"WARN: yt-dlp endete mit Code {proc.returncode}. Überspringe YouTube-Abgleich.", file=sys.stderr)
        return []

    videos: list[Video] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        title = item.get("title") or ""
        video_id = item.get("id") or ""
        webpage_url = item.get("webpage_url") or item.get("url") or ""
        if not title or not video_id:
            continue
        if webpage_url and webpage_url.startswith("http"):
            url = webpage_url
        else:
            url = f"https://www.youtube.com/watch?v={video_id}"
        videos.append(Video(
            title=title.strip(),
            url=url,
            description=clean_description(item.get("description") or ""),
            uploadDate=item.get("upload_date") or "",
            duration=int(item.get("duration") or 0),
            channel=item.get("channel") or item.get("uploader") or "The Nokturnal Times",
        ))
    print(f"YouTube: {len(videos)} Videos gelesen.", file=sys.stderr)
    return videos


def should_replace_title(track_title: str, youtube_title: str, match_score: float) -> bool:
    nt = normalize(track_title)
    ny = normalize(youtube_title)
    if match_score < 0.80:
        return False
    if len(ny) >= len(nt) + 12:
        return True
    tt = tokens(track_title)
    if tt and tt <= GENERIC_TITLES and len(ny) > len(nt):
        return True
    if re.match(r"^(\d+\s+)?(begruessung|begrüßung|diskussion|einleitung|intro)\b", nt):
        return True
    return False


def merge(audio_index: list[dict[str, Any]], videos: list[Video], threshold: float = 0.76) -> tuple[list[dict[str, Any]], int]:
    if not videos:
        return audio_index, 0

    # Für Geschwindigkeit: erst grob nach Token-Überlappung filtern, dann genau scoren.
    video_tokens = [(v, tokens(v.title)) for v in videos]
    matched = 0

    for track in audio_index:
        title = str(track.get("title") or track.get("name") or "")
        name = str(track.get("name") or "")
        folder = str(track.get("displayPath") or track.get("folder") or "")
        track_text = f"{title} {name} {folder}"
        tt = tokens(track_text)

        best_video: Video | None = None
        best_score = 0.0
        for video, vt in video_tokens:
            if tt and vt and not (tt & vt):
                continue
            s1 = score_titles(title, video.title)
            s2 = score_titles(f"{title} {folder}", video.title)
            s3 = score_titles(name, video.title)
            s = max(s1, s2, s3)
            if s > best_score:
                best_score = s
                best_video = video

        if best_video and best_score >= threshold:
            track["youtubeUrl"] = best_video.url
            track["youtubeTitle"] = best_video.title
            track["youtubeMatchScore"] = round(best_score, 3)
            if best_video.description and not track.get("description"):
                track["description"] = best_video.description
            if best_video.uploadDate and not track.get("youtubeUploadDate"):
                track["youtubeUploadDate"] = best_video.uploadDate
            if should_replace_title(title, best_video.title, best_score):
                track["originalTitle"] = title
                track["title"] = best_video.title
            # YouTube-Titel/Beschreibung auch in Tagsuche indirekt nutzbar machen, indem app.js sie einliest.
            matched += 1

    return audio_index, matched


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=DEFAULT_CHANNEL, help="YouTube-Kanal-/Videos-URL")
    ap.add_argument("--audio-index", default="audio-index.json", help="bestehende audio-index.json")
    ap.add_argument("--out", default="audio-index.json", help="Zieldatei für angereicherte audio-index.json")
    ap.add_argument("--youtube-out", default="youtube-index.json", help="separate Metadatendatei für YouTube-Rohdaten")
    ap.add_argument("--threshold", type=float, default=0.76, help="Fuzzy-Match-Schwelle, höher = vorsichtiger")
    ap.add_argument("--max-videos", type=int, default=0, help="0 = alle Videos, sonst Begrenzung zum Testen")
    args = ap.parse_args()

    audio_path = Path(args.audio_index)
    if not audio_path.exists():
        raise SystemExit(f"Fehlt: {audio_path}. Erst crawl_k23.py ausführen.")

    audio_index = json.loads(audio_path.read_text(encoding="utf-8"))
    videos = run_ytdlp(args.channel, max_videos=args.max_videos)

    Path(args.youtube_out).write_text(
        json.dumps([asdict(v) for v in videos], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    merged, matched = merge(audio_index, videos, threshold=args.threshold)
    Path(args.out).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"YouTube-Abgleich: {matched} Audio-Einträge ergänzt. Ausgabe: {args.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Ergänzt audio-index.json mit YouTube-Titeln und Beschreibungen.

Standardkanal: The Nokturnal Times
https://www.youtube.com/channel/UCgj0uCW9VR8p3PUJ91oDz9g

Benötigt yt-dlp. Im GitHub-Workflow wird es automatisch installiert.
Wenn YouTube temporär blockiert oder yt-dlp fehlt, bricht das Skript nicht hart ab,
sondern lässt den Audioindex verwendbar.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

from crawl_k23 import apply_text_fixes, detect_tags, extract_date, humanize_text, normalize

CHANNEL_URL = "https://www.youtube.com/channel/UCgj0uCW9VR8p3PUJ91oDz9g/videos"

@dataclass
class Video:
    title: str
    url: str
    description: str
    upload_date: str = ""


def import_ytdlp():
    try:
        import yt_dlp  # type: ignore
        return yt_dlp
    except Exception as exc:
        print(f"[warn] yt-dlp nicht verfügbar: {exc}", file=sys.stderr)
        return None


def clean_youtube_title(title: str) -> tuple[str, str, str]:
    title = humanize_text(title, remove_leading_number=True)
    title, date_label, date_iso = extract_date(title)
    title = apply_text_fixes(title)
    title = re.sub(r"\s+", " ", title).strip(" –")
    return title or "Ohne Titel", date_label, date_iso


def get_video_url(entry: dict[str, Any]) -> str:
    if entry.get("webpage_url"):
        return str(entry["webpage_url"])
    if entry.get("url") and str(entry["url"]).startswith("http"):
        return str(entry["url"])
    vid = entry.get("id") or entry.get("url")
    return f"https://www.youtube.com/watch?v={vid}" if vid else ""


def fetch_youtube(channel_url: str, max_videos: int) -> list[Video]:
    yt_dlp = import_ytdlp()
    if yt_dlp is None:
        return []

    flat_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "playlistend": max_videos,
        "socket_timeout": 30,
    }
    full_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": True,
        "socket_timeout": 30,
    }

    videos: list[Video] = []
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
    entries = (info or {}).get("entries") or []
    entries = [e for e in entries if e][:max_videos]
    print(f"[youtube] {len(entries)} Einträge gefunden", file=sys.stderr)

    with yt_dlp.YoutubeDL(full_opts) as ydl:
        for i, entry in enumerate(entries, 1):
            url = get_video_url(entry)
            if not url:
                continue
            try:
                info = ydl.extract_info(url, download=False) or entry
            except Exception as exc:
                print(f"[youtube warn] {url}: {exc}", file=sys.stderr)
                info = entry
            raw_title = info.get("title") or entry.get("title") or ""
            title, _, _ = clean_youtube_title(raw_title)
            description = info.get("description") or entry.get("description") or ""
            webpage_url = info.get("webpage_url") or url
            upload_date = info.get("upload_date") or entry.get("upload_date") or ""
            videos.append(Video(title=title, url=webpage_url, description=description, upload_date=str(upload_date)))
            print(f"[youtube] {i}/{len(entries)} {title}", file=sys.stderr)
    return videos


def token_set(text: str) -> set[str]:
    stop = {"der", "die", "das", "und", "oder", "ein", "eine", "einer", "eines", "zu", "zur", "zum", "von", "mit", "im", "im", "am", "an", "auf", "ueber", "uber", "teil", "vortrag", "diskussion", "gespraech", "gesprach"}
    return {w for w in normalize(text).split() if len(w) > 2 and w not in stop}


def match_score(audio_title: str, video_title: str) -> float:
    a = normalize(audio_title)
    b = normalize(video_title)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = token_set(a), token_set(b)
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    containment = 0.0
    if len(a) > 12 and len(b) > 12 and (a in b or b in a):
        containment = 0.93
    return max(ratio, overlap * 0.92, containment)


def enrich_tracks(tracks: list[dict[str, Any]], videos: list[Video], threshold: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    enriched = 0
    title_replaced = 0
    report_matches: list[dict[str, Any]] = []
    for track in tracks:
        title = track.get("title") or track.get("name") or ""
        best_video: Video | None = None
        best_score = 0.0
        for video in videos:
            score = match_score(title, video.title)
            if score > best_score:
                best_video, best_score = video, score
        if best_video and best_score >= threshold:
            enriched += 1
            track["youtubeUrl"] = best_video.url
            track["youtubeTitle"] = best_video.title
            track["description"] = best_video.description.strip()
            track["matchScore"] = round(best_score, 3)

            yt_title, yt_date_label, yt_date_iso = clean_youtube_title(best_video.title)
            # YouTube-Titel nur dann übernehmen, wenn der Treffer sehr sicher ist
            # oder der Audio-Titel auffällig kurz / generisch ist.
            generic = len(token_set(title)) <= 3 or re.search(r"\b(begrüßung|grusswort|grußwort|track|audio|mitschnitt)\b", normalize(title))
            if best_score >= 0.88 or generic:
                if yt_title and yt_title != track.get("title"):
                    track["title"] = yt_title
                    title_replaced += 1
            if not track.get("dateLabel") and yt_date_label:
                track["dateLabel"] = yt_date_label
                track["dateIso"] = yt_date_iso
                track["sortDate"] = yt_date_iso
            elif not track.get("dateLabel") and best_video.upload_date and len(best_video.upload_date) == 8:
                y, m, d = best_video.upload_date[:4], best_video.upload_date[4:6], best_video.upload_date[6:8]
                track["dateLabel"] = f"{d}.{m}.{y}"
                track["dateIso"] = f"{y}-{m}-{d}"
                track["sortDate"] = track["dateIso"]

            tags = detect_tags(track.get("title", ""), track.get("name", ""), track.get("folder", ""), track.get("displayPath", ""), best_video.description)
            track["tags"] = tags
            report_matches.append({
                "audio": title,
                "youtube": best_video.title,
                "score": round(best_score, 3),
                "url": best_video.url,
            })
    report = {"tracks": len(tracks), "videos": len(videos), "enriched": enriched, "title_replaced": title_replaced, "matches": report_matches[:300]}
    return tracks, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="audio-index.json")
    ap.add_argument("--youtube-out", default="youtube-index.json")
    ap.add_argument("--report", default="crawler-report.json")
    ap.add_argument("--channel", default=os.getenv("YOUTUBE_CHANNEL_URL", CHANNEL_URL))
    ap.add_argument("--max-videos", type=int, default=int(os.getenv("MAX_YOUTUBE_VIDEOS", "500")))
    ap.add_argument("--threshold", type=float, default=float(os.getenv("YOUTUBE_MATCH_THRESHOLD", "0.74")))
    args = ap.parse_args()

    with open(args.index, "r", encoding="utf-8") as f:
        tracks = json.load(f)

    videos = fetch_youtube(args.channel, args.max_videos)
    with open(args.youtube_out, "w", encoding="utf-8") as f:
        json.dump([asdict(v) for v in videos], f, ensure_ascii=False, indent=2)

    if videos:
        tracks, report = enrich_tracks(tracks, videos, args.threshold)
    else:
        report = {"tracks": len(tracks), "videos": 0, "enriched": 0, "title_replaced": 0, "matches": []}

    with open(args.index, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()

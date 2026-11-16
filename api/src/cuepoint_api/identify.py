"""Track identification via the audd.io recognition API.

For each analyzed segment, clip ~12 s from its middle (where one track plays
alone), send it to AudD, and write back artist/title. Segments the database
doesn't know stay unnamed — the UI labels them "Unreleased ID" once a full
identification pass has run. Tracklist-imported names (confidence 0.95) are
never overwritten."""

import json
import subprocess
import tempfile
import traceback
from pathlib import Path

import urllib3

from .config import settings
from .db import SessionLocal
from .models import SetRecord
from .storage import download_to

AUDD_URL = "https://api.audd.io/"
MATCH_CONFIDENCE = 0.85  # acoustic match, slightly below tracklist-import's 0.95
CLIP_S = 12.0


def parse_audd_response(data: dict) -> tuple[str, str] | None:
    """(artist, title) when AudD recognized the clip, else None."""
    if data.get("status") != "success":
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    artist = (result.get("artist") or "").strip()
    title = (result.get("title") or "").strip()
    if not artist and not title:
        return None
    return artist or "Unknown artist", title or "Unknown title"


def _recognize_clip(http: urllib3.PoolManager, clip_path: Path) -> tuple[str, str] | None:
    body = clip_path.read_bytes()
    r = http.request(
        "POST",
        AUDD_URL,
        fields={"api_token": settings.audd_token, "file": ("clip.mp3", body, "audio/mpeg")},
        timeout=urllib3.Timeout(total=30),
    )
    return parse_audd_response(json.loads(r.data))


def _cut_clip(src: Path, mid_s: float, out: Path) -> bool:
    start = max(0.0, mid_s - CLIP_S / 2)
    proc = subprocess.run(
        # protocol_whitelist: a malicious "audio" file that is really a playlist
        # (HLS/concat) must not make ffmpeg fetch URLs or read local paths.
        ["ffmpeg", "-y", "-nostdin", "-v", "error", "-protocol_whitelist", "file,crypto",
         "-ss", f"{start:.2f}", "-t", f"{CLIP_S:.0f}",
         "-i", str(src), "-ac", "1", "-b:a", "128k", str(out)],
        capture_output=True,
        timeout=60,
        check=False,  # a failed cut just means this segment is skipped
    )
    return proc.returncode == 0 and out.exists()


def run_identify(set_id: str) -> None:
    with SessionLocal() as db:
        rec = db.get(SetRecord, set_id)
        if rec is None:
            return
        audio_key = rec.audio_key

    try:
        http = urllib3.PoolManager()
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / f"audio{Path(audio_key).suffix or '.mp3'}"
            download_to(audio_key, audio)

            with SessionLocal() as db:
                rec = db.get(SetRecord, set_id)
                for i, seg in enumerate(rec.segments):
                    if seg.match_confidence is not None and seg.match_confidence >= 0.9:
                        continue  # named by tracklist import; keep it
                    clip = Path(tmp) / f"seg{i}.mp3"
                    mid = (seg.start_s + seg.end_s) / 2
                    match = None
                    if _cut_clip(audio, mid, clip):
                        match = _recognize_clip(http, clip)
                    if match is not None:
                        seg.artist, seg.title = match
                        seg.match_confidence = MATCH_CONFIDENCE
                    else:
                        seg.artist = None
                        seg.title = None
                        seg.match_confidence = 0.0
                    db.commit()  # per-segment, so partial progress survives a crash
                rec.identify_status = "done"
                db.commit()
    except Exception:
        print(f"[identify] failed for set {set_id}\n{traceback.format_exc()}", flush=True)
        with SessionLocal() as db:
            rec = db.get(SetRecord, set_id)
            if rec is not None:
                rec.identify_status = "failed"
                db.commit()
        raise

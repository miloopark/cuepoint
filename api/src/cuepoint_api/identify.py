"""Track identification via the audd.io recognition API.

For each analyzed segment, clip ~12 s from its middle (where one track plays
alone), send it to AudD, and write back artist/title. Segments the database
doesn't know stay unnamed — the UI labels them "Unreleased ID" once a full
identification pass has run. Tracklist-imported names (confidence 0.95) are
never overwritten.

Clips are seek-read from the original file at native sample rate (fingerprinting
needs full bandwidth) and the container gate is magic-byte sniffing — no
ffmpeg/ffprobe subprocess, which both simplifies deployment (Vercel functions)
and removes the external-parser attack surface."""

import contextlib
import io
import json
import time
import traceback

import soundfile as sf
import urllib3
from sqlalchemy import or_ as sa_or
from sqlalchemy import update as sa_update

from .config import settings
from .db import SessionLocal
from .models import SetRecord
from .queueing import IDENTIFY_JOB_TIMEOUT_S
from .storage import download_bytes, head_size

AUDD_URL = "https://api.audd.io/"
MATCH_CONFIDENCE = 0.85  # acoustic match, slightly below tracklist-import's 0.95
CLIP_S = 12.0

# Container formats we accept, by magic bytes. Anything else — playlists,
# concat lists, images — is not uploaded audio and never reaches a decoder.
ALLOWED_FORMATS = {"mp3", "wav", "flac", "aiff", "m4a", "ogg", "aac"}


def probe_format(src) -> str | None:
    """Identify the audio container by magic bytes (no external parser).
    Accepts raw bytes or a filesystem path."""
    if isinstance(src, (bytes, bytearray)):
        head = bytes(src[:16])
    else:
        try:
            with open(src, "rb") as f:
                head = f.read(16)
        except OSError:
            return None
    if len(head) < 4:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return "aiff"
    if head[:4] == b"OggS":
        return "ogg"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head[:3] == b"ID3":
        return "mp3"
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3"  # MPEG audio frame sync (raw MP3 or ADTS AAC — both allowed)
    return None


def claim_identify(set_id: str) -> float | None:
    """Atomically claim the identification slot for a set. Returns the claim
    timestamp, or None when a live run already holds it. Shared by the API
    route and the worker's auto-identify so neither can bypass the other."""
    stale_before = time.time() - 2 * IDENTIFY_JOB_TIMEOUT_S
    claim_ts = time.time()
    with SessionLocal() as db:
        claimed = db.execute(
            sa_update(SetRecord)
            .where(SetRecord.id == set_id)
            .where(
                sa_or(
                    SetRecord.identify_status.is_(None),
                    SetRecord.identify_status != "running",
                    SetRecord.identify_started_at < stale_before,
                )
            )
            .values(identify_status="running", identify_started_at=claim_ts)
        )
        db.commit()
        return claim_ts if claimed.rowcount == 1 else None


def release_failed_claim(set_id: str, claim_ts: float) -> None:
    """Revert a claim to 'failed' — only if we still own that exact claim."""
    with SessionLocal() as db:
        db.execute(
            sa_update(SetRecord)
            .where(SetRecord.id == set_id)
            .where(SetRecord.identify_status == "running")
            .where(SetRecord.identify_started_at == claim_ts)
            .values(identify_status="failed")
        )
        db.commit()


class AuddError(RuntimeError):
    """The API itself failed (bad token, quota, server error) — distinct from
    'recognized nothing', which is a normal outcome."""


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


def _recognize_clip(http: urllib3.PoolManager, wav_bytes: bytes) -> tuple[str, str] | None:
    r = http.request(
        "POST",
        AUDD_URL,
        fields={"api_token": settings.audd_token, "file": ("clip.wav", wav_bytes, "audio/wav")},
        timeout=urllib3.Timeout(total=30),
    )
    data = json.loads(r.data)
    if data.get("status") == "error":
        raise AuddError(str(data.get("error")))
    return parse_audd_response(data)


def _wav_clip(raw: bytes, mid_s: float) -> bytes | None:
    """CLIP_S seconds around mid_s as 16-bit WAV, seek-read from the original
    file at native sample rate — fingerprinting needs full bandwidth, not the
    reduced analysis rate."""
    with sf.SoundFile(io.BytesIO(raw)) as f:
        sr = f.samplerate
        half = int(CLIP_S / 2 * sr)
        start = max(0, int(mid_s * sr) - half)
        if start >= f.frames:
            return None
        f.seek(start)
        seg = f.read(min(2 * half, f.frames - start), dtype="float32", always_2d=True).mean(axis=1)
    if len(seg) < sr:  # under a second of audio — nothing to recognize
        return None
    buf = io.BytesIO()
    sf.write(buf, seg, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def run_identify(set_id: str) -> None:
    with SessionLocal() as db:
        rec = db.get(SetRecord, set_id)
        if rec is None:
            return
        audio_key = rec.audio_key

    try:
        http = urllib3.PoolManager()
        with contextlib.nullcontext():
            size = head_size(audio_key)
            if size is None or size > settings.max_upload_mb * 1024 * 1024:
                raise ValueError(f"object missing or exceeds {settings.max_upload_mb} MB cap")
            raw = download_bytes(audio_key)

            fmt = probe_format(raw)
            if fmt not in ALLOWED_FORMATS:
                raise ValueError(f"unsupported or unsafe container format: {fmt!r}")

            consecutive_api_errors = 0
            total_api_errors = 0
            with SessionLocal() as db:
                rec = db.get(SetRecord, set_id)
                for seg in rec.segments:
                    if seg.match_confidence is not None and seg.match_confidence >= 0.9:
                        continue  # named by tracklist import; keep it
                    mid = (seg.start_s + seg.end_s) / 2
                    match = None
                    try:
                        wav = _wav_clip(raw, mid)
                        if wav is not None:
                            match = _recognize_clip(http, wav)
                            # Reset only after an actual successful API response.
                            consecutive_api_errors = 0
                    except AuddError as e:
                        # Leave the segment untouched; a dead token/quota must
                        # fail the job, not mislabel everything "unreleased".
                        consecutive_api_errors += 1
                        total_api_errors += 1
                        if consecutive_api_errors >= 3 or total_api_errors >= 10:
                            raise ValueError(f"recognition API failing: {e}") from e
                        continue
                    if match is not None:
                        seg.artist, seg.title = match
                        seg.match_confidence = MATCH_CONFIDENCE
                    else:
                        seg.artist = None
                        seg.title = None
                        seg.match_confidence = 0.0
                    rec.identify_started_at = time.time()  # heartbeat for staleness checks
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

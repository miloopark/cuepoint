"""Cuepoint API. The browser uploads audio straight to object storage via a
presigned URL; this app only handles metadata, jobs, and results."""

import asyncio
import json
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from botocore.exceptions import BotoCoreError, ClientError
from cuepoint_analysis.labels import parse_tracklist
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_ as sa_or
from sqlalchemy import update as sa_update

from .config import settings
from .db import SessionLocal, engine
from .models import Base, SetRecord
from .queueing import enqueue_analysis, enqueue_identify, read_progress
from .storage import ensure_bucket, head_size, presign_get, presign_put


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    try:
        ensure_bucket()
    except (ClientError, BotoCoreError) as e:
        # Storage may be down (or absent in tests); uploads will surface the error.
        print(f"[api] could not ensure bucket at startup: {e}", flush=True)
    yield


app = FastAPI(title="Cuepoint API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


ALLOWED_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/aiff",
    "audio/x-aiff",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
}
# Exactly the shape create_upload issues — anything else is a forged key.
AUDIO_KEY_RE = re.compile(r"uploads/[0-9a-f]{32}/[A-Za-z0-9._-]{1,80}")


class UploadRequest(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"


class CreateSetRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    audio_key: str


class EditRequest(BaseModel):
    edit_token: str = Field(min_length=1, max_length=64)


class TracklistRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    offset_s: float = Field(default=0.0, ge=-7200, le=7200)
    edit_token: str = Field(min_length=1, max_length=64)


def _set_or_404(db, set_id: str) -> SetRecord:
    rec = db.get(SetRecord, set_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="set not found")
    return rec


def _status_payload(rec: SetRecord) -> dict:
    payload = {
        "id": rec.id,
        "title": rec.title,
        "status": rec.status,
        "progress": rec.progress,
        "stage": rec.stage,
        "duration_s": rec.duration_s,
        "error": rec.error,
        "identify_status": rec.identify_status,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
    if rec.status == "processing":
        live = read_progress(rec.id)
        if live:
            payload["progress"] = live["progress"]
            payload["stage"] = live["stage"]
    return payload


@app.post("/uploads")
def create_upload(req: UploadRequest) -> dict:
    if req.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="unsupported content type")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", req.filename)[-80:] or "audio"
    key = f"uploads/{uuid.uuid4().hex}/{safe}"
    return {"key": key, "upload_url": presign_put(key, req.content_type)}


@app.post("/sets", status_code=201)
def create_set(req: CreateSetRequest) -> dict:
    if not AUDIO_KEY_RE.fullmatch(req.audio_key):
        raise HTTPException(status_code=400, detail="invalid audio key")
    size = head_size(req.audio_key)
    if size is None:
        raise HTTPException(status_code=400, detail="no uploaded file at that key")
    if size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"file exceeds {settings.max_upload_mb} MB cap")
    with SessionLocal() as db:
        rec = SetRecord(title=req.title, audio_key=req.audio_key)
        db.add(rec)
        db.commit()
        payload = _status_payload(rec)
        # Returned only here, never on later reads: it's the uploader's edit capability.
        payload["edit_token"] = rec.edit_token
    enqueue_analysis(rec.id)
    return payload


@app.get("/sets/{set_id}")
def get_set(set_id: str) -> dict:
    with SessionLocal() as db:
        return _status_payload(_set_or_404(db, set_id))


def _current_payload(set_id: str) -> dict:
    with SessionLocal() as db:
        rec = db.get(SetRecord, set_id)
        return _status_payload(rec) if rec else {"status": "failed", "error": "not found"}


# Going async removed the threadpool's implicit cap on concurrent streams; these are
# the explicit ones: a global cap plus a per-set cap so no one set's viewers (or one
# abuser) can occupy every slot. Permits are acquired and released inside the
# generator so a response that is never iterated can't leak one.
_SSE_GLOBAL_SLOTS = asyncio.Semaphore(32)
_SSE_PER_SET_MAX = 4
_sse_per_set: dict[str, int] = {}

_BUSY_EVENT = f"data: {json.dumps({'status': 'busy'})}\n\n"


@app.get("/sets/{set_id}/events")
async def set_events(set_id: str) -> StreamingResponse:
    def check_exists() -> None:
        with SessionLocal() as db:
            _set_or_404(db, set_id)

    await run_in_threadpool(check_exists)  # forged ids never hold stream resources

    def _drop_per_set_count() -> None:
        remaining = _sse_per_set.get(set_id, 1) - 1
        if remaining <= 0:
            _sse_per_set.pop(set_id, None)
        else:
            _sse_per_set[set_id] = remaining

    async def stream():
        # Global slot first, so a connection that is merely waiting holds no
        # per-set budget.
        try:
            await asyncio.wait_for(_SSE_GLOBAL_SLOTS.acquire(), timeout=2.0)
        except TimeoutError:
            yield _BUSY_EVENT  # EventSource auto-reconnects after a pause
            return
        holds_per_set = False
        holds_global = True
        try:
            # Check-and-increment with no await in between (asyncio won't preempt),
            # so concurrent connects can't race past the per-set cap.
            count = _sse_per_set.get(set_id, 0)
            if count >= _SSE_PER_SET_MAX:
                # Let go of the global permit before the final write so a slow
                # reader can't pin it.
                _SSE_GLOBAL_SLOTS.release()
                holds_global = False
                yield _BUSY_EVENT
                return
            _sse_per_set[set_id] = count + 1
            holds_per_set = True
            # Short hold; longer jobs ride EventSource's automatic reconnect.
            for _ in range(180):
                payload = await run_in_threadpool(_current_payload, set_id)
                yield f"data: {json.dumps(payload)}\n\n"
                if payload["status"] in ("done", "failed"):
                    return
                await asyncio.sleep(1.0)
        finally:
            # One finally covers TimeoutError paths, client disconnect
            # (GeneratorExit), cancellation, and normal completion.
            if holds_global:
                _SSE_GLOBAL_SLOTS.release()
            if holds_per_set:
                _drop_per_set_count()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/sets/{set_id}/tracklist")
def import_tracklist(set_id: str, req: TracklistRequest) -> dict:
    """Name segments from a pasted tracklist: each segment takes the entry whose
    time interval contains the segment's midpoint."""
    with SessionLocal() as db:
        rec = _set_or_404(db, set_id)
        # Authorize before touching attacker-supplied text; encode so non-ASCII
        # tokens fail the comparison instead of raising.
        if not secrets.compare_digest((rec.edit_token or "").encode(), req.edit_token.encode()):
            raise HTTPException(status_code=403, detail="not allowed to edit this set")
        if rec.status != "done":
            raise HTTPException(status_code=409, detail="import after analysis finishes")

        entries = parse_tracklist(req.text)
        if not entries:
            raise HTTPException(status_code=400, detail="no timestamped lines found in tracklist")
        entries.sort(key=lambda e: e.start_s)
        named = 0
        for seg in rec.segments:
            midpoint = (seg.start_s + seg.end_s) / 2 + req.offset_s
            match = None
            for i, e in enumerate(entries):
                next_start = entries[i + 1].start_s if i + 1 < len(entries) else float("inf")
                if e.start_s <= midpoint < next_start:
                    match = e
                    break
            if match is not None:
                seg.artist = match.artist or None
                seg.title = match.title or None
                seg.match_confidence = 0.95  # named by tracklist, not fingerprint
                named += 1
        db.commit()
        return {"named": named, "segments": [s.to_dict() for s in rec.segments]}


@app.post("/sets/{set_id}/identify", status_code=202)
def identify_set(set_id: str, req: EditRequest) -> dict:
    """Queue a recognition pass over the set's segments (audd.io)."""
    if not settings.audd_token:
        raise HTTPException(status_code=503, detail="recognition not configured (CUEPOINT_AUDD_TOKEN)")
    with SessionLocal() as db:
        rec = _set_or_404(db, set_id)
        if not secrets.compare_digest((rec.edit_token or "").encode(), req.edit_token.encode()):
            raise HTTPException(status_code=403, detail="not allowed to edit this set")
        if rec.status != "done":
            raise HTTPException(status_code=409, detail="identify after analysis finishes")
        # Atomic claim; a "running" older than the job timeout is a dead worker
        # and may be retried.
        stale_before = time.time() - 1800
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
            .values(identify_status="running", identify_started_at=time.time())
        )
        if claimed.rowcount == 0:
            raise HTTPException(status_code=409, detail="identification already running")
        db.commit()
    try:
        enqueue_identify(set_id)
    except Exception:
        with SessionLocal() as db:
            rec = db.get(SetRecord, set_id)
            if rec is not None:
                rec.identify_status = "failed"
                db.commit()
        raise HTTPException(status_code=503, detail="job queue unavailable")
    return {"identify_status": "running"}


@app.get("/sets/{set_id}/analysis")
def get_analysis(set_id: str) -> dict:
    with SessionLocal() as db:
        rec = _set_or_404(db, set_id)
        if rec.status != "done" or rec.result is None:
            raise HTTPException(status_code=409, detail=f"analysis not ready (status: {rec.status})")
        return {
            "id": rec.id,
            "title": rec.title,
            "duration_s": rec.duration_s,
            "identify_status": rec.identify_status,
            "segments": [s.to_dict() for s in rec.segments],
            "features": rec.result["features"],
            "transitions": rec.result["transitions"],
        }


@app.get("/sets/{set_id}/waveform")
def get_waveform(set_id: str) -> dict:
    with SessionLocal() as db:
        rec = _set_or_404(db, set_id)
        if rec.status != "done" or rec.result is None:
            raise HTTPException(status_code=409, detail=f"analysis not ready (status: {rec.status})")
        return {"waveform": rec.result["waveform"], "duration_s": rec.duration_s}


@app.get("/sets/{set_id}/audio")
def get_audio(set_id: str) -> RedirectResponse:
    with SessionLocal() as db:
        rec = _set_or_404(db, set_id)
    return RedirectResponse(presign_get(rec.audio_key), status_code=307)


@app.get("/sets")
def list_sets(limit: int = 20) -> list[dict]:
    with SessionLocal() as db:
        recs = (
            db.query(SetRecord).order_by(SetRecord.created_at.desc()).limit(min(limit, 100)).all()
        )
        return [_status_payload(r) for r in recs]

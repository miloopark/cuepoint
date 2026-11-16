"""Cuepoint API. The browser uploads audio straight to object storage via a
presigned URL; this app only handles metadata, jobs, and results."""

import json
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import settings
from .db import SessionLocal, engine
from .models import Base, SetRecord
from .queueing import enqueue_analysis, read_progress
from .storage import ensure_bucket, presign_get, presign_put


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    try:
        ensure_bucket()
    except Exception:
        pass  # storage may be down in tests; uploads will surface the error
    yield


app = FastAPI(title="Cuepoint API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UploadRequest(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"


class CreateSetRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    audio_key: str


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
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", req.filename)[-80:]
    key = f"uploads/{uuid.uuid4().hex}/{safe}"
    return {"key": key, "upload_url": presign_put(key, req.content_type)}


@app.post("/sets", status_code=201)
def create_set(req: CreateSetRequest) -> dict:
    with SessionLocal() as db:
        rec = SetRecord(title=req.title, audio_key=req.audio_key)
        db.add(rec)
        db.commit()
        payload = _status_payload(rec)
    enqueue_analysis(rec.id)
    return payload


@app.get("/sets/{set_id}")
def get_set(set_id: str) -> dict:
    with SessionLocal() as db:
        return _status_payload(_set_or_404(db, set_id))


@app.get("/sets/{set_id}/events")
def set_events(set_id: str) -> StreamingResponse:
    def stream():
        while True:
            with SessionLocal() as db:
                rec = db.get(SetRecord, set_id)
                payload = _status_payload(rec) if rec else {"status": "failed", "error": "not found"}
            yield f"data: {json.dumps(payload)}\n\n"
            if payload["status"] in ("done", "failed"):
                return
            time.sleep(1.0)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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

"""The analysis job: download from storage, run the DSP pipeline, write results.

Run with:  rq worker --worker-class rq.SimpleWorker analysis
(SimpleWorker: no fork per job — macOS + numpy/Accelerate deadlock under fork.)"""

import tempfile
import traceback
from pathlib import Path

from cuepoint_analysis.pipeline import analyze_set

from .db import SessionLocal, engine
from .models import Base, SegmentRecord, SetRecord
from .config import settings
from .queueing import publish_progress
from .storage import download_to, head_size


def _update_set(set_id: str, **fields) -> None:
    with SessionLocal() as db:
        rec = db.get(SetRecord, set_id)
        if rec is None:
            return
        for k, v in fields.items():
            setattr(rec, k, v)
        db.commit()


def run_analysis(set_id: str) -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        rec = db.get(SetRecord, set_id)
        if rec is None:
            return
        audio_key = rec.audio_key

    _update_set(set_id, status="processing", progress=0.0, stage="downloading")
    publish_progress(set_id, 0.0, "downloading")

    try:
        # Re-check size at download time: the presigned PUT URL stays valid after
        # /sets accepts the key, so the create-time check alone can be raced.
        size = head_size(audio_key)
        if size is None or size > settings.max_upload_mb * 1024 * 1024:
            raise ValueError(f"object missing or exceeds {settings.max_upload_mb} MB cap")

        suffix = Path(audio_key).suffix or ".mp3"
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / f"audio{suffix}"
            download_to(audio_key, local)

            def progress(fraction: float, stage: str) -> None:
                publish_progress(set_id, fraction, stage)
                _update_set(set_id, progress=fraction, stage=stage)

            result = analyze_set(local, progress=progress)

        with SessionLocal() as db:
            rec = db.get(SetRecord, set_id)
            rec.duration_s = result["duration_s"]
            rec.status = "done"
            rec.progress = 1.0
            rec.stage = "done"
            rec.result = {
                "features": result["features"],
                "waveform": result["waveform"],
                "transitions": result["transitions"],
            }
            rec.segments.clear()
            for seg in result["segments"]:
                rec.segments.append(
                    SegmentRecord(
                        start_s=seg["start_s"],
                        end_s=seg["end_s"],
                        transition_start_s=seg["transition_start_s"],
                        transition_end_s=seg["transition_end_s"],
                        bpm=seg["bpm"],
                        camelot_key=seg["camelot_key"],
                        key_confidence=seg["key_confidence"],
                    )
                )
            db.commit()
        publish_progress(set_id, 1.0, "done")
    except Exception:
        # Full traceback goes to the worker log only; API consumers get a generic message.
        print(f"[worker] analysis failed for set {set_id}\n{traceback.format_exc()}", flush=True)
        _update_set(set_id, status="failed", error="Analysis failed — the file may be corrupt or unsupported.")
        publish_progress(set_id, 1.0, "failed")
        raise

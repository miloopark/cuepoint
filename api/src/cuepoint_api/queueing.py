"""RQ queue + Redis progress channel. Redis holds only the queue and live progress;
results land in Postgres."""

import json

from redis import Redis
from rq import Queue

from .config import settings

ANALYSIS_QUEUE = "analysis"


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url)


def enqueue_analysis(set_id: str) -> None:
    Queue(ANALYSIS_QUEUE, connection=get_redis()).enqueue(
        "cuepoint_api.worker.run_analysis", set_id, job_timeout=3600
    )


IDENTIFY_JOB_TIMEOUT_S = 1800


def enqueue_identify(set_id: str) -> None:
    Queue(ANALYSIS_QUEUE, connection=get_redis()).enqueue(
        "cuepoint_api.identify.run_identify", set_id, job_timeout=IDENTIFY_JOB_TIMEOUT_S
    )


def _progress_key(set_id: str) -> str:
    return f"set:{set_id}:progress"


def publish_progress(set_id: str, fraction: float, stage: str) -> None:
    get_redis().set(
        _progress_key(set_id), json.dumps({"progress": fraction, "stage": stage}), ex=86400
    )


def read_progress(set_id: str) -> dict | None:
    raw = get_redis().get(_progress_key(set_id))
    return json.loads(raw) if raw else None

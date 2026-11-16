"""Job queue in two modes, plus the Redis progress channel (local only).

- "rq": local docker Redis + RQ worker process.
- "vercel": Vercel Queues topics; push subscribers (queue_subscribers.py at the
  repo root) run the same job functions inside Vercel functions.

Progress always lands in Postgres; Redis only mirrors it for the local SSE
fast path and is absent in vercel mode."""

import json

from redis import Redis
from rq import Queue

from .config import settings

ANALYSIS_QUEUE = "analysis"
ANALYSIS_TOPIC = "cuepoint-analysis"
IDENTIFY_TOPIC = "cuepoint-identify"


def _vercel_send(topic: str, set_id: str) -> None:
    from vercel.queue.sync import QueueClient  # lazy: not installed in local rq mode

    QueueClient().send(topic, {"set_id": set_id})


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url)


def enqueue_analysis(set_id: str) -> None:
    if settings.queue_backend == "vercel":
        _vercel_send(ANALYSIS_TOPIC, set_id)
        return
    Queue(ANALYSIS_QUEUE, connection=get_redis()).enqueue(
        "cuepoint_api.worker.run_analysis", set_id, job_timeout=3600
    )


IDENTIFY_JOB_TIMEOUT_S = 1800


def enqueue_identify(set_id: str) -> None:
    if settings.queue_backend == "vercel":
        _vercel_send(IDENTIFY_TOPIC, set_id)
        return
    Queue(ANALYSIS_QUEUE, connection=get_redis()).enqueue(
        "cuepoint_api.identify.run_identify", set_id, job_timeout=IDENTIFY_JOB_TIMEOUT_S
    )


def _progress_key(set_id: str) -> str:
    return f"set:{set_id}:progress"


def publish_progress(set_id: str, fraction: float, stage: str) -> None:
    if settings.queue_backend == "vercel":
        return  # Postgres is the only progress channel in vercel mode
    get_redis().set(
        _progress_key(set_id), json.dumps({"progress": fraction, "stage": stage}), ex=86400
    )


def read_progress(set_id: str) -> dict | None:
    if settings.queue_backend == "vercel":
        return None  # SSE falls back to the row's progress/stage columns
    raw = get_redis().get(_progress_key(set_id))
    return json.loads(raw) if raw else None

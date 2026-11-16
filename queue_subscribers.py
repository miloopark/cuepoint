"""Vercel Queues push subscribers — the deployed replacement for the RQ worker.

Registered via [[tool.vercel.subscribers]] in pyproject.toml; at build time
Vercel compiles each subscription into a private queue-triggered function that
runs the same job code the local RQ worker runs."""

from vercel.queue import subscribe

from cuepoint_api.identify import run_identify
from cuepoint_api.queueing import ANALYSIS_TOPIC, IDENTIFY_TOPIC
from cuepoint_api.worker import run_analysis


@subscribe(topic=ANALYSIS_TOPIC, retry_after=60, max_attempts=3)
def handle_analysis(message: dict[str, str]) -> None:
    run_analysis(message["set_id"])


@subscribe(topic=IDENTIFY_TOPIC, retry_after=60, max_attempts=3)
def handle_identify(message: dict[str, str]) -> None:
    run_identify(message["set_id"])

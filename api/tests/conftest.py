"""API tests run on SQLite with the queue and storage untouched (enqueue is patched)."""

import os
import tempfile

_db_path = tempfile.mkstemp(suffix=".db")[1]
os.environ["CUEPOINT_DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["CUEPOINT_REDIS_URL"] = "redis://localhost:63790/0"  # never contacted in tests
os.environ["CUEPOINT_S3_ENDPOINT"] = "http://localhost:18333"  # presigning is offline

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    from cuepoint_api import main

    monkeypatch.setattr(main, "enqueue_analysis", lambda set_id: None)
    with TestClient(main.app) as c:
        yield c

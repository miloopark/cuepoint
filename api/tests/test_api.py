from cuepoint_api.db import SessionLocal
from cuepoint_api.models import SegmentRecord, SetRecord


def _make_done_set(result: dict | None = None) -> str:
    with SessionLocal() as db:
        rec = SetRecord(
            title="Test Set",
            audio_key="uploads/x/test.mp3",
            edit_token="e" * 32,
            status="done",
            progress=1.0,
            duration_s=120.0,
            result=result
            or {
                "features": {"energy_times": [2.5], "energy": [0.5]},
                "waveform": [10, 50, 100],
                "transitions": [],
            },
        )
        rec.segments.append(
            SegmentRecord(start_s=0.0, end_s=120.0, bpm=128, camelot_key="8A", key_confidence=0.9)
        )
        db.add(rec)
        db.commit()
        return rec.id


def test_presign_upload_returns_key_and_url(client):
    r = client.post("/uploads", json={"filename": "my mix (live).mp3"})
    assert r.status_code == 200
    body = r.json()
    assert body["key"].startswith("uploads/")
    assert body["key"].endswith(".mp3")
    assert body["key"].split("/")[-1] in body["upload_url"]


def test_create_set_and_get_status(client):
    r = client.post("/sets", json={"title": "My Mix", "audio_key": "uploads/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/mix.mp3"})
    assert r.status_code == 201
    set_id = r.json()["id"]
    assert r.json()["status"] == "queued"

    r2 = client.get(f"/sets/{set_id}")
    assert r2.status_code == 200
    assert r2.json()["title"] == "My Mix"


def test_get_missing_set_404(client):
    assert client.get("/sets/doesnotexist").status_code == 404


def test_analysis_conflict_before_done(client):
    r = client.post("/sets", json={"title": "Pending", "audio_key": "uploads/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/mix.mp3"})
    set_id = r.json()["id"]
    assert client.get(f"/sets/{set_id}/analysis").status_code == 409


def test_analysis_and_waveform_when_done(client):
    set_id = _make_done_set()

    r = client.get(f"/sets/{set_id}/analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["duration_s"] == 120.0
    assert len(body["segments"]) == 1
    assert body["segments"][0]["camelot_key"] == "8A"

    r2 = client.get(f"/sets/{set_id}/waveform")
    assert r2.status_code == 200
    assert r2.json()["waveform"] == [10, 50, 100]


def test_import_tracklist_names_segments(client):
    set_id = _make_done_set()

    text = "[0:00:00] First Artist - Opener\n[0:01:00] Second Artist - Closer\n"
    r = client.post(f"/sets/{set_id}/tracklist", json={"text": text, "edit_token": "e" * 32})
    assert r.status_code == 200
    body = r.json()
    assert body["named"] == 1
    # The lone 0-120s segment's midpoint (60s) falls in the second entry's interval.
    assert body["segments"][0]["artist"] == "Second Artist"
    assert body["segments"][0]["title"] == "Closer"
    assert body["segments"][0]["match_confidence"] == 0.95

    analysis = client.get(f"/sets/{set_id}/analysis").json()
    assert analysis["segments"][0]["artist"] == "Second Artist"


def test_import_tracklist_rejects_unparseable_text(client):
    set_id = _make_done_set()
    r = client.post(f"/sets/{set_id}/tracklist", json={"text": "no timestamps here", "edit_token": "e" * 32})
    assert r.status_code == 400


def test_import_tracklist_rejects_wrong_edit_token(client):
    set_id = _make_done_set()
    r = client.post(
        f"/sets/{set_id}/tracklist",
        json={"text": "[0:00:00] A - B", "edit_token": "wrong"},
    )
    assert r.status_code == 403


def test_create_set_returns_edit_token_but_reads_do_not(client):
    r = client.post("/sets", json={"title": "Tok", "audio_key": "uploads/" + "a" * 32 + "/mix.mp3"})
    assert len(r.json()["edit_token"]) == 32
    r2 = client.get(f"/sets/{r.json()['id']}")
    assert "edit_token" not in r2.json()


def test_identify_requires_configured_token(client):
    set_id = _make_done_set()
    r = client.post(f"/sets/{set_id}/identify", json={"edit_token": "e" * 32})
    assert r.status_code == 503  # CUEPOINT_AUDD_TOKEN unset in tests


def test_identify_rejects_wrong_edit_token(client, monkeypatch):
    from cuepoint_api.config import settings

    monkeypatch.setattr(settings, "audd_token", "x" * 10)
    set_id = _make_done_set()
    r = client.post(f"/sets/{set_id}/identify", json={"edit_token": "wrong"})
    assert r.status_code == 403


def test_identify_enqueues_and_sets_status(client, monkeypatch):
    from cuepoint_api import main
    from cuepoint_api.config import settings

    monkeypatch.setattr(settings, "audd_token", "x" * 10)
    queued = []
    monkeypatch.setattr(main, "enqueue_identify", queued.append)
    set_id = _make_done_set()

    r = client.post(f"/sets/{set_id}/identify", json={"edit_token": "e" * 32})
    assert r.status_code == 202
    assert queued == [set_id]
    assert client.get(f"/sets/{set_id}").json()["identify_status"] == "running"
    # A second request while running is rejected.
    assert client.post(f"/sets/{set_id}/identify", json={"edit_token": "e" * 32}).status_code == 409

    # ...but a stale "running" (dead worker) can be retried.
    with SessionLocal() as db:
        rec = db.get(SetRecord, set_id)
        rec.identify_started_at = 1.0  # epoch 1970 — long past the timeout
        db.commit()
    assert client.post(f"/sets/{set_id}/identify", json={"edit_token": "e" * 32}).status_code == 202


def test_list_sets_includes_created(client):
    set_id = _make_done_set()
    r = client.get("/sets")
    assert r.status_code == 200
    assert any(s["id"] == set_id for s in r.json())

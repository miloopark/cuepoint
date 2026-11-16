import numpy as np
import soundfile as sf

from cuepoint_api.identify import ALLOWED_FORMATS, parse_audd_response, probe_format


def test_parses_successful_match():
    data = {"status": "success", "result": {"artist": "Some Artist", "title": "Some Track"}}
    assert parse_audd_response(data) == ("Some Artist", "Some Track")


def test_null_result_means_no_match():
    assert parse_audd_response({"status": "success", "result": None}) is None


def test_error_status_means_no_match():
    assert parse_audd_response({"status": "error", "error": {"error_code": 901}}) is None


def test_blank_fields_mean_no_match():
    assert parse_audd_response({"status": "success", "result": {"artist": " ", "title": ""}}) is None


def test_probe_accepts_real_wav(tmp_path):
    path = tmp_path / "tone.wav"
    sf.write(path, np.zeros(22050, dtype=np.float32), 22050)
    assert probe_format(path) in ALLOWED_FORMATS


def test_probe_rejects_playlist_masquerading_as_audio(tmp_path):
    path = tmp_path / "evil.mp3"
    path.write_text("#EXTM3U\n#EXTINF:10,\nfile:///etc/passwd\n")
    assert probe_format(path) not in ALLOWED_FORMATS

from conftest import SR
from cuepoint_analysis.key import estimate_key, key_over_time, to_camelot


def test_camelot_mapping():
    assert to_camelot("A", "minor") == "8A"
    assert to_camelot("C", "major") == "8B"
    assert to_camelot("F#", "minor") == "11A"
    assert to_camelot("Ab", "minor") == "1A"


def test_a_minor_chord_detected_as_8a(a_minor_chord):
    key, camelot, confidence = estimate_key(a_minor_chord, SR)
    assert camelot == "8A"
    assert 0.0 < confidence <= 1.0


def test_key_over_time_windows(a_minor_chord):
    times, keys, confidences = key_over_time(a_minor_chord, SR, win_s=10.0)
    assert len(times) == len(keys) == len(confidences)
    assert len(keys) >= 2
    assert all(k == "8A" for k in keys)

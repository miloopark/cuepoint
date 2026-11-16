import numpy as np
from scipy.signal import butter, sosfilt

from conftest import SR, click_track, sine_chord
from cuepoint_analysis.transitions import detect_transitions


def _texture(kind: str, duration_s: float) -> np.ndarray:
    """Two clearly different musical textures."""
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(int(duration_s * SR)).astype(np.float32)
    if kind == "dark":
        sos = butter(4, 500, "lowpass", fs=SR, output="sos")
        bed = sosfilt(sos, noise).astype(np.float32)
        return 0.4 * bed + click_track(124, duration_s) + 0.3 * sine_chord([110.0, 220.0], duration_s)
    sos = butter(4, 2000, "highpass", fs=SR, output="sos")
    bed = sosfilt(sos, noise).astype(np.float32)
    return 0.4 * bed + click_track(150, duration_s) + 0.3 * sine_chord([587.33, 880.0], duration_s)


def test_detects_single_splice_between_textures():
    y = np.concatenate([_texture("dark", 120.0), _texture("bright", 120.0)])
    transitions = detect_transitions(y, SR)
    assert len(transitions) == 1
    t = transitions[0]
    assert abs(t.peak_s - 120.0) <= 15.0
    assert t.start_s <= t.peak_s <= t.end_s


def test_uniform_texture_yields_no_transitions():
    y = _texture("dark", 240.0)
    assert detect_transitions(y, SR) == []

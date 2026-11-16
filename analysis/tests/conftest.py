"""Synthetic audio fixtures. Deterministic, generated in-memory — no audio files needed."""

import numpy as np
import pytest

SR = 22050


def click_track(bpm: float, duration_s: float, sr: int = SR) -> np.ndarray:
    """Impulse train at the given tempo, with a short decaying burst per click."""
    n = int(duration_s * sr)
    y = np.zeros(n, dtype=np.float32)
    period = 60.0 / bpm
    click_len = int(0.01 * sr)
    burst = (np.random.default_rng(0).standard_normal(click_len) * np.exp(-np.arange(click_len) / (0.002 * sr))).astype(np.float32)
    t = 0.0
    while int(t * sr) + click_len < n:
        i = int(t * sr)
        y[i : i + click_len] += burst
        t += period
    return y


def sine_chord(freqs: list[float], duration_s: float, sr: int = SR) -> np.ndarray:
    """Sum of sines at the given frequencies, normalized."""
    t = np.arange(int(duration_s * sr)) / sr
    y = sum(np.sin(2 * np.pi * f * t) for f in freqs)
    return (y / np.max(np.abs(y))).astype(np.float32)


@pytest.fixture(scope="session")
def click_128() -> np.ndarray:
    """60 s click track at exactly 128 BPM."""
    return click_track(128.0, 60.0)


@pytest.fixture(scope="session")
def a_minor_chord() -> np.ndarray:
    """30 s A-minor triad (A3, C4, E4) with octave doublings."""
    return sine_chord([220.0, 261.63, 329.63, 440.0, 523.25, 659.26], 30.0)

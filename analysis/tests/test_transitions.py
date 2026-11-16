import numpy as np
from scipy.signal import butter, sosfilt

from conftest import SR, click_track, sine_chord
from cuepoint_analysis.transitions import (
    beat_blocks,
    detect_transitions,
    key_cue,
    pick_peaks,
    tempo_cue,
)


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


def test_features_work_at_reduced_rate():
    # Long sets analyze at 11025 Hz; every feature extractor must survive the
    # lower Nyquist (spectral_contrast's default bands exceed it).
    import soxr

    from cuepoint_analysis.energy import energy_curve
    from cuepoint_analysis.key import key_over_time
    from cuepoint_analysis.tempo import bpm_over_time

    sr_low = 11025
    y = soxr.resample(
        np.concatenate([_texture("dark", 120.0), _texture("bright", 120.0)]), SR, sr_low
    ).astype(np.float32)

    transitions = detect_transitions(y, sr_low)
    assert len(transitions) == 1
    assert abs(transitions[0].peak_s - 120.0) <= 15.0

    _, bpm = bpm_over_time(y, sr_low)
    assert len(bpm) > 0
    _, keys, _ = key_over_time(y, sr_low, win_s=30.0)
    assert len(keys) > 0
    _, energy = energy_curve(y, sr_low)
    assert np.all((energy >= 0) & (energy <= 1))


def test_pick_peaks_works_on_irregular_time_grid():
    # Blocks of alternating duration (like beat-sync blocks under tempo drift).
    dts = np.tile([6.0, 9.0], 50)
    times = np.cumsum(dts)
    novelty = np.zeros(len(times))
    novelty[40] = 2.0
    transitions = pick_peaks(novelty, times, sigma=1.0, min_spacing_s=90.0, min_prominence=0.3)
    assert len(transitions) == 1
    assert abs(transitions[0].peak_s - times[40]) < 1e-6


def test_beat_blocks_on_click_track(click_128):
    times, blocks = beat_blocks(click_128, SR, beats_per_block=8)
    # 60 s at 128 BPM ≈ 128 beats → ~16 blocks of 8 beats (~3.75 s each)
    assert blocks.shape[0] >= 10
    assert len(times) == blocks.shape[0]
    assert np.all(np.diff(times) > 0)
    # rows are unit vectors (same normalization as fixed blocks)
    norms = np.linalg.norm(blocks, axis=1)
    assert np.allclose(norms[norms > 0], 1.0, atol=1e-3)


def test_tempo_cue_peaks_at_bpm_jump():
    block_times = np.arange(0.0, 300.0, 2.0)
    bpm_times = np.arange(15.0, 300.0, 10.0)
    bpm_values = np.where(bpm_times < 150.0, 124.0, 150.0)
    cue = tempo_cue(block_times, bpm_times, bpm_values)
    assert np.all((cue >= 0) & (cue <= 1))
    assert cue[np.argmin(np.abs(block_times - 150.0))] > 0.8
    assert cue[np.argmin(np.abs(block_times - 50.0))] < 0.1


def test_key_cue_peaks_at_key_change():
    block_times = np.arange(0.0, 300.0, 2.0)
    key_times = np.arange(15.0, 300.0, 30.0)
    keys = ["8A" if t < 150 else "3B" for t in key_times]  # distant jump on the wheel
    confs = np.full(len(key_times), 0.9)
    cue = key_cue(block_times, key_times, keys, confs)
    assert np.all((cue >= 0) & (cue <= 1))
    assert cue[np.argmin(np.abs(block_times - 150.0))] > 0.5
    assert cue[np.argmin(np.abs(block_times - 50.0))] < 0.05


def test_detect_transitions_accepts_cue_series():
    y = np.concatenate([_texture("dark", 120.0), _texture("bright", 120.0)])
    bpm_series = (np.array([60.0, 180.0]), np.array([124.0, 150.0]))
    key_series = (np.array([60.0, 180.0]), ["8A", "3B"], np.array([0.9, 0.9]))
    transitions = detect_transitions(
        y, SR, bpm_series=bpm_series, key_series=key_series, tempo_weight=0.2, key_weight=0.2
    )
    assert len(transitions) == 1
    assert abs(transitions[0].peak_s - 120.0) <= 15.0

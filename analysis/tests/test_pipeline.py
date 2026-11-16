import numpy as np
import soundfile as sf

from conftest import SR, click_track
from cuepoint_analysis.pipeline import analyze_set, build_segments, waveform_peaks
from cuepoint_analysis.transitions import Transition


def _series(times_values: list[tuple[float, float]]):
    times = np.array([t for t, _ in times_values])
    values = np.array([v for _, v in times_values])
    return times, values


def test_build_segments_splits_at_transition_peaks():
    transitions = [
        Transition(start_s=90.0, end_s=110.0, peak_s=100.0, strength=1.0),
        Transition(start_s=190.0, end_s=210.0, peak_s=200.0, strength=1.0),
    ]
    bpm_times, bpm_values = _series([(50, 120), (150, 125), (250, 130)])
    key_times = np.array([50.0, 150.0, 250.0])
    keys = ["8A", "9A", "10A"]
    key_confs = np.array([0.9, 0.8, 0.7])

    segments = build_segments(
        duration_s=300.0,
        transitions=transitions,
        bpm_times=bpm_times,
        bpm_values=bpm_values,
        key_times=key_times,
        keys=keys,
        key_confs=key_confs,
    )

    assert len(segments) == 3
    assert segments[0]["start_s"] == 0.0
    assert segments[0]["end_s"] == 100.0
    assert segments[0]["bpm"] == 120
    assert segments[0]["camelot_key"] == "8A"
    assert segments[0]["transition_start_s"] is None
    assert segments[1]["transition_start_s"] == 90.0
    assert segments[1]["transition_end_s"] == 110.0
    assert segments[1]["camelot_key"] == "9A"
    assert segments[2]["end_s"] == 300.0
    assert segments[2]["camelot_key"] == "10A"


def test_build_segments_merges_weak_boundary_between_identical_tracks():
    transitions = [
        Transition(start_s=90.0, end_s=110.0, peak_s=100.0, strength=2.0),
        Transition(start_s=190.0, end_s=210.0, peak_s=200.0, strength=0.1),  # spurious split
    ]
    bpm_times, bpm_values = _series([(50, 125), (150, 128), (250, 128)])
    key_times = np.array([50.0, 150.0, 250.0])
    keys = ["8A", "9A", "9A"]  # segments 2 and 3 are the same track
    key_confs = np.array([0.9, 0.8, 0.8])

    segments = build_segments(
        duration_s=300.0,
        transitions=transitions,
        bpm_times=bpm_times,
        bpm_values=bpm_values,
        key_times=key_times,
        keys=keys,
        key_confs=key_confs,
    )

    assert len(segments) == 2
    assert segments[1]["start_s"] == 100.0
    assert segments[1]["end_s"] == 300.0
    assert segments[1]["camelot_key"] == "9A"


def test_build_segments_without_transitions_is_one_segment():
    bpm_times, bpm_values = _series([(50, 128)])
    segments = build_segments(
        duration_s=100.0,
        transitions=[],
        bpm_times=bpm_times,
        bpm_values=bpm_values,
        key_times=np.array([50.0]),
        keys=["5A"],
        key_confs=np.array([0.9]),
    )
    assert len(segments) == 1
    assert segments[0]["start_s"] == 0.0
    assert segments[0]["end_s"] == 100.0


def test_waveform_peaks_shape_and_range():
    y = click_track(128.0, 30.0)
    peaks = waveform_peaks(y, n_bins=500)
    assert len(peaks) == 500
    assert all(isinstance(p, int) and 0 <= p <= 100 for p in peaks)
    assert max(peaks) == 100


def test_analyze_set_end_to_end_on_short_clip(tmp_path):
    y = click_track(128.0, 40.0)
    path = tmp_path / "clip.wav"
    sf.write(path, y, SR)

    stages = []

    def progress(fraction: float, stage: str) -> None:
        stages.append((fraction, stage))

    result = analyze_set(path, progress=progress)

    assert abs(result["duration_s"] - 40.0) < 0.5
    assert len(result["segments"]) >= 1
    seg = result["segments"][0]
    assert abs(seg["bpm"] - 128.0) <= 2.0
    assert len(result["waveform"]) == 1000
    assert len(result["features"]["energy_times"]) == len(result["features"]["energy"])
    fractions = [f for f, _ in stages]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0

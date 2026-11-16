"""Full-mix analysis: one call that produces everything the API stores for a set."""

from collections.abc import Callable
from pathlib import Path

import numpy as np

from .audio import load_audio
from .energy import energy_curve
from .key import key_over_time
from .tempo import bpm_over_time
from .transitions import Transition, detect_transitions

ProgressFn = Callable[[float, str], None]


def waveform_peaks(y: np.ndarray, n_bins: int = 1000) -> list[int]:
    """Downsampled |amplitude| peaks, scaled 0-100, for drawing the waveform."""
    chunks = np.array_split(np.abs(y), n_bins)
    peaks = [float(c.max()) if len(c) else 0.0 for c in chunks]
    top = max(peaks) or 1.0
    return [int(round(p / top * 100)) for p in peaks]


def build_segments(
    duration_s: float,
    transitions: list[Transition],
    bpm_times: np.ndarray,
    bpm_values: np.ndarray,
    key_times: np.ndarray,
    keys: list[str],
    key_confs: np.ndarray,
) -> list[dict]:
    """One segment per detected track: boundaries at transition peaks, per-segment
    BPM (median of windows inside) and key (confidence-weighted majority vote)."""
    bounds = [0.0] + [t.peak_s for t in transitions] + [duration_s]
    segments = []
    for i in range(len(bounds) - 1):
        start, end = bounds[i], bounds[i + 1]

        mask = (bpm_times >= start) & (bpm_times < end)
        if mask.any():
            bpm = float(np.median(bpm_values[mask]))
        else:
            bpm = float(np.median(bpm_values)) if len(bpm_values) else 0.0

        votes: dict[str, float] = {}
        for kt, k, c in zip(key_times, keys, key_confs):
            if start <= kt < end:
                votes[k] = votes.get(k, 0.0) + float(c)
        if votes:
            key = max(votes, key=lambda k: votes[k])
            confs = [
                float(c)
                for kt, k, c in zip(key_times, keys, key_confs)
                if start <= kt < end and k == key
            ]
            key_conf = float(np.mean(confs))
        else:
            key = keys[0] if keys else None
            key_conf = 0.0

        prev = transitions[i - 1] if i > 0 else None
        segments.append(
            {
                "start_s": float(start),
                "end_s": float(end),
                "transition_start_s": float(prev.start_s) if prev else None,
                "transition_end_s": float(prev.end_s) if prev else None,
                "bpm": round(bpm),
                "camelot_key": key,
                "key_confidence": key_conf,
            }
        )
    return segments


def analyze_set(
    path: str | Path,
    progress: ProgressFn = lambda fraction, stage: None,
    n_waveform_bins: int = 1000,
) -> dict:
    progress(0.02, "decoding")
    y, sr = load_audio(path)
    duration_s = len(y) / sr

    progress(0.2, "detecting transitions")
    transitions = detect_transitions(y, sr)

    progress(0.55, "estimating tempo")
    bpm_times, bpm_values = bpm_over_time(y, sr)

    progress(0.7, "detecting key")
    key_times, keys, key_confs = key_over_time(y, sr)

    progress(0.85, "computing energy and waveform")
    energy_times, energy = energy_curve(y, sr)
    waveform = waveform_peaks(y, n_waveform_bins)

    segments = build_segments(duration_s, transitions, bpm_times, bpm_values, key_times, keys, key_confs)

    progress(1.0, "done")
    return {
        "duration_s": float(duration_s),
        "segments": segments,
        "transitions": [
            {"start_s": t.start_s, "end_s": t.end_s, "peak_s": t.peak_s, "strength": t.strength}
            for t in transitions
        ],
        "features": {
            "bpm_times": np.asarray(bpm_times).tolist(),
            "bpm": np.asarray(bpm_values).tolist(),
            "key_times": np.asarray(key_times).tolist(),
            "keys": list(keys),
            "key_confidences": np.asarray(key_confs).tolist(),
            "energy_times": np.asarray(energy_times).tolist(),
            "energy": np.asarray(energy).tolist(),
        },
        "waveform": waveform,
    }

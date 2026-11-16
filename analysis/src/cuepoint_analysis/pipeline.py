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

# Boundaries weaker than this fraction of the median boundary strength are merge
# candidates (dropped only when BPM and key agree on both sides).
MERGE_REL_STRENGTH = 0.5


def _nearest_key(key_times: np.ndarray, keys: list[str], t: float) -> str | None:
    key_times = np.asarray(key_times)
    if len(key_times) == 0:
        return None
    return keys[int(np.argmin(np.abs(key_times - t)))]


def waveform_peaks(y: np.ndarray, n_bins: int = 1000) -> list[int]:
    """Downsampled |amplitude| peaks, scaled 0-100, for drawing the waveform."""
    chunks = np.array_split(np.abs(y), n_bins)
    peaks = [float(c.max()) if len(c) else 0.0 for c in chunks]
    top = max(peaks) or 1.0
    return [round(p / top * 100) for p in peaks]


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
    # A boundary whose fused-novelty prominence is well below its peers *and*
    # whose neighbors agree on BPM and key is almost always one track split in
    # two — drop it before building segments.
    if transitions:
        strengths = np.array([t.strength for t in transitions])
        median_strength = float(np.median(strengths))
        kept = []
        for t in transitions:
            if t.strength >= MERGE_REL_STRENGTH * median_strength:
                kept.append(t)
                continue
            before_mask = (bpm_times >= t.peak_s - 90) & (bpm_times < t.peak_s)
            after_mask = (bpm_times >= t.peak_s) & (bpm_times < t.peak_s + 90)
            same_bpm = (
                before_mask.any()
                and after_mask.any()
                and abs(np.median(bpm_values[before_mask]) - np.median(bpm_values[after_mask])) <= 1.0
            )
            k1 = _nearest_key(key_times, keys, t.peak_s - 45)
            k2 = _nearest_key(key_times, keys, t.peak_s + 45)
            if same_bpm and k1 is not None and k1 == k2:
                continue  # merge: weak boundary between identical-sounding neighbors
            kept.append(t)
        transitions = kept

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

    progress(0.2, "estimating tempo")
    bpm_times, bpm_values = bpm_over_time(y, sr)

    progress(0.4, "detecting key")
    key_times, keys, key_confs = key_over_time(y, sr)

    progress(0.55, "detecting transitions")
    transitions = detect_transitions(
        y,
        sr,
        bpm_series=(bpm_times, bpm_values),
        key_series=(key_times, keys, key_confs),
    )

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

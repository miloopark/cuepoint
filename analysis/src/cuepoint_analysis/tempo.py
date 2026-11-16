"""BPM over time: windowed tempo estimation with half/double-time folding."""

import librosa
import numpy as np
from scipy.signal import medfilt

BPM_LO = 70.0
BPM_HI = 180.0
ONSET_HOP = 512


def fold_bpm(bpm: float, reference: float, lo: float = BPM_LO, hi: float = BPM_HI) -> float:
    """Fold octave errors (half/double/quadruple time) toward a reference tempo."""
    candidates = [bpm * f for f in (0.25, 0.5, 1.0, 2.0, 4.0)]
    in_range = [c for c in candidates if lo <= c <= hi] or candidates
    return min(in_range, key=lambda c: abs(c - reference))


def bpm_over_time(
    y: np.ndarray,
    sr: int,
    win_s: float = 30.0,
    hop_s: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Tempo per sliding window. Returns (window-center times, folded + smoothed BPM)."""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=ONSET_HOP)
    env_rate = sr / ONSET_HOP
    win_f = int(win_s * env_rate)
    hop_f = max(1, int(hop_s * env_rate))

    times, raw = [], []
    for start in range(0, len(onset_env) - win_f + 1, hop_f):
        seg = onset_env[start : start + win_f]
        t = librosa.feature.tempo(onset_envelope=seg, sr=sr, hop_length=ONSET_HOP, max_tempo=BPM_HI)
        times.append(start / env_rate + win_s / 2)
        raw.append(float(t[0]))

    raw_arr = np.array(raw)
    reference = float(np.median(raw_arr))
    folded = np.array([fold_bpm(b, reference) for b in raw_arr])
    if len(folded) >= 3:
        folded = medfilt(folded, kernel_size=3)
    return np.array(times), folded

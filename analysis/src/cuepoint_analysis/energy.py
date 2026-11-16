"""Energy curve: loudness + brightness + onset density, combined into a 0–1 score per block."""

import librosa
import numpy as np

HOP = 512


def _per_block(x: np.ndarray, frames_per_block: int, n_blocks: int) -> np.ndarray:
    return np.array([x[i * frames_per_block : (i + 1) * frames_per_block].mean() for i in range(n_blocks)])


def _minmax(x: np.ndarray) -> np.ndarray:
    span = x.max() - x.min()
    if span <= 0:
        return np.zeros_like(x)
    return (x - x.min()) / span


def energy_curve(y: np.ndarray, sr: int, hop_s: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=HOP)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)

    frames_per_block = int(hop_s * sr / HOP)
    n_blocks = min(len(rms), len(centroid), len(onset)) // frames_per_block

    energy = (
        0.5 * _minmax(_per_block(rms, frames_per_block, n_blocks))
        + 0.25 * _minmax(_per_block(centroid, frames_per_block, n_blocks))
        + 0.25 * _minmax(_per_block(onset, frames_per_block, n_blocks))
    )
    times = (np.arange(n_blocks) + 0.5) * hop_s
    return times, np.clip(energy, 0.0, 1.0)

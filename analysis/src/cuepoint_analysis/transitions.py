"""Transition detection: self-similarity novelty (Foote checkerboard) + peak picking.

The checkerboard kernel is computed in its decomposed form: novelty at block i is
(mean within-similarity of the halves before and after i) minus (mean cross-similarity
between them). This avoids materializing the full self-similarity matrix, so a
multi-hour set stays O(N·K²) instead of O(N²)."""

from dataclasses import dataclass

import librosa
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

BLOCK_S = 2.0
KERNEL_S = 64.0
MIN_SPACING_S = 90.0
HOP = 512


@dataclass(frozen=True)
class Transition:
    start_s: float
    end_s: float
    peak_s: float
    strength: float


def _block_features(y: np.ndarray, sr: int, block_s: float) -> np.ndarray:
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, hop_length=HOP)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=HOP)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, hop_length=HOP)
    feats = np.vstack([mfcc, chroma, contrast])

    frames_per_block = max(1, int(block_s * sr / HOP))
    n_blocks = feats.shape[1] // frames_per_block
    blocks = np.array(
        [feats[:, i * frames_per_block : (i + 1) * frames_per_block].mean(axis=1) for i in range(n_blocks)]
    )
    blocks = (blocks - blocks.mean(axis=0)) / (blocks.std(axis=0) + 1e-9)
    return blocks / (np.linalg.norm(blocks, axis=1, keepdims=True) + 1e-9)


def novelty_curve(
    y: np.ndarray,
    sr: int,
    block_s: float = BLOCK_S,
    kernel_s: float = KERNEL_S,
) -> tuple[np.ndarray, np.ndarray]:
    blocks = _block_features(y, sr, block_s)
    n = len(blocks)
    half = max(2, int(kernel_s / block_s / 2))
    novelty = np.zeros(n)
    for i in range(half, n - half):
        before = blocks[i - half : i]
        after = blocks[i : i + half]
        within = (before @ before.T).mean() + (after @ after.T).mean()
        across = (before @ after.T).mean()
        novelty[i] = within / 2.0 - across
    times = (np.arange(n) + 0.5) * block_s
    return times, novelty


def detect_transitions(
    y: np.ndarray,
    sr: int,
    block_s: float = BLOCK_S,
    kernel_s: float = KERNEL_S,
    min_spacing_s: float = MIN_SPACING_S,
) -> list[Transition]:
    times, novelty = novelty_curve(y, sr, block_s, kernel_s)
    if len(novelty) == 0:
        return []
    smooth = gaussian_filter1d(novelty, sigma=2.0)

    threshold = max(0.3, float(smooth.mean() + 3.0 * smooth.std()))
    peaks, props = find_peaks(smooth, height=threshold, distance=max(1, int(min_spacing_s / block_s)))

    transitions = []
    for p, height in zip(peaks, props["peak_heights"]):
        half_height = height / 2.0
        lo = p
        while lo > 0 and smooth[lo] > half_height:
            lo -= 1
        hi = p
        while hi < len(smooth) - 1 and smooth[hi] > half_height:
            hi += 1
        transitions.append(
            Transition(
                start_s=float(times[lo]),
                end_s=float(times[hi]),
                peak_s=float(times[p]),
                strength=float(height),
            )
        )
    return transitions

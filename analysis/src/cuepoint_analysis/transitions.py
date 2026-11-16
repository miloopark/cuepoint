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
# Tuned by scripts/tune_transitions.py against the two labeled sets (2026-11-15):
# kernel 128 s / sigma 1 / prominence 0.15 → mean F1@±30s 0.38 vs 0.07 for the
# original 64 s kernel + 3-sigma height threshold. DJ blends run 15-60 s, so the
# checkerboard needs ~2 min of context on each side to see a boundary.
KERNEL_S = 128.0
MIN_SPACING_S = 90.0
SIGMA = 1.0
MIN_PROMINENCE = 0.15
HOP = 512


@dataclass(frozen=True)
class Transition:
    start_s: float
    end_s: float
    peak_s: float
    strength: float


def block_features(y: np.ndarray, sr: int, block_s: float = BLOCK_S) -> np.ndarray:
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


def novelty_from_blocks(blocks: np.ndarray, block_s: float, kernel_s: float) -> np.ndarray:
    n = len(blocks)
    half = max(2, int(kernel_s / block_s / 2))
    novelty = np.zeros(n)
    for i in range(half, n - half):
        before = blocks[i - half : i]
        after = blocks[i : i + half]
        within = (before @ before.T).mean() + (after @ after.T).mean()
        across = (before @ after.T).mean()
        novelty[i] = within / 2.0 - across
    return novelty


def novelty_curve(
    y: np.ndarray,
    sr: int,
    block_s: float = BLOCK_S,
    kernel_s: float = KERNEL_S,
) -> tuple[np.ndarray, np.ndarray]:
    blocks = block_features(y, sr, block_s)
    novelty = novelty_from_blocks(blocks, block_s, kernel_s)
    times = (np.arange(len(blocks)) + 0.5) * block_s
    return times, novelty


def pick_peaks(
    novelty: np.ndarray,
    block_s: float = BLOCK_S,
    sigma: float = SIGMA,
    min_spacing_s: float = MIN_SPACING_S,
    min_prominence: float = MIN_PROMINENCE,
) -> list[Transition]:
    if len(novelty) == 0:
        return []
    smooth = gaussian_filter1d(novelty, sigma=sigma)
    peaks, props = find_peaks(
        smooth, prominence=min_prominence, distance=max(1, int(min_spacing_s / block_s))
    )
    times = (np.arange(len(novelty)) + 0.5) * block_s

    transitions = []
    for p, prom in zip(peaks, props["prominences"]):
        half_level = smooth[p] - prom / 2.0
        lo = p
        while lo > 0 and smooth[lo] > half_level:
            lo -= 1
        hi = p
        while hi < len(smooth) - 1 and smooth[hi] > half_level:
            hi += 1
        transitions.append(
            Transition(
                start_s=float(times[lo]),
                end_s=float(times[hi]),
                peak_s=float(times[p]),
                strength=float(prom),
            )
        )
    return transitions


def detect_transitions(
    y: np.ndarray,
    sr: int,
    block_s: float = BLOCK_S,
    kernel_s: float = KERNEL_S,
    min_spacing_s: float = MIN_SPACING_S,
    sigma: float = SIGMA,
    min_prominence: float = MIN_PROMINENCE,
) -> list[Transition]:
    _, novelty = novelty_curve(y, sr, block_s, kernel_s)
    return pick_peaks(novelty, block_s, sigma, min_spacing_s, min_prominence)

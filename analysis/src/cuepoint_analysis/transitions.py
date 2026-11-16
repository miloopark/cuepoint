"""Transition detection: self-similarity novelty (Foote checkerboard) fused with
tempo-jump and key-change cues, then peak picking on the fused score.

The checkerboard kernel is computed in its decomposed form: novelty at block i is
(mean within-similarity of the halves before and after i) minus (mean cross-similarity
between them). This avoids materializing the full self-similarity matrix, so a
multi-hour set stays O(N·K²) instead of O(N²).

Feature blocks come in two flavors: fixed-duration (block_s) or beat-synchronous
(beats_per_block beats each, ~one phrase), selected by the beats_per_block arg.
All downstream code works on an explicit block-times array, so irregular
beat-sync grids need no special casing."""

import re
from dataclasses import dataclass

import librosa
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from .audio import fft_size, framewise

BLOCK_S = 2.0
# Tuned 2026-11-16 (train: Cloonee, holdout: Franky — see tune_transitions.py).
# kernel 128 / sigma 2 / prominence 0.2 / key cue 0.25 improves BOTH sets over
# the previous defaults (F1@±30s: 0.59→0.67 train, 0.53→0.61 holdout). Kernel
# 192 scored 0.78 on train but collapsed to 0.36 on holdout (its track lengths
# differ) — a textbook overfit, rejected. Beat-sync blocks (beat16) did not
# beat fixed 2 s blocks on either set. The tempo cue is inert on these
# constant-tempo sets; kept at a small weight for sets that do shift tempo.
KERNEL_S = 128.0
MIN_SPACING_S = 90.0
SIGMA = 2.0
MIN_PROMINENCE = 0.2
BEATS_PER_BLOCK: int | None = None
TEMPO_WEIGHT = 0.1
KEY_WEIGHT = 0.25
HOP = 512


@dataclass(frozen=True)
class Transition:
    start_s: float
    end_s: float
    peak_s: float
    strength: float


def _stack_features(y: np.ndarray, sr: int) -> np.ndarray:
    n_fft = fft_size(sr)
    # Octave bands must fit under Nyquist: fmin 200 Hz × 2^n_bands ≤ sr/2.
    n_bands = min(6, int(np.log2(sr / 2 / 200.0)))
    # framewise keeps STFT transients chunk-sized — a multi-hour mix would
    # otherwise materialize gigabyte spectrogram buffers per feature.
    mfcc = framewise(
        lambda s, **kw: librosa.feature.mfcc(y=s, sr=sr, n_mfcc=20, n_fft=n_fft, hop_length=HOP, **kw),
        y, n_fft=n_fft, hop=HOP, sr=sr,
    )
    chroma = framewise(
        lambda s, **kw: librosa.feature.chroma_stft(y=s, sr=sr, n_fft=n_fft, hop_length=HOP, **kw),
        y, n_fft=n_fft, hop=HOP, sr=sr,
    )
    contrast = framewise(
        lambda s, **kw: librosa.feature.spectral_contrast(
            y=s, sr=sr, n_fft=n_fft, hop_length=HOP, n_bands=n_bands, **kw
        ),
        y, n_fft=n_fft, hop=HOP, sr=sr,
    )
    n = min(mfcc.shape[1], chroma.shape[1], contrast.shape[1])
    return np.vstack([mfcc[:, :n], chroma[:, :n], contrast[:, :n]])


def _normalize_blocks(blocks: np.ndarray) -> np.ndarray:
    blocks = (blocks - blocks.mean(axis=0)) / (blocks.std(axis=0) + 1e-9)
    return blocks / (np.linalg.norm(blocks, axis=1, keepdims=True) + 1e-9)


def block_features(
    y: np.ndarray, sr: int, block_s: float = BLOCK_S
) -> tuple[np.ndarray, np.ndarray]:
    """Fixed-duration feature blocks. Returns (block center times, blocks)."""
    feats = _stack_features(y, sr)
    frames_per_block = max(1, int(block_s * sr / HOP))
    n_blocks = feats.shape[1] // frames_per_block
    blocks = np.array(
        [feats[:, i * frames_per_block : (i + 1) * frames_per_block].mean(axis=1) for i in range(n_blocks)]
    )
    times = (np.arange(n_blocks) + 0.5) * block_s
    return times, _normalize_blocks(blocks)


def beat_blocks(
    y: np.ndarray, sr: int, beats_per_block: int = 16
) -> tuple[np.ndarray, np.ndarray]:
    """Beat-synchronous feature blocks (~one phrase each). Falls back to fixed
    blocks when beat tracking finds too few beats."""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    _, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=HOP, trim=False)
    if len(beats) < 2 * beats_per_block:
        return block_features(y, sr)

    feats = _stack_features(y, sr)
    bounds = np.asarray(beats[::beats_per_block])
    bounds = bounds[bounds < feats.shape[1]]
    if len(bounds) < 3:
        return block_features(y, sr)

    synced = librosa.util.sync(feats, bounds, aggregate=np.mean)  # len(bounds)+1 slices
    blocks = synced.T[1:-1]  # interior slices only: between consecutive bounds
    bound_times = librosa.frames_to_time(bounds, sr=sr, hop_length=HOP)
    times = (bound_times[:-1] + bound_times[1:]) / 2
    return times, _normalize_blocks(blocks)


def novelty_from_blocks(blocks: np.ndarray, times: np.ndarray, kernel_s: float) -> np.ndarray:
    n = len(blocks)
    dt = float(np.median(np.diff(times))) if n > 1 else BLOCK_S
    half = max(2, round(kernel_s / (2 * dt)))
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
    times, blocks = block_features(y, sr, block_s)
    return times, novelty_from_blocks(blocks, times, kernel_s)


def tempo_cue(
    times: np.ndarray,
    bpm_times: np.ndarray,
    bpm_values: np.ndarray,
    span_s: float = 20.0,
    scale_bpm: float = 10.0,
) -> np.ndarray:
    """0-1 score per block: how much the tempo differs span_s before vs after."""
    before = np.interp(times - span_s, bpm_times, bpm_values)
    after = np.interp(times + span_s, bpm_times, bpm_values)
    return np.clip(np.abs(after - before) / scale_bpm, 0.0, 1.0)


_CAMELOT_RE = re.compile(r"^(\d+)(A|B)$")


def _camelot_dist(a: str, b: str) -> float:
    ma, mb = _CAMELOT_RE.match(a or ""), _CAMELOT_RE.match(b or "")
    if not ma or not mb:
        return 0.0
    na, la = int(ma.group(1)), ma.group(2)
    nb, lb = int(mb.group(1)), mb.group(2)
    ring = min(abs(na - nb), 12 - abs(na - nb))
    return float(ring + (1 if la != lb else 0))


def _nearest_idx(ts: np.ndarray, t: float) -> int:
    i = int(np.searchsorted(ts, t))
    if i <= 0:
        return 0
    if i >= len(ts):
        return len(ts) - 1
    return i if abs(ts[i] - t) < abs(ts[i - 1] - t) else i - 1


def key_cue(
    times: np.ndarray,
    key_times: np.ndarray,
    keys: list[str],
    key_confs: np.ndarray,
    span_s: float = 20.0,
    scale_dist: float = 3.0,
) -> np.ndarray:
    """0-1 score per block: Camelot-wheel distance between the key windows span_s
    before and after, weighted by the lower of the two confidences."""
    key_times = np.asarray(key_times)
    out = np.zeros(len(times))
    if len(key_times) == 0:
        return out
    for j, t in enumerate(times):
        i1 = _nearest_idx(key_times, t - span_s)
        i2 = _nearest_idx(key_times, t + span_s)
        if i1 == i2:
            continue
        d = _camelot_dist(keys[i1], keys[i2]) * float(min(key_confs[i1], key_confs[i2]))
        out[j] = min(1.0, d / scale_dist)
    return out


def pick_peaks(
    novelty: np.ndarray,
    times: np.ndarray,
    sigma: float = SIGMA,
    min_spacing_s: float = MIN_SPACING_S,
    min_prominence: float = MIN_PROMINENCE,
) -> list[Transition]:
    if len(novelty) == 0:
        return []
    dt = float(np.median(np.diff(times))) if len(times) > 1 else BLOCK_S
    smooth = gaussian_filter1d(novelty, sigma=sigma)
    peaks, props = find_peaks(
        smooth, prominence=min_prominence, distance=max(1, int(min_spacing_s / dt))
    )

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
    beats_per_block: int | None = BEATS_PER_BLOCK,
    bpm_series: tuple[np.ndarray, np.ndarray] | None = None,
    key_series: tuple[np.ndarray, list[str], np.ndarray] | None = None,
    tempo_weight: float = TEMPO_WEIGHT,
    key_weight: float = KEY_WEIGHT,
) -> list[Transition]:
    if beats_per_block:
        times, blocks = beat_blocks(y, sr, beats_per_block)
    else:
        times, blocks = block_features(y, sr, block_s)
    fused = novelty_from_blocks(blocks, times, kernel_s)
    if bpm_series is not None and tempo_weight > 0:
        fused = fused + tempo_weight * tempo_cue(times, bpm_series[0], bpm_series[1])
    if key_series is not None and key_weight > 0:
        fused = fused + key_weight * key_cue(times, key_series[0], key_series[1], key_series[2])
    return pick_peaks(fused, times, sigma, min_spacing_s, min_prominence)

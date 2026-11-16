"""Key detection: Krumhansl–Schmuckler profile correlation, reported in Camelot notation."""

import librosa
import numpy as np

PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# Krumhansl–Schmuckler key profiles (probe-tone ratings), index 0 = tonic.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

_CAMELOT_MINOR = {
    "G#": "1A", "D#": "2A", "A#": "3A", "F": "4A", "C": "5A", "G": "6A",
    "D": "7A", "A": "8A", "E": "9A", "B": "10A", "F#": "11A", "C#": "12A",
}
_CAMELOT_MAJOR = {
    "B": "1B", "F#": "2B", "C#": "3B", "G#": "4B", "D#": "5B", "A#": "6B",
    "F": "7B", "C": "8B", "G": "9B", "D": "10B", "A": "11B", "E": "12B",
}


def to_camelot(tonic: str, mode: str) -> str:
    tonic = _FLAT_TO_SHARP.get(tonic, tonic)
    table = _CAMELOT_MINOR if mode == "minor" else _CAMELOT_MAJOR
    return table[tonic]


def _best_key(chroma_mean: np.ndarray) -> tuple[str, str, float]:
    best = ("C", "major", -np.inf)
    for mode, profile in (("major", _MAJOR), ("minor", _MINOR)):
        for shift in range(12):
            r = float(np.corrcoef(chroma_mean, np.roll(profile, shift))[0, 1])
            if r > best[2]:
                best = (PITCHES[shift], mode, r)
    tonic, mode, r = best
    confidence = float(np.clip(r, 0.0, 1.0))
    return f"{tonic} {mode}", to_camelot(tonic, mode), confidence


def estimate_key(y: np.ndarray, sr: int) -> tuple[str, str, float]:
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    return _best_key(chroma.mean(axis=1))


def key_over_time(
    y: np.ndarray,
    sr: int,
    win_s: float = 30.0,
) -> tuple[np.ndarray, list[str], np.ndarray]:
    """Camelot key per non-overlapping window. Returns (center times, keys, confidences).

    One chroma_stft pass over the whole signal, averaged per window — chroma_cqt per
    window would take minutes on a multi-hour mix."""
    hop = 2048
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop)
    win_f = max(1, int(win_s * sr / hop))
    n = chroma.shape[1] // win_f
    times, keys, confs = [], [], []
    for i in range(n):
        _, camelot, conf = _best_key(chroma[:, i * win_f : (i + 1) * win_f].mean(axis=1))
        times.append((i + 0.5) * win_s)
        keys.append(camelot)
        confs.append(conf)
    return np.array(times), keys, np.array(confs)

"""Decode + resample: everything downstream works on 22,050 Hz mono float32."""

from pathlib import Path

import librosa
import numpy as np

TARGET_SR = 22050


def load_audio(path: str | Path, sr: int = TARGET_SR) -> tuple[np.ndarray, int]:
    y, sr_out = librosa.load(str(path), sr=sr, mono=True)
    return y.astype(np.float32), int(sr_out)

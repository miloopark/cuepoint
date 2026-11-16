"""Decode + resample. Everything downstream works on mono float32 at the
analysis rate (22,050 Hz by default).

Decoding is chunked and streaming: soundfile reads blocks at the native rate,
each block is mixed to mono and pushed through a soxr ResampleStream, so the
full native-rate signal (≈1.9 GB for a 90-minute 44.1 kHz stereo mix) never
exists in memory — only the resampled result does. Accepts paths or file-like
objects, so callers can keep downloads entirely in memory."""

import io
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

TARGET_SR = 22050
_BLOCK_FRAMES = 1 << 20  # ~24 s of 44.1 kHz audio per block


def framewise(
    fn,
    y: np.ndarray,
    n_fft: int,
    hop: int,
    sr: int,
    chunk_s: float = 600.0,
) -> np.ndarray:
    """Apply a frame-based librosa feature fn(seg, center=...) over y in time
    chunks and concatenate along frames.

    Keeps transient STFT memory proportional to chunk length instead of mix
    length. Frames align exactly with a whole-signal center=True call: y is
    reflect-padded by n_fft//2 once, then each chunk is computed center=False
    on a slice that carries its own context, so there are no seam artifacts."""
    chunk_frames = max(1, int(chunk_s * sr / hop))
    total_frames = 1 + len(y) // hop
    if total_frames <= chunk_frames:
        return fn(y, center=True)

    pad = n_fft // 2
    y_pad = np.pad(y, pad, mode="reflect")
    outs = []
    for f0 in range(0, total_frames, chunk_frames):
        f1 = min(f0 + chunk_frames, total_frames)
        lo = f0 * hop
        hi = (f1 - 1) * hop + n_fft
        seg = y_pad[lo:hi]
        if len(seg) < n_fft:
            break
        outs.append(fn(seg, center=False))
    return np.concatenate(outs, axis=-1)


def fft_size(sr: int) -> int:
    """n_fft matched to the analysis rate: 1024 at 11025 Hz has the same ~93 ms
    window and ~10.8 Hz bin spacing as 2048 at 22050 Hz, and halves the STFT
    memory that otherwise OOMs a 2 GB worker on multi-hour sets."""
    return 2048 if sr >= TARGET_SR else 1024


def _rewind(src) -> None:
    if hasattr(src, "seek"):
        src.seek(0)


def probe_duration(path_or_file) -> float:
    """Duration in seconds from the container header, without decoding."""
    _rewind(path_or_file)
    info = sf.info(path_or_file)
    _rewind(path_or_file)
    return float(info.frames) / float(info.samplerate)


def load_audio(
    path_or_file: str | Path | io.IOBase,
    sr: int = TARGET_SR,
    block_frames: int = _BLOCK_FRAMES,
) -> tuple[np.ndarray, int]:
    src = str(path_or_file) if isinstance(path_or_file, Path) else path_or_file
    _rewind(src)
    try:
        with sf.SoundFile(src) as f:
            in_rate = f.samplerate
            resampler = (
                soxr.ResampleStream(in_rate, sr, 1, dtype="float32") if in_rate != sr else None
            )
            out: list[np.ndarray] = []
            while True:
                block = f.read(block_frames, dtype="float32", always_2d=True)
                if block.shape[0] == 0:
                    break
                mono = block.mean(axis=1)
                out.append(resampler.resample_chunk(mono) if resampler else mono)
            if resampler is not None:
                tail = resampler.resample_chunk(np.zeros(0, dtype=np.float32), last=True)
                if len(tail):
                    out.append(tail)
        y = np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
        return y.astype(np.float32, copy=False), sr
    except sf.LibsndfileError:
        # Formats libsndfile can't read (m4a/aac) — fall back to librosa's
        # audioread path. Needs ffmpeg, so this works locally but not on Vercel.
        import librosa

        _rewind(src)
        y, sr_out = librosa.load(src, sr=sr, mono=True)
        return y.astype(np.float32), int(sr_out)

import io

import numpy as np
import soundfile as sf

from cuepoint_analysis.audio import load_audio, probe_duration


def _stereo_wav_bytes(duration_s: float = 2.0, sr_in: int = 44100) -> bytes:
    t = np.arange(int(sr_in * duration_s)) / sr_in
    stereo = np.stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 220 * t)], axis=1)
    buf = io.BytesIO()
    sf.write(buf, stereo, sr_in, format="WAV")
    return buf.getvalue()


def test_loads_wav_resampled_to_22050_mono(tmp_path):
    path = tmp_path / "tone.wav"
    path.write_bytes(_stereo_wav_bytes())

    y, sr = load_audio(path)

    assert sr == 22050
    assert y.ndim == 1
    assert y.dtype == np.float32
    assert abs(len(y) / sr - 2.0) < 0.05


def test_loads_from_file_like_object():
    y, sr = load_audio(io.BytesIO(_stereo_wav_bytes()))
    assert sr == 22050
    assert abs(len(y) / sr - 2.0) < 0.05


def test_load_audio_honors_requested_rate():
    y, sr = load_audio(io.BytesIO(_stereo_wav_bytes()), sr=11025)
    assert sr == 11025
    assert abs(len(y) / sr - 2.0) < 0.05


def test_chunked_decode_matches_whole_decode():
    data = _stereo_wav_bytes(duration_s=3.0)
    y_small_chunks, _ = load_audio(io.BytesIO(data), block_frames=4096)
    y_big_chunks, _ = load_audio(io.BytesIO(data), block_frames=1 << 22)
    assert len(y_small_chunks) == len(y_big_chunks)
    assert np.allclose(y_small_chunks, y_big_chunks, atol=1e-4)


def test_probe_duration():
    assert abs(probe_duration(io.BytesIO(_stereo_wav_bytes(duration_s=2.0))) - 2.0) < 0.01


def test_chunked_framewise_matches_whole():
    import librosa

    from cuepoint_analysis.audio import framewise

    rng = np.random.default_rng(7)
    y = (0.3 * rng.standard_normal(22050 * 30)).astype(np.float32)

    def mfcc(seg, **kw):
        return librosa.feature.mfcc(y=seg, sr=22050, n_mfcc=20, n_fft=2048, hop_length=512, **kw)

    whole = mfcc(y)
    chunked = framewise(mfcc, y, n_fft=2048, hop=512, chunk_s=5.0, sr=22050)
    assert chunked.shape == whole.shape
    # Interior frames must match exactly; edges may differ by padding mode.
    assert np.allclose(chunked[:, 4:-4], whole[:, 4:-4], atol=1e-3)

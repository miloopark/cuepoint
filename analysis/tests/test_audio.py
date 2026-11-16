import numpy as np
import soundfile as sf

from cuepoint_analysis.audio import load_audio


def test_loads_wav_resampled_to_22050_mono(tmp_path):
    sr_in = 44100
    t = np.arange(sr_in * 2) / sr_in
    stereo = np.stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 220 * t)], axis=1)
    path = tmp_path / "tone.wav"
    sf.write(path, stereo, sr_in)

    y, sr = load_audio(path)

    assert sr == 22050
    assert y.ndim == 1
    assert y.dtype == np.float32
    assert abs(len(y) / sr - 2.0) < 0.05

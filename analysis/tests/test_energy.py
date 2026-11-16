import numpy as np

from conftest import SR
from cuepoint_analysis.energy import energy_curve


def test_energy_in_unit_range_and_louder_half_scores_higher():
    rng = np.random.default_rng(1)
    quiet = (0.02 * rng.standard_normal(SR * 30)).astype(np.float32)
    loud = (0.8 * rng.standard_normal(SR * 30)).astype(np.float32)
    y = np.concatenate([quiet, loud])

    times, energy = energy_curve(y, SR, hop_s=5.0)

    assert len(times) == len(energy)
    assert np.all(energy >= 0.0) and np.all(energy <= 1.0)
    half = len(energy) // 2
    assert energy[half:].mean() > energy[:half].mean() + 0.2

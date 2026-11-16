import numpy as np

from conftest import SR
from cuepoint_analysis.tempo import bpm_over_time, fold_bpm


def test_click_track_estimates_128_in_every_window(click_128):
    times, bpm = bpm_over_time(click_128, SR, win_s=30.0, hop_s=10.0)
    assert len(times) == len(bpm)
    assert len(bpm) >= 3
    assert np.all(np.abs(bpm - 128.0) <= 2.0)


def test_fold_bpm_doubles_half_time_toward_reference():
    assert fold_bpm(64.0, reference=126.0) == 128.0


def test_fold_bpm_halves_double_time_toward_reference():
    assert fold_bpm(250.0, reference=126.0) == 125.0


def test_fold_bpm_leaves_in_range_value_alone():
    assert fold_bpm(124.0, reference=126.0) == 124.0

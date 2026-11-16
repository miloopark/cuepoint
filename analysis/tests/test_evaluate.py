from cuepoint_analysis.evaluate import score_transitions


def test_score_counts_hits_misses_and_false_alarms():
    result = score_transitions(detected_s=[118.0, 500.0], truth_s=[120.0, 300.0], tol_s=15.0)
    assert result.true_positives == 1
    assert result.false_negatives == 1
    assert result.false_positives == 1
    assert result.precision == 0.5
    assert result.recall == 0.5


def test_each_truth_matches_at_most_one_detection():
    result = score_transitions(detected_s=[118.0, 122.0], truth_s=[120.0], tol_s=15.0)
    assert result.true_positives == 1
    assert result.false_positives == 1


def test_perfect_match():
    result = score_transitions(detected_s=[100.0, 200.0], truth_s=[100.0, 200.0], tol_s=15.0)
    assert result.precision == 1.0
    assert result.recall == 1.0

"""Score detected transitions against ground-truth boundaries."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionScore:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float


def score_transitions(detected_s: list[float], truth_s: list[float], tol_s: float = 15.0) -> TransitionScore:
    """Greedy one-to-one matching: each truth boundary claims the nearest unused detection within tol."""
    detected = sorted(detected_s)
    used = [False] * len(detected)
    tp = 0
    for t in sorted(truth_s):
        best_i, best_d = None, None
        for i, d in enumerate(detected):
            if used[i]:
                continue
            dist = abs(d - t)
            if dist <= tol_s and (best_d is None or dist < best_d):
                best_i, best_d = i, dist
        if best_i is not None:
            used[best_i] = True
            tp += 1
    fp = len(detected) - tp
    fn = len(truth_s) - tp
    return TransitionScore(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=tp / len(detected) if detected else 0.0,
        recall=tp / len(truth_s) if truth_s else 0.0,
    )

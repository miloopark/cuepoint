#!/usr/bin/env python
"""Grid-search transition-detection parameters against the labeled sets.

Block features are computed once per set; novelty once per (set, kernel);
peak picking is swept over sigma and prominence. Ranks by mean F1 at ±30 s
(the crowd-sourced timestamps are rounded to the nearest 10-60 s, so ±15 s
underestimates real accuracy), with ±15 s reported alongside."""

import argparse
import itertools
import json
import time
from pathlib import Path

from cuepoint_analysis.audio import load_audio
from cuepoint_analysis.evaluate import score_transitions
from cuepoint_analysis.labels import filter_within_duration, parse_tracklist
from cuepoint_analysis.transitions import block_features, novelty_from_blocks, pick_peaks

BLOCK_S = 2.0
KERNELS = [32.0, 64.0, 96.0, 128.0]
SIGMAS = [1.0, 2.0, 3.0]
PROMINENCES = [0.05, 0.1, 0.15, 0.2, 0.3, 0.5]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    sets = []
    for s in manifest["sets"]:
        t0 = time.time()
        y, sr = load_audio(args.root / s["audio"])
        duration_s = len(y) / sr
        entries = filter_within_duration(parse_tracklist((args.root / s["labels"]).read_text()), duration_s)
        truth = [e.start_s for e in entries if e.start_s > 0]
        blocks = block_features(y, sr, BLOCK_S)
        print(f"prepared {s['id']}: {len(truth)} truth boundaries ({time.time() - t0:.0f}s)", flush=True)
        sets.append({"id": s["id"], "truth": truth, "blocks": blocks})

    novelty = {}
    for s, kernel_s in itertools.product(sets, KERNELS):
        novelty[(s["id"], kernel_s)] = novelty_from_blocks(s["blocks"], BLOCK_S, kernel_s)
    print("novelty curves done", flush=True)

    results = []
    for kernel_s, sigma, prom in itertools.product(KERNELS, SIGMAS, PROMINENCES):
        per_set = []
        for s in sets:
            transitions = pick_peaks(
                novelty[(s["id"], kernel_s)], BLOCK_S, sigma=sigma, min_prominence=prom
            )
            detected = [t.peak_s for t in transitions]
            r30 = score_transitions(detected, s["truth"], tol_s=30.0)
            r15 = score_transitions(detected, s["truth"], tol_s=15.0)
            f1 = (
                2 * r30.precision * r30.recall / (r30.precision + r30.recall)
                if (r30.precision + r30.recall) > 0
                else 0.0
            )
            per_set.append((f1, r30, r15, len(detected)))
        mean_f1 = sum(p[0] for p in per_set) / len(per_set)
        results.append((mean_f1, kernel_s, sigma, prom, per_set))

    results.sort(key=lambda r: -r[0])
    print("\ntop 8 by mean F1@±30s:")
    for mean_f1, kernel_s, sigma, prom, per_set in results[:8]:
        print(f"\nF1 {mean_f1:.3f}  kernel {kernel_s:.0f}s sigma {sigma:.0f} prominence {prom}")
        for s, (f1, r30, r15, n) in zip(sets, per_set):
            print(
                f"  {s['id']}: {n} detected | ±30s P {r30.precision:.2f} R {r30.recall:.2f}"
                f" | ±15s P {r15.precision:.2f} R {r15.recall:.2f}"
            )


if __name__ == "__main__":
    main()

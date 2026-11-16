#!/usr/bin/env python
"""Grid-search transition-detection parameters.

Tunes on the Cloonee set and reports the Franky set as HELD OUT, so the chosen
parameters aren't fit to both label sets. Label offsets from the manifest are
applied. Block features (fixed and beat-sync), novelty per kernel, and cue
curves are cached; the sweep itself is cheap peak-picking."""

import argparse
import itertools
import json
import time
from pathlib import Path

from cuepoint_analysis.audio import load_audio
from cuepoint_analysis.evaluate import score_transitions
from cuepoint_analysis.key import key_over_time
from cuepoint_analysis.labels import parse_tracklist
from cuepoint_analysis.tempo import bpm_over_time
from cuepoint_analysis.transitions import (
    beat_blocks,
    block_features,
    key_cue,
    novelty_from_blocks,
    pick_peaks,
    tempo_cue,
)

TRAIN_ID = "cloonee-b2b-prospa-destino"
VARIANTS = ["fixed2s", "beat16"]
KERNELS = [96.0, 128.0, 192.0]
SIGMAS = [1.0, 2.0]
PROMINENCES = [0.1, 0.15, 0.2, 0.3]
TEMPO_WEIGHTS = [0.0, 0.1, 0.25]
KEY_WEIGHTS = [0.0, 0.1, 0.25]


def prepare(root: Path, s: dict) -> dict:
    t0 = time.time()
    y, sr = load_audio(root / s["audio"])
    duration_s = len(y) / sr
    offset = float(s.get("label_offset_s", 0.0))
    entries = parse_tracklist((root / s["labels"]).read_text())
    truth = [e.start_s - offset for e in entries if 0 < e.start_s - offset < duration_s]

    bpm_series = bpm_over_time(y, sr)
    key_series = key_over_time(y, sr)

    blocks = {
        "fixed2s": block_features(y, sr),
        "beat16": beat_blocks(y, sr, 16),
    }
    novelty = {}
    cues = {}
    for variant, (times, bl) in blocks.items():
        for kernel_s in KERNELS:
            novelty[(variant, kernel_s)] = novelty_from_blocks(bl, times, kernel_s)
        cues[variant] = (
            times,
            tempo_cue(times, bpm_series[0], bpm_series[1]),
            key_cue(times, key_series[0], key_series[1], key_series[2]),
        )
    print(f"prepared {s['id']}: {len(truth)} boundaries ({time.time() - t0:.0f}s)", flush=True)
    return {"id": s["id"], "truth": truth, "novelty": novelty, "cues": cues}


def score(prep: dict, variant: str, kernel_s: float, sigma: float, prom: float, wt: float, wk: float):
    times, tcue, kcue = prep["cues"][variant]
    fused = prep["novelty"][(variant, kernel_s)] + wt * tcue + wk * kcue
    detected = [t.peak_s for t in pick_peaks(fused, times, sigma=sigma, min_prominence=prom)]
    r30 = score_transitions(detected, prep["truth"], tol_s=30.0)
    r15 = score_transitions(detected, prep["truth"], tol_s=15.0)
    f1 = (
        2 * r30.precision * r30.recall / (r30.precision + r30.recall)
        if (r30.precision + r30.recall) > 0
        else 0.0
    )
    return f1, r30, r15, len(detected)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    preps = {s["id"]: prepare(args.root, s) for s in manifest["sets"]}
    train = preps[TRAIN_ID]
    holdouts = [p for sid, p in preps.items() if sid != TRAIN_ID]

    results = []
    for combo in itertools.product(VARIANTS, KERNELS, SIGMAS, PROMINENCES, TEMPO_WEIGHTS, KEY_WEIGHTS):
        f1, r30, r15, n = score(train, *combo)
        results.append((f1, combo, r30, r15, n))
    results.sort(key=lambda r: -r[0])

    print(f"\ntop 10 by TRAIN ({TRAIN_ID}) F1@±30s, with holdout:")
    for f1, combo, r30, r15, n in results[:10]:
        variant, kernel_s, sigma, prom, wt, wk = combo
        print(
            f"\nF1 {f1:.3f}  {variant} kernel {kernel_s:.0f}s sigma {sigma:.0f} "
            f"prom {prom} wt {wt} wk {wk}"
        )
        print(
            f"  train:   {n} detected | ±30s P {r30.precision:.2f} R {r30.recall:.2f}"
            f" | ±15s P {r15.precision:.2f} R {r15.recall:.2f}"
        )
        for h in holdouts:
            _hf1, hr30, hr15, hn = score(h, *combo)
            print(
                f"  holdout: {hn} detected | ±30s P {hr30.precision:.2f} R {hr30.recall:.2f}"
                f" | ±15s P {hr15.precision:.2f} R {hr15.recall:.2f}  ({h['id']})"
            )


if __name__ == "__main__":
    main()

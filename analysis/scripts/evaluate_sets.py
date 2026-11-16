#!/usr/bin/env python
"""Run transition detection on each labeled set and score against its tracklist."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from cuepoint_analysis.audio import load_audio
from cuepoint_analysis.evaluate import score_transitions
from cuepoint_analysis.labels import parse_tracklist
from cuepoint_analysis.tempo import bpm_over_time
from cuepoint_analysis.transitions import detect_transitions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=None, help="repo root that manifest paths are relative to")
    args = ap.parse_args()
    root = args.root or args.manifest.resolve().parents[2]

    manifest = json.loads(args.manifest.read_text())
    for s in manifest["sets"]:
        print(f"\n=== {s['title']} ===", flush=True)
        t0 = time.time()
        y, sr = load_audio(root / s["audio"])
        duration_s = len(y) / sr
        print(f"decoded {duration_s / 60:.1f} min in {time.time() - t0:.0f}s", flush=True)

        offset = float(s.get("label_offset_s", 0.0))
        entries = parse_tracklist((root / s["labels"]).read_text())
        # Shift labels onto the recording's clock; the first boundary at 0:00 is the
        # set start, not a transition.
        truth = [e.start_s - offset for e in entries if 0 < e.start_s - offset < duration_s]

        t0 = time.time()
        transitions = detect_transitions(y, sr)
        detected = [t.peak_s for t in transitions]
        print(f"detected {len(detected)} transitions in {time.time() - t0:.0f}s (ground truth: {len(truth)})", flush=True)

        for tol in (15.0, 30.0):
            r = score_transitions(detected, truth, tol_s=tol)
            print(
                f"  ±{tol:.0f}s  precision {r.precision:.2f}  recall {r.recall:.2f}  "
                f"(tp {r.true_positives} / fp {r.false_positives} / fn {r.false_negatives})",
                flush=True,
            )

        t0 = time.time()
        _, bpm = bpm_over_time(y, sr)
        print(
            f"BPM median {np.median(bpm):.1f}, range {bpm.min():.0f}–{bpm.max():.0f} "
            f"({time.time() - t0:.0f}s)",
            flush=True,
        )


if __name__ == "__main__":
    main()

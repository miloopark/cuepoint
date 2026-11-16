# Cuepoint

Upload a recorded DJ mix and get back its timeline: where each track starts and ends, tempo and key over time, the energy curve, and the name of each track, identified by a hand-written audio fingerprinting engine.

> Status: frontend only. The pages run on sample data until the analysis worker and API are in place.

## Repo layout

```
web/        React + TypeScript + Vite frontend
analysis/   Python DSP package: tempo, key (Camelot), energy, transition detection
api/        (planned) FastAPI app, RQ worker, Postgres schema
data/       labeled evaluation sets: tracklists in labels/, audio in mixes/ (untracked)
```

## Analysis

```bash
cd analysis
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                        # unit tests on synthetic audio
.venv/bin/python scripts/evaluate_sets.py --manifest ../data/labels/sets.json --root ..
.venv/bin/python scripts/tune_transitions.py --manifest ../data/labels/sets.json --root ..
```

Current transition-detection numbers on the two labeled sets (novelty kernel 128 s,
prominence 0.15, tuned by the grid search): precision 0.48–0.56 and recall 0.60–0.62
at ±30 s. One set's tracklist is minute-rounded and offset-corrected by +65 s
(see `data/labels/sets.json` notes).

## Frontend

```bash
cd web
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production build into web/dist
```

### Pages

| Route | What it shows |
| --- | --- |
| `/` | Landing page: upload, demo sets, method, evaluation, architecture |
| `/processing` | Job progress: percentage, waveform filling in, pipeline stages |
| `/sets/:id` | Set analysis: energy, waveform, track blocks by Camelot key, BPM line, selected-track detail, tracklist |

### Where things live

- `web/src/styles.css`: the design tokens (`--paper`, `--ink`, `--accent`, fonts) and all styles
- `web/src/components/Logo.tsx`: the Cuepoint mark and wordmark. Each dot ring uses `pathLength` equal to its dot count, so the dots are evenly spaced
- `web/src/lib/sample.ts`: sample segments and helpers. Its `Segment` shape matches the planned `segments` table, so swapping in real API data is a drop-in change
- `web/vercel.json`: SPA rewrite for Vercel

### Wiring up the API (next)

- `Landing.tsx` → `accept()`: replace the TODO with `POST /uploads` → PUT to the presigned URL → `POST /sets`, then route to the set's processing page
- `Processing.tsx`: replace the simulated progress with the SSE stream at `/sets/{id}/events`
- `Analysis.tsx`: load `/sets/{id}/analysis` and `/sets/{id}/waveform` in place of `sample.ts`

## Design

"Pressed Grain": black ink on warm off-white paper, halftone dot textures, hairline rules, and one signal-red accent. The type is Inter Tight for text, Instrument Serif italic for one word per heading, JetBrains Mono for data, and Unbounded for the wordmark.

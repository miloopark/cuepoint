# Cuepoint

Upload a recorded DJ mix and get back its timeline: where each track starts and ends, tempo and key over time, the energy curve, and the name of each track, identified by a hand-written audio fingerprinting engine.

> Status: frontend only. The pages run on sample data until the analysis worker and API are in place.

## Repo layout

```
web/        React + TypeScript + Vite frontend
analysis/   (planned) Python DSP package: tempo, key, energy, transitions, fingerprinting
api/        (planned) FastAPI app, RQ worker, Postgres schema
```

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

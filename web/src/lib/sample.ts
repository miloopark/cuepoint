// Sample analysis used until the API is wired up.
// Shape mirrors the `segments` table in the build plan.

export interface Segment {
  startMin: number;
  endMin: number;
  bpm: number;
  camelotKey: string;
  matchConfidence: number; // 0–1
  artist: string | null;
  title: string | null;
}

export const SAMPLE_DURATION_MIN = 62.2;

/** Match confidence below this is shown as "No match". */
export const MATCH_THRESHOLD = 0.5;

/** Half-width of each blend window, in minutes. */
export const BLEND_HALF_MIN = 0.4;

const raw: [number, number, number, string, number][] = [
  [0, 5.5, 122, '8A', 0.93],
  [5.5, 10.8, 123, '9A', 0.88],
  [10.8, 16.2, 124, '9A', 0.81],
  [16.2, 21, 124, '10A', 0.95],
  [21, 26.4, 125, '10B', 0.91],
  [26.4, 31.5, 126, '11A', 0.76],
  [31.5, 36.8, 126, '11A', 0.22],
  [36.8, 41.6, 127, '12A', 0.84],
  [41.6, 47, 128, '1A', 0.97],
  [47, 52.2, 128, '12A', 0.89],
  [52.2, 57.4, 126, '11A', 0.79],
  [57.4, 62.2, 124, '8A', 0.86],
];

export const sampleSegments: Segment[] = raw.map(([startMin, endMin, bpm, camelotKey, matchConfidence]) => ({
  startMin,
  endMin,
  bpm,
  camelotKey,
  matchConfidence,
  artist: null,
  title: null,
}));

/** Track boundaries (every segment start except the first). */
export const sampleCuts = sampleSegments.slice(1).map((s) => s.startMin);

/** Deterministic pseudo-random value in [0, 1). */
export function rnd(i: number): number {
  const x = Math.sin(i * 12.9898 + 4.1) * 43758.5453;
  return x - Math.floor(x);
}

/** Sample energy curve, t in [0, 1] → 0–1, dipping at each blend. */
export function sampleEnergy(t: number): number {
  let e = 0.3 + 0.6 * Math.pow(Math.sin(Math.PI * Math.min(t * 1.06, 1)), 1.2);
  for (const c of sampleCuts) {
    const d = (t * SAMPLE_DURATION_MIN - c) / 0.55;
    e -= 0.3 * Math.exp(-d * d);
  }
  return Math.max(0.06, Math.min(1, e));
}

/** Waveform bar heights in percent. */
export function sampleBars(n: number): number[] {
  return Array.from({ length: n }, (_, i) => {
    const t = i / (n - 1);
    return Math.round(sampleEnergy(t) * (0.5 + 0.5 * rnd(i)) * 100);
  });
}

/** Minutes → "mm:ss". */
export function formatTime(min: number): string {
  const s = Math.round(min * 60);
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/** Minutes → percent of the set length. */
export function pct(min: number, duration = SAMPLE_DURATION_MIN): number {
  return (min / duration) * 100;
}

export function trackName(s: Segment): string {
  if (s.matchConfidence < MATCH_THRESHOLD) return 'Unidentified';
  return `${s.artist ?? '[Artist]'} — ${s.title ?? '[Title]'}`;
}

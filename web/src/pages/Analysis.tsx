import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Nav } from '../components/Nav';
import { audioUrl, getAnalysis, getWaveform } from '../lib/api';
import {
  BLEND_HALF_MIN,
  MATCH_THRESHOLD,
  SAMPLE_DURATION_MIN,
  formatTime,
  sampleBars,
  sampleEnergy,
  sampleSegments,
} from '../lib/sample';

interface ViewSegment {
  startMin: number;
  endMin: number;
  bpm: number;
  camelotKey: string;
  matchConfidence: number;
  artist: string | null;
  title: string | null;
  blendStartMin: number | null;
  blendEndMin: number | null;
}

interface SetView {
  id: string;
  title: string | null;
  durationMin: number;
  segments: ViewSegment[];
  energy: number[]; // 0–1, ~160 points
  wave: number[]; // 0–100, 240 bars
  isSample: boolean;
  audioSrc: string | null;
}

function resample(values: number[], n: number, reduce: (chunk: number[]) => number): number[] {
  if (values.length === 0) return Array(n).fill(0);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const lo = Math.floor((i / n) * values.length);
    const hi = Math.max(lo + 1, Math.floor(((i + 1) / n) * values.length));
    out.push(reduce(values.slice(lo, hi)));
  }
  return out;
}

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

function sampleView(id: string): SetView {
  return {
    id,
    title: null,
    durationMin: SAMPLE_DURATION_MIN,
    segments: sampleSegments.map((s, i) => ({
      ...s,
      blendStartMin: i === 0 ? null : s.startMin - BLEND_HALF_MIN,
      blendEndMin: i === 0 ? null : s.startMin + BLEND_HALF_MIN,
    })),
    energy: Array.from({ length: 160 }, (_, i) => sampleEnergy(i / 159)),
    wave: sampleBars(240),
    isSample: true,
    audioSrc: null,
  };
}

async function fetchView(id: string): Promise<SetView> {
  const [analysis, waveform] = await Promise.all([getAnalysis(id), getWaveform(id)]);
  return {
    id,
    title: analysis.title,
    durationMin: analysis.duration_s / 60,
    segments: analysis.segments.map((s) => ({
      startMin: s.start_s / 60,
      endMin: s.end_s / 60,
      bpm: s.bpm ?? 0,
      camelotKey: s.camelot_key ?? '—',
      matchConfidence: s.match_confidence ?? 0,
      artist: null,
      title: null,
      blendStartMin: s.transition_start_s === null ? null : s.transition_start_s / 60,
      blendEndMin: s.transition_end_s === null ? null : s.transition_end_s / 60,
    })),
    energy: resample(analysis.features.energy, 160, mean),
    wave: resample(waveform.waveform, 240, (c) => Math.max(...c)),
    isSample: false,
    audioSrc: audioUrl(id),
  };
}

/** Grey tint per Camelot number, so neighbouring keys read as neighbouring tones. */
function keyTint(key: string): string {
  const n = (parseInt(key, 10) || 0) % 12;
  return `rgba(14, 14, 14, ${(0.06 + (n / 12) * 0.2).toFixed(3)})`;
}

function trackName(s: ViewSegment): string {
  if (s.matchConfidence < MATCH_THRESHOLD) return 'Unidentified';
  return `${s.artist ?? '[Artist]'} — ${s.title ?? '[Title]'}`;
}

function keyPath(segments: ViewSegment[]): string {
  const compressed = segments
    .map((s) => s.camelotKey)
    .filter((k, i, ks) => i === 0 || k !== ks[i - 1]);
  if (compressed.length <= 3) return compressed.join(' → ');
  return `${compressed[0]} → ${compressed[Math.floor(compressed.length / 2)]} → ${compressed[compressed.length - 1]}`;
}

export function Analysis() {
  const { id = 'demo-01' } = useParams();
  const isDemo = id.startsWith('demo');
  const [view, setView] = useState<SetView | null>(isDemo ? sampleView(id) : null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sel, setSel] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentMin, setCurrentMin] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (isDemo) {
      setView(sampleView(id));
      setSel(4);
      return;
    }
    setView(null);
    setLoadError(null);
    fetchView(id)
      .then((v) => {
        setView(v);
        setSel(0);
      })
      .catch((e: Error) => setLoadError(e.message));
  }, [id, isDemo]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(t);
  }, [toast]);

  const segments = view?.segments ?? [];
  const s = segments[Math.min(sel, Math.max(0, segments.length - 1))];
  const D = view?.durationMin ?? SAMPLE_DURATION_MIN;
  const pctD = (min: number) => (min / D) * 100;

  const ticks = useMemo(() => {
    const step = D > 150 ? 30 : D > 75 ? 20 : 10;
    const out: number[] = [];
    for (let m = 0; m <= D; m += step) out.push(m);
    return out;
  }, [D]);

  const energyShape = useMemo(() => {
    const e = view?.energy ?? [];
    const pts: string[] = [];
    const clip: string[] = ['0% 100%'];
    e.forEach((v, i) => {
      const t = i / Math.max(1, e.length - 1);
      const y = 100 - v * 92;
      pts.push(`${(t * 1000).toFixed(1)},${y.toFixed(1)}`);
      clip.push(`${(t * 100).toFixed(2)}% ${y.toFixed(1)}%`);
    });
    clip.push('100% 100%');
    return { points: pts.join(' '), clip: `polygon(${clip.join(', ')})` };
  }, [view]);

  const bpmLane = useMemo(() => {
    const bpms = segments.map((x) => x.bpm).filter((b) => b > 0);
    if (!bpms.length) return { points: '', lo: 120, hi: 130 };
    const lo = Math.min(...bpms) - 2;
    const hi = Math.max(...bpms) + 2;
    const y = (bpm: number) => (90 - ((bpm - lo) / Math.max(1, hi - lo)) * 80).toFixed(1);
    const points = segments
      .map((x) => `${((x.startMin / D) * 1000).toFixed(1)},${y(x.bpm)} ${((x.endMin / D) * 1000).toFixed(1)},${y(x.bpm)}`)
      .join(' ');
    return { points, lo, hi };
  }, [segments, D]);

  const waveColors = useMemo(
    () =>
      (view?.wave ?? []).map((_, i, arr) => {
        const m = (i / (arr.length - 1)) * D;
        return s && m >= s.startMin && m < s.endMin ? 'var(--accent)' : 'var(--ink)';
      }),
    [view, s, D],
  );

  async function copy(text: string, message: string) {
    try {
      await navigator.clipboard.writeText(text);
      setToast(message);
    } catch {
      setToast('Couldn’t reach the clipboard');
    }
  }

  function playFrom(min: number | null) {
    const el = audioRef.current;
    if (!el) {
      setToast('Audio is only available for uploaded sets');
      return;
    }
    if (min !== null) el.currentTime = min * 60;
    if (el.paused) void el.play();
    else if (min === null) el.pause();
  }

  if (loadError) {
    return (
      <>
        <Nav>
          <Link to="/#upload">Analyze a mix</Link>
        </Nav>
        <main className="wrap page" style={{ paddingTop: 56 }}>
          <span className="mono-label muted">Set / {id}</span>
          <h1 className="set-title">Couldn’t load this set.</h1>
          <p className="lede">{loadError}</p>
          <Link to="/" className="btn" style={{ alignSelf: 'flex-start' }}>
            Back home
          </Link>
        </main>
      </>
    );
  }

  if (!view || !s) {
    return (
      <>
        <Nav />
        <main className="wrap page" style={{ paddingTop: 56 }}>
          <span className="mono-label muted">( Loading set… )</span>
        </main>
      </>
    );
  }

  const ok = s.matchConfidence >= MATCH_THRESHOLD;
  const identified = segments.filter((x) => x.matchConfidence >= MATCH_THRESHOLD).length;
  const bpms = segments.map((x) => x.bpm).filter((b) => b > 0);
  const playheadMin = playing && currentMin !== null ? currentMin : s.startMin;
  const tracklistText = segments.map((x) => `${formatTime(x.startMin)}  ${trackName(x)}`).join('\n');

  return (
    <>
      <Nav>
        <Link to="/#demo">Demo sets</Link>
        <Link to="/#upload">Analyze a mix</Link>
      </Nav>

      {view.audioSrc && (
        <audio
          ref={audioRef}
          src={view.audioSrc}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={(e) => setCurrentMin(e.currentTarget.currentTime / 60)}
        />
      )}

      <main className="wrap page" style={{ paddingTop: 56, gap: 40 }}>
        <div className="set-head">
          <div>
            <span className="mono-label muted" style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              Set / {view.id.slice(0, 8)} {view.isSample && <span className="pill">Sample data</span>}
            </span>
            <h1 className="set-title">
              {view.title ?? (
                <>
                  [Set title], <span className="it">[venue]</span>
                </>
              )}
            </h1>
          </div>
          <div className="set-actions">
            <button
              type="button"
              className="play-btn"
              aria-label={playing ? 'Pause set' : 'Play set'}
              onClick={() => playFrom(null)}
            >
              {playing ? (
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
                  <path d="M3.5 2.5h3v11h-3zm6 0h3v11h-3z" fill="var(--ink)" />
                </svg>
              ) : (
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
                  <path d="M4 2.5v11l9-5.5z" fill="var(--ink)" />
                </svg>
              )}
            </button>
            <button type="button" className="btn" onClick={() => copy(tracklistText, 'Tracklist copied')}>
              Copy tracklist
            </button>
            <button type="button" className="btn btn-solid" onClick={() => copy(window.location.href, 'Link copied')}>
              Share set
            </button>
          </div>
        </div>

        <dl className="stats">
          <div>
            <dt>Length</dt>
            <dd>{formatTime(D)}</dd>
          </div>
          <div>
            <dt>Tracks</dt>
            <dd>{segments.length}</dd>
          </div>
          <div>
            <dt>Identified</dt>
            <dd>
              {identified}
              <span className="it muted"> / {segments.length}</span>
            </dd>
          </div>
          <div>
            <dt>Tempo</dt>
            <dd>
              {bpms.length ? `${Math.min(...bpms)}–${Math.max(...bpms)}` : '—'}
              <small> BPM</small>
            </dd>
          </div>
          <div>
            <dt>Key path</dt>
            <dd>{keyPath(segments)}</dd>
          </div>
        </dl>

        <section aria-label="Timeline" className="timeline-scroll">
          <div className="timeline">
            <div aria-hidden="true" className="lane-labels">
              <span style={{ height: 28 }} />
              <span style={{ height: 80, borderTopColor: 'var(--ink)' }}>Energy</span>
              <span style={{ height: 112 }}>Wave</span>
              <span style={{ height: 72 }}>Tracks</span>
              <span
                style={{
                  height: 72,
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  justifyContent: 'center',
                  gap: 4,
                  borderBottom: '1px solid var(--ink)',
                }}
              >
                BPM
                <small>
                  {bpmLane.lo}–{bpmLane.hi}
                </small>
              </span>
            </div>

            <div className="lanes">
              <div aria-hidden="true" className="lane lane-axis">
                {ticks.map((m) => (
                  <span key={m} style={{ left: `${pctD(m)}%` }}>
                    {m}:00
                  </span>
                ))}
              </div>

              <div aria-hidden="true" className="lane lane-energy">
                <div className="energy-fill" style={{ clipPath: energyShape.clip }} />
                <svg viewBox="0 0 1000 100" preserveAspectRatio="none">
                  <polyline
                    points={energyShape.points}
                    fill="none"
                    stroke="var(--ink)"
                    strokeWidth={1.5}
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              </div>

              <div aria-hidden="true" className="lane lane-wave wave">
                {view.wave.map((h, i) => (
                  <i key={i} style={{ height: `${h}%`, background: waveColors[i] }} />
                ))}
              </div>

              <div className="lane lane-tracks">
                {segments.map((seg, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`seg ${i === sel ? 'is-on' : ''}`}
                    aria-pressed={i === sel}
                    aria-label={`Track ${i + 1}, ${seg.camelotKey}, ${seg.bpm} BPM, starts ${formatTime(seg.startMin)}`}
                    onClick={() => setSel(i)}
                    style={{
                      left: `${pctD(seg.startMin)}%`,
                      width: `${pctD(seg.endMin - seg.startMin)}%`,
                      background: keyTint(seg.camelotKey),
                    }}
                  >
                    <span>{String(i + 1).padStart(2, '0')}</span>
                    <strong>{seg.camelotKey}</strong>
                  </button>
                ))}
                {segments
                  .filter((seg) => seg.blendStartMin !== null && seg.blendEndMin !== null)
                  .map((seg) => (
                    <div
                      key={`b${seg.startMin}`}
                      aria-hidden="true"
                      className="blend"
                      style={{
                        left: `${pctD(seg.blendStartMin!)}%`,
                        width: `${pctD(seg.blendEndMin! - seg.blendStartMin!)}%`,
                      }}
                    />
                  ))}
              </div>

              <div aria-hidden="true" className="lane lane-bpm">
                <svg viewBox="0 0 1000 100" preserveAspectRatio="none">
                  <polyline
                    points={bpmLane.points}
                    fill="none"
                    stroke="var(--ink)"
                    strokeWidth={2}
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
              </div>

              <div aria-hidden="true" className="playhead" style={{ top: 6, bottom: 0, left: `${pctD(playheadMin)}%` }} />
              <span
                aria-hidden="true"
                className="playhead-tag"
                style={{ top: 0, left: `${pctD(playheadMin)}%`, fontSize: 10, padding: '2px 6px' }}
              >
                {formatTime(playheadMin)}
              </span>
            </div>
          </div>
        </section>

        <div className="detail-row">
          <aside aria-label="Selected track" className="detail">
            <div className="detail-meta mono-label">
              <span>
                Track {String(sel + 1).padStart(2, '0')} / {segments.length}
              </span>
              <span>
                {formatTime(s.startMin)} – {formatTime(s.endMin)}
              </span>
            </div>
            <p className="detail-name">{trackName(s)}</p>
            <div className="detail-key">
              <b>{s.camelotKey}</b>
              <span className="it">Camelot</span>
            </div>
            <dl>
              <div>
                <dt>Tempo</dt>
                <dd>{s.bpm || '—'} BPM</dd>
              </div>
              <div>
                <dt>Blend in</dt>
                <dd>
                  {s.blendStartMin === null || s.blendEndMin === null
                    ? '—'
                    : `${formatTime(s.blendStartMin)}–${formatTime(s.blendEndMin)}`}
                </dd>
              </div>
            </dl>
            <div>
              <div className="meter-label mono-label">
                <span>Match confidence</span>
                <span>{ok ? `${Math.round(s.matchConfidence * 100)}%` : 'No match'}</span>
              </div>
              <div className="meter">
                <div style={{ width: `${Math.round(s.matchConfidence * 100)}%` }} />
              </div>
            </div>
            <button
              type="button"
              className="btn btn-light btn-sm"
              style={{ alignSelf: 'flex-start' }}
              onClick={() => playFrom(s.startMin)}
            >
              Play from {formatTime(s.startMin)}
            </button>
          </aside>

          <section aria-label="Tracklist" className="tracklist">
            <table>
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Time</th>
                  <th scope="col">Track</th>
                  <th scope="col">BPM</th>
                  <th scope="col">Key</th>
                  <th scope="col">Match</th>
                </tr>
              </thead>
              <tbody>
                {segments.map((seg, i) => {
                  const on = i === sel;
                  const matched = seg.matchConfidence >= MATCH_THRESHOLD;
                  return (
                    <tr key={i} className={on ? 'is-on' : undefined} onClick={() => setSel(i)}>
                      <td>
                        <button type="button" className="row-btn" aria-label={`Select track ${i + 1}`} aria-pressed={on}>
                          {String(i + 1).padStart(2, '0')}
                        </button>
                      </td>
                      <td className="mono muted">{formatTime(seg.startMin)}</td>
                      <td style={{ fontWeight: 500 }}>{trackName(seg)}</td>
                      <td className="mono">{seg.bpm || '—'}</td>
                      <td style={{ fontWeight: 700 }}>{seg.camelotKey}</td>
                      <td className={`mono ${matched ? '' : 'muted'}`}>
                        {matched ? `${Math.round(seg.matchConfidence * 100)}%` : 'No match'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        </div>
      </main>

      {toast && (
        <div role="status" className="toast">
          {toast}
        </div>
      )}
    </>
  );
}

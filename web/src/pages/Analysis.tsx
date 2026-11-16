import { useEffect, useMemo, useState } from 'react';
import { Nav } from '../components/Nav';
import { Link } from 'react-router-dom';
import {
  BLEND_HALF_MIN,
  MATCH_THRESHOLD,
  SAMPLE_DURATION_MIN as D,
  formatTime,
  pct,
  sampleBars,
  sampleCuts,
  sampleEnergy,
  sampleSegments as segments,
  trackName,
} from '../lib/sample';

const WAVE = sampleBars(240);
const TICKS = [0, 10, 20, 30, 40, 50, 60];

// Energy curve as SVG points (0–1000 × 0–100) and a matching clip-path polygon.
const ENERGY = (() => {
  const pts: string[] = [];
  const clip: string[] = ['0% 100%'];
  const n = 160;
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const y = 100 - sampleEnergy(t) * 92;
    pts.push(`${(t * 1000).toFixed(1)},${y.toFixed(1)}`);
    clip.push(`${(t * 100).toFixed(2)}% ${y.toFixed(1)}%`);
  }
  clip.push('100% 100%');
  return { points: pts.join(' '), clip: `polygon(${clip.join(', ')})` };
})();

// BPM as a stepped line, 120–130 BPM mapped to the lane height.
const yBpm = (bpm: number) => (90 - ((bpm - 120) / 10) * 80).toFixed(1);
const BPM_POINTS = segments
  .map((s) => `${((s.startMin / D) * 1000).toFixed(1)},${yBpm(s.bpm)} ${((s.endMin / D) * 1000).toFixed(1)},${yBpm(s.bpm)}`)
  .join(' ');

const identified = segments.filter((s) => s.matchConfidence >= MATCH_THRESHOLD).length;
const bpms = segments.map((s) => s.bpm);

/** Grey tint per Camelot number, so neighbouring keys read as neighbouring tones. */
function keyTint(key: string): string {
  const n = parseInt(key, 10) % 12;
  return `rgba(14, 14, 14, ${(0.06 + (n / 12) * 0.2).toFixed(3)})`;
}

function tracklistText(): string {
  return segments.map((s) => `${formatTime(s.startMin)}  ${trackName(s)}`).join('\n');
}

export function Analysis() {
  const [sel, setSel] = useState(4);
  const [toast, setToast] = useState<string | null>(null);
  const s = segments[sel];

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 1800);
    return () => window.clearTimeout(t);
  }, [toast]);

  const waveColors = useMemo(
    () =>
      WAVE.map((_, i) => {
        const m = (i / (WAVE.length - 1)) * D;
        return m >= s.startMin && m < s.endMin ? 'var(--accent)' : 'var(--ink)';
      }),
    [s],
  );

  async function copy(text: string, message: string) {
    try {
      await navigator.clipboard.writeText(text);
      setToast(message);
    } catch {
      setToast('Couldn’t reach the clipboard');
    }
  }

  const ok = s.matchConfidence >= MATCH_THRESHOLD;

  return (
    <>
      <Nav>
        <Link to="/#demo">Demo sets</Link>
        <Link to="/#upload">Analyze a mix</Link>
      </Nav>

      <main className="wrap page" style={{ paddingTop: 56, gap: 40 }}>
        <div className="set-head">
          <div>
            <span className="mono-label muted" style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              Set / [id] <span className="pill">Sample data</span>
            </span>
            <h1 className="set-title">
              [Set title], <span className="it">[venue]</span>
            </h1>
          </div>
          <div className="set-actions">
            <button type="button" className="play-btn" aria-label="Play set">
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
                <path d="M4 2.5v11l9-5.5z" fill="var(--ink)" />
              </svg>
            </button>
            <button type="button" className="btn" onClick={() => copy(tracklistText(), 'Tracklist copied')}>
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
              {Math.min(...bpms)}–{Math.max(...bpms)}
              <small> BPM</small>
            </dd>
          </div>
          <div>
            <dt>Key path</dt>
            <dd>8A → 1A → 8A</dd>
          </div>
        </dl>

        <section aria-label="Timeline" className="timeline-scroll">
          <div className="timeline">
            <div aria-hidden="true" className="lane-labels">
              <span style={{ height: 28 }} />
              <span style={{ height: 80, borderTopColor: 'var(--ink)' }}>Energy</span>
              <span style={{ height: 112 }}>Wave</span>
              <span style={{ height: 72 }}>Tracks</span>
              <span style={{ height: 72, flexDirection: 'column', alignItems: 'flex-start', justifyContent: 'center', gap: 4, borderBottom: '1px solid var(--ink)' }}>
                BPM<small>120–130</small>
              </span>
            </div>

            <div className="lanes">
              <div aria-hidden="true" className="lane lane-axis">
                {TICKS.map((m) => (
                  <span key={m} style={{ left: `${pct(m)}%` }}>
                    {m}:00
                  </span>
                ))}
              </div>

              <div aria-hidden="true" className="lane lane-energy">
                <div className="energy-fill" style={{ clipPath: ENERGY.clip }} />
                <svg viewBox="0 0 1000 100" preserveAspectRatio="none">
                  <polyline points={ENERGY.points} fill="none" stroke="var(--ink)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
                </svg>
              </div>

              <div aria-hidden="true" className="lane lane-wave wave">
                {WAVE.map((h, i) => (
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
                    style={{ left: `${pct(seg.startMin)}%`, width: `${pct(seg.endMin - seg.startMin)}%`, background: keyTint(seg.camelotKey) }}
                  >
                    <span>{String(i + 1).padStart(2, '0')}</span>
                    <strong>{seg.camelotKey}</strong>
                  </button>
                ))}
                {sampleCuts.map((c) => (
                  <div
                    key={c}
                    aria-hidden="true"
                    className="blend"
                    style={{ left: `${pct(c - BLEND_HALF_MIN)}%`, width: `${pct(BLEND_HALF_MIN * 2)}%` }}
                  />
                ))}
              </div>

              <div aria-hidden="true" className="lane lane-bpm">
                <svg viewBox="0 0 1000 100" preserveAspectRatio="none">
                  <polyline points={BPM_POINTS} fill="none" stroke="var(--ink)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
                </svg>
              </div>

              <div aria-hidden="true" className="playhead" style={{ top: 6, bottom: 0, left: `${pct(s.startMin)}%` }} />
              <span aria-hidden="true" className="playhead-tag" style={{ top: 0, left: `${pct(s.startMin)}%`, fontSize: 10, padding: '2px 6px' }}>
                {formatTime(s.startMin)}
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
                <dd>{s.bpm} BPM</dd>
              </div>
              <div>
                <dt>Blend in</dt>
                <dd>
                  {sel === 0
                    ? '—'
                    : `${formatTime(s.startMin - BLEND_HALF_MIN)}–${formatTime(s.startMin + BLEND_HALF_MIN)}`}
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
            <button type="button" className="btn btn-light btn-sm" style={{ alignSelf: 'flex-start' }}>
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
                      <td className="mono">{seg.bpm}</td>
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

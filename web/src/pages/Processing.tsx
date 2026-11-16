import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Nav } from '../components/Nav';
import { formatTime, SAMPLE_DURATION_MIN, sampleBars } from '../lib/sample';

// Each stage ends at this overall percentage.
const STAGES: [label: string, endsAt: number][] = [
  ['Decode & resample', 10],
  ['Tempo over time', 28],
  ['Key over time', 46],
  ['Energy curve', 62],
  ['Transition detection', 82],
  ['Fingerprint lookup', 100],
];

const BARS = sampleBars(200);

interface UploadState {
  fileName?: string;
  size?: number;
}

export function Processing() {
  const navigate = useNavigate();
  const upload = (useLocation().state ?? {}) as UploadState;
  const [progress, setProgress] = useState(0);

  // Simulated progress until the API streams real events from /sets/{id}/events.
  useEffect(() => {
    const id = window.setInterval(() => {
      setProgress((p) => Math.min(100, p + 0.6 + Math.random() * 0.8));
    }, 120);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (progress < 100) return;
    const t = window.setTimeout(() => navigate('/sets/demo-01'), 700);
    return () => window.clearTimeout(t);
  }, [progress, navigate]);

  const pctInt = Math.floor(progress);
  const runningIndex = STAGES.findIndex(([, end]) => progress < end);
  const sizeMb = upload.size ? `${Math.round(upload.size / 1024 / 1024)} MB` : '[size] MB';

  const stages = useMemo(
    () =>
      STAGES.map(([label], i) => ({
        label,
        state: runningIndex === -1 || i < runningIndex ? 'done' : i === runningIndex ? 'running' : 'queued',
      })),
    [runningIndex],
  );

  return (
    <>
      <Nav>
        <span className="muted">Job / [set-id]</span>
      </Nav>
      <main className="wrap page">
        <div className="proc-head">
          <div>
            <span className="mono-label muted">( Analyzing )</span>
            <h1 className="proc-file">{upload.fileName ?? '[set-file-name].wav'}</h1>
            <span className="mono muted" style={{ fontSize: 13 }}>
              {sizeMb} · 22,050 Hz mono
            </span>
          </div>
          <p className="proc-pct" role="status" aria-live="polite" aria-label={`${pctInt} percent complete`}>
            <b>{pctInt}</b>
            <span className="it">%</span>
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div aria-hidden="true" className="proc-wave">
            <div className="wave">
              {BARS.map((h, i) => (
                <i key={i} className={i / (BARS.length - 1) > progress / 100 ? 'is-pending' : undefined} style={{ height: `${h}%` }} />
              ))}
            </div>
            <div className="playhead" style={{ top: -10, bottom: -10, left: `${progress}%` }} />
            <span className="playhead-tag" style={{ top: -32, left: `${progress}%` }}>
              {formatTime((progress / 100) * SAMPLE_DURATION_MIN)}
            </span>
          </div>
          <div className="mono muted" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span>00:00</span>
            <span>[duration]</span>
          </div>
        </div>

        <div className="split">
          <div className="split-aside" style={{ gap: 14 }}>
            <span className="mono-label muted">Pipeline</span>
            <p className="lede" style={{ maxWidth: 340 }}>
              Results open automatically when the job finishes. It’s safe to close this tab — your set will be waiting
              at its own link.
            </p>
            <Link to="/sets/demo-01" className="btn btn-sm" style={{ alignSelf: 'flex-start' }}>
              Skip to results
            </Link>
          </div>
          <ol className="stages">
            {stages.map((s, i) => (
              <li key={s.label} className={`is-${s.state}`}>
                <span className="mono muted" style={{ fontSize: 12 }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span>{s.label}</span>
                <span className="mono-label status">
                  {s.state === 'running' && <span aria-hidden="true" className="status-dot" />}
                  {s.state === 'done' ? 'Done' : s.state === 'running' ? 'Running' : 'Queued'}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </main>
    </>
  );
}

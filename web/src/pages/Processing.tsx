import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Nav } from '../components/Nav';
import { eventsUrl } from '../lib/api';
import { formatTime, SAMPLE_DURATION_MIN, sampleBars } from '../lib/sample';

// Each stage ends at this overall percentage; thresholds mirror the worker pipeline.
const STAGES: [label: string, endsAt: number][] = [
  ['Download from storage', 2],
  ['Decode & resample', 20],
  ['Tempo over time', 40],
  ['Key over time', 55],
  ['Transition detection', 85],
  ['Energy & waveform', 100],
];

const BARS = sampleBars(200);

interface UploadState {
  setId?: string;
  fileName?: string;
  size?: number;
}

export function Processing() {
  const navigate = useNavigate();
  const upload = (useLocation().state ?? {}) as UploadState;
  const [progress, setProgress] = useState(0);
  const [failed, setFailed] = useState<string | null>(null);

  // Real progress over SSE when a set id is present; simulated sweep otherwise
  // (direct visits to /processing keep working as a design preview).
  useEffect(() => {
    if (!upload.setId) {
      const id = window.setInterval(() => {
        setProgress((p) => Math.min(100, p + 0.6 + Math.random() * 0.8));
      }, 120);
      return () => window.clearInterval(id);
    }
    const es = new EventSource(eventsUrl(upload.setId));
    es.onmessage = (e) => {
      const d = JSON.parse(e.data) as { status: string; progress: number; error: string | null };
      if (d.status === 'busy') return; // server at stream capacity; EventSource will reconnect
      setProgress(Math.round((d.progress ?? 0) * 100));
      if (d.status === 'done') {
        es.close();
        navigate(`/sets/${upload.setId}`);
      } else if (d.status === 'failed') {
        es.close();
        setFailed(d.error ?? 'Analysis failed.');
      }
    };
    es.onerror = () => {
      /* EventSource retries on its own; surface nothing unless the job fails */
    };
    return () => es.close();
  }, [upload.setId, navigate]);

  useEffect(() => {
    if (upload.setId || progress < 100) return;
    const t = window.setTimeout(() => navigate('/sets/demo-01'), 700);
    return () => window.clearTimeout(t);
  }, [progress, navigate, upload.setId]);

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
        <span className="muted">Job / {upload.setId ?? '[set-id]'}</span>
      </Nav>
      <main className="wrap page">
        <div className="proc-head">
          <div>
            <span className="mono-label muted">( {failed ? 'Failed' : 'Analyzing'} )</span>
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

        {failed ? (
          <div role="alert" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <p className="lede">Something went wrong while analyzing this set.</p>
            <pre className="mono muted" style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
              {failed}
            </pre>
            <Link to="/#upload" className="btn" style={{ alignSelf: 'flex-start' }}>
              Try another file
            </Link>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div aria-hidden="true" className="proc-wave">
                <div className="wave">
                  {BARS.map((h, i) => (
                    <i
                      key={i}
                      className={i / (BARS.length - 1) > progress / 100 ? 'is-pending' : undefined}
                      style={{ height: `${h}%` }}
                    />
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
                  Results open automatically when the job finishes. It’s safe to close this tab — your set will be
                  waiting at its own link.
                </p>
                {upload.setId && (
                  <Link to={`/sets/${upload.setId}`} className="btn btn-sm" style={{ alignSelf: 'flex-start' }}>
                    Open set page
                  </Link>
                )}
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
          </>
        )}
      </main>
    </>
  );
}

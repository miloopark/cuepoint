import { useEffect, useRef, useState, type CSSProperties, type DragEvent, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Nav } from '../components/Nav';
import { LogoMark } from '../components/Logo';
import { createSet, requestUpload, uploadFile } from '../lib/api';
import { BLEND_HALF_MIN, SAMPLE_DURATION_MIN, pct, sampleBars, sampleCuts } from '../lib/sample';

const MAX_BYTES = 200 * 1024 * 1024;
const BAND_BARS = sampleBars(180);
const TICKS = [0, 10, 20, 30, 40, 50, 60];

const DEMOS = [
  { id: 'demo-01', meta: '01 / 62:12 / 12 tracks', title: '[Demo set title]' },
  { id: 'demo-02', meta: '02 / [length] / [tracks]', title: '[Demo set title]' },
  { id: 'demo-03', meta: '03 / [length] / [tracks]', title: '[Demo set title]' },
];

const EVALUATION = [
  { read: 'Transitions', metric: 'Recall within ±15 s', target: '≥ 80%', measured: '[—]' },
  { read: 'Tempo', metric: 'Segments within ±2 BPM', target: '[—]', measured: '[—]' },
  { read: 'Key', metric: 'Exact / Camelot-compatible', target: '[—]', measured: '[—]' },
  { read: 'Identity', metric: 'Top-1 accuracy, 500+ track library', target: '≥ 70%', measured: '[—]' },
  { read: 'Speed', metric: 'Processing time per hour of audio', target: '< 3 min', measured: '[—]' },
];

const ARCH = [
  { k: 'A →', name: 'Browser', sub: 'React · wavesurfer' },
  { k: 'B →', name: 'Object storage', sub: 'R2 · presigned' },
  { k: 'C →', name: 'API', sub: 'FastAPI · SSE' },
  { k: 'D →', name: 'Queue', sub: 'Redis · RQ' },
  { k: 'E →', name: 'Worker', sub: 'librosa · numpy', accent: true },
  { k: 'F', name: 'Postgres', sub: 'features · hashes' },
];

export function Landing() {
  const { hash } = useLocation();

  // Scroll to #section when arriving from another page (e.g. /#demo).
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash]);

  return (
    <>
      <Nav>
        <a href="#demo">Demo sets</a>
        <a href="#how">How it works</a>
        <a href="#eval">Evaluation</a>
        <a href="#stack">Architecture</a>
      </Nav>
      <div className="wrap">
        <div className="strip mono-label">
          <span>No. 01 — Audio analysis tool</span>
          <span>Tempo / Key / Energy / Transitions / Identity</span>
          <span>Edition 2026</span>
        </div>
      </div>

      <main>
        <Hero />
        <WaveBand />
        <Upload />
        <Method />
        <Evaluation />
        <Architecture />
      </main>

      <footer className="footer">
        <div className="wrap footer-inner">
          <p className="footer-word">
            Cue<span className="it">point</span>
          </p>
          <div className="footer-row mono-label">
            <span>Cuepoint — 2026</span>
            <span className="footer-links">
              <a href="#">Write-up ↗</a>
              <a href="#">Portfolio ↗</a>
            </span>
          </div>
        </div>
      </footer>
    </>
  );
}

function Hero() {
  return (
    <section id="top" className="wrap hero">
      <div className="hero-copy">
        <p className="mono-label muted">( Upload a mix — get the timeline )</p>
        <h1 className="hero-title">
          Every set
          <br />
          has a <span className="it">shape.</span>
        </h1>
        <div className="hero-row">
          <p className="hero-text">
            Drop in a recorded DJ mix. Get back where every track starts and ends, tempo and key over time, the energy
            arc of the night, and the name of each track — identified by a fingerprint engine built from scratch.
          </p>
          <div className="hero-actions">
            <a href="#upload" className="btn btn-solid">
              Analyze a mix <span aria-hidden="true">→</span>
            </a>
            <a href="#demo" className="btn">
              Open a demo set
            </a>
          </div>
        </div>
      </div>
      <div className="hero-mark">
        <LogoMark />
      </div>
    </section>
  );
}

function WaveBand() {
  return (
    <section aria-label="Example timeline" className="band">
      <div className="wrap band-inner">
        <div className="band-meta mono-label">
          <span>Fig. 1 — A 62-minute mix, {sampleCuts.length} transition windows</span>
          <span>
            <span aria-hidden="true" className="hatch-key" />
            Blend window
          </span>
        </div>
        <div aria-hidden="true" className="wave wave-band">
          {sampleCuts.map((c) => (
            <div
              key={c}
              className="blend"
              style={{ left: `${pct(c - BLEND_HALF_MIN)}%`, width: `${pct(BLEND_HALF_MIN * 2)}%` }}
            />
          ))}
          {BAND_BARS.map((h, i) => (
            <i key={i} style={{ height: `${h}%` }} />
          ))}
        </div>
        <div aria-hidden="true" className="ticks">
          {TICKS.map((m) => (
            <span key={m} style={{ left: `${pct(m, SAMPLE_DURATION_MIN)}%` }}>
              {m}:00
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function Upload() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);

  async function accept(file: File | undefined) {
    if (!file || uploadPct !== null) return;
    if (!file.type.startsWith('audio/') && !/\.(mp3|wav|flac|aiff?|m4a)$/i.test(file.name)) {
      setError('That doesn’t look like an audio file.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('Files are capped at 200 MB.');
      return;
    }
    setError(null);
    setUploadPct(0);
    try {
      const { key, upload_url } = await requestUpload(file.name, file.type || 'audio/mpeg');
      await uploadFile(upload_url, file, setUploadPct);
      const title = file.name.replace(/\.[^.]+$/, '');
      const set = await createSet(title, key);
      navigate('/processing', { state: { setId: set.id, fileName: file.name, size: file.size } });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed — is the API running?');
      setUploadPct(null);
    }
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setOver(false);
    accept(e.dataTransfer.files[0]);
  }

  return (
    <section id="upload" className="wrap split section-inner">
      <div className="split-aside">
        <span className="mono-label muted">§ 01 — Start</span>
        <h2 className="h2">
          Bring your <span className="it">own</span> recording.
        </h2>
        <p className="lede">
          Files go straight to storage, never through the server. Audio is deleted after analysis — only features and
          waveform peaks are kept.
        </p>
      </div>
      <div className="split-main">
        <label
          htmlFor="mix"
          className={`drop halftone ${over ? 'is-over' : ''}`}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <span>
            <span className="drop-title">
              {uploadPct === null ? 'Drop a mix here' : `Uploading… ${uploadPct}%`}
            </span>
            <span className="drop-hint">MP3 · WAV · FLAC · AIFF — up to 200 MB / 2 hours</span>
          </span>
          <span className="btn btn-solid btn-sm drop-btn">{uploadPct === null ? 'Choose file' : 'Uploading'}</span>
          <input
            ref={inputRef}
            id="mix"
            type="file"
            accept="audio/*"
            onChange={(e) => accept(e.target.files?.[0])}
          />
        </label>
        {error && (
          <p role="alert" className="drop-error">
            {error}
          </p>
        )}

        <div id="demo" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <span className="mono-label muted">Or open a demo set</span>
          <div className="demo-grid">
            {DEMOS.map((d) => (
              <Link key={d.id} to={`/sets/${d.id}`} className="demo-card">
                <span className="mono">{d.meta}</span>
                <strong>
                  {d.title} <span aria-hidden="true">↗</span>
                </strong>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Method() {
  return (
    <section id="how" className="section">
      <div className="wrap section-inner" style={{ display: 'flex', flexDirection: 'column', gap: 56 }}>
        <div className="section-head">
          <div>
            <span className="mono-label muted">§ 02 — Method</span>
            <h2 className="h2 h2-xl">
              Five reads of
              <br />
              one <span className="it">recording.</span>
            </h2>
          </div>
          <p className="lede" style={{ maxWidth: 360 }}>
            One decode — 22,050 Hz mono — then overlapping windows. Each feature starts with librosa and is replaced,
            where it matters, by hand-written DSP.
          </p>
        </div>
        <ol className="steps">
          <Step n="01" title="Tempo" glyph={<TempoGlyph />}>
            Onset envelope, autocorrelation in 30 s windows. Half- and double-time errors fold toward the set’s median.
          </Step>
          <Step n="02" title="Key" glyph={<KeyGlyph />}>
            Chroma matched against 24 Krumhansl–Schmuckler profiles, written in Camelot — the way DJs think.
          </Step>
          <Step n="03" title="Energy" glyph={<EnergyGlyph />}>
            Loudness, brightness and onset density blended into one 0–1 curve: the builds, the drops, the arc.
          </Step>
          <Step n="04" title="Transitions" glyph={<TransitionGlyph />}>
            A checkerboard kernel slides along the self-similarity matrix. Blends are reported as windows, not points.
          </Step>
          <Step n="05" title="Identity" glyph={<IdentityGlyph />}>
            Spectral peaks paired into hashes; a true match is one tall spike in the time-offset histogram.
          </Step>
        </ol>
      </div>
    </section>
  );
}

function Step({ n, title, glyph, children }: { n: string; title: string; glyph: ReactNode; children: ReactNode }) {
  return (
    <li>
      <span className="mono muted" style={{ fontSize: 12 }}>
        {n}
      </span>
      <div aria-hidden="true" className="glyph">
        {glyph}
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </li>
  );
}

const bar = (h: string, accent = false, extra: CSSProperties = {}) => ({
  height: h,
  background: accent ? 'var(--accent)' : 'var(--ink)',
  ...extra,
});

function TempoGlyph() {
  const hs = ['100%', '30%', '55%', '30%', '100%', '30%', '55%', '30%', '100%'];
  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'flex-end', gap: 6 }}>
      {hs.map((h, i) => (
        <div key={i} style={bar(h, i === hs.length - 1, { width: 3 })} />
      ))}
    </div>
  );
}

function KeyGlyph() {
  const hs = ['70%', '12%', '30%', '18%', '55%', '22%', '14%', '100%', '16%', '40%', '12%', '26%'];
  return (
    <div style={{ height: '100%', width: '100%', display: 'grid', gridTemplateColumns: 'repeat(12, minmax(0, 1fr))', gap: 3, alignItems: 'end' }}>
      {hs.map((h, i) => (
        <div key={i} style={bar(h, i === 7)} />
      ))}
    </div>
  );
}

function EnergyGlyph() {
  return (
    <svg viewBox="0 0 200 72" preserveAspectRatio="none" style={{ width: '100%', height: 72 }}>
      <polyline
        points="0,62 30,55 55,58 85,34 105,40 130,14 150,22 170,8 200,30"
        fill="none"
        stroke="var(--ink)"
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={170} cy={8} r={4} fill="var(--accent)" />
    </svg>
  );
}

function TransitionGlyph() {
  return (
    <div style={{ height: 72, width: 72, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', border: '1px solid var(--ink)' }}>
      <div style={{ backgroundImage: 'radial-gradient(var(--ink) 1px, transparent 1.4px)', backgroundSize: '5px 5px' }} />
      <div />
      <div />
      <div style={{ background: 'var(--accent)' }} />
    </div>
  );
}

function IdentityGlyph() {
  const hs = ['8%', '14%', '6%', '100%', '18%', '10%', '7%', '12%'];
  return (
    <div style={{ height: '100%', width: '100%', display: 'flex', alignItems: 'flex-end', gap: 4 }}>
      {hs.map((h, i) => (
        <div key={i} style={bar(h, i === 3, { flex: 1 })} />
      ))}
    </div>
  );
}

function Evaluation() {
  return (
    <section id="eval" className="section halftone">
      <div className="wrap split section-inner">
        <div className="split-aside">
          <span className="mono-label muted">§ 03 — Evaluation</span>
          <h2 className="h2">
            Measured, <span className="it">honestly.</span>
          </h2>
          <p className="lede" style={{ maxWidth: 360 }}>
            Scored against hand-labeled sets and DJ-software exports. Numbers update from the evaluation harness on
            every merge.
          </p>
        </div>
        <div className="split-main">
          <div className="table-box">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Read</th>
                  <th scope="col">Metric</th>
                  <th scope="col">Target</th>
                  <th scope="col">Measured</th>
                </tr>
              </thead>
              <tbody>
                {EVALUATION.map((r) => (
                  <tr key={r.read}>
                    <th scope="row">{r.read}</th>
                    <td>{r.metric}</td>
                    <td className="mono">{r.target}</td>
                    <td className="mono muted">{r.measured}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}

function Architecture() {
  return (
    <section id="stack" className="section">
      <div className="wrap section-inner" style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
        <div className="section-head">
          <div>
            <span className="mono-label muted">§ 04 — Architecture</span>
            <h2 className="h2">
              The API never <span className="it">touches audio.</span>
            </h2>
          </div>
          <p className="lede" style={{ maxWidth: 360 }}>
            Presigned uploads, a job queue with live progress, a worker that does every bit of DSP.
          </p>
        </div>
        <div className="arch">
          {ARCH.map((a) => (
            <div key={a.name} className={a.accent ? 'is-accent' : undefined}>
              <span className="mono" style={{ fontSize: 11 }}>
                {a.k}
              </span>
              <strong>{a.name}</strong>
              <span className="mono">{a.sub}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

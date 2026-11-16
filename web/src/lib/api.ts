// Client for the Cuepoint API (FastAPI, localhost:8000 in dev).

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

export interface SetStatus {
  id: string;
  title: string;
  status: 'queued' | 'processing' | 'done' | 'failed';
  progress: number; // 0–1
  stage: string | null;
  duration_s: number | null;
  error: string | null;
}

export interface ApiSegment {
  start_s: number;
  end_s: number;
  transition_start_s: number | null;
  transition_end_s: number | null;
  bpm: number | null;
  camelot_key: string | null;
  key_confidence: number | null;
  track_id: number | null;
  match_confidence: number | null;
  artist: string | null;
  title: string | null;
}

export interface AnalysisData {
  id: string;
  title: string;
  duration_s: number;
  segments: ApiSegment[];
  features: {
    energy_times: number[];
    energy: number[];
    bpm_times: number[];
    bpm: number[];
    keys: string[];
    key_times: number[];
    key_confidences: number[];
  };
  transitions: { start_s: number; end_s: number; peak_s: number; strength: number }[];
}

async function asJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = ((await r.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

export async function requestUpload(filename: string, contentType: string) {
  return asJson<{ key: string; upload_url: string }>(
    await fetch(`${API_URL}/uploads`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ filename, content_type: contentType }),
    }),
  );
}

/** PUT straight to object storage. XHR instead of fetch for upload progress. */
export function uploadFile(url: string, file: File, onProgress: (pct: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    xhr.setRequestHeader('content-type', file.type || 'audio/mpeg');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`upload failed (${xhr.status})`));
    xhr.onerror = () => reject(new Error('upload failed — is the storage service running?'));
    xhr.send(file);
  });
}

export async function createSet(title: string, audioKey: string) {
  const set = await asJson<SetStatus & { edit_token: string }>(
    await fetch(`${API_URL}/sets`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ title, audio_key: audioKey }),
    }),
  );
  // The edit capability is only issued once, at creation — keep it client-side.
  try {
    localStorage.setItem(`cuepoint-edit-${set.id}`, set.edit_token);
  } catch {
    /* private mode — import will be unavailable */
  }
  return set;
}

export function editToken(id: string): string | null {
  try {
    return localStorage.getItem(`cuepoint-edit-${id}`);
  } catch {
    return null;
  }
}

export async function getAnalysis(id: string) {
  return asJson<AnalysisData>(await fetch(`${API_URL}/sets/${id}/analysis`));
}

export async function getWaveform(id: string) {
  return asJson<{ waveform: number[]; duration_s: number }>(await fetch(`${API_URL}/sets/${id}/waveform`));
}

export async function importTracklist(id: string, text: string, token: string) {
  return asJson<{ named: number; segments: ApiSegment[] }>(
    await fetch(`${API_URL}/sets/${id}/tracklist`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text, edit_token: token }),
    }),
  );
}

export const eventsUrl = (id: string) => `${API_URL}/sets/${id}/events`;
export const audioUrl = (id: string) => `${API_URL}/sets/${id}/audio`;

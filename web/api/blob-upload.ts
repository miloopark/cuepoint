// Mints client-upload tokens for Vercel Blob: the browser sends audio straight
// to the store, this function only authorizes it (audio types, 300 MB cap).
import { handleUpload, type HandleUploadBody } from '@vercel/blob/client';

const AUDIO_TYPES = [
  'audio/mpeg',
  'audio/mp3',
  'audio/wav',
  'audio/x-wav',
  'audio/flac',
  'audio/aiff',
  'audio/x-aiff',
  'audio/mp4',
  'audio/x-m4a',
  'audio/aac',
];

const AUDIO_EXT = /\.(mp3|wav|flac|aiff?|m4a|aac|ogg)$/i;

export async function POST(request: Request): Promise<Response> {
  const body = (await request.json()) as HandleUploadBody;
  try {
    const result = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname) => {
        // Flat, short, audio-extension filenames only — no nested paths or
        // attacker-chosen directory structure in the store.
        if (pathname.length > 120 || pathname.includes('/') || !AUDIO_EXT.test(pathname)) {
          throw new Error('invalid audio filename');
        }
        return {
          allowedContentTypes: AUDIO_TYPES,
          maximumSizeInBytes: 300 * 1024 * 1024,
          addRandomSuffix: true,
          validUntil: Date.now() + 10 * 60 * 1000, // token usable for 10 min only
        };
      },
      onUploadCompleted: async () => {
        // Registration happens when the browser POSTs /sets with the blob URL.
      },
    });
    return Response.json(result);
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}

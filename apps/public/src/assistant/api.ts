// The Assistant's two calls that openapi-fetch can't make: a streamed chat
// (Server-Sent Events over a POST, read off the response body) and a recorded
// question uploaded as multipart. Both carry the token like every other call,
// and a 401 drops it, as the shared middleware does.
import type { components } from '../api/schema'
import { tokenStore } from '../auth/token'

export type ChatContext = components['schemas']['AssistantContext']
export type ChatRequest = components['schemas']['AssistantChat']

export type ChatEvent =
  | { type: 'status'; text: string }
  | { type: 'paragraph'; id: number; text: string }
  | { type: 'audio'; id: number; audio: string }
  | { type: 'check'; id: number; numbers: string[] }
  | { type: 'error'; text: string }
  | { type: 'done' }

export class AssistantError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const BASE = import.meta.env.VITE_API_URL

function auth(): Record<string, string> {
  const token = tokenStore.get()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function failure(res: Response): Promise<never> {
  if (res.status === 401 && tokenStore.get()) tokenStore.set(null)
  let detail = `HTTP ${res.status}`
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') detail = body.detail
  } catch {
    // Not JSON: the status says enough.
  }
  throw new AssistantError(res.status, detail)
}

/** POST one question and hand each event to `onEvent` as its frame arrives. */
export async function streamChat(body: ChatRequest, onEvent: (event: ChatEvent) => void, signal: AbortSignal) {
  const res = await fetch(`${BASE}/assistant/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth() },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) return failure(res)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const frames = buf.split('\n\n')
    buf = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(6)) as ChatEvent)
      } catch {
        // A malformed frame costs that frame, not the answer.
      }
    }
  }
}

/** A recorded question as text (ElevenLabs Scribe on the server). */
export async function transcribe(audio: Blob, signal?: AbortSignal): Promise<string> {
  const ext = audio.type.includes('mp4') ? 'mp4' : audio.type.includes('ogg') ? 'ogg' : 'webm'
  const form = new FormData()
  form.append('audio', audio, `question.${ext}`)
  const res = await fetch(`${BASE}/assistant/transcribe`, { method: 'POST', headers: auth(), body: form, signal })
  if (!res.ok) return failure(res)
  const body = (await res.json()) as components['schemas']['AssistantTranscript']
  return body.text
}

/** base64 MP3 from an `audio` event, as a URL an <audio> element can play. */
export function audioUrl(b64: string): string {
  const bytes = atob(b64)
  const buf = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i)
  return URL.createObjectURL(new Blob([buf], { type: 'audio/mpeg' }))
}

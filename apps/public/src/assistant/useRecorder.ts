// A spoken question: tap to start, tap to stop (or cancel). While recording it
// exposes the elapsed time and a rolling strip of input levels for the
// waveform. The recording is handed over as one Blob for the server to
// transcribe; the browser's own speech recognition is not used, since it
// barely knows Mongolian and doesn't exist in Firefox.
import { useCallback, useEffect, useRef, useState } from 'react'

export type RecorderState = 'idle' | 'starting' | 'recording'
export type RecorderError = 'denied' | 'unsupported' | 'failed' | null

const MAX_SECONDS = 60
const MIN_SECONDS = 0.6
export const BARS = 32

function pickMime(): string {
  const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  return options.find((m) => MediaRecorder.isTypeSupported?.(m)) ?? ''
}

export function useRecorder(onRecorded: (audio: Blob) => void) {
  const [state, setState] = useState<RecorderState>('idle')
  const [error, setError] = useState<RecorderError>(null)
  const [elapsed, setElapsed] = useState(0)
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0))

  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const context = useRef<AudioContext | null>(null)
  const frame = useRef(0)
  const startedAt = useRef(0)
  const keep = useRef(true)
  const handler = useRef(onRecorded)
  useEffect(() => {
    handler.current = onRecorded
  }, [onRecorded])

  const supported =
    typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

  const cleanup = useCallback(() => {
    cancelAnimationFrame(frame.current)
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    context.current?.close().catch(() => {})
    context.current = null
    recorder.current = null
    setLevels(Array(BARS).fill(0))
    setElapsed(0)
    setState('idle')
  }, [])

  const finish = useCallback((send: boolean) => {
    keep.current = send
    const rec = recorder.current
    if (rec && rec.state !== 'inactive') rec.stop()
  }, [])

  const start = useCallback(async () => {
    if (!supported) {
      setError('unsupported')
      return
    }
    if (recorder.current) return
    setError(null)
    setState('starting')
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      stream.current = media
      const mime = pickMime()
      const rec = new MediaRecorder(media, mime ? { mimeType: mime } : undefined)
      const chunks: Blob[] = []
      rec.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data)
      }
      rec.onstop = () => {
        const seconds = (performance.now() - startedAt.current) / 1000
        const blob = new Blob(chunks, { type: rec.mimeType || mime || 'audio/webm' })
        cleanup()
        if (keep.current && seconds >= MIN_SECONDS && blob.size) handler.current(blob)
      }
      recorder.current = rec

      // Input levels for the waveform, sampled every animation frame.
      const ctx = new AudioContext()
      context.current = ctx
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 512
      ctx.createMediaStreamSource(media).connect(analyser)
      const data = new Uint8Array(analyser.fftSize)
      let last = 0
      const tick = (now: number) => {
        frame.current = requestAnimationFrame(tick)
        const secs = (now - startedAt.current) / 1000
        if (secs >= MAX_SECONDS) finish(true)
        if (now - last < 60) return
        last = now
        analyser.getByteTimeDomainData(data)
        let peak = 0
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128) / 128)
        setLevels((prev) => [...prev.slice(1), Math.min(1, peak * 2.2)])
        setElapsed(secs)
      }

      keep.current = true
      startedAt.current = performance.now()
      rec.start(250)
      setState('recording')
      frame.current = requestAnimationFrame(tick)
    } catch (exc) {
      cleanup()
      const name = exc instanceof DOMException ? exc.name : ''
      setError(name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : 'failed')
    }
  }, [supported, cleanup, finish])

  // Leaving the page mid-recording releases the microphone.
  useEffect(
    () => () => {
      keep.current = false
      if (recorder.current?.state === 'recording') recorder.current.stop()
      cleanup()
    },
    [cleanup],
  )

  return {
    supported,
    state,
    error,
    elapsed,
    levels,
    start,
    stop: () => finish(true),
    cancel: () => finish(false),
    clearError: () => setError(null),
  }
}

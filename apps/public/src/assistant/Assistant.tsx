// The Assistant (CONTEXT.md): the «Ask» button in the bottom-right corner of
// every page, and the chat it opens. Typed or spoken questions; answers stream
// in paragraph by paragraph, each spoken aloud when the voice is on. Ported
// from cstat's _assistant.html.
//
// The conversation lives only in this tab (sessionStorage), never on the
// server: every question resends the earlier turns as plain text.
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { $api } from '../api/client'
import { AssistantError, audioUrl, streamChat, transcribe, type ChatEvent } from './api'
import { suggestions, usePageContext, type PageContext } from './context'
import { Check, Close, Mic, NewChat, Pin, Play, Retry, Send, Sparkle, Speaker, SpeakerOff, StopSquare } from './icons'
import { useRecorder } from './useRecorder'
import { useSpeaker, type Speaker as SpeakerApi } from './useSpeaker'
import './assistant.css'

interface Para {
  text: string
  audio?: string
}

interface Turn {
  id: string
  role: 'user' | 'assistant'
  paras: Para[]
  steps?: string[]
  pending?: boolean
  error?: string
  stopped?: boolean
  spoken?: boolean
  /** The page a question was asked on (its label). */
  page?: string
}

type OrbState = 'idle' | 'thinking' | 'speaking' | 'listening'

const STORE = 'cs-analyze.assistant.v1'
const VOICE = 'cs-analyze.assistant.voice'
const MAX_CHARS = 2000

const uid = () => Math.random().toString(36).slice(2, 10)

function loadTurns(): Turn[] {
  try {
    const turns = JSON.parse(sessionStorage.getItem(STORE) ?? '[]')
    return Array.isArray(turns) ? turns.filter((t: Turn) => t?.id && Array.isArray(t.paras)) : []
  } catch {
    return []
  }
}

function saveTurns(turns: Turn[]) {
  try {
    // Text only: audio URLs die with the page. An answer cut off by a reload
    // comes back as stopped, with whatever it had written.
    const kept = turns.map(({ id, role, paras, error, stopped, spoken, steps, pending, page }) => ({
      id,
      role,
      page,
      paras: paras.filter(Boolean).map((p) => ({ text: p.text })),
      error,
      stopped: stopped || pending,
      spoken,
      steps,
    }))
    sessionStorage.setItem(STORE, JSON.stringify(kept))
  } catch {
    // Storage unavailable: the chat still works, it just won't survive a reload.
  }
}

function loadVoice(): boolean {
  try {
    return localStorage.getItem(VOICE) !== '0'
  } catch {
    return true
  }
}

function saveVoice(on: boolean) {
  try {
    localStorage.setItem(VOICE, on ? '1' : '0')
  } catch {
    // Not remembered; the toggle still works for this page.
  }
}

/** Earlier answered questions as plain text, oldest first: what the server is resent.
 *  Each question carries the page it was asked on, so one asked about another
 *  Fixture isn't read as about this one. The server keeps the last 12 messages. */
function historyOf(turns: Turn[]) {
  const out: { role: string; content: string; page: string }[] = []
  turns.forEach((t, i) => {
    const q = turns[i - 1]
    if (t.role !== 'assistant' || t.error || t.pending || !t.paras.length || q?.role !== 'user') return
    out.push(
      { role: 'user', content: q.paras.map((p) => p.text).join('\n\n'), page: q.page ?? '' },
      { role: 'assistant', content: t.paras.map((p) => p.text).join('\n\n'), page: q.page ?? '' },
    )
  })
  return out.slice(-12)
}

function scopeText(page: PageContext): string {
  switch (page.scope) {
    case 'fixture':
      return page.label || 'Game Plan'
    case 'team':
      return page.label || 'Баг'
    case 'match':
      return page.label || 'Тоглолт'
    default:
      return 'Ерөнхий — дурын багийн талаар'
  }
}

function greeting(page: PageContext): string {
  const tail = 'Зөвхөн parse хийсэн тоглолтын өгөгдлөөр, хэдэн map дээр үндэслэснээ хэлж хариулна.'
  switch (page.scope) {
    case 'fixture':
      return `${page.label || 'Энэ Fixture'}: map, veto, тоглогчид, H2H, төлөвлөгөөний талаар асуу. ${tail}`
    case 'team':
      return `${page.label || 'Энэ баг'}-ийн map pool, тоглогчдын үүрэг, хүчтэй сул талын талаар асуу. ${tail}`
    case 'match':
      return `${page.label || 'Энэ тоглолт'}: хоёр багийн талаар асуу. ${tail}`
    default:
      return `Дурын багийн map pool, тоглогчид, H2H, скаутын дүгнэлтийн талаар асуу. ${tail}`
  }
}

const RECORDER_ERRORS = {
  denied: 'Микрофон ашиглах зөвшөөрөл өгөөгүй байна. Браузерын хаягийн мөрний тохиргооноос зөвшөөрнө үү.',
  unsupported: 'Энэ браузер дуу бичихийг дэмжихгүй байна. Бичиж асууна уу.',
  failed: 'Микрофоныг асааж чадсангүй. Өөр програм ашиглаж байгаа эсэхийг шалгана уу.',
}

export default function Assistant() {
  const config = $api.useQuery('get', '/assistant/config', {}, { staleTime: 5 * 60_000 })
  const configured = config.data?.configured ?? false
  const voiceAvailable = config.data?.voice ?? false
  const page = usePageContext()

  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>(loadTurns)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [unread, setUnread] = useState(false)
  const [voiceOn, setVoiceOn] = useState(loadVoice)
  const speaker = useSpeaker()

  const abort = useRef<AbortController | null>(null)
  const turnsRef = useRef(turns)
  const openRef = useRef(open)
  const voiceRef = useRef(voiceOn)
  const logRef = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  useEffect(() => {
    turnsRef.current = turns
    saveTurns(turns)
  }, [turns])
  useEffect(() => {
    openRef.current = open
  }, [open])
  useEffect(() => {
    voiceRef.current = voiceOn
  }, [voiceOn])

  const patch = useCallback((id: string, fn: (t: Turn) => Turn) => {
    setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)))
  }, [])

  const ask = useCallback(
    async (text: string, spoken = false) => {
      const message = text.trim().slice(0, MAX_CHARS)
      if (!message || abort.current || !configured) return
      speaker.unlock()
      speaker.stop()
      const reply: Turn = { id: uid(), role: 'assistant', paras: [], steps: [], pending: true }
      const history = historyOf(turnsRef.current)
      setTurns((ts) => [...ts, { id: uid(), role: 'user', paras: [{ text: message }], spoken, page: page.label }, reply])
      setDraft('')
      setNotice(null)
      setBusy(true)
      pinned.current = true
      const ctrl = new AbortController()
      abort.current = ctrl

      const onEvent = (event: ChatEvent) => {
        switch (event.type) {
          case 'status':
            patch(reply.id, (t) => ({ ...t, steps: [...(t.steps ?? []), event.text] }))
            break
          case 'paragraph':
            patch(reply.id, (t) => {
              const paras = [...t.paras]
              paras[event.id] = { ...paras[event.id], text: event.text }
              return { ...t, paras }
            })
            break
          case 'audio': {
            const url = audioUrl(event.audio)
            patch(reply.id, (t) => {
              const paras = [...t.paras]
              paras[event.id] = { text: paras[event.id]?.text ?? '', audio: url }
              return { ...t, paras }
            })
            if (voiceRef.current) speaker.enqueue(`${reply.id}:${event.id}`, url)
            break
          }
          case 'error':
            patch(reply.id, (t) => ({ ...t, error: event.text }))
            break
        }
      }

      try {
        await streamChat(
          { message, history, context: page.context, voice: voiceRef.current && voiceAvailable },
          onEvent,
          ctrl.signal,
        )
      } catch (exc) {
        if (ctrl.signal.aborted) patch(reply.id, (t) => ({ ...t, stopped: true }))
        else
          patch(reply.id, (t) => ({
            ...t,
            error:
              exc instanceof AssistantError
                ? `Туслахтай холбогдож чадсангүй (${exc.message}).`
                : 'Сүлжээний алдаа: туслахтай холбогдож чадсангүй.',
          }))
      } finally {
        patch(reply.id, (t) => ({ ...t, pending: false, paras: t.paras.filter(Boolean) }))
        abort.current = null
        setBusy(false)
        if (!openRef.current) setUnread(true)
      }
    },
    [configured, voiceAvailable, page.context, patch, speaker],
  )

  const stop = useCallback(() => {
    abort.current?.abort()
    speaker.stop()
  }, [speaker])

  const onRecorded = useCallback(
    async (audio: Blob) => {
      setTranscribing(true)
      try {
        const text = await transcribe(audio)
        if (text.trim()) await ask(text, true)
        else setNotice('Юу ч сонсогдсонгүй. Микрофон руу ойртож дахин ярина уу.')
      } catch {
        setNotice('Яриаг таньж чадсангүй. Дахин оролдох эсвэл бичиж асууна уу.')
      } finally {
        setTranscribing(false)
      }
    },
    [ask],
  )
  const recorder = useRecorder(onRecorded)
  const recording = recorder.state !== 'idle'

  const shownNotice = notice ?? (recorder.error ? RECORDER_ERRORS[recorder.error] : null)

  const reset = useCallback(() => {
    stop()
    setTurns([])
    setNotice(null)
  }, [stop])

  const retry = useCallback(
    (replyId: string) => {
      const ts = turnsRef.current
      const i = ts.findIndex((t) => t.id === replyId)
      const q = ts[i - 1]
      if (!q || q.role !== 'user') return
      setTurns(ts.filter((_, j) => j !== i && j !== i - 1))
      void ask(q.paras[0]?.text ?? '', q.spoken)
    },
    [ask],
  )

  const toggleVoice = () => {
    const on = !voiceOn
    setVoiceOn(on)
    saveVoice(on)
    if (!on) speaker.stop()
  }

  // Esc cancels a recording, else closes; focus lands in the box on open.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (recording) recorder.cancel()
      else setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, recording, recorder])

  // Follow the answer as it grows, unless the User scrolled up to read.
  useEffect(() => {
    const log = logRef.current
    if (log && pinned.current) log.scrollTop = log.scrollHeight
  }, [turns, open, busy])

  const orb: OrbState = recording ? 'listening' : busy || transcribing ? 'thinking' : speaker.playing ? 'speaking' : 'idle'

  return (
    <>
      {open && (
        <section
          role="dialog"
          aria-label="AI туслах"
          className="as-panel fixed right-5 bottom-24 z-50 flex h-[min(680px,calc(100dvh-8rem))] w-[420px] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_24px_70px_rgba(0,0,0,0.55)] max-sm:inset-0 max-sm:h-auto max-sm:w-auto max-sm:rounded-none max-sm:border-0"
        >
          <header className="flex items-center gap-3 border-b border-line bg-surface-2 px-4 py-3">
            <Orb state={orb} size="h-9 w-9" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink">
                <span className="as-gradient-text">AI</span> туслах
              </p>
              <p className="flex items-center gap-1 truncate text-xs text-ink-3" title={scopeText(page)}>
                <Pin width={13} height={13} className="shrink-0" />
                <span className="truncate">{scopeText(page)}</span>
              </p>
            </div>
            {speaker.playing && (
              <button
                onClick={speaker.stop}
                className="flex items-center gap-1.5 rounded-full bg-raised px-2.5 py-1 text-xs font-medium text-ink hover:bg-line"
                title="Дуугаа зогсоох"
              >
                <Equalizer /> Зогсоох
              </button>
            )}
            {voiceAvailable && (
              <IconButton
                label={voiceOn ? 'Дуут хариулт асаалттай — унтраах' : 'Дуут хариулт унтраалттай — асаах'}
                pressed={voiceOn}
                onClick={toggleVoice}
              >
                {voiceOn ? <Speaker /> : <SpeakerOff />}
              </IconButton>
            )}
            <IconButton label="Шинэ яриа эхлэх" onClick={reset} disabled={!turns.length}>
              <NewChat />
            </IconButton>
            <IconButton label="Хаах (Esc)" onClick={() => setOpen(false)}>
              <Close />
            </IconButton>
          </header>

          <div
            ref={logRef}
            role="log"
            aria-live="polite"
            onScroll={(e) => {
              const el = e.currentTarget
              pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
            }}
            className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4"
          >
            {!turns.length ? (
              <Welcome page={page} configured={configured} loading={config.isPending} voice={voiceAvailable} onPick={ask} />
            ) : (
              turns.map((turn) =>
                turn.role === 'user' ? (
                  <UserBubble key={turn.id} turn={turn} />
                ) : (
                  <Reply key={turn.id} turn={turn} speaker={speaker} onRetry={() => retry(turn.id)} />
                ),
              )
            )}
          </div>

          <Composer
            draft={draft}
            setDraft={setDraft}
            busy={busy}
            disabled={!configured}
            transcribing={transcribing}
            notice={shownNotice}
            onDismiss={() => {
              setNotice(null)
              recorder.clearError()
            }}
            onSend={() => void ask(draft)}
            onStop={stop}
            recorder={voiceAvailable ? recorder : null}
          />
        </section>
      )}

      <button
        onClick={() => {
          setOpen((o) => !o)
          setUnread(false)
        }}
        aria-expanded={open}
        aria-label={open ? 'AI туслахыг хаах' : 'AI туслахаас асуух'}
        className={`fixed right-5 bottom-5 z-50 flex items-center gap-2.5 rounded-full border border-line bg-raised py-1.5 pr-4 pl-1.5 text-sm font-semibold text-ink shadow-[0_10px_30px_rgba(0,0,0,0.45)] transition hover:-translate-y-0.5 hover:border-[#4a4f8a] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ct ${open ? 'max-sm:hidden' : ''}`}
      >
        <Orb state={orb} size="h-9 w-9" />
        <span>Ask</span>
        {unread && <span className="absolute -top-0.5 -right-0.5 h-3 w-3 rounded-full bg-good ring-2 ring-ground" />}
      </button>
    </>
  )
}

function Orb({ state, size }: { state: OrbState; size: string }) {
  return (
    <span className={`as-orb shrink-0 ${size}`} data-state={state}>
      {state === 'speaking' ? <Equalizer /> : state === 'listening' ? <Mic width={18} height={18} /> : <Sparkle width={19} height={19} />}
    </span>
  )
}

function Equalizer() {
  return (
    <span className="as-eq" aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
    </span>
  )
}

function IconButton(props: {
  label: string
  onClick: () => void
  children: ReactNode
  disabled?: boolean
  pressed?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.disabled}
      aria-label={props.label}
      aria-pressed={props.pressed}
      title={props.label}
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg text-ink-2 transition hover:bg-raised hover:text-ink disabled:pointer-events-none disabled:opacity-35 ${props.className ?? ''}`}
    >
      {props.children}
    </button>
  )
}

function Welcome(props: {
  page: PageContext
  configured: boolean
  loading: boolean
  voice: boolean
  onPick: (q: string) => void
}) {
  return (
    <div className="as-in flex flex-1 flex-col items-center justify-center gap-5 px-2 text-center">
      <Orb state="idle" size="h-14 w-14 [&_svg]:h-7 [&_svg]:w-7" />
      <div className="space-y-1.5">
        <p className="text-base font-semibold text-ink">Юу мэдэхийг хүсэж байна?</p>
        <p className="text-sm leading-relaxed text-ink-2">{greeting(props.page)}</p>
      </div>
      {!props.loading && !props.configured ? (
        <p className="rounded-xl border border-crit/50 bg-crit/10 px-3 py-2 text-sm text-crit">
          Туслах энэ сервер дээр тохируулагдаагүй байна (CLAUDE_API_KEY алга).
        </p>
      ) : (
        <div className="flex w-full flex-col gap-2">
          {suggestions(props.page.scope).map((q) => (
            <button
              key={q}
              onClick={() => props.onPick(q)}
              disabled={!props.configured}
              className="group flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2.5 text-left text-sm text-ink-2 transition hover:border-[#5d63b8] hover:text-ink disabled:opacity-50"
            >
              <Sparkle width={14} height={14} className="shrink-0 text-[#9a86f0] opacity-70 group-hover:opacity-100" />
              {q}
            </button>
          ))}
        </div>
      )}
      {props.voice && props.configured && (
        <p className="flex items-center gap-1.5 text-xs text-ink-3">
          <Mic width={14} height={14} /> товчийг дараад монголоор ярьж асууж болно
        </p>
      )}
    </div>
  )
}

function UserBubble({ turn }: { turn: Turn }) {
  return (
    <div className="as-in ml-auto flex max-w-[85%] flex-col items-end gap-1">
      <div className="rounded-2xl rounded-br-md bg-ct px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap text-ground">
        {turn.paras[0]?.text}
      </div>
      {turn.spoken && (
        <span className="flex items-center gap-1 text-[11px] text-ink-3">
          <Mic width={12} height={12} /> дуугаар асуусан
        </span>
      )}
    </div>
  )
}

function Reply({ turn, speaker, onRetry }: { turn: Turn; speaker: SpeakerApi; onRetry: () => void }) {
  const steps = turn.steps ?? []
  const waiting = turn.pending && !turn.paras.length
  return (
    <div className="as-in flex gap-2.5">
      <Orb state={turn.pending ? 'thinking' : 'idle'} size="mt-0.5 h-7 w-7 [&_svg]:h-4 [&_svg]:w-4" />
      <div className="min-w-0 flex-1 space-y-2">
        {steps.length > 0 && <Steps steps={steps} live={!!waiting} />}
        {waiting && (
          <div className="flex items-center gap-2 py-1 text-xs text-ink-3">
            <span className="as-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            {steps.length ? 'Шинжилж байна…' : 'Бодож байна…'}
          </div>
        )}
        {turn.paras.length > 0 && (
          <div className="space-y-1 rounded-2xl rounded-tl-md border border-line-soft bg-surface-2 px-1.5 py-1.5">
            {turn.paras.map((p, i) => {
              const key = `${turn.id}:${i}`
              const speaking = speaker.playing === key
              return (
                <div
                  key={key}
                  className={`group relative rounded-xl px-2.5 py-1.5 transition-colors ${speaking ? 'as-speaking' : ''}`}
                >
                  <p className="pr-7 text-sm leading-relaxed whitespace-pre-wrap text-ink">{p.text}</p>
                  {p.audio && (
                    <button
                      onClick={() => (speaking ? speaker.stop() : speaker.play(key, p.audio!))}
                      aria-label={speaking ? 'Зогсоох' : 'Энэ хэсгийг сонсох'}
                      title={speaking ? 'Зогсоох' : 'Энэ хэсгийг сонсох'}
                      className={`absolute top-1.5 right-1.5 grid h-6 w-6 place-items-center rounded-full transition ${
                        speaking
                          ? 'bg-[#8c6cf2] text-white'
                          : 'text-ink-3 opacity-60 group-hover:opacity-100 hover:bg-raised hover:text-ink max-sm:opacity-100'
                      }`}
                    >
                      {speaking ? <StopSquare width={12} height={12} /> : <Play width={12} height={12} />}
                    </button>
                  )}
                </div>
              )
            })}
            {turn.pending && (
              <div className="px-2.5 pb-1">
                <span className="as-dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
              </div>
            )}
          </div>
        )}
        {turn.stopped && <p className="text-xs text-ink-3">Зогсоосон.</p>}
        {turn.error && (
          <div className="flex items-start gap-2 rounded-xl border border-crit/50 bg-crit/10 px-3 py-2 text-sm text-crit">
            <span className="flex-1">{turn.error}</span>
            <button
              onClick={onRetry}
              className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-ink hover:bg-crit/20"
            >
              <Retry width={14} height={14} /> Дахин
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/** The lookups behind an answer: live while it runs, folded once it has an answer. */
function Steps({ steps, live }: { steps: string[]; live: boolean }) {
  const list = (
    <ul className="space-y-1">
      {steps.map((s, i) => {
        const current = live && i === steps.length - 1
        return (
          <li key={i} className="flex items-start gap-1.5 text-xs text-ink-3">
            {current ? (
              <span className="mt-0.5 h-3 w-3 shrink-0 animate-spin rounded-full border-[1.5px] border-ink-3 border-t-transparent" />
            ) : (
              <Check width={13} height={13} className="mt-px shrink-0 text-good" />
            )}
            <span className={current ? 'text-ink-2' : ''}>{s}</span>
          </li>
        )
      })}
    </ul>
  )
  if (live) return list
  return (
    <details className="group text-xs text-ink-3">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 hover:text-ink-2">
        <Check width={13} height={13} className="text-good" />
        {steps.length} өгөгдөл уншсан
        <span className="transition group-open:rotate-90">›</span>
      </summary>
      <div className="mt-1.5 pl-1">{list}</div>
    </details>
  )
}

function Composer(props: {
  draft: string
  setDraft: (s: string) => void
  busy: boolean
  disabled: boolean
  transcribing: boolean
  notice: string | null
  onDismiss: () => void
  onSend: () => void
  onStop: () => void
  recorder: ReturnType<typeof useRecorder> | null
}) {
  const { recorder, draft } = props
  const input = useRef<HTMLTextAreaElement>(null)

  // The box grows with its text, up to about six lines.
  useEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`
  }, [draft])

  const canSend = !!props.draft.trim() && !props.disabled
  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

  return (
    <div className="border-t-1 border-line bg-surface-2 px-3 pt-2.5 pb-3">
      {props.notice && (
        <div className="as-in mb-2 flex items-start gap-2 rounded-lg bg-raised px-3 py-2 text-xs text-ink-2">
          <span className="flex-1">{props.notice}</span>
          <button onClick={props.onDismiss} aria-label="Хаах" className="text-ink-3 hover:text-ink">
            <Close width={14} height={14} />
          </button>
        </div>
      )}

      {recorder && recorder.state !== 'idle' ? (
        <div className="flex h-12 items-center gap-2 rounded-2xl border border-crit/40 bg-ground px-2">
          <IconButton label="Цуцлах (Esc)" onClick={recorder.cancel}>
            <Close />
          </IconButton>
          <span className="flex items-center gap-1.5 font-mono text-xs text-ink-2 tabular-nums">
            <span className="as-rec-dot h-2 w-2 rounded-full bg-crit" />
            {recorder.state === 'starting' ? '…' : mmss(recorder.elapsed)}
          </span>
          <div className="as-wave flex h-7 flex-1 items-center gap-[2px] overflow-hidden" aria-hidden="true">
            {recorder.levels.map((l, i) => (
              <span key={i} style={{ height: `${Math.max(8, l * 100)}%`, opacity: 0.35 + l * 0.65 }} />
            ))}
          </div>
          <button
            onClick={recorder.stop}
            disabled={recorder.state !== 'recording'}
            aria-label="Дуусгаад илгээх"
            title="Дуусгаад илгээх"
            className="as-orb h-9 w-9 shrink-0 disabled:opacity-50"
            data-state="none"
          >
            <Check width={18} height={18} />
          </button>
        </div>
      ) : props.transcribing ? (
        <div className="flex h-12 items-center justify-center gap-2 rounded-2xl border border-line bg-ground text-sm text-ink-2">
          <span className="as-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          Яриаг таньж байна…
        </div>
      ) : (
        <form
          className="flex items-end gap-2 rounded-2xl border border-line bg-ground py-1.5 pr-1.5 pl-3.5 transition focus-within:border-[#5d63b8]"
          onSubmit={(e) => {
            e.preventDefault()
            if (canSend && !props.busy) props.onSend()
          }}
        >
          <textarea
            ref={input}
            rows={1}
            autoFocus
            maxLength={MAX_CHARS}
            value={props.draft}
            disabled={props.disabled}
            onChange={(e) => props.setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                if (canSend && !props.busy) props.onSend()
              }
            }}
            placeholder={props.disabled ? 'Туслах тохируулагдаагүй' : 'Баг, map, тоглолтын талаар асуу…'}
            aria-label="Асуулт"
            className="max-h-[150px] min-h-[36px] flex-1 resize-none bg-transparent py-1.5 text-sm leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none disabled:opacity-50"
          />
          {recorder && !props.busy && (
            <IconButton
              label="Дуугаар асуух"
              onClick={() => void recorder.start()}
              disabled={props.disabled}
              className="h-9 w-9 rounded-full"
            >
              <Mic />
            </IconButton>
          )}
          {props.busy ? (
            <button
              type="button"
              onClick={props.onStop}
              aria-label="Хариултыг зогсоох"
              title="Хариултыг зогсоох"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-ground transition hover:opacity-85"
            >
              <StopSquare width={16} height={16} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canSend}
              aria-label="Илгээх (Enter)"
              title="Илгээх (Enter)"
              className="as-orb h-9 w-9 shrink-0 transition disabled:opacity-30 disabled:shadow-none"
              data-state="none"
            >
              <Send width={18} height={18} />
            </button>
          )}
        </form>
      )}
      <p className="mt-1.5 px-1 text-[11px] text-ink-3 max-sm:hidden">
        Enter — илгээх · Shift+Enter — шинэ мөр
      </p>
    </div>
  )
}

// One <audio> element plays the Assistant's paragraphs in order. A reply's
// paragraphs are queued as their audio arrives; replaying one paragraph drops
// the queue and starts there. Safari only lets an element play on its own
// once it has played inside a user gesture, so `unlock` plays a blip of
// silence when the User sends a question.
import { useEffect, useMemo, useState } from 'react'

const SILENCE =
  'data:audio/wav;base64,UklGRnQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA=='

interface Clip {
  key: string
  url: string
}

class ClipPlayer {
  private readonly el = new Audio()
  private queue: Clip[] = []
  private current: string | null = null
  private unlocked = false
  private readonly onChange: (key: string | null) => void

  constructor(onChange: (key: string | null) => void) {
    this.onChange = onChange
    const onEnd = () => {
      if (this.current) this.next()
    }
    this.el.addEventListener('ended', onEnd)
    this.el.addEventListener('error', onEnd)
  }

  private set(key: string | null) {
    this.current = key
    this.onChange(key)
  }

  private next() {
    const clip = this.queue.shift()
    if (!clip) {
      this.set(null)
      return
    }
    this.el.src = clip.url
    this.set(clip.key)
    this.el.play().catch(() => this.next())
  }

  enqueue = (key: string, url: string) => {
    this.queue.push({ key, url })
    if (!this.current) this.next()
  }

  play = (key: string, url: string) => {
    this.queue = [{ key, url }]
    this.el.pause()
    this.next()
  }

  stop = () => {
    this.queue = []
    this.el.pause()
    this.set(null)
  }

  unlock = () => {
    if (this.current || this.unlocked) return
    this.el.src = SILENCE
    this.el
      .play()
      .then(() => {
        this.unlocked = true
      })
      .catch(() => {})
  }
}

export interface Speaker {
  /** The key of the paragraph being spoken, or null. */
  playing: string | null
  enqueue(key: string, url: string): void
  play(key: string, url: string): void
  stop(): void
  unlock(): void
}

export function useSpeaker(): Speaker {
  const [playing, setPlaying] = useState<string | null>(null)
  const [player] = useState(() => new ClipPlayer(setPlaying))
  useEffect(() => () => player.stop(), [player])
  return useMemo(
    () => ({ playing, enqueue: player.enqueue, play: player.play, stop: player.stop, unlock: player.unlock }),
    [playing, player],
  )
}

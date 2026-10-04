// The Assistant's icons: 20px line icons on currentColor, plus the sparkle mark.
import type { SVGProps } from 'react'

type Props = SVGProps<SVGSVGElement>

function Line({ children, ...props }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

/** The AI mark: a four-point sparkle with a smaller companion. */
export function Sparkle(props: Props) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true" {...props}>
      <path d="M10.2 2.8c.3-.9 1.6-.9 1.9 0l1.3 3.9a5 5 0 0 0 3.2 3.2l3.9 1.3c.9.3.9 1.6 0 1.9l-3.9 1.3a5 5 0 0 0-3.2 3.2l-1.3 3.9c-.3.9-1.6.9-1.9 0l-1.3-3.9a5 5 0 0 0-3.2-3.2l-3.9-1.3c-.9-.3-.9-1.6 0-1.9l3.9-1.3a5 5 0 0 0 3.2-3.2l1.3-3.9Z" />
      <path
        d="M19 1.8c.1-.4.7-.4.8 0l.5 1.5a2 2 0 0 0 1.3 1.3l1.5.5c.4.1.4.7 0 .8l-1.5.5a2 2 0 0 0-1.3 1.3l-.5 1.5c-.1.4-.7.4-.8 0l-.5-1.5a2 2 0 0 0-1.3-1.3l-1.5-.5c-.4-.1-.4-.7 0-.8l1.5-.5a2 2 0 0 0 1.3-1.3l.5-1.5Z"
        opacity=".75"
      />
    </svg>
  )
}

export const Mic = (p: Props) => (
  <Line {...p}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
  </Line>
)

export const Send = (p: Props) => (
  <Line {...p}>
    <path d="M12 19V5M6 11l6-6 6 6" />
  </Line>
)

export const StopSquare = (p: Props) => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true" {...p}>
    <rect x="6.5" y="6.5" width="11" height="11" rx="2.5" />
  </svg>
)

export const Speaker = (p: Props) => (
  <Line {...p}>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4Z" />
    <path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" />
  </Line>
)

export const SpeakerOff = (p: Props) => (
  <Line {...p}>
    <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5H4Z" />
    <path d="m16 9.5 5 5M21 9.5l-5 5" />
  </Line>
)

export const NewChat = (p: Props) => (
  <Line {...p}>
    <path d="M12 4H6.5A2.5 2.5 0 0 0 4 6.5v11A2.5 2.5 0 0 0 6.5 20h11a2.5 2.5 0 0 0 2.5-2.5V12" />
    <path d="M17.6 3.6a2 2 0 0 1 2.8 2.8L12.5 14.3 9 15l.7-3.5 7.9-7.9Z" />
  </Line>
)

export const Close = (p: Props) => (
  <Line {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Line>
)

export const Play = (p: Props) => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true" {...p}>
    <path d="M8 5.6v12.8c0 .8.9 1.3 1.6.8l9.6-6.4a1 1 0 0 0 0-1.6L9.6 4.8C8.9 4.3 8 4.8 8 5.6Z" />
  </svg>
)

export const Check = (p: Props) => (
  <Line {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Line>
)

export const Retry = (p: Props) => (
  <Line {...p}>
    <path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.5M20 4v4.5h-4.5M20 12a8 8 0 0 1-13.7 5.6L4 15.5M4 20v-4.5h4.5" />
  </Line>
)

export const Pin = (p: Props) => (
  <Line {...p}>
    <path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" />
    <circle cx="12" cy="10" r="2.3" />
  </Line>
)

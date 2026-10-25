// The v2 building blocks (the DEMOLAB design): panels, KPI tiles, bars, toggles
// and sparklines, in the tokens v2.css sets under .v2.
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { GOOD, sparkPath } from './format'

export function PageHead(props: { label: string; title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <section className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1.5">
        <span className="lbl">{props.label}</span>
        <h1 className="cond m-0 text-[32px] leading-tight font-bold sm:text-[40px]">{props.title}</h1>
        {props.sub && <p className="m-0 text-[15px] text-ink-3">{props.sub}</p>}
      </div>
      {props.actions && <div className="flex flex-wrap items-center gap-2">{props.actions}</div>}
    </section>
  )
}

export function Panel(props: {
  title?: ReactNode
  sub?: ReactNode
  right?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`flex min-w-0 flex-col gap-3.5 rounded-lg border border-line bg-surface p-5 ${props.className ?? ''}`}>
      {(props.title || props.right) && (
        <div className="flex flex-wrap items-baseline justify-between gap-2.5">
          <div className="flex flex-col gap-1">
            {props.title && <h2 className="cond m-0 text-[22px] font-bold">{props.title}</h2>}
            {props.sub && <span className="text-[13px] text-ink-3">{props.sub}</span>}
          </div>
          {props.right}
        </div>
      )}
      {props.children}
    </section>
  )
}

/** An inner box on a panel. */
export function Box(props: { children: ReactNode; className?: string }) {
  return (
    <div className={`flex min-w-0 flex-col gap-1.5 rounded-md border border-line-soft bg-surface-2 p-3.5 ${props.className ?? ''}`}>
      {props.children}
    </div>
  )
}

export function Kpi(props: { label: string; value: ReactNode; sub?: ReactNode; color?: string; size?: number }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-lg border border-line bg-surface p-4">
      <span className="lbl">{props.label}</span>
      <span className="num font-semibold" style={{ fontSize: props.size ?? 28, color: props.color }}>
        {props.value}
      </span>
      {props.sub && <span className="text-xs text-ink-3">{props.sub}</span>}
    </div>
  )
}

/** A filled bar on its track; `to` 0–100. */
export function Bar(props: { pct: number | null | undefined; color?: string; h?: number; className?: string }) {
  const h = props.h ?? 8
  const w = Math.max(0, Math.min(100, props.pct ?? 0))
  return (
    <div className={`rounded-full bg-line ${props.className ?? ''}`} style={{ height: h }}>
      <div className="rounded-full" style={{ height: h, width: `${w}%`, background: props.color ?? GOOD }} />
    </div>
  )
}

/** A label above a bar with its value on the right. */
export function BarRow(props: { label: ReactNode; value: ReactNode; pct: number | null | undefined; color?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between gap-2 text-sm">
        <span>{props.label}</span>
        <span className="num font-semibold" style={{ color: props.color }}>
          {props.value}
        </span>
      </div>
      <Bar pct={props.pct} color={props.color} />
    </div>
  )
}

/** The design's toggle group: bordered buttons, the picked one in the accent. */
export function Toggle<K extends string>(props: {
  options: readonly (readonly [K, ReactNode])[]
  value: K
  onChange: (k: K) => void
  label: string
  small?: boolean
}) {
  return (
    <div role="group" aria-label={props.label} className="flex flex-wrap gap-1.5">
      {props.options.map(([k, text]) => {
        const on = k === props.value
        return (
          <button
            key={k}
            type="button"
            aria-pressed={on}
            onClick={() => props.onChange(k)}
            className={`${props.small ? 'h-9 px-3 text-[13px]' : 'h-11 px-4 text-sm'} rounded-md border ${
              on ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong text-ink-2 hover:text-ink'
            }`}
          >
            {text}
          </button>
        )
      })}
    </div>
  )
}

/** T / CT, as one joined control. */
export function SideToggle(props: { value: 't' | 'ct'; onChange: (s: 't' | 'ct') => void; h?: number }) {
  const h = props.h ?? 44
  return (
    <div role="group" aria-label="Тал" className="flex overflow-hidden rounded-md border border-line-strong">
      {(['t', 'ct'] as const).map((s) => {
        const on = props.value === s
        const bg = on ? (s === 't' ? 'var(--t)' : 'var(--ct)') : 'transparent'
        return (
          <button
            key={s}
            type="button"
            aria-pressed={on}
            onClick={() => props.onChange(s)}
            className="px-4 text-sm font-semibold"
            style={{ height: h, background: bg, color: on ? '#0A0D10' : 'var(--ink-2)' }}
          >
            {s === 't' ? 'T тал' : 'CT тал'}
          </button>
        )
      })}
    </div>
  )
}

export function Tag(props: { children: ReactNode; color: string; solid?: boolean }) {
  return (
    <span
      className="cond rounded px-2 py-1 text-xs font-bold tracking-[0.06em] whitespace-nowrap uppercase"
      style={
        props.solid
          ? { background: props.color, color: '#0A0D10' }
          : { border: `1px solid ${props.color}`, color: props.color }
      }
    >
      {props.children}
    </span>
  )
}

const BUTTON = 'inline-flex h-11 items-center gap-2 rounded-md px-4 text-sm no-underline'

export function ButtonLink(props: { to: string; children: ReactNode; primary?: boolean; external?: boolean }) {
  const cls = `${BUTTON} plain ${
    props.primary ? 'bg-accent font-semibold !text-[#0A0D10]' : 'border border-line-strong bg-raised text-ink'
  }`
  if (props.external) return <a href={props.to} className={cls}>{props.children}</a>
  return (
    <Link to={props.to} className={cls}>
      {props.children}
    </Link>
  )
}

export function Button(props: {
  onClick?: () => void
  children: ReactNode
  primary?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
}) {
  return (
    <button
      type={props.type ?? 'button'}
      onClick={props.onClick}
      disabled={props.disabled}
      className={`${BUTTON} ${
        props.primary ? 'bg-accent font-semibold text-[#0A0D10]' : 'border border-line-strong bg-raised text-ink'
      } disabled:opacity-50`}
    >
      {props.children}
    </button>
  )
}

/** Where the data has nothing to say: said plainly, never a made-up number. */
export function Empty(props: { children?: ReactNode }) {
  return <p className="m-0 text-[13px] text-ink-3">{props.children ?? 'Мэдээлэл алга.'}</p>
}

export function Spark(props: { values: number[]; w?: number; h?: number; lo?: number; hi?: number; color?: string; base?: number }) {
  const w = props.w ?? 110
  const h = props.h ?? 26
  const lo = props.lo ?? Math.min(...props.values)
  const hi = props.hi ?? Math.max(...props.values)
  const baseY = props.base == null ? h / 2 : h - ((props.base - lo) / (hi - lo || 1)) * h
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <path d={`M0 ${baseY} H${w}`} stroke="var(--line-strong)" strokeDasharray="2 3" />
      <path d={sparkPath(props.values, w, h, lo, hi)} fill="none" stroke={props.color ?? GOOD} strokeWidth={2} />
    </svg>
  )
}

/** A legend swatch with its words. */
export function Swatch(props: { color: string; children: ReactNode; line?: boolean; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        style={
          props.line
            ? { width: 14, height: 0, borderTop: `${props.dashed ? '2px dashed' : '3px solid'} ${props.color}` }
            : { width: 10, height: 10, borderRadius: 2, background: props.color }
        }
      />
      {props.children}
    </span>
  )
}

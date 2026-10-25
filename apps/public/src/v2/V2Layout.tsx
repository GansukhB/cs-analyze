// The v2 frame (the DEMOLAB design): the brand, the four menu groups, the my
// team switch and the demo upload, on every v2 page. Staff only: a Player login
// keeps its own page (/me).
import { useQueryClient } from '@tanstack/react-query'
import { Suspense, useEffect, useRef, useState } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router'
import Assistant from '../assistant/Assistant'
import { tokenStore } from '../auth/token'
import { useMe, useMyTeams } from '../auth/useMe'
import { PageSkeleton } from '../ui/Skeleton'
import { at, initials } from './team'
import './v2.css'

// The four groups of the design's top menu: overview, analysis, the opponent, the team.
const NAV: [string, string][][] = [
  [['', 'Тойм']],
  [
    ['replay', '2D Replay'],
    ['matches', 'Тоглолт'],
    ['players', 'Тоглогч'],
    ['spatial', 'Байршил'],
    ['utility', 'Utility'],
  ],
  [
    ['scouting', 'Скаутинг'],
    ['gameplan', 'Game plan'],
  ],
  [
    ['practice', 'Бэлтгэл'],
    ['owner', 'Удирдлага'],
  ],
]

// «Бусад ▾»: the v1 pages v2 shows in its frame (grilling 2026-10-25), grouped.
const MORE: [string, [string, string][]][] = [
  [
    'Ажил',
    [
      ['scout', 'Шинэ Scout'],
      ['jobs', 'Ажлууд'],
      ['uploads', 'Демо оруулах'],
    ],
  ],
  [
    'Бэлтгэл',
    [
      ['briefings', 'Briefing'],
      ['stratbook', 'Stratbook'],
    ],
  ],
  ['Шинжилгээ', [['forecasts', 'Forecast']]],
  ['Байгууллага', [['workspace', 'Workspace']]],
]

export default function V2Layout() {
  const me = useMe()
  const mine = useMyTeams()
  const { team = '' } = useParams()
  if (!me.data) return <div className="v2" />
  if (me.data.role !== 'staff') return <Navigate to="/me" replace />
  const id = Number(team)
  if (!mine.some((t) => t.id === id)) {
    return mine.length ? (
      <Navigate to={at(mine[0].id)} replace />
    ) : (
      <div className="v2 p-8 text-ink-2">Энэ Workspace-д my team алга: эхлээд `npm run workspace:team` хийнэ үү.</div>
    )
  }
  return (
    <div className="v2 flex flex-col">
      <Header teamId={id} />
      <main className="mx-auto flex w-full max-w-[1376px] flex-1 flex-col gap-6 px-4 pt-7 pb-16 sm:px-8">
        <Suspense fallback={<PageSkeleton />}>
          <Outlet />
        </Suspense>
      </main>
      <div className="print:hidden">
        <Assistant />
      </div>
    </div>
  )
}

function Header({ teamId }: { teamId: number }) {
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line-soft bg-[#0D1115] px-4 py-3 sm:px-8 print:hidden">
      <Link to={at(teamId)} className="plain flex items-center gap-2.5 text-ink">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="12" r="8" />
          <path d="M12 1v6M12 17v6M1 12h6M17 12h6" />
        </svg>
        <span className="cond text-[17px] font-bold tracking-[0.14em]">DEMOLAB</span>
      </Link>
      {/* On a phone the nav scrolls on its own row with «Бусад» pinned at its end,
          outside the scrolling box so the menu isn't clipped. */}
      <div className="order-3 flex w-full min-w-0 items-center gap-x-2 xl:order-none xl:w-auto xl:flex-1">
        <nav
          aria-label="Үндсэн цэс"
          className="-mx-1 flex min-w-0 flex-1 items-center gap-x-2 overflow-x-auto xl:mx-0 xl:flex-none"
        >
          {NAV.map((group, gi) => (
            <div key={gi} className={`flex items-center gap-0.5 ${gi ? 'border-l border-line-strong pl-2' : ''}`}>
              {group.map(([key, label]) => (
                <NavLink
                  key={key}
                  to={key ? at(teamId, key) : at(teamId)}
                  end={!key}
                  className={({ isActive }) =>
                    `plain border-b-2 px-2 py-3 text-sm font-medium whitespace-nowrap ${
                      isActive ? 'border-accent !text-ink' : 'border-transparent !text-ink-3 hover:!text-ink'
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <More teamId={teamId} />
      </div>
      <div className="ml-auto flex items-center gap-2.5">
        <TeamSwitch teamId={teamId} />
        <Link
          to={at(teamId, 'uploads')}
          aria-label="Демо оруулах"
          className="plain flex h-11 items-center gap-2 rounded-md border border-accent px-4 text-sm font-semibold !text-accent"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
            <path d="M12 16V4M6 10l6-6 6 6M4 20h16" />
          </svg>
          <span className="hidden sm:inline xl:hidden 2xl:inline">Демо оруулах</span>
        </Link>
        <UserMenu />
      </div>
    </header>
  )
}

function Popover(props: {
  button: (open: boolean, toggle: () => void) => React.ReactNode
  children: (close: () => void) => React.ReactNode
  /** Where the menu opens from, as position classes (default: under the right edge). */
  align?: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])
  return (
    <div ref={ref} className="relative">
      {props.button(open, () => setOpen((o) => !o))}
      {open && (
        <div className={`absolute ${props.align ?? 'right-0'} z-30 mt-1 min-w-56 rounded-md border border-line-strong bg-raised p-1 shadow-xl`}>
          {props.children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

function TeamSwitch({ teamId }: { teamId: number }) {
  const mine = useMyTeams()
  const navigate = useNavigate()
  const location = useLocation()
  const current = mine.find((t) => t.id === teamId)
  // Switching keeps the section (overview, practice...) but drops what belongs to
  // the old team (a Match, a Player, an opponent).
  const section = location.pathname.split('/')[4] ?? ''
  const keep = ['spatial', 'utility', 'practice', 'owner', 'matches', 'replay', 'players', 'scouting', 'gameplan',
    ...MORE.flatMap(([, items]) => items.map(([key]) => key))]
  return (
    <Popover
      button={(open, toggle) => (
        <button
          type="button"
          aria-expanded={open}
          aria-haspopup="listbox"
          onClick={toggle}
          className="flex h-11 items-center gap-2 rounded-md border border-line-strong bg-raised px-3.5 text-sm text-ink"
        >
          <span className="cond grid h-[22px] w-[22px] place-items-center rounded bg-accent text-[11px] font-bold text-[#0A0D10]">
            {initials(current?.name ?? '?')}
          </span>
          {current?.name}
          {current?.label && <span className="hidden text-ink-3 2xl:inline">· {current.label}</span>}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
      )}
    >
      {(close) => (
        <ul role="listbox" aria-label="My team" className="m-0 list-none p-0">
          {mine.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                role="option"
                aria-selected={t.id === teamId}
                onClick={() => {
                  close()
                  navigate(keep.includes(section) ? at(t.id, section) : at(t.id))
                }}
                className={`flex w-full items-center gap-2 rounded px-3 py-2.5 text-left text-sm ${
                  t.id === teamId ? 'text-accent' : 'text-ink hover:bg-chip'
                }`}
              >
                {t.name}
                {t.label && <span className="text-ink-3">· {t.label}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Popover>
  )
}

function UserMenu() {
  const me = useMe()
  const queryClient = useQueryClient()
  if (!me.data) return null
  return (
    <Popover
      button={(open, toggle) => (
        <button
          type="button"
          aria-expanded={open}
          aria-label="Хэрэглэгчийн цэс"
          onClick={toggle}
          className="cond grid h-11 w-11 place-items-center rounded-full border border-line-strong bg-raised text-sm font-bold text-ink"
        >
          {initials(me.data.username)}
        </button>
      )}
    >
      {(close) => (
        <div className="flex flex-col text-sm">
          <span className="px-3 py-2 text-ink-3">
            {me.data.workspace.name} · {me.data.username}
          </span>
          {[['/', 'Хуучин хувилбар (v1)']].map(([to, label]) => (
            <Link key={to} to={to} onClick={close} className="plain rounded px-3 py-2.5 !text-ink hover:bg-chip">
              {label}
            </Link>
          ))}
          <button
            type="button"
            onClick={() => {
              tokenStore.set(null)
              queryClient.clear()
            }}
            className="rounded px-3 py-2.5 text-left text-crit hover:bg-chip"
          >
            Гарах
          </button>
        </div>
      )}
    </Popover>
  )
}

function More({ teamId }: { teamId: number }) {
  const location = useLocation()
  const section = location.pathname.split('/')[4] ?? ''
  const here = MORE.some(([, items]) => items.some(([key]) => key === section))
  return (
    <Popover
      align="right-0 xl:right-auto xl:left-0"
      button={(open, toggle) => (
        <button
          type="button"
          aria-expanded={open}
          aria-haspopup="menu"
          onClick={toggle}
          className={`flex items-center gap-1 border-b-2 px-2 py-3 text-sm font-medium whitespace-nowrap ${
            here ? 'border-accent text-ink' : 'border-transparent text-ink-3 hover:text-ink'
          }`}
        >
          Бусад
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
      )}
    >
      {(close) => (
        <div className="flex flex-col gap-1 py-1 text-sm">
          {MORE.map(([group, items]) => (
            <div key={group} className="flex flex-col">
              <span className="lbl px-3 pt-1.5 pb-1">{group}</span>
              {items.map(([key, label]) => (
                <NavLink
                  key={key}
                  to={at(teamId, key)}
                  onClick={close}
                  className={({ isActive }) =>
                    `plain rounded px-3 py-2 hover:bg-chip ${isActive ? '!text-accent' : '!text-ink'}`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </div>
      )}
    </Popover>
  )
}

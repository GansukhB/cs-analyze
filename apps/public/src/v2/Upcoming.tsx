// The next Upcoming match (CONTEXT.md), and the form Staff enter one with.
import { useState } from 'react'
import { $api } from '../api/client'
import type { components } from '../api/schema'
import { TeamPicker, type PickedTeam } from './TeamPicker'
import { at } from './team'
import { ButtonLink } from './ui'
import { countdown, when } from './format'
import { useInvalidateV2 } from './hooks'

export type Upcoming = components['schemas']['UpcomingRead']

export function UpcomingBlock(props: { teamId: number; upcoming: Upcoming | null | undefined }) {
  const [adding, setAdding] = useState(false)
  const u = props.upcoming
  if (adding || !u)
    return adding ? (
      <UpcomingForm teamId={props.teamId} onDone={() => setAdding(false)} />
    ) : (
      <div className="flex flex-col gap-2">
        <span className="text-[13px] text-ink-3">Ирэх тоглолт оруулаагүй байна.</span>
        <button type="button" onClick={() => setAdding(true)} className="self-start text-sm text-ct underline">
          Ирэх тоглолт нэмэх
        </button>
      </div>
    )
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex flex-col gap-1">
        <span className="cond text-lg font-bold">vs {u.opponent.name}</span>
        <span className="text-[13px] text-ink-3">
          {when(u.starts_at)} · BO{u.best_of}
          {u.tournament && ` · ${u.tournament}`} · <span className="num text-accent">{countdown(u.starts_at)}</span>
        </span>
        <button type="button" onClick={() => setAdding(true)} className="self-start text-xs text-ink-3 underline">
          Өөр тоглолт нэмэх
        </button>
      </div>
      <ButtonLink to={at(props.teamId, 'gameplan', u.opponent.id)}>Game plan</ButtonLink>
    </div>
  )
}

export function UpcomingForm(props: { teamId: number; onDone: () => void; opponent?: PickedTeam }) {
  const invalidate = useInvalidateV2()
  const [opponent, setOpponent] = useState<PickedTeam | null>(props.opponent ?? null)
  const [starts, setStarts] = useState('')
  const [bestOf, setBestOf] = useState<1 | 3 | 5>(3)
  const [tournament, setTournament] = useState('')
  const save = $api.useMutation('post', '/v2/upcoming', {
    onSuccess: () => {
      void invalidate()
      props.onDone()
    },
  })
  const error = (save.error as { detail?: string } | null)?.detail
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (!opponent || !starts) return
        // The input is Ulaanbaatar's wall clock (UTC+8, no DST).
        save.mutate({
          body: {
            team_id: props.teamId,
            opponent_id: opponent.id,
            starts_at: `${starts}:00+08:00`,
            best_of: bestOf,
            tournament,
          },
        })
      }}
    >
      <TeamPicker label="Өрсөлдөгч" value={opponent} onChange={setOpponent} exclude={[props.teamId]} />
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="lbl">Огноо, цаг (УБ)</span>
          <input
            type="datetime-local"
            required
            value={starts}
            onChange={(e) => setStarts(e.target.value)}
            className="h-11 rounded-md border border-line-strong bg-surface-2 px-3 text-sm text-ink"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="lbl">Формат</span>
          <select
            value={bestOf}
            onChange={(e) => setBestOf(Number(e.target.value) as 1 | 3 | 5)}
            className="h-11 rounded-md border border-line-strong bg-surface-2 px-3 text-sm text-ink"
          >
            <option value={1}>BO1</option>
            <option value={3}>BO3</option>
            <option value={5}>BO5</option>
          </select>
        </label>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="lbl">Тэмцээн</span>
        <input
          value={tournament}
          maxLength={160}
          onChange={(e) => setTournament(e.target.value)}
          className="h-11 rounded-md border border-line-strong bg-surface-2 px-3 text-sm text-ink"
        />
      </label>
      {error && <p className="m-0 text-sm text-crit">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!opponent || !starts || save.isPending}
          className="h-11 rounded-md bg-accent px-4 text-sm font-semibold text-[#0A0D10] disabled:opacity-50"
        >
          Хадгалах
        </button>
        <button type="button" onClick={props.onDone} className="h-11 rounded-md border border-line-strong px-4 text-sm">
          Болих
        </button>
      </div>
    </form>
  )
}

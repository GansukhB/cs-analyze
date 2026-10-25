// Pick any stored Team by name (GET /teams), most parsed Maps first: an
// Upcoming match's opponent, a scouting target.
import { useId, useMemo, useState } from 'react'
import { $api } from '../api/client'

export type PickedTeam = { id: number; name: string }

export function TeamPicker(props: {
  value: PickedTeam | null
  onChange: (t: PickedTeam | null) => void
  label: string
  exclude?: number[]
  parsedOnly?: boolean
}) {
  const teams = $api.useQuery('get', '/teams', {}, { staleTime: 5 * 60_000 })
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const id = useId()
  const found = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (teams.data?.teams ?? [])
      .filter((t) => !(props.exclude ?? []).includes(t.id))
      .filter((t) => !props.parsedOnly || t.maps > 0)
      .filter((t) => !needle || t.name.toLowerCase().includes(needle))
      .slice(0, 12)
  }, [teams.data, q, props.exclude, props.parsedOnly])

  return (
    <div className="relative flex flex-col gap-1.5">
      <label htmlFor={id} className="lbl">
        {props.label}
      </label>
      <input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        autoComplete="off"
        value={open ? q : (props.value?.name ?? q)}
        placeholder="Багийн нэр…"
        onFocus={() => {
          setOpen(true)
          setQ('')
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setQ(e.target.value)
          props.onChange(null)
        }}
        className="h-11 rounded-md border border-line-strong bg-surface-2 px-3 text-sm text-ink"
      />
      {open && (
        <ul
          id={`${id}-list`}
          role="listbox"
          className="absolute top-full z-30 mt-1 max-h-72 w-full overflow-auto rounded-md border border-line-strong bg-raised p-1"
        >
          {found.length === 0 && <li className="px-3 py-2 text-sm text-ink-3">Олдсонгүй.</li>}
          {found.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                role="option"
                aria-selected={props.value?.id === t.id}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  props.onChange({ id: t.id, name: t.name })
                  setQ(t.name)
                  setOpen(false)
                }}
                className="flex w-full justify-between gap-3 rounded px-3 py-2 text-left text-sm text-ink hover:bg-chip"
              >
                <span>{t.name}</span>
                <span className="num text-xs text-ink-3">{t.maps} map</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

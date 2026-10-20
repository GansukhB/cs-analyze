// Every line of a Map's Playbook a Briefing can hold, with its place in the panel:
// the server freezes a Briefing from these paths (app/services/briefings.py), so
// they must name the panel's own lists in the same order.
import type { PlaybookPanel } from '../gameplan/types'

export interface PickLine {
  path: string
  group: string
  title: string
  sub: string
}

export function pickLines(p: PlaybookPanel): PickLine[] {
  const out: PickLine[] = []
  p.plan.forEach((x, i) => out.push({ path: `plan.${i}`, group: 'Төлөвлөгөө', title: x.title, sub: x.counter }))
  for (const side of p.advice.sides) {
    side.levers.forEach((a, i) =>
      out.push({ path: `advice.${side.side}.levers.${i}`, group: `Ашиглах · ${side.label}`, title: a.title, sub: a.counter }),
    )
    side.cautions.forEach((a, i) =>
      out.push({ path: `advice.${side.side}.cautions.${i}`, group: `Анхаарах · ${side.label}`, title: a.title, sub: a.counter }),
    )
  }
  for (const s of p.sections) {
    s.habits.forEach((h, i) => out.push({ path: `sections.${s.key}.${i}`, group: s.title, title: h.title, sub: h.counter }))
  }
  p.pistols.forEach((x, i) => out.push({ path: `pistols.${i}`, group: 'Pistol', title: x.text, sub: x.next }))
  p.economy.habits.forEach((h, i) =>
    out.push({ path: `economy.${i}`, group: 'Эдийн засаг', title: h.title, sub: h.counter }),
  )
  p.players.forEach((x, i) =>
    out.push({ path: `players.${i}`, group: 'Тоглогчид', title: x.player, sub: x.lines.join(' ') }),
  )
  for (const side of p.self_scout) {
    side.habits.forEach((h, i) =>
      out.push({ path: `self.${side.side}.${i}`, group: `Self-scout · ${side.label}`, title: h.title, sub: h.counter }),
    )
  }
  return out
}

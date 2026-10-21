// A Strat's kinds as the pages name them (docs/plans/08 SB-1).
import type { components } from '../api/schema'

export type StratWrite = components['schemas']['StratWrite']

export const KINDS: [StratWrite['kind'], string][] = [
  ['default', 'Default'],
  ['execute', 'Execute'],
  ['fake', 'Fake'],
  ['retake', 'Retake'],
  ['setup', 'CT setup'],
  ['pistol', 'Pistol'],
  ['anti_eco', 'Anti-eco'],
  ['force', 'Force'],
]

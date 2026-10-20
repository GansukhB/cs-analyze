# Private data belongs to a Workspace; what HLTV shows is shared

cs-analyze stays a one-club tool for now, but from the first private feature on, everything a club keeps to itself belongs to its Workspace: its Users, its my teams, Scrims, Matches it uploaded, notes, its Stratbook, shared plans and who may see Forecasts. HLTV's Teams and Matches, and what parsing their Demos produced, stay shared by every Workspace. A Match a Workspace uploaded counts like an HLTV Match (Own form, habits, the Pool) but only inside that Workspace. We chose this over today's single space where every User sees everything, because adding ownership to private data later means auditing every query that ever read it, and over full multi-club SaaS (billing, sign-up, per-club settings) because one club uses it.

## Consequences

- The Pool, and every cache keyed on the Match Maps it reads (`pool:roles`, `pool:metrics`, the Game Plan's `gp:` stamps), depend on the Workspace once it has uploaded Matches.
- Users belong to one Workspace, as Staff or tied to a Player. Staff invite Users and deactivate them; only the first Staff of a Workspace is created from the server CLI.
- The Assistant's tools read through the same Workspace scope as the pages.

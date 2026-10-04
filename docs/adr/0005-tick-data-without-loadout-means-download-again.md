# Tick Data that lacks the Loadout is re-downloaded too

The Replay shows each Player's Loadout, Held weapon, armor and money under their name, read with demoparser on the Replay's 8 Hz grid and stored as the bundle's `loadout` table. Tick Data written before schema 12 has no such table, and it can't be rebuilt from Tick Data (the ticks carry no inventory). So we treat it exactly like Tick Data without the economy (ADR 0003): the map counts as stale, can't be re-parsed from its Tick Data, and the next Scout that covers its Match downloads the Demo again.

At first we let such maps keep a Replay without the Loadout, refreshed only by `npm run data:cstat` when cstat still had the `.dem`. We dropped that because most Matches' Demos are no longer on disk anywhere. A Scout then found nothing to do, and the Loadout never showed up on the Matches people were actually looking at.

## Consequences

- Each Scout re-downloads every Match in its Windows whose maps were parsed before schema 12, once. That costs as much as a first download.
- A Match Map outside every future Scout's Windows keeps a Replay without the Loadout (names only under the scoreboard). Everything else about it still works.
- The Loadout is never per-tick columns: about 140 K rows and 140 KB a map against roughly 1.5 million tick rows.

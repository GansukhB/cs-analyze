# Tick Data without Sightings is still reviewed, never downloaded again

Sightings (the game's own radar-spotting state, who had which enemy in view) are read at parse time from schema 13 on, and the Match Map review uses them to find missed chances. Unlike the economy (0003) and the Loadout (0005), a Match Map whose Tick Data has no Sightings does **not** make its Match download again: its review runs on what its Tick Data has, leaves out the findings that need Sightings, and says so on the page. A Demo is 300 to 470 MB through Cloudflare-fronted HLTV, and Sightings are approximate (on a measured Inferno demo, only 58% of kills had the killer spotting the victim in the 3 seconds before). The review's core (Swing, trades, utility) does not need them.

## Consequences

- `tickdata.reparseable` must not treat a missing Sightings table as a reason to download again. A stale map re-parsed from its Tick Data reaches schema 13 without Sightings, so schema 13 does not imply Sightings. Read the bundle's tables, not the schema number.

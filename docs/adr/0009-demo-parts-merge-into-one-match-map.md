# Demo parts are merged into one Match Map

When a server is restarted mid-map, HLTV's archive holds that Match Map as several Demo parts (`…-m2-inferno-p1.dem`, `…-p2.dem`), and each later part resumes from the round backup the game was restored to: the game's own `total_rounds_played` carries on across the parts. We parse every part and merge them into one Match Map and one Tick Data, with the later parts' ticks moved after the earlier ones and every Round numbered as it was played. Where parts overlap (the backup went back over Rounds already played) the later part wins, because those Rounds were officially played again. A part that is missing or won't parse leaves its Rounds out, named in the job's log, and the rest is kept.

The parts used to be read as unrelated maps with no map number, so each was stored as map 1 and the last one parsed replaced the others: an `m1` split kept one part's Rounds (Falcons vs Astralis' Ancient had 3 of 21), an `m2` split never got its Match Map at all, and a 45-character file stem overflowed `demos.map` and failed a whole Scout. That was 7 of production's Match Maps, three of them The Huns', the kind of Team this tool is for.

## Considered Options

- Keep the part with the most Rounds: simple, but it drops whole halves (The Huns vs NAS' Ancient would keep 11 of 18 Rounds) and the Match Map's score stops matching HLTV's.
- Skip split Match Maps: nothing wrong is stored, but the map is missing exactly where it is most often needed.

## Consequences

- Because the bundle stores the merged frames, `tickdata.parsed_map` re-parses a merged Match Map like any other, with no Demo.
- A Match whose Demo parts were parsed before this change has only one part's data anywhere, so like ADR 0003 and 0005 the next Scout that covers it downloads it again; locally `npm run data:cstat` merges the ones cstat still has on disk.
- An error on one Match (registering its Demos or parsing a map) now fails that Match, not the Scout.

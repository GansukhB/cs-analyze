# cs-analyze

A private tool for scouting professional Counter-Strike teams: it collects matches and demos from HLTV, parses what happened in each game, and builds reports from it. Only people who were given an account can use it.

## Access

**User**:
A person who signs in to cs-analyze with a Username and password. Users are only created by someone with server access; nobody can sign up on their own.
_Avoid_: Account, member, customer

**Username**:
The unique name a User signs in with. Case matters: "Bat" and "bat" are two different Usernames.
_Avoid_: Login, handle

**Deactivated User**:
A User who can no longer sign in or keep using the app, but whose records are kept. Only someone with server access can deactivate or reactivate a User.
_Avoid_: Deleted, banned, disabled

## Sources (what HLTV says)

**Team**:
A Counter-Strike team as HLTV lists it. Different Teams can share a display name.
_Avoid_: Club, org, clan

**Unidentified Team**:
A Team known only by its name because HLTV hasn't yet shown its id. No two Unidentified Teams share a name.

**Tournament**:
A competition that Matches are played in, such as "BLAST Open Porto 2026".
_Avoid_: Event (reserved for things that happen inside a Round, and for job log lines)

**Match**:
A series between two Teams at a Tournament, made up of one or more Match Maps.
_Avoid_: Game, series

**Demo**:
A recording of play downloaded from HLTV. One archive per Match holds one map demo per Match Map. A Demo is only kept while it is being parsed: what it showed lives on as the Match Map's analysis and Tick Data.
_Avoid_: Replay, recording

## Analysis (what happened in the game)

**Map**:
A Counter-Strike map such as Anubis or Mirage, as a dimension of its own.
_Avoid_: Level

**Match Map**:
One Map played inside a Match. Analysis belongs to the Match Map and survives deleting its Demo.
_Avoid_: Game, map result

**Round**:
One round of a Match Map. Every in-game Event belongs to a Round.

**Side**:
Counter-Terrorist (CT) or Terrorist (T). Teams swap Sides at half time, so a Side is never a Team.

**Player**:
One person, identified by their Steam id for good. Names change, so a Player keeps every name they've been seen under.

**Callout**:
The name the game gives the part of a Map a player stands in, such as "BombsiteB" or "Ramp". A Callout only means something inside its own Map.
_Avoid_: Place, location, zone

**Floor**:
One level of a two-level Map such as Nuke. A position's Floor comes from its altitude, never from its Callout.
_Avoid_: Level (in prose), storey

**Tick Data**:
Every Player's position and state at every tick of a Match Map, plus the game's own event tables, as the parse read them from the Demo. It is what a Match Map can be parsed again from without downloading its Demo, and what Replays and walked routes are cut from.
_Avoid_: Parquet, bundle (in prose), positions

**Replay**:
One Round played back from the parsed tick data: where every Player stood and what they did, second by second.
_Avoid_: Demo (that is the file), playback

**Loadout**:
Everything a Player is carrying at a given moment: guns, grenades, armor and helmet, a defuse kit, the bomb. Money is not part of the Loadout.
_Avoid_: Inventory, equipment (equipment value is the economy's measure of a buy)

**Held weapon**:
The one item in a Player's Loadout that they have in hand at that moment.
_Avoid_: Active weapon, current weapon

**Event**:
Something that happens inside a Round: a kill, damage, a bomb action, or a grenade.
_Avoid_: Using it for a Tournament

## Jobs

**Analysis Job**:
One background run, such as a scouting report on an opponent or re-parsing a single Match Map. Its story (log lines) and the pictures it draws are kept after it finishes.
_Avoid_: Task (that's the worker-level mechanism), report

**Scout**:
An Analysis Job about one fixture: "my team" versus an opponent, named as typed and resolved to Teams.

**Window**:
How many recent Matches a Scout looks at in one category: my team's own, the opponent's own, or Head-to-head. "My own" and "their own" never include Matches between the two Teams.
_Avoid_: Limit, sample size

**Head-to-head**:
A Match the two Teams of a Scout played against each other.
_Avoid_: H2H in prose, rematch

**Stage**:
One step of an Analysis Job's run, in a fixed order: resolving the Teams, fetching Demos, unpacking archives, parsing map demos, then done. Only one Analysis Job runs at a time; the rest wait queued.
_Avoid_: Phase, step

## Preparation (what to do about it)

**Fixture**:
The ordered pair a Game Plan is about: my team first, the opponent second. Swapping them is a different Fixture, because every panel is read from my team's side.
_Avoid_: Matchup, pairing

**Game Plan**:
The match-preparation page for one Fixture, computed only from parsed Match Maps: a decision, the evidence behind it in sections, and what to do. Unlike a Scout it downloads nothing and keeps nothing; it is recomputed whenever a Match Map is parsed.
_Avoid_: Report (that is a Scout's output), scouting page

**Lineup**:
Up to five Players a Fixture's Team is expected to field. The User picks it, from Players who have played for that Team or by searching any Player; left unpicked, it is the five from the Team's most recent parsed Match. A Lineup decides whose numbers a Game Plan shows and ranks; it does not narrow the Team's habits, which still come from all its Match Maps. A Player in a Lineup who never played for its Team, such as a new signing, is shown with their numbers from the Teams they did play for, marked as such.
_Avoid_: Roster (who actually played a Match Map), active roster, current five

**Pool**:
Every Team with at least two maps' worth of parsed Rounds. A Game Plan calls something a strength or a weakness only against the Pool, never against the opponent alone.
_Avoid_: League, baseline (in prose)

**Own form**:
A Team's numbers over its parsed Match Maps against anyone but the Fixture's other Team. What changes against that Team is the Head-to-head delta.
_Avoid_: Overall stats

**Playbook**:
The part of a Game Plan that says how to play each Map of the Fixture, for preparation before the match: the veto, my CT plan against their T habits, my T plan against their CT habits, pistol and economy rounds, their Set plays and how to meet them, and Player matchups. It reads the opponent's habits from all their parsed Match Maps, Head-to-head included, and marks which Head-to-head Rounds a habit came from. Every line carries its Evidence strength.
_Avoid_: Strategy (in prose), todo, tips

**Evidence strength**:
How far a Playbook line can be trusted. A habit is named only once it repeats in at least 4 Rounds on the same Side. It is weak when those Rounds come from one Match Map, medium from two or three, and strong from four or more. Weak lines are shown, marked as weak.
_Avoid_: Confidence (in prose), sample size

**Buy type**:
How a Team equipped itself for a Round, read from its five Players' summed equipment value as the Round goes live: Pistol (the first Round of each regulation half; overtime starts everyone on $10,000), Eco (under $5,000), Force ($5,000 to $19,999) or Full (from $20,000).
_Avoid_: Buy round, economy round

**Set play**:
A grenade pattern a Team repeats on one Map and Side: at least two smokes or molotovs landing on the same Callouts at about the same time (within 5 seconds) in the first 40 seconds after buy time, seen in at least 4 Rounds. It is reported with where the Round went next and how often it was won, plus a counter.
_Avoid_: Strat, execute (in prose)

**Self-scout**:
The Playbook's view of my own team: the same habits and Set plays it finds on the opponent, read from my team's Match Maps, so I can see what the opponent could prepare against.
_Avoid_: Own form (that's the numbers, not the habits)

**Setup**:
Where a Team's Players stand 20 seconds after buy time ends, on one Side of one Map: each Player's Callout, and how many lean toward A, mid and B (such as 2-1-2). On CT it is how they hold; on T it is their default.
_Avoid_: Formation, position (in prose)

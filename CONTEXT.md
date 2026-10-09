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

**Spot**:
A smaller named part of a Map than its Callout, as players call it: Coffin, Dark and New Box are Spots inside Inferno's BombsiteB. Spots are drawn by hand for each Map; where none is drawn, the Callout stands in.
_Avoid_: Sub-callout, pro callout, area

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

**Sighting**:
A stretch of time in which a Player had an enemy in view, as the game itself judged it for the radar. Only Match Maps parsed since Sightings were read have them; the game's judgement is approximate, so a kill can happen without one.
_Avoid_: Spotted, visibility, line of sight

**Event**:
Something that happens inside a Round: a kill, damage, a bomb action, or a grenade.
_Avoid_: Using it for a Tournament

## Review (what decided a Match Map)

**Review**:
The account of one Match Map after it was played: Round by Round, which Findings decided it, for both Teams alike and filterable by Player. It states only what the parsed Match Map shows; a Match Map without Sightings gets every Finding that does not need them.
_Avoid_: Analysis (that is what parsing produced), report, debrief

**Win probability**:
A Side's chance of winning a Round from one moment's state: who is alive, what they carry, whether the bomb is down and how much time is left. It is read from how parsed Rounds in the same state ended.
_Avoid_: Win chance, odds, expected win

**Swing**:
How much one action (a kill, a plant, a defuse, a flash that set up a kill) moved its Team's Win probability, credited to the Players behind it. A Player's Swing over a Round or a Match Map is the sum of theirs.
_Avoid_: Impact (HLTV's Impact rating is another thing), value, rating

**Trade**:
Killing the enemy who just killed a teammate, within 5 seconds of that death.
_Avoid_: Refrag, revenge

**Finding**:
One thing the Review points out, tied to a Round, a moment in it and the Players involved, with its Swing and the reason it was flagged. It is a Key play, a Mistake, a Missed chance or a Utility effect.
_Avoid_: Insight, highlight, moment

**Key play**:
A Finding about an action that won its Team a large Swing: an entry, a multi-kill, a clutch, a retake, a plant or defuse under pressure.
_Avoid_: Highlight, MVP play

**Mistake**:
A Finding about something a Player did that cost their Team a large Swing, with a named cause such as dying untraded, dying to a teammate's flash, losing a rifle when the Round was already lost, or losing a duel with a knife or grenade as the Held weapon. A costly death with no identifiable cause is not a Mistake. Some Mistakes belong to the Team, such as Terrorists running out of time.
_Avoid_: Error, blunder

**Missed chance**:
A Finding about something a Player could have done and did not, such as a Trade they were close enough to take, an enemy they had damaged and left alive, or a blinded enemy nobody punished.
_Avoid_: Missed opportunity (in prose), what-if

**Utility effect**:
A Finding about a grenade that changed a Round: a flash that set up a kill, HE or fire damage that let a kill land, a molotov that held up a plant or defuse. A flash that blinded the thrower's own teammates, or utility that touched nobody, counts against them.
_Avoid_: Nade impact, util value

**Summary**:
A Team's account at one level, a Round, a Match Map or a Match: what went well, what went wrong and what to work on, told only from that level's Findings and Round facts. Both Teams get one, side by side.
_Avoid_: Debrief, overview, report, takeaway

**Pattern**:
The same kind of Finding repeating within one Match Map more often than it does for most Teams, counted and tied to the Players and places behind it; across a Match, anything a Summary says on two Maps or more. It describes what happened there; a habit (Playbook) is what a Team tends to do across all its Match Maps.
_Avoid_: Trend, habit

**Focus point**:
One of the few things that went wrong that a Summary puts first as what to work on, ranked by the Swing it cost.
_Avoid_: Lesson, todo, tip

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

## Asking

**Assistant**:
A chat, typed or spoken, that answers a User's questions about Teams, Maps and Fixtures. It states only what it read from the same parsed analysis the pages show, with how much data each answer rests on. It knows which page it was opened from: on a Game Plan it answers about that Fixture and its Lineups, on a Team page about that Team. It can answer aloud. A conversation lives only in the User's browser tab and is never stored.
_Avoid_: Bot, chatbot, AI (in prose), Ask (that is the button)

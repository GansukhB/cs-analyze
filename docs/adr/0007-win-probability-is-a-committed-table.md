# Win probability is a committed table, refit only by hand

The Review's Swing comes from a Win probability model fitted on every parsed Round. The fitted model is committed to the repo as a versioned table and refit only by a CLI command. It is not refit as Match Maps are parsed. A live refit would make every stored Review's numbers drift each time a Match Map is parsed, and a Review read last week would no longer match today's. Refitting bumps the table's version, which rebuilds the stored Reviews the same way a changed Replay is rebuilt.

Since version 2 (docs/plans/07 RV-4) the table is fitted on the states the Review itself reads from each Match Map's Tick Data (health, grenades carried, positions for the defuse race), not on the database's round rows. The fit and the Review then share one reading of a moment and can't drift apart. Only Tick Data with the economy and the Loadout is fitted on; the Review of an older Match Map reads those features as even.

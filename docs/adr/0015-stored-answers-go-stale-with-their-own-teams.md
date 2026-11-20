# A stored answer goes stale with its own Teams and Matches; the Pool only brings it round

ADR 0014 stamped every stored answer with one global data stamp. Any Match parsed anywhere moved it, so every one of the ~13,000 answers on production (two my teams, 89 opponents each) went stale after every Match. One full warm-up round costs about 24 hours of CPU on the 2-CPU host (the Game Plan's style 26 s × 1246, Playbooks 20 s × 1246, tabs 10 s × 1780, on 2026-11-20). With 28 Team Scouts queued, a Match was parsed every few minutes, so the round never finished and every page read «Шинэчилж байна». The page that had just been parsed waited behind thousands of pages nothing had changed for. Each round also rewrote every payload, and with `binlog_row_image=FULL` and 30-day binlogs the disk reached 100% on 2026-11-20. Redis then refused writes and the worker stopped. (Binlogs from the parses themselves, ~15 GB a day under Team Scouts, were most of that volume.)

A stamp now has two parts, `<fresh>~<pool>` (`answers.stamp`):

- **fresh**: what the answer reads of its own Teams and Matches, plus what every answer reads. The kind declares its `deps` from its parameters: `t:<team>` covers the Team's parsed Match Maps, Matches, Vetoes and Reviews at the current version, and its rows' edits. `m:<match>` covers one Match's Maps and Reviews. Every answer also reads the Ratings, Staff's declared roles, the Review model's version, the Active Duty Maps and, for a daily kind, the day. Only this part decides fresh or stale. A parse of Bravo against Charlie leaves Alpha vs Delta fresh.
- **pool**: where the Pools stood (`pool_cache.parse_stamp`, `review_pool.stamp`). When only this moved, the page still calls the answer fresh. The warm-up computes it again in its last turn, oldest first, and never before `POOL_MIN_AGE` (6 h), so each answer comes round every day or two.

The warm-up's order is: answers someone just read stale; then answers whose own data moved, the latest change first; then planned answers never computed; then the Pool's turn. After each Match a Scout parses (`tasks._warm_pool`) and after a Review refresh, the warm-up plans again, so that Match's two Teams' fixtures come first. It computes them while the next Match downloads, which needs no heavy permit.

Pages that read a Team alone are that Team's own answers, and every fixture shares them: its style and utility map by Map (`team.style`, `team.utility`), heatmaps, routes, roster and after-contact. Before, a fixture recomputed both Teams' style, and my team's utility map came out the same against all 89 opponents. The plan also covers v2's match list and each Match Map's report, and the match page's summary, agenda and audit for every my team's Match. It covers each fixture Team's heatmaps and routes at their first view. Other views are stored when first opened and kept current for 30 days.

An answer computed again that came out the same (`stored_answers.digest`, migration 0034) rewrites its stamp alone, never its payload. Production's MySQL keeps binlogs one day (`binlog_expire_logs_seconds=86400`) and logs no unchanged BLOB (`binlog_row_image=NOBLOB`), both `SET PERSIST`. Nothing replicates from it, and no backup reads the binlogs.

We chose per-Team stamps over a faster global round. No speed-up of a 24-hour round would keep up with a Match every few minutes, and the Match just parsed is the one Staff are about to open. Rejected alternatives:

- **Per-answer dependency rows.** Every row would list what it read. That is exact, but it is a second table to keep right, for little over Teams and Matches.
- **A Pool frozen once a night.** It would make Pool numbers consistent across pages, but every Pool cache and the Review tallies would need to split into a frozen Pool and the Team's live numbers.

Pool caches that only rank a Team or set a bar are cut at most every 6 h (`pool_cache.epoch_stamp`): the style Pool, the Tells' bars, the economy's worth of each choice. Cutting them per parse meant the whole Map's Rounds again after every Match a Scout parsed: style took 30 s a page on production. Each Team's own numbers are read from its Match Maps on every call (`style.own`), so its page is current while the others' stand where the Pool last cut them.

## Consequences

- A page's numbers against the Pool (percentiles, Pool priors, Levers judged against every Team) can be a day or two behind, while its Teams' own numbers are current. The page does not say so. Only a change to its own Teams marks it as being refreshed.
- A Briefing is refused (409) only when either of its fixture's two Teams moved (`gameplan.fixture_stamp`), not on any parse.
- Data an answer reads beyond its `deps` does not make it stale. Examples are a newcomer's last Team in a picked Lineup and an opponent's opponents. Such data only comes round in the Pool's turn. A new kind must declare what it reads, or leave `deps` out, in which case any change makes it stale (the old behaviour).
- Answers stored before this change, whose Teams have not changed since they were computed, are adopted with the current fresh part and no Pool part (`warmer.adopt_legacy`). The deploy therefore does not show every page as being refreshed.

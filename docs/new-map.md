# When a Map enters the Active Duty pool

A checklist for the day Valve swaps a Map into the pool (docs/plans/09 VIZ-11). Each step names the file and what breaks without it.

1. **The pool's dates.** Add the patch to `apps/api/app/data/patches.json` (`patches`: date, name, note) and the Map's period to `pool` (`[from, null]`), closing the period of the Map that left. Without it `map_pool.active_duty()` keeps the old seven, and the Forecast's veto, the Game Plan's map board and the Stratbook's rows follow it.
2. **The overview image.** Put Valve's 1024 px radar as `apps/public/public/radars/<map>.png` (and `<map>_lower.png` for a second floor). Without it the Replay, the heatmaps and a Strat's board draw on a dark background.
3. **The calibration.** Check the Map's `pos_x`, `pos_y` and `scale` in `CALIBRATION` (`apps/api/app/services/radar.py`); for two floors set `"lower": True` and, only once measured across several parsed Maps, `"split_z"` (the empty altitude band between the floors' clusters, as Nuke's −495 was). A wrong calibration shifts every dot on every picture.
4. **The Spots.** Draw the Map's polygons in `apps/api/app/data/spots/<map>.json` (first match wins; filter by Callout and altitude where floors overlap). Without them the Review names places by the game's Callouts only. Saving the file rebuilds that Map's Reviews only (`spots.version(map)`, VIZ-11).
5. **The Win probability.** A new Map has no `by_map` calibration in `apps/api/app/data/winprob.json` until refit (`npm run review:fit`, docs/adr/0007); its Reviews use the shared model meanwhile. Refit once it has some 15 parsed Maps, and compare with `--dry-run` first.
6. **The Pool.** Habits judged against the Map's Pool (Playbook, Style, the utility map) say little until several Teams have been parsed on it; the pages say so through their thin-sample marks. Scout the Teams you meet there first.
7. **After a patch to a Map already in the pool.** Recheck its Spots and calibration against the new radar (Cache had several patches; Dust II's mid changed), then `npm run data:rebuild` if the Replays or Callouts moved.

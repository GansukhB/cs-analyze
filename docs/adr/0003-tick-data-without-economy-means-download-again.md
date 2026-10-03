# Tick Data that lacks the economy is re-downloaded, not re-parsed

The Playbook needs each Team's Buy type and who carried which weapon, read from every Player's money, equipment value and inventory as each Round goes live. Tick Data written before schema 11 does not hold them. Tick Data can only give back what the parse wrote into it, so a stale Match Map whose Tick Data has no `economy` table counts as having no Tick Data: the next Scout that covers its Match downloads the Demo again. Every other stale map still re-parses from Tick Data (ADR 0002). We chose a one-time re-download over guessing buys from the weapons fired in kills and shots, because that guess misses every Player who never fired and cannot tell a Force from a Full. At 14 parsed maps, now is the cheapest time to do it.

## Consequences

- A Match Map outside every future Scout's Windows keeps its schema-10 analysis and has no economy. It still shows everywhere else, and each Scout covering its teams logs it as needing a download.
- The economy is read with demoparser at each Round's freeze end and stored as its own small table in the bundle, never as per-tick columns: per tick it would add seven columns to about 1.5 million rows per map.

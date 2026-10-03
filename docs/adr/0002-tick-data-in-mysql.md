# Everything a parse produces lives in MySQL; `data/` is scratch

The apps are headed for DigitalOcean App Platform, whose containers have no persistent disk. So nothing a page or a later parse needs may live on the filesystem: a Demo is downloaded, unpacked and parsed one Match at a time in a scratch directory, and its files are deleted when that Match is done, whether it parsed or not. The Tick Data of each Match Map (awpy's zipped parquet tables, about 10 MB a map, plus the flashbang and HE detonations the ingest also needs) is stored as a compressed BLOB in MySQL, and a stale Match Map is re-parsed from that BLOB instead of from its Demo. Replays and walked routes are cut from the Tick Data at ingest and stored as rows, so the API never reads Tick Data on a page view; heatmaps are drawn in the browser from kill coordinates. We chose MySQL BLOBs over object storage (Spaces/S3) to keep one stateful service to run and back up.

## Consequences

- The database grows by about 10 MB per parsed Match Map, and backups with it; at a few thousand maps object storage becomes the cheaper home, and moving there means changing where the BLOB is read and written, nothing else.
- A failed parse cannot be retried from disk: retrying means downloading the archive again.
- A change to how Replays or routes are cut from Tick Data needs them rebuilt from the stored BLOBs (a CLI command), not a re-download.

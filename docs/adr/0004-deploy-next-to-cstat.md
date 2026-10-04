# Production shares cstat's host, and cstat's worker is switched off

cs-analyze runs on cs.bizon.mn next to cstat, from `/home/cs2.bizon.mn`: the public app is static files nginx serves for cs2.bizon.mn, and the API is `cs2-api` behind cs2-api.bizon.mn, with the Celery worker as `cs2-worker`. Both use cstat's MySQL server and its `root` account (a database of their own, `cs_analyze`), and cstat's Redis and its ACL user (DBs 10, 11 and 12; cstat has 9). Ansible (`ansible/`) reads those credentials from the local cstat checkout's `.env.production` at deploy time, so no secret is committed here. JWT_SECRET is generated on the server once. We chose this over a host of our own because the host already runs everything this needs. But one Scout pipeline (Chromium plus demo parsing) takes most of the host's 7.3 GB, as cstat's does, so cstat's `celery-worker` is stopped and disabled: cstat's pages stay up, and its new jobs never run.

## Consequences

- A worker restart (every deploy, the OOM killer) can end a job midway. When `cs2-worker` starts, it purges its broker queue, fails any job still RUNNING and re-sends whatever was queued, and it ignores stale messages (`jobs.recover`, `tasks._recover`). That only holds while one worker consumes the queue, and while it runs the threads pool, so an OOM kill takes the whole process down and systemd restarts it.
- The public app is built on the deploying machine with `VITE_API_URL=https://cs2-api.bizon.mn`. The host has no Node.
- A deploy rsyncs the working tree, uncommitted changes included.
- Both names sit behind Cloudflare's proxy. The origin certificate is Let's Encrypt, issued over the webroot challenge (`ansible/certbot.yml`).

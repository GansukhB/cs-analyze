# 11. Платформ: найдвартай байдал, аюулгүй байдал, гүйцэтгэл

> Item-ийн ID: `OPS-…`. Баримтууд 2026-10-21-ний кодын аудитаас (локал DB, `npm run test:api`, `npm run lint`) авсан.

## Зорилго

Тэмцээний өмнөх шөнө coach Game Plan нээхэд ажилладаг байх. Дата алдагдахгүй байх: Demo parse хийсний дараа устдаг тул MySQL дахь Tick Data бол тэр тоглолтын цорын ганц хуулбар. Хувийн мэдээлэл задрахгүй байх: Scrim, тоглогчдын account нэмэгдэнэ (`01-workspace-access.md`). Шинэ ачаалал (upload, дэлхийн үр дүн, Rating-ийн тооцоо) одоогийн хуваалцсан host дээр багтах (grilling Q10).

## Одоогийн байдал

| Сэдэв | Байдал | Эх |
|---|---|---|
| Тест | 166 passed, 2 skipped (real demo, opt-in), 82 s. Бүгд in-memory SQLite. Frontend тест байхгүй | `npm run test:api` |
| Lint | ruff, oxlint, `tsc -b` бүгд цэвэр | `npm run lint` |
| CI | Байхгүй (`.github/` байхгүй) | repo |
| Deploy | Working tree-г rsync хийдэг (commit хийгээгүй өөрчлөлт ч орно). Test gate, rollback байхгүй. Deploy бүр worker-ийг restart хийж, ажиллаж буй Scout-ийг 600 s-ийн дараа алдаг | `ansible/`, `worker.service.j2:26` |
| Backup | **Огт байхгүй** | repo |
| Нууц задрал | **`GET /workers` нь `REDIS_BROKER_URL`-ыг бүтнээр нь буцаадаг. Production-д энэ URL дотор cstat-ийн Redis ACL нэр, нууц үг байгаа бөгөөд Jobs хуудас үүнийг нэвтэрсэн хэн бүхэнд харуулдаг** | `routers/jobs.py:156`, `JobsPage.tsx:24` |
| Эрх | cstat-ийн MySQL `root` account. Хоёр systemd unit `root`-ээр ажилладаг. Chromium sandbox-гүй (Playwright default) HLTV-ийн зартай хуудсуудаар ордог | ADR 0004, `browser.py:95-107` |
| Rate limit | `/auth/token` (оролдлого бүр argon2 hash), `/assistant/chat` хоёуланд нь байхгүй. Assistant-ийн хэрэглээг бүртгэдэггүй | `routers/auth.py`, `assistant.py` |
| Job-ийн хугацаа | Download `timeout=0`, bsdtar timeout байхгүй, Celery time limit байхгүй. Локал job 25,034 s "unpacking"-д гацсан | `browser.py:260,279`, `archive.py:146-151` |
| Review refresh | Scout-тэй нэг queue, нэг slot дээр. Тиймээс ADR 0008-д бичсэнээс өөрөөр Scout-ийн ард хүлээдэг | `review_pool.py:848` |
| `/workers` | Jobs хуудас 4 s тутам дуудаж, тэр бүрд 1 s-ийн Celery inspect ажиллуулдаг | `routers/jobs.py:172` |
| Хадгалалт | Локал 113 map = 1.44 GB (`tick_datasets` 1,248 MB), ~12.8 MB/map. Production-ийн ~355 map-ийг `pool_cache.py:7`-ийн тайлбарт дурдсан, тэгвэл ≈ 4.5 GB (тооцоо). 1,000 map ≈ 13 GB | information_schema |
| Хуучирсан derived | 93 bundle `derived_version` 4.1.1 дээр байна (одоогийнх 5.1.1). Тэднийг хамгийн түрүүнд нээсэн page request дотор rebuild хийдэг. Хуучирсан Review-г match page-ийн GET дотор rebuild хийдэг | `tickdata.ensure`, `review_view.py:21,113` |
| Frontend | 520 KB нэг JS chunk. Query retry унтраастай. 5xx алдаа "олдсонгүй" гэж харагддаг | `main.tsx:9` |
| Бусад | Production-д `/docs` нээлттэй. WebSocket DB session-ийг барьсаар байдаг. Dead code: `REPARSE_MAP`, `ANALYSING`/`RENDERING` stage, `AnalysisArtifact` (0 мөр) | `main.py:10`, `routers/jobs.py:194-234` |

## Шийдэл

### OPS-1. Яаралтай засвар (P0, S)

> **Төлөв:** ✅ `bcd3813` (improvement-01).

Нэг PR-д багтах, эрсдэлгүй засварууд:

1. **`/workers`-ийн нууц:** broker URL-аас нэр, нууц үгийг хасна (`redis://***@host:port/db`). Celery inspect-ийн оронд worker-ийн бичдэг `system:worker` heartbeat key-г уншина. Тэгвэл 4 s тутмын inspect хэрэггүй болно.
   - Production-д энэ URL нэвтэрсэн хэрэглэгч бүрт харагдаж байсан. Тиймээс cstat-ийн Redis ACL нууц үгийг солих хэрэгтэй. Энэ cstat-ийн `.env.production`-д ч нөлөөлөх тул хүн шийдэж хийх алхам.
2. **Гацахаас хамгаалах:** download-д watchdog тавина (120 s байт ирэхгүй бол abort). Item бүрт хугацааны хязгаар: download 30 мин, bsdtar 10 мин (`subprocess.run(timeout=)`), parse 15 мин. Хязгаар хэтэрвэл тэр Match fail болж, Scout үргэлжилнэ.
3. **Review refresh:** `refresh_reviews`-ийг өөрийн queue-д (`-Q reviews`) гаргаж, тусдаа thread дээр ажиллуулна. Lock TTL-ийг heartbeat-аар сунгадаг болгоно. Ингэвэл ADR 0008-д бичсэнтэй таарна.
4. **Rate limit:** nginx `limit_req`-ийг `CF-Connecting-IP`-ээр түлхүүрлэж тавина: `/auth/token`-д 10 r/m, `/assistant/chat`-д 20 r/m. Апп талд Username тус бүрээр тоолуур нэмнэ (WS-6).
5. **`/docs`, `/openapi.json`:** production-д хаана (`docs_url=None`, тохиргоогоор).
6. **WebSocket:** snapshot илгээсний дараа DB session-ийг хаана.

**Хүлээгдэх үр дүн:** Jobs хуудсанд нууц харагдахгүй. Гацсан download 2 минутын дотор fail болно. Review refresh Scout-ийн ард хүлээхгүй.

### OPS-2. Backup ба сэргээлт (P0, S–M)

> **Төлөв:** ✅ `73d00eb` (improvement-01). Host-оос гадуурх хуулбар (rclone) нь тохиргоогоор асна.

- **Өдөр бүр:** `tick_datasets`-аас бусад бүх хүснэгтийн `mysqldump --single-transaction --hex-blob | zstd` (жижиг, хэдэн зуун MB).
- **Tick Data:** `tick_datasets` бараг зөвхөн нэмэгддэг (append-only). Тиймээс шинэ болон өөрчлөгдсөн мөрүүдийг (`id`/`updated_at`-аар) өдөр бүр тусдаа файлаар гаргаж, сард нэг удаа бүтэн dump хийнэ. Bundle аль хэдийн шахагдсан тул zstd бараг үр дүнгүй.
- **Хадгалах газар:** host-оос гадуур, бага төсөвтэй object storage руу `rclone`-оор. Жишээ нь Cloudflare R2-ийн үнэгүй tier, Backblaze B2, Hetzner Storage Box.
- **Хадгалах хугацаа:** 7 өдрийн, 4 долоо хоногийн, 6 сарын хуулбар.
- **Хэрэгжүүлэлт:** Ansible `backup.yml` ба systemd timer. Амжилтгүй бол alert (OPS-5).
- **Сэргээлтийн дасгал:** сар бүр хуулбарыг түр DB-д сэргээж, `alembic check` болон `GET /health` шалгана. Хугацааг нь тэмдэглэнэ.

### OPS-3. CI ба deploy gate (P0, S–M)

> **Төлөв:** ✅ `b9c4143` (improvement-01).

GitHub Actions (`.github/workflows/ci.yml`):

1. `npm run lint`.
2. `npm run test:api` (~90 s, service хэрэггүй).
3. MySQL 8.4 service дээр `alembic upgrade head && alembic check`, MySQL-д онцлог тестүүд: `utf8mb4_bin`, generated column, error 3065. Local job 2 MySQL-ийн алдаагаар унаж байсан бөгөөд SQLite тест үүнийг барьж чадаагүй.
4. `npm run openapi`-ийн дараа `git diff --exit-code packages/openapi apps/public/src/api`: commit хийсэн contract кодтой таарч байгааг шалгана.
5. `vite build` (bundle-ийн хэмжээг тэмдэглэнэ).

Deploy:

- `npm run deploy` нь цэвэр биш tree-г (`git status --porcelain`) татгалзана, CI амжилттай болсон commit-ийг л deploy хийнэ.
- Deploy-оос өмнө `/system`-ээс ажиллаж буй Scout байгаа эсэхийг шалгана. Байвал хүлээх эсвэл асууна.
- Deploy хийсэн commit-ийн hash-ийг footer-т харуулна.
- `REPLAY_SCHEMA`, `REVIEW_SCHEMA` зэрэг version өөрчлөгдсөн бол deploy-ийн дараа `data:rebuild`, `review:rebuild`-ийг background queue-д хийнэ. Ингэвэл хамгийн түрүүнд нээсэн хүн rebuild-ийг хүлээхгүй (OPS-8).

### OPS-4. Хамгийн бага эрх (P1, M)

> **Төлөв:** 🟡 `94c4b86` (improvement-01). Өөрийн MySQL account (`deploy:db-user`), worker-т OOMScoreAdjust, `-e harden=true`-ээр MemoryMax ба ProtectSystem, JWT солих журам (ADR 0012). Root биш service user, Redis ACL үлдсэн. Deploy хийгээгүй.

- MySQL дээр зөвхөн `cs_analyze.*` эрхтэй тусдаа user, Redis-д тусдаа ACL user үүсгэнэ (ADR 0004-ийн "root account"-ыг шинэ ADR-аар солино).
- systemd: `User=cs2`, `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ReadWritePaths=/home/cs2.bizon.mn/data`. Worker-т `MemoryMax=3500M`, `OOMScoreAdjust=500` тавина. Санах ой дутвал OOM killer MySQL биш worker-ийг алах ёстой (production-д OOM аль хэдийн тохиолдсон, `browser.py:187-190`).
- Root биш user дээр Chromium-ийг `chromium_sandbox=True`-тэй ажиллуулна.
- JWT secret-ийг солих журам бичнэ: солиход бүх token хүчингүй болно гэдгийг баримтжуулна.

### OPS-5. Ажиглалт ба alert (P1, S–M)

> **Төлөв:** 🟡 `bf55894` (improvement-01). Telegram alert (тохиргоотой үед), 5 минут тутмын watch (heartbeat, stage 45 мин, диск 85%, HLTV 3 удаа блок), backup/worker OnFailure, долоо хоног бүрийн canary, Assistant-ийн хязгаар; Jobs хуудсанд stage-ийн медиан. Sentry ба гадны uptime account шаардана. Deploy хийгээгүй.

- **Алдаа:** Sentry-ийн үнэгүй tier эсвэл self-hosted GlitchTip. Backend, worker, frontend гурвуулаа.
- **Alert:** Telegram bot (үнэгүй, багийнхан аль хэдийн хэрэглэдэг) дараах тохиолдлуудад мэдэгдэнэ:
  - worker-ийн heartbeat 2 минутаас удаан алга болох
  - нэг stage 45 минутаас удаан үргэлжлэх
  - диск 85%-аас дээш дүүрэх
  - backup амжилтгүй болох
  - Cloudflare-ийн challenge дараалан 3 удаа амжилтгүй болох
  - HLTV-ийн selector canary унах (OPS-9)
  - Assistant-ийн өдрийн зардлын хязгаар хэтрэх
- **Job-ийн хэмжүүр:** `stage_log`-оос download-ийн хурд (MB/s), parse-ийн хугацааг `/system` хуудсанд trend болгон харуулна. Одоогийн median: archive 567 MB, download 273 s (2.1 MB/s), unpack 23 s, map бүрийн parse 8 s. Шинэ Match ~5 мин, үүний 88% нь download.
- **Uptime:** гаднаас ping хийх үнэгүй үйлчилгээ (UptimeRobot, Better Stack) `cs2.bizon.mn`, `cs2-api.bizon.mn/health` хоёрт.

### OPS-6. Queue ба нөөцийн хуваарилалт (P0, M; DATA-1 ба DATA-2-ийн өмнөх нөхцөл)

> **Төлөв:** ✅ `21e244d` (improvement-01). `hltv` queue-г тусад нь салгаагүй: Scout-ууд `celery` queue-д single-flight хэвээр.

Шинэ ажлууд нэмэгдэнэ: upload parse, үр дүн ба хуваарь унших, Rating-ийн тооцоо. Тэдгээр нэг slot дээр Scout-ийн ард хүлээж болохгүй. Гэхдээ 7.3 GB-ийн хуваалцсан host дээр хоёр parse зэрэг явбал OOM болно.

| Queue | Юу | Зэрэг ажиллах тоо | Тайлбар |
|---|---|---|---|
| `hltv` | HLTV-тэй харьцах бүх зүйл: Scout, үр дүн, хуваарь, roster | 1 | Нэг Chromium, Cloudflare-ийн хязгаар. Хуваарь, үр дүн унших ажил download-оос түрүүлнэ (priority), item хооронд солигдоно |
| `parse` | Upload parse, `_reparse`, `data:rebuild` | 1 | Redis semaphore `heavy` (1 permit)-ийг `hltv`-ийн parse алхамтай хуваалцана. Download сүлжээнээс хамаардаг тул parse-тай зэрэг явж болно |
| `light` | `refresh_reviews`, Rating fit, Forecast-ийн дүгнэлт, Pool warm | 1 | Санах ой бага |

Celery-ийн `task_routes`, worker бүрт `-Q`. Одоогийн `--pool=threads` хэвээр.

### OPS-7. Хадгалалтын өсөлт (P1 төлөвлөгөө, P2 хэрэгжүүлэлт, M)

> **Төлөв:** 🟡 `8985393` (improvement-01). Хэмжилт (2026-10-21, локал): 113 map, `tick_datasets` 1.25 GB (bundle дундаж 11.2 MB, walks ~150 KB), `replay_rounds` 90 MB (раунд бүр ~29 KB + токен 1.3 KB), Review ~19 KB/map; бусад хүснэгт нийт <150 MB. Bundle-ийг зөвхөн `tickdata.load_bundle`/`store`-оор уншиж бичдэг болсон. Object storage руу шилжүүлэлт босго хүрэхэд (P2).

- **Тооцоо:**
  - Одоо ~12.8 MB/map.
  - Scrim: долоо хоногт 15–25 map гэвэл сард ~1 GB.
  - Дэлхийн үр дүн (DATA-2): мөр л тул хэдэн арван MB.
- **Шилжих босго:** MySQL-ийн дата 25 GB хүрэх эсвэл диск 70% дүүрэх. Тэр үед `tick_datasets.bundle`-ийг object storage руу (R2 эсвэл B2) шилжүүлнэ. ADR 0002 үүнийг урьдчилан хэлсэн.
- **Одооноос бэлдэх:** bundle-ийг зөвхөн `tickdata.load_bundle(match_map_id)`, `store_bundle()` гэсэн хоёр функцээр дамжуулж уншиж бичдэг болгоно. Тэгвэл шилжүүлэлт нэг модульд л хийгдэнэ.
- **Хэмжээ хэмнэх:** ticks нь bundle-ийн 78%. Хуучин Scrim-ийн ticks-ийг 32 Hz болгож багасгах сонголтыг тусдаа ADR-аар шийднэ. Review-д дэлгэрэнгүй хэрэгтэй тул default-аар хийхгүй.
- **Scrim:** Staff Scrim-ийг устгаж чадна. Хадгалах хугацааны бодлогыг босго хүрэхэд шийднэ.

### OPS-8. Гүйцэтгэл (P1, M)

> **Төлөв:** 🟡 `820d389` (improvement-01). Model хуучирсан Review-г хуучнаар нь үзүүлж worker-т rebuild өгнө; Server-Timing; lazy route (main 702→328 KB); 404/5xx ялгаа, retry 1; skeleton. Tick Data-ийн cut inline хэвээр.

- **Page request дотор rebuild хийхгүй:** хуучирсан Review болон derived-ийг background-д rebuild хийж, тэр хооронд хуучин хувилбарыг "шинэчлэгдэж байна" гэсэн banner-тай харуулна.
- **Game Plan:** tab бүрийн p95 хугацааг `Server-Timing` header-ээр хэмжинэ. Хэрэв tab 10 s-ээс удаан бол cache warm хийх дарааллыг өөрчилнө. Pool аль хэдийн Redis-д хуваалцагддаг.
- **Frontend:**
  - Replay, Game Plan, Assistant-ийг route-ийн түвшинд lazy болгоно (code splitting).
  - 5xx болон сүлжээний алдаанд `retry: 1` тавьж, 404-ийг бусад алдаанаас ялгана. Одоо Cloudflare-ийн 52x алдаа «Баг олдсонгүй» гэж харагддаг.
  - Текстэн loader-ийг skeleton-оор солино.

### OPS-9. Тестийн стратеги (P1, M, тасралтгүй)

> **Төлөв:** 🟡 `99d1db6` (improvement-01). Vitest (filters, format, lineup, heatmap, Round token) CI-д; model baseline-ийн regression тест; opt-in browser smoke тест (давхар key олсон); `hltv:canary`. Rating backtest-ийн CI ажиллуулалт data шаардана.

- CI-ийн MySQL job (OPS-3).
- **HLTV selector canary:** долоо хоног бүр мэдэгдэж буй results болон match хуудсыг уншиж, selector-ууд ажиллаж байгааг шалгана. Одоо HLTV markup-аа өөрчилбөл Scout "SUCCESS, 0 Match" гэж дуусна.
- **Detector-ийн fixture тест:** Finding бүрт нэг Round, Swing-ийн нийлбэр тэг байх invariant, defuse-ийн timeline (`07-review-development.md` RV-1, RV-3).
- **Rating, Forecast:** backtest-ийн регресс тест. Шинэ model хуучнаасаа муу log loss өгвөл CI анхааруулна (`03-ratings-forecast.md`).
- **Frontend:** `filters.ts`, `lineup.ts`, `review/format.ts`, heatmap-ийн density-д Vitest. Таван гол замын Playwright smoke тест: Scout → Game Plan, Review, Player page, Briefing, нэвтрэлт.

### OPS-10. Цэвэрлэгээ (P2, S)

> **Төлөв:** 🟡 `41eeede` (improvement-01). Assistant-ийн hex өнгө token болсон; `lang="mn"` байсан. Dead code (REPARSE_MAP, AnalysisArtifact) prod-ийн датаг шалгасны дараа; хоёр Chip-ийг нэгтгэх, UI текстийн толь үлдсэн.

- Dead code-ийг устгана: `REPARSE_MAP`, `ANALYSING`/`RENDERING`, `AnalysisArtifact` (эсвэл Briefing-ийн PDF-д ашиглана).
- Assistant-ийн hex өнгийг palette token болгоно (`Assistant.tsx:403,480,482,548,691`). Хоёр өөр Chip component-ийг нэгтгэнэ.
- `<html lang="mn">` болгоно. Англи, монгол холилдсон UI текстийг нэг толь бичигт оруулна (`10-assistant.md`-ээс тусдаа, UI-ийн текст).

## Дараалал

1. OPS-1, OPS-2 энэ долоо хоногт. Нууц задрал ба backup байхгүй байдал бол хамгийн том эрсдэл.
2. OPS-3: шинэ том ажил (Workspace, upload) эхлэхээс өмнө.
3. OPS-6 (P0): DATA-1 (upload) ба DATA-2 (үр дүн)-оос өмнө.
4. OPS-4, OPS-5, OPS-8 P1-ийн дунд.
5. OPS-7: босго хүрэхэд. OPS-9 тасралтгүй. OPS-10 боломж гарах үед.

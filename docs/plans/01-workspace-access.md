# 01. Workspace, эрх, хуваалцах

> Нэр томъёо: `CONTEXT.md` (Workspace, My team, User, Staff, Scrim, Forecast, Briefing, Development plan). Шийдвэр: ADR 0010, 0011. Item-ийн ID (`WS-…`) README-ийн roadmap-д ашиглагдана.

## Зорилго

Одоо нэг клуб (The Huns) ашиглана. Гэхдээ клубын хувийн дата эхний өдрөөс нь тухайн клубын **Workspace**-д харьяалагдана: Scrim, upload хийсэн Match, тэмдэглэл, Stratbook, Briefing, Forecast-ыг хэн харах. Ингэснээр хоёр дахь клуб орж ирэхэд query бүрийг дахин шалгах шаардлагагүй (ADR 0011). Тоглогчид өөрсдөө нэвтэрч өөрийн Review, Focus point, Development plan-аа харна. Staff Game Plan-аас Briefing бэлдэж багтаа өгнө.

Дасгалжуулагчийн үүднээс гол ач холбогдол: тоглогч бүр "юун дээр ажиллах вэ" гэдгээ өөрийн дэлгэцээс харна. Ингэснээр coach хуудас бүрийг screenshot хийж Discord-оор явуулах шаардлагагүй болно. Нөгөө талаас тоглогчийн сэтгэл зүйд нөлөөлж болох зүйлийг (бага Forecast, бусдын сул тал) Staff шүүж өгнө.

## Одоогийн байдал

- `users` (`apps/api/app/models/user.py`): `id`, `username` (`utf8mb4_bin`), `password_hash`, `is_active`, `created_at`. Эрхийн ялгаа огт байхгүй. Нэвтэрсэн хүн бүр бүх хуудсыг харж, Scout эхлүүлж, зогсоож чадна.
- Хэрэглэгчийг зөвхөн CLI-аар үүсгэнэ (`npm run user:create`, `app/cli.py`). Бүртгүүлэх endpoint байхгүй.
- `POST /auth/token` (`app/routers/auth.py`) нь 24 цагийн JWT өгнө. Апп түүнийг `localStorage`-д хадгална (ADR 0001). `get_current_user` (`app/deps.py:31`) хүсэлт бүрт User-ийг дахин уншдаг. Тиймээс deactivate хийхэд шууд хүчингүй болно.
- Хувийн дата гэж байхгүй: HLTV-ийн Team, Match, Match Map, Review, Game Plan бүгд нийтлэг.
- `matches.hltv_id` нь `NOT NULL UNIQUE` (`app/models/source.py`). HLTV-д байхгүй, upload хийсэн Match-ийг хадгалах боломжгүй (→ `02-data-sources.md`, DATA-1).
- `analysis_jobs.requested_by_id` нь хэн Scout эхлүүлснийг хадгалдаг. Гэхдээ жагсаалтыг хэрэглэгчээр шүүдэггүй.

## Дутуу зүйл

1. Workspace, my team гэсэн ойлголт кодод байхгүй. "My team"-ийг Scout бүрт гараар бичдэг (`my_team_name`).
2. Staff, тоглогч гэсэн ялгаа байхгүй. Тоглогчид нэвтрэх эрх өгвөл Forecast, эсрэг багийн тайлан, Scout удирдлага бүгд нээлттэй болно.
3. Хувийн дата (Scrim, тэмдэглэл, Strat) нэмэгдэх үед түүнийг хамгаалах scope helper байхгүй.
4. Хэрэглэгчийг зөвхөн серверийн хандалттай хүн үүсгэдэг. Тоглогч нэмэх, нууц үг сэргээх бүрт хөгжүүлэгч хэрэгтэй болно.
5. Хуваалцах арга байхгүй: Game Plan амьд тооцоолол учраас өнөөдөр харсан зүйл маргааш өөрчлөгдөнө. Тоглогчдод тогтвортой хувилбар (Briefing) хэрэгтэй.

## Харагдах байдлын дүрэм

Default дүрэм. Staff үүнийг Briefing болон Development plan-аар өргөтгөнө.

| Дата | Staff | Player User | Өөр Workspace |
|---|---|---|---|
| HLTV-ийн Team, Match, Match Map, Review, Replay | Бүгд | Зөвхөн өөрийн my team-ийн Match Map (Review нь default-аар өөрөөр нь шүүгдсэн) | Бүгд |
| Upload хийсэн official Match (ADR 0011) | Бүгд | Өөрийн my team-ийнх | Харагдахгүй (404) |
| Scrim (ADR 0010) | Бүгд | Өөрийн оролцсон Scrim-ийн Review, Replay | Харагдахгүй |
| Game Plan, Playbook, Scout | Бүгд | Харагдахгүй. Зөвхөн хуваалцсан Briefing | Өөрийн |
| Forecast, Rating | Бүгд | Зөвхөн Briefing-д Staff оруулсан бол | Өөрийн Forecast |
| Focus point, Development plan | Бүх тоглогчийнх | Зөвхөн өөрийнх | Харагдахгүй |
| Stratbook, Strat | Бүгд | Staff хуваалцсан Strat (read-only) | Харагдахгүй |
| Assistant | Бүрэн | P2: зөвхөн өөрийн датаны тухай | Өөрийн |

## Шийдэл

### WS-1. Workspace ба my team (P0, M)

> **Төлөв:** ✅ `ac9d497` (improvement-01).

**Хүснэгт** (нэг Alembic migration, `0010_workspaces`):

- `workspaces`: `id` BIGINT, `public_id` CHAR(32), `name` VARCHAR(120), `created_at`.
- `workspace_teams`: `workspace_id`, `team_id`, `label` VARCHAR(40) ("main", "academy" гэх мэт, заавал биш), `created_at`. `UNIQUE(workspace_id, team_id)`, нэр нь `uq_ws_team`.
- `users`: нэмэх багана `workspace_id` (backfill хийсний дараа `NOT NULL`), `role` VARCHAR(12) (`staff` | `player`, Django шиг check-гүй `StrEnum`), `player_id` (nullable FK → `players`, `role=player` үед заавал), `last_login_at`.
- Backfill: "The Huns" Workspace үүсгэж, одоо байгаа бүх User-ийг түүний Staff болгоно. The Huns-ийг my team болгоно.

**Код:**

- `app/deps.py`: `CurrentUser`-ийг `Viewer` (user, `workspace_id`, `role`, `player_id`, my team-ийн id-ууд) болгон өргөтгөнө. `StaffOnly` dependency нэмнэ.
- `app/services/scope.py` (шинэ): `visible_matches(viewer)` нь `Match.workspace_id IS NULL OR Match.workspace_id = :ws` нөхцлийг буцаана. Player User-д my team-ийн Match-аар нэмж шүүнэ. Match, Match Map, Round уншдаг router бүр үүгээр дамжина. `dbctx.using(db)`-тэй адил `scope.using(viewer)` контекст гаргаж, `gameplan`, `playbook`, `roles`… модулиуд `scope.current()`-ийг уншина. Ингэснээр cstat-аас ирсэн session-гүй гарын үсгүүд хэвээр үлдэнэ.
- `GET /gameplan/...`, `POST /jobs`, `POST /jobs/{id}/stop` зэрэг өөрчлөлт хийх эсвэл Staff-д зориулсан endpoint бүр `StaffOnly`-оор хамгаалагдана.
- Scout-ийн форм my team-ийг жагсаалтаас сонгодог болно (одоо гараар бичдэг).

**Хүлээгдэх үр дүн:** одоогийн хэрэглэгчдэд юу ч өөрчлөгдөхгүй. Шинэ тест: route бүрийг Player User-ийн token-оор дуудаж 403/404 шалгана. Мөн Workspace B-д upload хийсэн Match-ийг Workspace A id-аар нь авч чадахгүй (404) гэдгийг шалгана.

### WS-2. Pool ба cache-ийн Workspace хамаарал (P0, S, DATA-1-ийн дараа)

> **Төлөв:** ✅ `50da541` (improvement-01). `scope.py` нь Match ба MatchMap-ийн бүх ORM query-д нэг шүүлтүүр нэмнэ. Cache-ийн түлхүүрт `scope.cache_part` нэмэгдэнэ.

ADR 0011-ийн дагуу upload хийсэн official Match тухайн Workspace-ийн Pool-д л орно. Workspace-д upload байхгүй бол Pool нь өнөөдрийнх шиг нийтлэг байна, cache ч хуваалцагдана. Upload байгаа бол:

- `pool_cache`-ийн түлхүүр: `pool:roles:v<POOL_SCHEMA>:<hash>`-ийн hash-д Workspace-ийн харагдах Match Map-ууд орно. Hash нь Match Map-ийн жагсаалтаас тооцогддог учраас загвар өөрчлөгдөхгүй, зөвхөн оролт нь өөр болно.
- Game Plan-ийн `gp:v9:…:<stamp>` дээр `:<ws>` нэмнэ (зөвхөн upload-тай Workspace-д). Version-ийг `v10` болгоно.
- `review_pool.stamp()` мөн адил.
- Scrim аль ч Pool-д орохгүй (ADR 0010).

### WS-3. Урилга ба гишүүдийн удирдлага (P1, M)

> **Төлөв:** ✅ `5e037c3` (improvement-01). Урилгын линкийг frontend нь `window.location.origin`-оор угсарна, тохиргоо шаардлагагүй.

- `invites`: `id`, `workspace_id`, `token_hash` (SHA-256), `role`, `player_id` (nullable), `created_by_id`, `expires_at` (7 хоног), `used_at`, `used_by_id`.
- `POST /workspace/invites` (Staff): урилга үүсгээд `https://cs2.bizon.mn/invite/<token>` линк буцаана. `POST /invites/{token}/accept` нь Username, нууц үг авч User үүсгэнэ. Нэг удаагийн, хугацаатай.
- `GET /workspace/members`, `PATCH /workspace/members/{id}` (идэвхгүй болгох, Player холбох, role солих). Staff өөрийгөө идэвхгүй болгож чадахгүй, сүүлийн Staff-ыг ч мөн адил.
- Нууц үг мартсан бол Staff шинэ урилга (reset) үүсгэнэ. Имэйл огт шаардлагагүй.
- CLI: `npm run workspace:create -- <name> <first-staff-username>`. Одоогийн `user:create`, `deactivate`, `activate` нь `--workspace` авдаг болно.
- Frontend: `/workspace` хуудас (Staff): my team-үүд, гишүүд, урилгууд.

### WS-4. Тоглогчийн нүүр хуудас (P1, M, RV-9-тэй хамт)

> **Төлөв:** ✅ `98eaa23` (improvement-01). Development plan-ийн KPI (RV-9) хийгдсэний дараа энэ хуудсанд нэмэгдэнэ.

Player User нэвтрэхэд `/me` руу орно:

- Миний сүүлийн Match Map ба Scrim-үүд: Review нь `?player=<steamid>` шүүлттэй нээгдэнэ (одоогийн `src/review/filters.ts`).
- Миний Focus point-ууд (сүүлийн 5 Match Map-аас, Swing-ээр эрэмбэлсэн), Development plan болон түүний KPI-ийн явц (→ `07-review-development.md`).
- Надад хуваалцсан Briefing ба Strat-ууд.
- Navigation-ийг role-оор нь багасгана: Teams, Gameplan, Jobs цэс Player-т харагдахгүй.

### WS-5. Briefing: Game Plan-аас тогтвортой хуваалцах хувилбар (P1, M)

> **Төлөв:** ✅ `14e460f` (improvement-01). PDF (GP-7) ба «Төлөвлөгөө ажилласан уу» (GP-8) үлдсэн; хэвлэх CSS бэлэн.

Game Plan амьд: Match Map нэмэгдэх бүрт тоо нь өөрчлөгдөнө. Тоглогчдод "мягмар гарагт тохиролцсон төлөвлөгөө" хэрэгтэй.

- `briefings`: `id`, `public_id`, `workspace_id`, `fixture` (`my_team_id`, `opponent_id`, lineup-ууд), `match_id` (nullable, хуваарьт тоглолттой холбоно), `title`, `payload` (gzip JSON: сонгосон panel-ууд, Map бүрийн Playbook-ийн мөрүүд, Staff-ын тэмдэглэл), `include_forecast` BOOL, `created_by_id`, `created_at`, `shared_at`.
- Game Plan хуудсанд "Briefing бэлдэх" товч: Map бүрээс мөр сонгох, тэмдэглэл бичих, "Forecast оруулах" checkbox (default нь унтраастай, Q15). Хадгалах үед panel-ийн JSON хөлдөнө.
- Тоглогч `/me` болон `/briefings/:id` дээр уншина. Хэвлэх (print CSS) болон PDF (P2, `06-game-plan.md` GP-7).
- Тоглолтын дараа Briefing → "Төлөвлөгөө ажилласан уу" харьцуулалт (GP-8).

### WS-6. Нэвтрэлтийг бэхжүүлэх (P1, S)

> **Төлөв:** ✅ `1e67e76` (improvement-01). Rate limit нь OPS-1-д хийгдсэн.

Тоглогчид нэвтрэх болсноор account-ын тоо, төхөөрөмж нэмэгдэнэ. ADR 0001-ийн эрсдэл (XSS-ээр token хулгайлагдах) өснө.

- `POST /auth/token`-д Redis дээр rate limit тавина: Username болон IP тус бүрээр 15 минутад 10 удаа.
- Token-ийн хугацааг 24 цагаас 12 цаг болгоно. Нууц үг хамгийн багадаа 10 тэмдэгт байна.
- nginx-ээр `Content-Security-Policy` тавина (`script-src 'self'`, API-ийн host, ElevenLabs).
- P2 (хоёр дахь клуб орж ирэхэд): httpOnly cookie, CSRF руу шилжих эсэхийг шинэ ADR-аар шийднэ. ADR 0001-ийг supersede хийнэ.

### WS-7. Audit log (P2, S)

> **Төлөв:** ✅ `9e505fd` (improvement-01). `audit_events`: гишүүний эрх/идэвх (CLI-ээс ч), урилга үүсгэх/цуцлах/ашиглах, Briefing хуваалцах/устгах, Strat ба Playlist устгах. Workspace хуудсанд. Нууц хэзээ ч бичигдэхгүй.

`audit_events`: хэн хэнийг урьсан, идэвхгүй болгосон, Briefing хуваалцсан, Scrim устгасан гэх мэт. Олон клуб болох үед итгэлцэлд хэрэгтэй.

## Дараалал

1. WS-1 (бусад хувийн дата бүгд `workspace_id`-аас хамаарна) → DATA-1 (upload) → WS-2.
2. WS-6-ийн rate limit ба CSP-г тоглогчдод урилга явуулахаас өмнө хийнэ → WS-3 → WS-4, WS-5.
3. WS-7 олон клуб болох үед.

## Эрсдэл

- **Нэвчилт (leak):** хувийн дата уншдаг query scope helper-ийг алгасвал Scrim өөр Workspace-д харагдана. Хариу арга: scope-ийг router-ийн түвшинд биш, service-ийн түвшинд (`scope.current()`) хэрэгжүүлнэ. Мөн route бүрийг хоёр Workspace, хоёр role-оор дууддаг parametrized тест бичнэ.
- **Cache-ийн хуваагдал:** Workspace бүр өөрийн Pool-той болбол Redis-ийн ачаалал нэмэгдэнэ. Одоо нэг Workspace учраас асуудалгүй. Upload-гүй Workspace-ууд нийтлэг cache-ээ хуваалцана.

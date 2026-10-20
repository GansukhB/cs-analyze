# 02. Дата эх сурвалж: upload, дэлхийн үр дүн, хуваарь, roster, FACEIT

> Item-ийн ID: `DATA-…`. Нэр томъёо: Demo, Demo part, Match, Match Map, Scrim, Workspace, Tick Data, Scout, Window (`CONTEXT.md`). Шийдвэр: grilling Q2, Q5, Q7, Q9, Q13; ADR 0010, 0011. Эх сурвалжийн баримтыг 2026-10-21-нд шалгасан (`12-research-sources.md`).

## Зорилго

- **Өөрийн баг:** Scrim, HLTV-д ороогүй official тоглолтоо оруулна. Ингэснээр Review, Replay, хөгжлийн KPI-д хамгийн их датаг ашиглана.
- **Forecast:** дэлхийн бүх багийн үр дүнг (demo-гүй) цуглуулж Rating тооцно (`03`).
- **Цаг алдахгүй:** удахгүй болох тоглолт, roster-ийн өөрчлөлтийг автоматаар мэдэж Scout-ийг урьдчилан ажиллуулна.
- **Нэмэлт эх:** дараа нь FACEIT-ээр нэмэлт demo, тоглогчийн хувийн форм авна.

**Дараалал (Q5):** HLTV үндсэн эх хэвээр. ① upload → ② хуваарь, roster, ranking → ③ FACEIT, Premier.

## Одоогийн байдал (кодын аудит, 2026-10-21)

**HLTV-ээс уншдаг хуудсууд:**

- `/` (Cloudflare cookie)
- `/search`
- `/results?team=<id>`: зөвхөн эхний хуудас
- match page: зөвхөн `/download/demo/` линк
- download

**Огт уншдаггүй:**

- rankings, upcoming, team, player, event хуудсууд
- match page дээрх veto, формат, Map бүрийн оноо, lineup, LAN

**Window:**

- Хамгийн ихдээ 5 Match, үргэлж хамгийн сүүлийн N (`config.py:46-47`). Огноо, offset-оор сонгох боломжгүй.
- Demo-гүй Match ч слот эзэлдэг. Түүнийг нөхөж өөр Match авдаггүй.

**Хурд:**

- Шинэ Match ~5 мин: archive 567 MB, download 2.1 MB/s, unpack 23 s, Map бүрийн parse 8 s. Хамгийн ихдээ цагт ~12 шинэ Match.
- Нэг slot. Prod worker `--concurrency=1`.

**Хуучирсан дата (re-download debt):**

- Локал 113 Map-аас 104 нь Loadout-гүй. Scout бүр тэдгээрийн Match-ийг дахин татна (ADR 0005).
- 107 нь Sighting-гүй (ADR 0006).
- 9 нь schema 10, эдийн засаггүй.

**Upload:** боломжгүй.

- `matches.hltv_id` нь `NOT NULL UNIQUE`.
- `ingest_map` нь `demo.match`-аар түлхүүрлэгддэг (`analysis_store.py:264-271`).
- nginx `client_max_body_size` 10 MB (`nginx.conf.j2:64`).
- Cloudflare Free/Pro-ийн нэг хүсэлтийн хязгаар 100 MB. Map-ын `.dem` 230–470 MB.

**Автоматжуулалт:** Celery beat, cron, watcher огт байхгүй.

**Parse-ийн хувилбарууд:**

- awpy 2.0.2, demoparser2 0.42.0 (`uv.lock`).
- demoparser2 #362: pawn index ≥2048 тоглогчийн бүх prop null болдог. Perfect World-ийн demo дээр гарсан, main дээр засагдсан ч release хийгдээгүй.
- awpy 3.0 (2026-10-14) Rust дээр бүрэн дахин бичигдсэн. 3.1 (10-17) multipart demo-г шууд уншдаг.

**Локал хамрах хүрээ:** The Huns-ийн 2026-06-25–10-05 хооронд хадгалсан 15 Match бүгд HLTV-ийн demo-той. Гэтэл VRS тэр хугацаанд Huns-ийн 37 Match тоолсон. Тиймээс сул тал нь HLTV-ийн хамрах хүрээ биш, Scout хэр их татдагт байна.

## Шийдэл

### DATA-1. Өөрийн demo upload: Scrim ба HLTV-д ороогүй official (P0, эхний хувилбар M, бүтэн L)

**Өгөгдлийн загвар** (migration, WS-1-ийн дараа):

- `matches`:
  - `hltv_id`-ийг nullable болгоно. MySQL-ийн UNIQUE олон NULL-ийг зөвшөөрдөг.
  - `workspace_id` нэмнэ. NULL бол HLTV, нийтлэг.
  - `kind` нэмнэ: `official` | `scrim`. `source` нэмнэ: `hltv` | `upload`.
- **Scrim-ийг тусдаа хүснэгтэд биш, `matches`-д `kind=scrim`-ээр хадгална.** Ингэвэл Match Map, Round, Review, Replay-ийн бүх pipeline өөрчлөгдөхгүй ажиллана. CONTEXT.md-д Scrim нь Match биш боловч "Match Map шиг review хийгддэг".
- **Нэг төв шүүлтүүр:** `scope.official_match_maps()`. Pool, Own form, habit, Set play, Self-scout, Rating-ийг уншдаг query бүр үүгээр дамжина (ADR 0010).
- **Тест:**
  - Scrim нэмэхэд `pool:roles`-ийн hash, `metric_pool`, Playbook-ийн үр дүн өөрчлөгдөхгүй гэдгийг шалгана.
  - Workspace B-ийн Scrim Workspace A-д 404 өгнө.

**Upload-ийн урсгал:**

1. Staff `/uploads/new` дээр дараахыг сонгоно:
   - төрөл (Scrim эсвэл HLTV-д ороогүй official), огноо
   - my team, өрсөлдөгч (хайлт эсвэл чөлөөт нэр → Unidentified Team)
   - official бол Tournament, тэмдэглэл
2. **Файл:** `.dem` эсвэл archive (`.zip`, `.rar`, `.7z`, `.gz`, `.bz2`; `archive.py`-ийн bsdtar).
   - **Chunked upload:** `POST /uploads` → `PUT /uploads/{id}/parts/{n}` (50 MB) → `POST /uploads/{id}/complete`. nginx-ийн хязгаарыг зөвхөн энэ location-д 60 MB болгоно. Cloudflare-ийн 100 MB-ийн хязгаарт багтана.
   - **URL-аар import:** scrim server-ийн үйлчилгээ эсвэл Drive-ийн шууд линк. Worker өөрөө татна, Cloudflare-ийн хязгаар хамаарахгүй.
3. **Worker job** (`JobKind.upload`, `parse` queue, OPS-6):
   - unpack хийж, Map ба Demo part-ыг танина (ADR 0009). `tickdata.parse_parts` → `ingest_map`.
   - Файлыг устгана (ADR 0002 stateless).
4. **"Хэн хэн бэ" алхам:** Scrim-ийн demo-д clan нэр ихэвчлэн байдаггүй. Steam id-аар мэдэгдэх Player-уудыг таниад my team, өрсөлдөгчийн 5 тоглогчийг санал болгоно. Staff баталгаажуулна.
5. **Scrim-ийн онцлог:**
   - Warmup, knife Round, `mp_restartgame`-ийн дараах restart, backup-аас сэргээх.
   - "Бүх 24 Round тоглох" тохиргоо: 13 хожсоны дараах Round-ууд дасгалд тооцогдоно, онооны дүнд орохгүй.
   - Pause, coach эсвэл spectator слотод байх, bot, 10-аас өөр тоглогчтой Round.
   - Хамгийн сүүлийн restart-аас хойшхи `round_officially_ended`-ийг л авна.
6. **UI:**
   - `/uploads` дээр төлөв.
   - My team-ийн Scrim-ийн жагсаалт: огноо, түнш, Map, оноо, KPI (RV-6).

**Харагдах байдал:** зөвхөн Workspace дотор. Official upload нь тэр Workspace-ийн Pool, Own form-д тооцогдоно (ADR 0011, WS-2). Scrim нь тооцогдохгүй (ADR 0010).

**Хүлээгдэх үр дүн:** coach scrim-ийн дараа 5 минутын дотор Review, Replay-ийг нээнэ.

### DATA-2. Дэлхийн үр дүнгийн сан (P0/P1, L; FC-1-ийн суурь)

Q9-ийн дагуу дэлхий даяар цуглуулна. Хамрах хүрээ: VRS-д бүртгэлтэй бүх roster (2026-10-05-ны жагсаалт ~380), сүүлийн 18 сар.

| Эх | Юу авах | Нөхцөл (2026-10-21) | Үүрэг |
|---|---|---|---|
| HLTV match page (Chromium-оор) | Map бүрийн оноо, хагасын оноо, veto-ийн мөр, формат, LAN, event, lineup (HLTV player id) | API байхгүй, Cloudflare. Нөхцөл: "лицензгүйгээр бизнесийн зорилгоор ашиглахгүй". Тиймээс зөвхөн дотоод хэрэглээ, хурдыг хязгаарлана (DATA-10) | Үндсэн |
| HLTV `/results?offset=` | Дэлхийн бүх үр дүнгийн жагсаалт, match-ийн линк | Мөн адил | Шинэ Match олох |
| Valve VRS repo | Сар бүрийн байр, оноо. Roster бүрийн тоолсон Match бүрийн огноо, өрсөлдөгч, W/L, LAN, 5 тоглогч, шагналын сан | GitHub, нээлттэй. LICENSE файлгүй. Дата нь "provided by HLTV.org" | Rating-ийн prior (FC-1), roster, хяналт |
| Liquipedia MediaWiki API | Roster-ийн цагийн шугам (шилжилтийн огноо), bracket, тэмцээний формат, FACEIT ↔ HLTV id | ≤1 хүсэлт / 2 s (`parse` ≤1 / 30 s), тодорхой User-Agent, CC-BY-SA 3.0 attribution. HTML scraping хориотой | Roster, хуваарь (DATA-3) |
| PandaScore (үнэгүй) | Хуваарь, үр дүн | 1k хүсэлт/цаг. Stats-ийн plan нь betting биш хэрэглээнд | Нөөц эх |
| bo3.gg | Match-ууд | Баримтгүй, албан бус API | Зөвхөн нөөц |

GRID-ийн үнэгүй Open Access хаагдсан бололтой (`grid.gg/open-access/` → `/plans/`), бусад нь бүгд арилжааны.

**Загварын өөрчлөлт:**

- `matches`: `format` (bo1/bo3/bo5), `lan`, `stage`, `vetoes` (JSON: түүхий мөр ба задалсан алхмууд), `hltv_event_id`.
- `match_maps`: demo-гүй Map ч оноотойгоо мөр болно. Нэмэх багана: `picked_by_team_id`, `half_scores` JSON.
  - HLTV match page хагасын оноог өнгөөр нь CT/T-ээр харуулдаг гэж бодож байна. Шалгаж баталгаажуулна. Хэрэв тийм бол demo-гүйгээр Side бүрийн Round-ын хожлыг авч FC-8-д ашиглана.
- `match_lineups`: `match_id`, `team_id`, `hltv_player_id`, `player_id` (nullable), `nickname`.
- `players.hltv_id`: parse хийсэн Match дээр HLTV-ийн lineup ба Steam id-ийг nickname-аар тааруулна.
- `teams`: `region`. `vrs_standings` (огноо, team, бүс, байр, оноо, roster).
- `tournaments`: `lan`, `start_on`, `end_on`, `prize_pool`, `region`, `veto_format`, `liquipedia_page`.

**Query-ийн аудит:**

- Demo-гүй Match Map (`parsed_at IS NULL`) бүх query-д орж ирнэ. Тиймээс `MatchMap.parsed` scope нэмж, analysis-ийн query бүрийг шалгана.
- Round, kill-ээр join хийдэг query-ууд тэднийг автоматаар хасдаг. "Map-ын тоо"-г тоолдог query-ууд хасдаггүй.
- Team page дээр үр дүнг "demo-гүй" тэмдэгтэйгээр харуулах нь ашигтай.

**Хэрэгжүүлэх үе шат:**

1. Pool-ийн ба Азийн багуудын 12 сарын backfill.
2. VRS-ийн бүх roster.
3. Өдөр бүр шинэ үр дүн, `hltv` queue-д бага priority-тэй, шөнө.

**Тооцоо:** нэг match page ≈ 3 s. 15k Match ≈ 12.5 цаг (хэдэн шөнөд хувааж). Өдөрт ~100 хуудас ≈ 5 мин.

### DATA-3. Хуваарь, удахгүй болох тоглолт, автомат Scout (P1, M)

- **Эх:**
  - HLTV-ийн team хуудас эсвэл `/matches` (selector-ийг live-аар шалгана, `browser.py`-ийн дүрмээр)
  - Liquipedia-ийн bracket
  - PandaScore (нөөц)
- **`upcoming_matches`:** `hltv_id` (nullable), багууд, event, формат, эхлэх цаг, эх, `last_checked`.
- **Watchlist:** my team-үүд, тэдний bracket дахь магадлалтай өрсөлдөгчид.
  - Тоглолтоос 3 хоногийн өмнө өрсөлдөгчийн Scout-ийг гүн Window-оор (DATA-4) автоматаар queue-д оруулна.
  - 24 цагийн өмнө Forecast гаргана (FC-4).
- **Мэдэгдэл:** browser notification, Telegram: "NEXVOID-той Пүрэв 15:00, Scout бэлэн, Forecast 48%".
- **Celery beat:** `cs2-beat` unit эсвэл worker-т `-B`. Нэг л worker queue-г хэрэглэдэг болохоор ADR 0004-ийн recovery-д нийцнэ.

### DATA-4. Scout v2 (P1, M)

- **Window:**
  - "Энэ огнооноос хойш" эсвэл offset-той N.
  - 5-аас их хязгаар (`ANALYSIS_MAX_MATCHES`).
  - Demo-гүй Match слот эзлэхгүй.
- **Шинэ job-ууд:**
  - "Team refresh": нэг баг, хадгалсан хамгийн сүүлийн `played_at`-аас хойших шинэ Match-ууд.
  - "Нэг Match-ийг HLTV URL-аар parse хийх".
- **Багийг таних:** `_local_team`-д `teamnames.resolve`-ийг ашиглана. Academy-аас хамгаалах дүрэм хэрэгжинэ (`tasks.py:284-289`).
- **Тоглогчоор (Steam id-аар) scout хийх:** тоглогчид Huns, MongolZ, Chinggis Warriors, NEXVOID хооронд байнга шилждэг. Тиймээс Lineup-ийн тоглогчдын бусад багт тоглосон Match-уудыг нэмж татах сонголттой.
- **Re-download debt:** My team болон ойрын 5 өрсөлдөгчийн Loadout, Sighting-гүй Match-уудыг шөнийн queue-д автоматаар дахин татна. 49 Match ≈ 4 цаг. Ингэвэл aim-ийн хэмжүүр (PL-5) болон Loadout шаарддаг detector-ууд (RV-5) ажиллана.

### DATA-5. Parse-ийн хамрах хүрээ, schema 14 (P1, M; ADR 0006 шиг заавал биш)

- **awpy аль хэдийн уншиж байгаа ч хаядаг event-ууд:**
  - `item_pickup`: AWP-ийг хэнд өгдөг, буу шидэж өгөх зан.
  - `player_spawn`.
- **Нэмж унших event-ууд:**
  - `grenade_thrown`: шидсэн цэг, цаг. Lineup (SB-3), Set play-ийн timing.
  - `bomb_beginplant`, `bomb_begindefuse`: fake defuse. Defuse-ийн Win probability-ийн алдааг үндсээр нь засна (RV-1).
  - `player_ping`, Round-ын зарлал (match point, хагасын сүүлийн Round).
- **Timeout:** gamerules-ийн prop-оос timeout-ийн төлөвийг уншина. Талбарын нэрийг шалгана. RV-8-ийн timeout audit, GP-4-т хэрэгтэй.
- **Controller-ийн Round бүрийн статистик** (`CSPerRoundStats_t`): enemies flashed, utility damage, money saved, kill reward, live time. `_economy` шиг Round-ын төгсгөлд уншина (`demo_parser.py:252-285`).
- **16 Hz-ийн aim grid-д нэмэх:** `in_bomb_zone`, `is_defusing`.
- **Demo chat:** 2026-09-09-нөөс шифрлэгдсэн. Уншихгүй.

### DATA-6. FACEIT ба Premier (P2, M; өргөдлийг одоо гаргах)

- **FACEIT Downloads API:**
  - Өргөдлийн маягттай, ~30 хоног хянадаг, Downloads эрхтэй token, signed URL, "Match Demo Ready" webhook.
  - Хянах хугацаа урт тул **өргөдлийг одоо гаргахыг** санал болгож байна. Энэ гадагш чиглэсэн алхам тул хэрэглэгч шийднэ. Интеграцийн ажил нь Q5-ийн дагуу P2-т хэвээр.
- **FACEIT Data API v4:** API key, нийтийн дата. `Match.demo_url`, championship-ийн match-ууд, тоглогчийн түүх.
  - ECL Asia бол FACEIT дээр явдаг. S52 Asia Cup #2-ийн бүх Match FACEIT room ID ба HLTV match ID хоёулантай.
  - HLTV-д demo байхгүй үед хоёр дахь эх болно.
- **Хэрэглээ:**
  1. ECL Asia болон FACEIT-ийн qualifier-уудын нэмэлт demo.
  2. Тоглогчдын FACEIT pug-ийн форм (Self-scout, шинэ тоглогч PL-9). Зөвхөн тоглогчийн зөвшөөрөлтэй.
- **Premier:** share code нэг сарын дараа хүчингүй болдог, тоглогч бүрийн authentication code шаардана. Зөвхөн өөрийн тоглогчдоос зөвшөөрөлтэй цуглуулна.

### DATA-7. Patch-ийн үе ба map pool-ийн тохиргоо (P1, S)

- **`game_patches`:** огноо, build, тэмдэглэл. Тэмдэглэх patch-ууд:
  - CT-ийн T тутамд $50 (2025-07-16)
  - SMG-ийн өөрчлөлт (2026-01-21)
  - reload (2026-03-18)
  - Animgraph 2 (2026-04-20)
  - C4 (2026-07-08/09/20)
  - чимээгүй reload, гранатын хязгаар (2026-09-22)
- **`map_pool_periods`:** Map бүрийн Active Duty-д байсан үе.
- **Ашиглах газар:**
  - Match Map бүрийг patch-ийн үеэр тэмдэглэнэ.
  - Win probability-г patch-ийн үеэр refit хийнэ (RV-4). Post-plant detector-уудыг 7 сараас хойших датагаар шалгана.
  - Game Plan-ийн "patch X-ээс хойш" шүүлтүүр.
  - Hard-code хийсэн `ACTIVE_DUTY`-г солино (VIZ-11).

### DATA-8. Parse-ийн чанарын шалгалт ба хувилбар шинэчлэлт (P0, S–M)

- **Parse-ийн дараах шалгалт:**
  - тоглогч бүрийн байрлал, HP-ийн null-ийн хувь
  - Round бүрт 10 тоглогч, Round-ууд тасралтгүй, tick-ийн хамрах хүрээ
- **Шалгалт унавал:** Map-ыг чимээгүй хадгалахгүй, fail болгож шалтгааныг log-д бичнэ. Ингэвэл #362 шиг алдааг барина.
- **Parser засагдсаны дараа:** түүхий `.dem` хадгалагддаггүй тул нөлөөлсөн Map-уудыг дахин татна.
- **Хувилбар:**
  - demoparser2-ийн #362, #366-г дагана.
  - **awpy 3.x-ийг corpus дээр туршина:** Rust, Polars 2 (апп polars ≥1.44 дээр pin хийгдсэн), multipart-ийг шууд уншдаг. Шилжихдээ `demo_parser.parse_map` ба `tickdata.parsed_map` хоёрыг ижил байлгана.

### DATA-9. Датаны хамрах хүрээний самбар (P1, S)

`/data` (Staff):

- **Баг бүр:** parse хийсэн Map (Map ба schema-аар), Loadout эсвэл Sighting байхгүй Map, сүүлийн parse, хуучирсан derived, Review-ийн version.
- **Map бүр:** Pool-ийн хэмжээ.
- **Дараагийн Fixture-д дутуу дата:** "татах" товчтой (DATA-4).
- **Re-download queue.**

### DATA-10. Хууль ба ёс зүй (P0 бодлого, S)

Хуулийн зөвлөгөө биш, болгоомжлол:

- **Дотоод хэрэглээ:** HLTV-ийн дата, demo-г гадагш тараахгүй. Хурдыг хязгаарлаж, cache-лэнэ. HLTV-ийн нөхцөл бизнесийн хэрэглээнд лиценз шаарддаг тул блоклогдох эрсдэлтэй. Олон клуб болох үед (WS) энэ асуудлыг дахин авч үзнэ.
- **Liquipedia:** зөвхөн API, attribution (CC-BY-SA), хурдны дүрэм.
- **Хувийн мэдээлэл:**
  - Demo-д Steam id, нэр, зан төлөвийн мэдээлэл байдаг.
  - Хандалт (Workspace), хадгалах хугацааг тодорхойлно.
  - Монголын хувийн мэдээллийн хууль (2022 оноос). ЕХ-ны тоглогчид байвал GDPR.
- **FACEIT, Premier:** тоглогчийн зөвшөөрөлтэй л.
- `docs/data-policy.md`-д нэг хуудсанд бичнэ.

## Дараалал

1. DATA-8, DATA-10 (S).
2. DATA-1 (WS-1, OPS-6-ийн дараа).
3. DATA-2 (FC-1-тэй зэрэг).
4. DATA-3, DATA-4.
5. DATA-7, DATA-9.
6. DATA-5.
7. DATA-6. Өргөдлийг одоо гаргавал P2 эхлэхэд бэлэн байна.

## Хүлээгдэх үр дүн

- Scrim бүр 5 минутын дотор Review хийгдэнэ.
- ~380 багийн 18 сарын үр дүн Rating-д орно.
- My team-ийн тоглолт бүрийн өмнө Scout ба Forecast автоматаар бэлэн байна.
- Parse-ийн алдаа чимээгүй хадгалагдахгүй.

# 10. Assistant

> Item-ийн ID: `AS-…`. Нэр томъёо: Assistant, Workspace, Briefing (`CONTEXT.md`). Код: `apps/api/app/services/assistant.py`, `voice.py`, `routers/assistant.py`, `apps/public/src/assistant/`.

## Зорилго

Coach монголоор, бичгээр эсвэл дуугаар асууна. Жишээ нь "Mirage дээр тэдний T default юу вэ?", "Манай X сүүлийн 5 тоглолтод ямар байна?", "Энэ тоглолтод юугаараа хожигдсон бэ?". Assistant хуудсуудтай ижил дата дээр тулгуурлан тоо, дээжийн хэмжээ, Replay-ийн линктэй хариулна. Мөн Briefing-ийн текстийн ноорог бэлдэж өгнө. Tool-оос ирээгүй тоог хэзээ ч хэлэхгүй.

## Одоогийн байдал (кодын аудит, 2026-10-21)

**Tool-ууд (8):**

| Tool | Буцаадаг зүйл |
|---|---|
| `list_teams` | Багуудын жагсаалт |
| `team_overview` | Багийн ерөнхий мэдээлэл |
| `map_strategy` | Map pool. Opponent өгвөл veto ба CT/T төлөвлөгөө |
| `role_report` | Тоглогчийн үүрэг |
| `scouting_report` | Head-to-head, аюул, сул тал, duel |
| `gameplan_section` | 14 хэсгийн нэг, түүний дотор `levers` |
| `match_summary` | Match-ийн Summary |
| `match_review` | Match Map-ын Review, 40 хүртэлх Finding |

**System prompt:**

- Тоо бүр tool-оос ирнэ. Дээжийн хэмжээг үргэлж хэлнэ.
- Ярианы хэв маяг: 2–4 өгүүлбэртэй догол мөр, 5 хүртэл догол мөр, markdown-гүй. CS2-ийн нэр томъёо англиар үлдэнэ.
- Хуудасны тэмдэглэл болон хэлний сануулгыг хэрэглэгчийн мессежийн ард залгадаг (`assistant.py:811-855, 974-991`).

**Хамгаалалт:**

- "Tool-оос ирээгүй зүйл хэлэхгүй" гэдэг нь зөвхөн prompt дотор бичигдсэн. Хариултын тоог tool-ийн гаралттай тулгаж шалгадаггүй.
- Refusal гарвал server-side fallback beta ажиллана, тэр нь ч амжилтгүй бол тогтмол монгол өгүүлбэр хэлнэ.
- Хуудасны context-ийг бодит мөртэй тулгадаг. Түүх: сүүлийн 12 мессеж, тус бүр 2,000 тэмдэгт.

**Сул тал:**

- 12,000 тэмдэгтээс урт tool-ийн гаралтыг JSON-ийн дундуур тасалдаг (`assistant.py:1013-1015`). Model буруу JSON авна.
- `match_summary`-д монгол статус шошго байхгүй (`mn.py:1783-1791`).
- Decision tab, Metrics-ийн Pool profile, Playbook-ийн habit-ийг уншиж чаддаггүй (`playbook_view.panel` огт дуудагддаггүй).
- Redis-ийн `gp:v9` cache-ийг ашиглахгүй, Game Plan-ийн хэсгийг дахин тооцоолдог.
- **Context:**
  - Match page дээр "аль ч тал хэрэглэгчийн баг биш" гэж хэлдэг (`assistant.py:845`). Coach "бид The Huns" гэж тайлбарлах шаардлагатай болдог.
  - Replay-ийн Round, Review-ийн шүүлтүүрийг context-д илгээдэггүй.
  - Нэг transcript бүх хуудсыг дамнадаг. Өөр Fixture-ийн тухай өмнөх ярилцлага шинэ хуудасны тэмдэглэлтэй хамт дахин явдаг. `PageContext.key` тооцоологддог ч уншигддаггүй.
  - Browser 24 мессеж явуулдаг, сервер 12-ыг л хадгалдаг.

**Зардал:**

- `claude-sonnet-5-5`, effort `medium`, дуудлага бүрт max output 16,000 token, 6 хүртэл tool round. Prompt caching асаалттай.
- Хэрэглэгчийн quota, rate limit, хэрэглээний log байхгүй.
- ElevenLabs тохируулагдсан бол дуу default-аар асаалттай, догол мөр бүрийг TTS хийдэг.

**Дуу:**

- TTS нь `eleven_v4_turbo`, 2 thread-ийн pool-д ажилладаг.
- STT нь Scribe v2, монгол хэлэнд тохируулж, Map ба багийн нэрсийг keyterm болгон өгдөг. Transcript-ийг засах боломжгүйгээр шууд илгээдэг.
- Audio blob URL-ийг суллаагүй тул санах ой алддаг (`assistant/api.ts:91`).

**Тест:** fake Claude-тай 11 тест. Хариултын чанар, үндэслэлийг (grounding) шалгадаг тест байхгүй.

**Хариулж чадахгүй асуултууд:**

- "Сүүлийн тоглолт маань ямар байсан бэ?" (match page-ээс гадуур)
- "Энэ тоглогч формтой юу?"
- "Тэдний Mirage-ийн T default, Set play юу вэ?"
- "Decision юу гэж байна?"
- "Trade-ээр Pool-д хэддүгээрт байна?"
- "14-р Round-ыг үзүүл"
- "B дээр хаана үхдэг вэ?"
- удахгүй болох тоглолт, тэмцээн, Scout-ийн явц

## Шийдэл

### AS-1. Зөв ажиллах засварууд (P0, S)

> **Төлөв:** ✅ `be20b0a` (improvement-01).

- Том гаралтыг бүтцээр нь тайрна: жагсаалтыг ач холбогдлоор нь богиносгоод "мөн N мөр байна" гэж хэлнэ.
- `match_summary`-д монгол статус шошго нэмнэ.
- **Хуудас ба түүх:**
  - Turn бүрийг хуудасны түлхүүрээр (`PageContext.key`) тэмдэглэнэ.
  - Хуудасны сэдэв өөрчлөгдөхөд өмнөх turn-уудыг "өөр сэдэв" гэж тэмдэглэх эсвэл шинэ thread эхлүүлнэ.
  - 24 ба 12 мессежийн зөрүүг арилгана.
- **"Бид":** WS-1-ийн дараа Workspace-ийн my team-үүдийг context-д оруулна. Match page дээр аль тал нь манайх болохыг мэддэг болно.
- **Context:** одоогийн Round, агшин, Review-ийн шүүлтүүрийг (`team`, `side`, `player`, `kind`) илгээнэ.

### AS-2. Зардал ба буруу хэрэглээг хянах (P0, S–M)

> **Төлөв:** ✅ `be20b0a` (improvement-01).

- **Хэрэглээний бүртгэл:** turn бүрийн `usage`-ийг `assistant_usage` хүснэгтэд хадгална:
  - `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`
  - model, tool round-ын тоо, TTS-ийн тэмдэгт, хугацаа, `workspace_id`, `user_id`
- **Зардлын тооцоо:** `/system` дээр сарын зардлыг тооцож харуулна. 2026-10-ийн жагсаалтаар `claude-sonnet-5-5` нь 1M token тутамд $2 input, $10 output, $0.20 cache read.
- **Хязгаар:**
  - Хэрэглэгч бүрийн өдрийн хязгаар (token ба TTS тэмдэгт) Redis-д. Хэтэрвэл найрсаг мессеж гаргана. Staff хэрэглээг харна.
  - nginx-ийн rate limit (OPS-1).
  - Anthropic-ийн хүсэлтэд `metadata.user_id` (hash) явуулна.
- **Сонголттой:** agentic loop-ийн token-ийн тааз болгож `task_budget` (beta) тавина. Дуу: turn бүрийн TTS-ийг эхний 3 догол мөрөөр хязгаарлах эсэхийг хэрэглээний log-оор шийднэ.
- **Cache-ийн эрүүл байдал:**
  - Хуудасны тэмдэглэл, хэлний сануулгыг хэрэглэгчийн мессежид залгахын оронд mid-conversation system message болгоно. Sonnet 5.5 дэмждэг. Ингэвэл cache-лэгдсэн prefix хадгалагдаж, prompt injection-оос хамгаалагдсан operator суваг болно.
  - `cache_read_input_tokens` > 0 эсэхийг log-оос хянана.

### AS-3. Tool-ийн хамрах хүрээ (P1, M; бүр нь холбогдох функц бэлэн болсны дараа)

> **Төлөв:** 🟡 `3b41467` (improvement-01). `team_matches`, `player_form`, `forecast`, `rating`, `gameplan_section` decision/playbook нэмэгдсэн. `find_rounds`, Stratbook, Scrim, хуваарийн tool-ууд нь тэдгээр функц хийгдэх үед.

| Tool | Хэзээ | Тайлбар |
|---|---|---|
| `team_matches(team_id, limit)` | Одоо (S) | Сүүлийн Match-ууд id-тай. "Сүүлийн тоглолт" асуултад |
| `gameplan_section`: `decision`, `metrics` | Одоо (S) | Байгаа panel-уудыг нээх |
| `playbook(mine, theirs, map)` | Одоо (M) | Cache-лэгдсэн Playbook-ийн panel-ийг уншина (`gp:…:playbook:<map>`). Байхгүй бол тооцоолно |
| `player_form(steamid, map?, side?, since?)` | PL-2-ийн дараа | Форм, Strength, Weakness |
| `forecast(mine, theirs, lineups)`, `rating(team)` | FC-1, FC-3-ийн дараа | Зөвхөн Staff-д (Q15) |
| `find_rounds(map, side, team, conditions)` | VIZ-7-ийн дараа | "B-д 3 хүнтэй орсон раундууд" |
| `stratbook_search`, `strat_stats` | SB-1-ийн дараа | Манай Strat ба түүний гүйцэтгэл |
| `scrim_kpis(team, since)`, `development_plan(steamid)` | RV-6, RV-9-ийн дараа | Scrim ба хөгжлийн явц |
| `upcoming_matches(team)` | DATA-3-ийн дараа | Хуваарь ба Forecast |

Tool бүр `Viewer`-ийн scope-оор уншина (ADR 0011). Player User-д зөвхөн өөрийн датаны tool-ууд нээлттэй (AS-8).

### AS-4. Үндэслэл (grounding) ба үнэлгээ (P1, M)

> **Төлөв:** 🟡 `053f6d5` (improvement-01). Хариултын тоог tool-ийн гаралттай тулгаж «шалгах» тэмдэг; 40 асуулттай golden set ба `assistant:eval` (төлбөртэй, ажиллуулаагүй). Citations-ийн туршилт үлдсэн.

- **Golden set:**
  - Coach-ийн 40 асуулт монголоор. Хуудас бүрээс, coach-ийн ажлын урсгалаас (`12-research-sources.md`).
  - Асуулт бүрт хүлээгдэх tool-ууд ба гол баримтууд.
  - Локал DB-ийн snapshot дээр ажиллуулна.
- **Шалгуур:**
  1. Зөв tool дуудсан эсэх.
  2. Хариултын тоо бүр tool-ийн гаралтад байгаа эсэх (хувь, бутархай, бөөрөнхийлөлтийг тооцно).
  3. Монгол хэлний чанар (гараар, түүвэр).
- **Ажиллуулах үе:** prompt, model, tool өөрчлөгдөх бүрт. Token зарцуулдаг тул гараар эсвэл шөнийн job-оор ажиллуулна.
- **Ажиллах үеийн шалгалт:** хариултаас тоонуудыг гаргаж tool-ийн гаралттай тулгана. Олдохгүй тоо байвал нэг удаа дахин үүсгэх эсвэл "шалгах" тэмдэглэгээ хийнэ.
- **API-ийн citations:** tool-ийн гаралтыг custom content document болгон citations-тэй дамжуулбал өгүүлбэр бүр эх сурвалжаа (`content_block_location`) заана. UI hover дээр эх сурвалжийг харуулна. Догол мөрөөр stream хийх ба дуутай хэрхэн нийцэхийг эхлээд жижиг туршилтаар шалгана.

### AS-5. Round-ын лавлагаа ба линк (P1, M)

> **Төлөв:** ✅ `d032218` (improvement-01). `[R14]`, `[R14 1:23 @sid]`, `[4021.2:R14]` → Replay-ийн линк; нээлттэй Replay шилжинэ; дуу «14 дүгээр Round».

- Хариултад `[R14]`, `[R14 1:23 <steamid>]` гэсэн токен оруулна. UI тэдгээрийг Replay-ийн линк болгоно (VIZ-2).
- Дуугаар "14 дүгээр Round" гэж уншина.
- Tool-ууд Replay-ийн ref-ийг аль хэдийн буцаадаг (Playbook-ийн evidence, Finding-ийн Round, агшин).

### AS-6. Briefing-ийн ноорог (P1, M; WS-5-тай хамт)

> **Төлөв:** ✅ `640b640` (improvement-01). Ноорог нь тоог мөртэй тулгадаг; TTS хувилбар ба Opus-ийн харьцуулалт үлдсэн.

- **Оролт:** Game Plan-аас Staff сонгосон мөрүүд. Assistant Map бүрт нэг хуудсанд багтах монгол текст бэлдэнэ:
  - тэдний 3 habit ба тус бүрийн эсрэг арга
  - манай 3 Lever
  - тоглогчдын matchup (PL-7)
  - эдийн засаг ба pistol-ийн төлөвлөгөө
- **Дүрэм:** тоо бүр panel-аас ирнэ (AS-4-ийн шалгалт). Staff засаад хадгална. Тоглогчдод зориулсан дуун хувилбар (TTS) сонголттой.
- **Model:** тохируулсан `claude-sonnet-5-5`-аар эхэлнэ. Briefing-ийн golden set дээр `claude-opus-5-5`-ийг (1M token тутамд $4/$20) чанар, зардлаар харьцуулж, сонголтыг хэрэглэгч хийнэ.

### AS-7. Хуудасны хамаарлыг сайжруулах (P1, S)

> **Төлөв:** 🟡 `336c908` (improvement-01). Player, Scout job (амжилттай бол Game Plan руу), Game Plan picker-ийн context; Team page-д rating, team_matches. Хуваарь DATA-3-ийг хүлээнэ.

- Job page: Scout-ийн явцыг хэлж, дууссан бол Game Plan руу чиглүүлнэ.
- Picker: Lineup-ийн тухай асуултыг ойлгоно.
- Player page (PL-2): тэр тоглогчийн тухай.
- Team page: Rating ба хуваарь (FC, DATA-3).

### AS-8. Тоглогчийн Assistant (P2, M)

Player User зөвхөн өөрийн Review, Focus point, Development plan, хуваалцсан Briefing-ийн тухай асууна. Tool-ийн жагсаалтыг role-оор нь шүүнэ. Forecast-ыг Staff хуваалцаагүй бол харуулахгүй.

### AS-9. Дууны UX (P2, S)

- Илгээхээс өмнө transcript-ийг засах боломж олгоно.
- Утсан дээр дарж байж ярих (push-to-talk) товч хийнэ.
- Audio blob URL-ийг сулладаг болгоно (`assistant/api.ts:91`).
- Hex өнгийг token болгоно (OPS-10).

## Дараалал

1. AS-1, AS-2 (P0): одоогийн хэрэглээг найдвартай, хямд, хянагдахуйц болгоно.
2. AS-3-ийн "одоо" мөрүүд, AS-5.
3. AS-4: tool нэмэх бүрийн өмнө golden set-тэй байх нь чухал.
4. AS-6 (WS-5-тай), AS-7.
5. Бусад tool-ууд холбогдох функцуудын хамт.
6. AS-8, AS-9.

## Хүлээгдэх үр дүн

- "Сүүлийн тоглолт маань ямар байсан бэ?" гэх асуултад ямар ч хуудаснаас Focus point болон Round-ын линктэй хариулна.
- Хариултын тоо бүр tool-ийн гаралтаас ирсэн нь golden set-ээр баталгаажна.
- Сарын зардал `/system` дээр харагдаж, хэрэглэгч бүрийн хязгаартай болно.

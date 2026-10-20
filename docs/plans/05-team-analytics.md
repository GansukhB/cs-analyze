# 05. Багийн анализ: хэв маяг, map pool, давуу ба сул тал

> Item-ийн ID: `TM-…`. Нэр томъёо: Team, Pool, Own form, Strength, Weakness, Setup, Set play, Playbook, Evidence strength, Head-to-head (`CONTEXT.md`). Rating ба Forecast: `03-ratings-forecast.md`.

## Зорилго

Багийн хэмжээнд гурван асуултад найдвартай хариулах:

1. Энэ баг ямар **хэв маягаар** тоглодог вэ (хурд, түрэмгий байдал, utility, эдийн засаг)?
2. Аль **Map, аль Side** дээр бусад багуудаас илт сайн эсвэл муу вэ?
3. Энэ **зуршил** жинхэнэ үү, эсвэл цөөн Round-ын азаар гарсан тоо уу?

Гурав дахь асуулт хамгийн чухал. Coach худал "сул тал"-ын эсрэг бэлдэхэд цаг, итгэл хоёулаа алдагдана.

## Одоогийн байдал (кодын аудит, 2026-10-21)

**Metrics tab** (`gameplan.py:62-174`): 12 Own form үзүүлэлт (CT win%, T win%, pistol, opening win%, plant rate, post-plant win%, "retake", traded deaths, multi-kill, ADR, KAST, utility/Round).

- **Pool:** 40+ Round-тай Team-үүд. Дундаж ба SD нь жингүй, SD floor нь дунджийн 10%. z ≥ 0.8 бол Strength.
- **Shrinkage байхгүй.** Map, Side-аар задрахгүй (CONTEXT.md-ийн Strength нь Map, Side бүрээр байх ёстой).
- Локал Pool-ийн 25 Team-ийн 12 нь 3 эсвэл түүнээс цөөн Match Map-тай.
- Floor нь ADR (бодит SD 4.3, хэрэглэсэн 7.2), KAST (4.3 → 7.2), post-plant, utility-ийн бодит тархалтыг дардаг. Тиймээс ADR, KAST бараг хэзээ ч Strength, Weakness болдоггүй.

**Decision** (`decision.py`) нь 12 үзүүлэлтээс "≥" хэдийг нь тоолж дүгнэдэг:

| Хэдэн үзүүлэлтэд түрүүлсэн | Дүгнэлт |
|---|---|
| 7+ | Хожих боломжтой |
| 5–6 | Lever 2+ байвал хожих боломжтой, үгүй бол ойролцоо |
| 3–4 | Дутуу |
| 3-аас бага | Хэцүү |

**Өрсөлдөгчийн хүчийг огт тооцдоггүй.** Huns vs The MongolZ "12/12 давуу, хожих боломжтой" гэж гардаг. Гэтэл MongolZ-ийн Match Map-ууд Vitality, Falcons, FaZe, HEROIC, NaVi-ийн эсрэг, Huns-ийнх 5star, Alter Ego, Nas, NEXVOID-ийн эсрэг тоглогдсон.

**Playbook-ийн habit** (`playbook.py`): Setup, stack, site, plant time, rush, retake, at_plant, opening duel, Set play, эдийн засаг. Бүгд тогтмол босготой, Pool-ийн base rate-тай харьцуулдаггүй.

- Retake ≤35% бол "сул" гэдэг. Гэтэл CT retake-ийн дундаж 23.5% тул 94 team-Map-ийн 70 нь "сул" гэж гардаг.
- Нэг site-д plant ≥60% бол habit гэдэг. Гэтэл 8 plant 50/50 хуваагдсан ч санамсаргүйгээр 73% тохиолдолд ийм гардаг.
- Recency, roster-ийн жин байхгүй. Freeze end-ээс хойш 40 s-ээс цааш юу ч шинжилдэггүй.

**`review_pool`** (Lever, Caution): reliability-ээр жигнэсэн z (Map, Side-ийн Pool), Map-ыг багийн бүх Map-ын хандлага руу татдаг.

- Мөрүүдийн 85% нь "all_maps" гэж гардаг. Өөрөөр хэлбэл Map бүрийн Playbook ихэвчлэн багийн ерөнхий хандлагыг давтдаг.
- Multiple comparison-ий хяналт байхгүй (~38 Measure, Map бүрт дунджаар 5.9 мөр).
- Дүгнэж буй баг өөрөө Pool дотор нь байдаг. Map ба Side бүрийн Pool 7–17 Team-тэй.

**Retake-ийн дөрвөн өөр тодорхойлолт** нэг хуудсан дээр бие биетэйгээ зөрчилдөж болно:

| Хаана | Тодорхойлолт |
|---|---|
| Playbook | 35/60% |
| `map_plan` | 25/45% |
| Summary | сайн ≥33% |
| Pool | z |

**Head-to-head delta:** 8-ын босго нэгжийг тооцдоггүй, дээжийн доод хязгааргүй. Жишээ нь ~12 pistol дээр "pistol collapse −10.4" гэж гарсан.

**Man advantage:** тоо хэмжээ анх зөрөх агшинг хэмждэг. Энэ нь үргэлж эхний kill тул бодитоор opening kill-ийг хожилд хувиргасан хувь болж байна.

## Шийдэл

### TM-1. Нийтлэг статистикийн модуль `app/services/stats.py` (P0/P1, M)

Одоо Pool-ийн хоёр өөр engine (`metric_pool`, `review_pool`), Playbook-ийн тогтмол босго, `roles`-ийн SD floor бие биеэсээ тусдаа ажилладаг. Тэдгээрийг нэг модульд нэгтгэнэ.

- **Хувь:** beta-binomial empirical Bayes. Prior-ийг Pool-ийн Map, Side бүр дээр method of moments-оор тааруулна.
- **Тасралтгүй тоо:** reliability-аар shrink хийнэ (`review_pool._reliability` аль хэдийн байгаа).
- **Бодит дээж:** Round хоорондын хамаарлыг тооцно (N_eff, `04-player-analytics.md` PL-3). Recency-ийн жин exp(−Δt/τ).
- **Pool:**
  - Дүгнэж буй багийг Pool-оос хасна (leave-one-out).
  - Pool-ийн гишүүдийг Round-ын тоогоор жигнэнэ.
  - 10%-ийн floor-ийг prior-ийн тархалтаар солино.
  - Workspace-ийн хамаарал: WS-2.
- **Тэмдэглэх дүрэм:** lfsr < 0.1 эсвэл BH-FDR q = 0.1, хамгийн багадаа 8 үйл явдал, нөлөөг Round-аар эрэмбэлнэ. Мөр бүр Pool-ийн хэмжээ ба base rate-ийг харуулна (жишээ нь "Pool: 14 баг, дундаж 23%").
- **Measure:** retake-ийг нэг Measure болгоно. Playbook, `map_plan`, Summary, Pool бүгд түүнийг уншина.
- **Хэрэглэгчид:** `gameplan.metric_pool`, `profile_team`, `review_pool`, `playbook`-ийн habit, `roles`, `playerplan`.
- **Хувилбар:** `POOL_SCHEMA`, `METRIC_POOL_SCHEMA`-г ахиулна.

**Хүлээгдэх үр дүн:**

- Retake "сул" гэсэн мөр 94-өөс 70 биш, Pool-ийн бодит тархалтаар хэдхэн багт л гарна.
- Нэг Map-ын Playbook-ийн мөрүүд долоо хоног бүр санамсаргүйгээр солигдохгүй.

### TM-2. Өрсөлдөгчийн хүчээр тохируулах (P1, M; FC-1-ийн дараа)

- **Round тус бүр:** өрсөлдөгчийн Rating-ийн зөрүүнээс хүлээгдэх хожлын хувийг тооцно. Үзүүлэлтийг бодит дүн ба хүлээгдэх дүнгийн зөрүү (residual) хэлбэрээр харуулна.
- **Own form-ийг өрсөлдөгчийн түвшингээр задлах:** top-20, 21–60, бусад (Rating-ийн quantile). Ингэснээр "бид сул багуудыг л хожиж байна уу" гэдэг харагдана.
- **Decision:** `decision._call`-ийг Forecast-аар солино (`03-ratings-forecast.md` FC-4). Ингэснээр 12 үзүүлэлтийн тоолох логик алга болно.

### TM-3. Recency ба roster-ийн үе (P1, M)

- **Хугацааны шүүлтүүр:** `since`, `until`-ийг `Report._window`-оор дамжуулна. Одоо зөвхөн `profile_team`, `map_board`, `map_plan` авдаг. Үүнийг players, roles, linchpin, Playbook-д ч хэрэглэж, cache-ийн түлхүүрт нэмнэ.
- **Хагас задралын жин:** habit-д τ = 60 хоног, map pool-д 90 хоног. Default утгууд бөгөөд backtest-ээр тааруулна.
- **Roster-ийн үе:**
  - Одоогийн Lineup-ийн 4+ тоглогч тоглосон Round-уудыг habit-ийн default дээж болгоно.
  - Хуучин roster-ийн мөрүүдийг тэмдэглэнэ.
  - Head-to-head-д аль хэдийн "≤3 тоглогч давхцвал хуучирсан" дүрэм бий (`gameplan.py:1083`).

### TM-4. Habit-ийг base rate-тай шалгах (P1, M)

Playbook-ийн habit бүрийг тогтмол босгоор биш, тухайн Map ба Side-ийн Pool-ийн base rate-тай харьцуулна:

- **Site:** plant-ийн хувийг тухайн Map-ын Pool-ийн A/B-ийн хувьтай binomial test эсвэл EB-ээр харьцуулна. Мөрөнд "Pool-д A 52%" гэж харуулна.
- **Retake:** posterior нь Pool-ийн доод quantile-аас доош байвал л сул гэнэ.
- **Plant time, rush:** Pool-ийн хуваарилалт дээрх байрлалаар (percentile) дүгнэнэ.
- **Set play:** Apriori-аар олдсон багц санамсаргүйгээр гарах магадлалыг тооцож шүүнэ.
- **Evidence strength:** одоогийн 4 Round, 1/2–3/4+ Match Map гэсэн дүрэм хэвээр. Шалгалтыг давсан мөр л харагдана.

### TM-5. Хэв маягийн хурууны хээ (style fingerprint) (P1, M)

Map, Side бүрээр хэмжигдэх хэмжүүрүүд. Бүгд Pool-тай percentile-аар харьцуулагдаж, Evidence-тэй байна.

| Тал | Хэмжүүр | Хаанаас |
|---|---|---|
| T | Хурд: анхны контакт, site-д анх орох, plant-ийн хугацааны хуваарилалт | kill, damage, `round_states` (VIZ-7) |
| T | Default ба хурдан execute-ийн харьцаа. Execute гэдэг нь нэг site-д 5–8 s дотор 2–3+ гранат буух, ~10 s дотор 3+ T орох | `grenade_throws`, байрлал |
| T | Fake: нэг site-д гранат цацаад нөгөөд plant хийх | гранат, plant |
| T | Mid control, lurk (багийн төвөөс хол нэг тоглогч), 1:00-ээс хойших plant | snapshot, walks |
| CT | Түрэмгий байдал: эхний 20 s-д site-ийн шугамаас цааш хийсэн kill, death | kill-ийн байрлал |
| CT | Stack-ийн давтамж, rotate-ийн хурд (T site-д орсноос хойш 2 дахь CT ирэх хугацаа) | Setup, ticks |
| CT | Retake эсвэл save, саатуулах utility (эхний 25 s дэх molotov, smoke) | гранат, Round-ын үр дүн |
| Хоёул | Эдийн засаг: pistol ялагдсаны дараа force, eco-ийн сахилга, bonus Round, anti-eco (full vs light-ийн хожил) | `rounds.ct_buy`/`t_buy` |
| Хоёул | Давуу байдлыг хожилд хувиргах: 5v4, 4v5, 4v4… бүрээр. Win probability-ийн хүлээгдэх утгатай харьцуулна (бодит − хүлээгдэх). `man_advantage`-ийн одоогийн "зөвхөн opening" алдааг засна | Review-ийн timeline |
| Хоёул | Timeout: хэдэн Round алдсаны дараа авдаг, дараа нь хүлээгдэхээс илүү хожсон эсэх. Нотолгоо сул тул Pool-ийн түвшинд л харуулна (TM-11) | Round-ын дараалал |

Тоглоомын event-ээс (`round_announce`, timeout) timeout-ийг шууд уншдаггүй. Хэрэгтэй бол DATA-5-ийн parse-ийн нэмэлт хэрэгтэй.

**UI:** Team page болон Game Plan-д Map бүрийн "хэв маяг" хэсэг. Хоёр багийг зэрэгцүүлсэн percentile bar.

### TM-6. Map pool-ийн гүн ба veto-ийн оролт (P1, M; FC-2-тэй хамт)

- **Map бүрийн хүч:** Map бүрийн Rating (`03`), shrink хийсэн Round-ын хожлын хувь (Beta prior), recency.
- **Map pool-ийн гүн:** Rating нь багийн дунджаас X-ээс бага доогуур биш Map-уудын тоо.
- **Veto-ийн түүх** (DATA-2: HLTV match page-ийн pick/ban мөр):
  - Багийн эхний ban, pick-ийн давтамж, Bo1 ба Bo3-аар тусад нь.
  - "Тэдний магадлалтай ban/pick" гэж хувиар харуулна.
- **Map-ийн жагсаалт:** одоогийн hard-code хийсэн `ACTIVE_DUTY` (Train байгаа, Cache байхгүй) хуучирсан. Сүүлийн 90 хоногт Pool-д тоглогдсон Map-ууд ба тохиргооноос автоматаар тодорхойлно.
- **Head-to-head-ийг давхар тоолохгүй:** Head-to-head Match Map-ууд одоо багийн өөрийн record-д ч, Head-to-head-ийн ban дүрэмд ч ордог.

### TM-7. Round-ын үе шат: эхний 40 s-ээс цааш (P1, M)

- **Анхны контактын дараа:** rotate, хожуу execute, plant-ийн дараах байрлал (at_plant snapshot бий), retake-ийн бүрэлдэхүүн.
- **"Анхны kill-ийн дараах шийдвэрийн мод":**
  - T A дээр opening kill авсны дараа: хэдэн хувьд нь A руу орж, хэдэн хувьд нь rotate хийдэг вэ.
  - CT B-д opening алдсаны дараа: хэдэн хувьд нь retake хийж, хэдэн хувьд нь stack хийдэг вэ.
- **Дата:** `round_states` (VIZ-7) ашиглан цагаар хуваасан тооллого.

### TM-8. Эдийн засгийн model (P2, M)

- **Round эхлэх үеийн model:** P(хожил | хоёр багийн buy ангилал, Map, Side), Pool дээр.
- **Дараагийн Round-ын мөнгө:** loss bonus-ийн шат, 2025 оны 7 сараас хойших CT-ийн T тутамд $50, хадгалсан зэвсгийг тооцно.
- **Map-ын хожлын магадлал:** MR12-ийн онооны төлөв бүр дээр dynamic programming.
- **Хэрэглээ:** багийн buy шийдвэрийг "хамгийн оновчтой"-той харьцуулна (Xenopoulos нарын Optimal Spending Error). Интервалаас хэтэрсэн тохиолдлыг л тэмдэглэнэ.
- **Жишээ мөр:** "Pistol ялагдсаны дараах 2 дахь Round-д хэт олон удаа force хийдэг: дунджаар 0.4 Round алддаг".

### TM-9. Head-to-head delta v2 (P1, S)

- Нэгжийг тооцсон босго тавина: хувь, тоо, ADR тус бүрт өөр.
- Measure бүрт дээжийн доод хязгаар тогтооно.
- "Өөрчлөгдөөгүй" (holds) дүрмийг засна.
- Caption-ийн зөрүүг засна (`panels.tsx:238,252,535,778`).

### TM-10. Team page v2 (P1, M)

`/teams/:id`:

- Rating-ийн trend (FC-1)
- Map pool-ийн график: Map бүрийн Rating, CT/T-ийн Round хожил, интервалтай
- Хэв маяг (TM-5)
- Roster-ийн цагийн шугам (`map_rosters`)
- Сүүлийн үр дүн: Forecast ба бодит дүн
- Map бүрийн гол habit (Playbook-ийн товч)
- Strength, Weakness

Хуудас дахь тоглогчийн нэр бүр Player page руу линктэй (PL-2).

### TM-11. Momentum (P2, S)

Pool-ийн түвшинд л судална: streak, pistol, timeout-ийн дараах "residual momentum"-ийг эдийн засгаар тохируулсан Round эхлэлийн Win probability-тай харьцуулна. Судалгаагаар momentum-ийн ихэнх нь эдийн засгаас үүдэлтэй (Parshakov 2026). 3+ Round-ын streak-ийн дараа техникийн timeout авбал дараагийн Round-д streak тасрах магадлал 11.7–13 хувийн нэгжээр өсдөг (Gómez Seeber 2024, CS:GO). Багт тусгайлан "tilt" гэж дүгнэх нь цөөн дээжтэй үед буруу тул хийхгүй.

## Дараалал

1. TM-1. Бүх зүйл түүн дээр тулгуурлана.
2. TM-9 (S) ба TM-4.
3. FC-1 бэлэн болмогц TM-2, TM-6.
4. TM-3, TM-5.
5. VIZ-7-ийн `round_states` бэлэн болмогц TM-7.
6. TM-10: хэсгүүд нь бэлэн болохын хэрээр.
7. TM-8, TM-11 (P2).

## Хүлээгдэх үр дүн

- "Huns vs MongolZ: 12/12 давуу" шиг өрөөсгөл дүгнэлт алга болно. Багийн үзүүлэлт бүр өрсөлдөгчийн хүчээр тохируулагдаж, Pool-ийн base rate-тай хамт харагдана.
- Map бүрийн Playbook-д тухайн Map-д л онцлог зуршил гарна (одоо 85% нь "all_maps").
- Coach "энэ баг хурдан тоглодог уу, default-оор уу" гэдгийг нэг дэлгэцээс Pool-ийн percentile-аар харна.

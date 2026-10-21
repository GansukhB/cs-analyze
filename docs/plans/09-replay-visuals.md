# 09. Replay, heatmap, movement, раунд хайх

> Item-ийн ID: `VIZ-…`. Нэр томъёо: Replay, Spot, Callout, Sighting, Setup (`CONTEXT.md`).

## Зорилго

Coach, analyst ажлынхаа ихэнх цагийг раунд үзэхэд зарцуулдаг. 2D хэрэгсэл тоглоом дотор demo үзэхээс хурдан байх ёстой: хэрэгтэй раундаа хайж олох, хэд хэдэн раундыг давхарлан харьцуулах, тэмдэглэх, тоглогчид линкээр явуулах. Өрсөлдөгчийн бүтээгдэхүүнүүд (Skybox EDGE, Noesis, Scope.gg) хамгийн их энэ хэсэгт хөрөнгө оруулдаг (`12-research-sources.md`).

## Одоогийн байдал

**Replay** (`apps/public/src/replay/player.ts`, `Replay.tsx`):

- **Байгаа зүйл:**
  - 8 Hz-ээр interpolate хийсэн байрлал, HP, харж буй чиглэл, цайрсан эсэх, Floor.
  - Callout ба Spot-ийн шошго. Loadout (Held weapon, item, armor, kit, мөнгө).
  - Kill, damage, shot-ийн feed. Гранатын нислэг, smoke ба галын талбай, flash ба HE-ийн дэлбэрэлт. Bomb-ийн цаг.
  - Toggle-ууд, 0.25–4× хурд, гарын товчлол.
  - Review-ийн линк тухайн агшинд үсэрч, тоглогчийг 8 s тойруулан тэмдэглэнэ (`ReplayBridge.goto`).
- **Байхгүй зүйл:**
  - zoom, pan
  - харах чиглэлийн конус, хэн хэнийг харж байгаа
  - хэд хэдэн раундыг давхарлах
  - тэмдэглэл, зураас, bookmark
  - клип гаргах
  - Win probability-ийн графикийн курсор Replay-ийн цагтай синк хийгддэггүй

**Код:** `player.ts` 1,253 мөр. `mountReplay` нь 38 дотоод функцтэй нэг closure, `Replay.tsx`-ийн element id-уудтай уягдсан.

**Deep link:**

- `?round=` ажилладаг.
- Агшин ба тоглогч Review → Replay bridge-ээр л дамждаг, URL-д ордоггүй (`MapReview.tsx:33-48`).
- Game Plan-ийн Maps tab-ийн map/side, Players tab-ийн тоглогч, heatmap-ийн сонголт зөвхөн component state-д хадгалагддаг (`panels.tsx:513-514,684`, `MapGrid.tsx:35`).

**Heatmap ба movement:**

- Kill/death-ийн байрлалыг browser-т gaussian KDE-ээр зурна (bandwidth 0.22, inferno/viridis).
- Movement нь route бүрийн medoid walk-ийг хөдөлгөөнтэй үзүүлнэ (`src/gameplan/scene.ts`).
- Харин байрлалын (kill биш) heatmap, цагаар хуваах, buy type-аар шүүх боломж байхгүй.

**Map:**

- Одоогийн Active Duty (2026-07-08-аас): Ancient, Anubis, Cache, Dust II, Inferno, Mirage, Nuke (`12-research-sources.md`).
- Эдгээр бүгд болон Overpass radar PNG, Spot-ийн polygon-той. Polygon нь kill-ийн байрлалын 98–100%-ийг хамардаг.
- Train (2026-01-21 хүртэл Active Duty байсан) датанд огт байхгүй.
- `spots.version()` бүх файлыг hash хийдэг тул нэг Map-ийн Spot засахад бүх Review rebuild хийгддэг.

**Mobile:** Replay-ийн товчлол гар шаарддаг, tooltip нь hover-оор ажилладаг.

## Шийдэл

### VIZ-1. `player.ts`-ийг модуль болгох (P1, M, VIZ-2..8-аас өмнө)

`state` (раунд, цаг, тоглогчид), `renderer` (canvas давхаргууд), `controls` (гар, хулгана, touch), `bridge` (`goto`, `onRound`, шинээр `onTime`) гэсэн хэсгүүдэд хуваана. Element id-ийн уялдааг props/refs болгоно. Vitest-ээр state-ийн interpolate, цагийн тооцоог шалгана. Ингэхгүй бол дараагийн функц бүр 1,253 мөртэй closure-ийг улам томруулна.

### VIZ-2. Deep link ба хуваалцах (P1, S)

> **Төлөв:** 🟡 `fa46c05` (improvement-01). `?round&t&player` линк, «Энэ агшны холбоос хуулах» товч. Game Plan-ийн сонголтыг URL-д оруулах нь үлдсэн.

- URL: `/matches/:id/m/:n?round=14&t=63.5&player=<steamid>`. "Энэ агшны линк хуулах" товч нэмнэ.
- Game Plan-ийн map/side, тоглогч, heatmap-ийн сонголтыг URL-д оруулна.
- Note (RV-7), Briefing (WS-5), Assistant (AS-5) бүгд энэ линкийг ашиглана.

### VIZ-3. Zoom, pan, тоглогчийг дагах камер, touch (P1, M)

> **Төлөв:** ✅ `1348038` (improvement-01). Wheel/pinch zoom, чирж pan, Shift+click дагах, double-click буцаах; утсан дээр шудрахад цаг гүйлгэнэ.

- Wheel эсвэл pinch-ээр zoom хийнэ, чирж pan хийнэ. "Тоглогчийг дагах" горимтой.
- Утсан дээр: товшвол play/pause, шудрахад цаг гүйлгэнэ. Ингэвэл тоглогчид Briefing-ийн линкийг утаснаасаа үзэж чадна.

### VIZ-4. Харах чиглэл ба Sighting (P1, M)

> **Төлөв:** 🟡 `5b3a466` (improvement-01). Харах конус ба Sighting-ийн шугам (`REPLAY_SCHEMA` 6); Sighting-гүй Map дээр зөвхөн конус, шалтгааныг хэлнэ. Раунд бүрийн анхны контактын тэмдэг үлдсэн.

- Ticks-ийн yaw-аас харах конус (90°) зурна. Toggle-тэй.
- Sighting байгаа Match Map дээр "хэн хэнийг харж байгаа" гэсэн шугамыг зурж, раунд бүрийн анхны контактыг тэмдэглэнэ. Sighting-гүй Map дээр toggle идэвхгүй байж, шалтгаанаа хэлнэ (ADR 0006).
- Аудитаар Sighting локал 113 Map-ийн зөвхөн 6-д нь байсан. Тиймээс DATA-1 (upload) ба шинэ Scout-ууд хэрэгтэй.

### VIZ-5. Олон раундыг давхарлах ("ghost" горим) (P1, M)

> **Төлөв:** 🟡 `dfd0efb` (improvement-01). `/ghost`: сонгосон раундуудыг freeze end-ээс синк хийж давхарлана, Playbook-ийн evidence-ээс «⧉ давхар». Онооны байдал, Setup, Set play-ээр шүүх нь үлдсэн.

Anti-strat-ийн хамгийн их хэрэглэгддэг харагдац: сонгосон N раундыг (жишээ нь өрсөлдөгчийн Inferno-гийн бүх Full buy T раунд) freeze end-ээс эхлэн синк хийж тоглуулна. Тоглогч бүр бүдэг цэг, мөрөөр харагдана.

- **Дата:** одоогийн `replay_rounds` (раунд бүр ~37 KB gzip). 30 раунд ≈ 1.1 MB тул шинэ хүснэгт хэрэггүй.
- **Шүүлтүүр:**
  - Map, Side, Team, Buy type, онооны байдал, Spot ба Callout
  - Setup (Playbook-ийн habit-аар, жишээ нь "B-д 3 хүн")
  - Set play
- **Playbook-оос нээх:** Playbook-ийн мөр бүрийн "Replay" evidence линк (одоо 8 хүртэл ref) "бүгдийг давхарлаж үзэх" товчтой болно.

### VIZ-6. Win probability-ийн курсор (P1, S)

> **Төлөв:** ✅ `fa46c05` (improvement-01). WinChart Replay-ийн цагийг даган курсор зурна, дарахад тэр агшин руу үсэрнэ.

`ReplayBridge`-д `onTime` нэмнэ. WinChart Replay-ийн цагийг даган курсор зурна, график дээр дарахад тэр агшин руу үсэрнэ.

### VIZ-7. Раунд хайх: "ийм раунд олж өг" (P1, L)

> **Төлөв:** 🟡 `1a799c6` (improvement-01). Токеныг `round_states` биш `replay_rounds.tokens`-д (Replay-тэй хамт, `REPLAY_SCHEMA` 7), Callout-оор; ±2 s цонх, Team ба buy шүүлт, үр дүн ghost горимд. Spot-оор хайх, үр дүнгийн нийт heatmap үлдсэн.

ggViz-ийн арга (Xenopoulos нар, CHI PLAY 2022, `12-research-sources.md`):

- **Индекс:** тоглоомын төлөвийг токен болгоно. Тал бүрийн тоглогчид аль Callout эсвэл Spot-д хэд байгааг 1 Hz-ээр тоолж, SQL-д `(map, token)`-оор индексжүүлнэ. Ингэснээр 10 сая төлөвөөс хэдхэн секундэд хайдаг.
- **Шинэ derived хүснэгт** `round_states`: `match_map_id`, `round`, `t` (секунд), `ct_token`, `t_token`, `alive_ct`, `alive_t`, `bomb`. Ingest болон `tickdata.derive` үед Tick Data-аас таслана. Шинэ `STATES_SCHEMA` нэмж, `derived_version`-д оруулна.
- **Хайлтын UI:** Map дээр Spot сонгоод "энд 2+ T, 0:15–0:30" гэх мэт нөхцөл тавина. Хэсэгчилсэн query (зөвхөн зарим Spot) болон Team, Buy type-ийн шүүлтүүртэй.
- **Үр дүн:** раундын жагсаалт. Тэдгээрийг VIZ-5-аар давхарлаж үзнэ, нийт дүнг heatmap-аар харуулна.
- **Сул тал:** Callout-ийн хил дээр токен үсэрдэг. Тиймээс хайлт ±2 s цонхтой байна.

### VIZ-8. Coach-ийн зураас ба тэмдэглэл (P1, M, RV-7-той хамт)

> **Төлөв:** 🟡 `1a799c6` (improvement-01). Сум, тойрог, текст Note-тэй хадгалагдаж, Replay дээр тэр агшинд харагдана. Briefing-д харуулах нь үлдсэн.

- Replay-ийг зогсоож сум, тойрог, текст зурна. Зурсныг Note (раунд, агшин, тоглогчид) болгон хадгална. Review болон Briefing-д харагдана.
- Тоглогч өөрт нь хаягласан Note-ийг `/me` дээр харна (WS-4).

### VIZ-9. Heatmap v2 (P1, M)

> **Төлөв:** 🟡 `ae4c470` (improvement-01). Хугацааны үе (0–15/15–30/30–60/60+/plant-ийн дараа), buy, Pool-той diff heatmap. Байрлалын heatmap ба «B дээр хаана үхдэг вэ» товч үлдсэн.

- **Цагаар хуваах:** 0–15 s, 15–30 s, 30–60 s, plant-ийн дараа.
- **Байрлалын heatmap:** kill биш, хаана зогсдог вэ. Хадгалсан walks ба `round_snapshots`-аас.
- **Шүүлтүүр:** Buy type, Side, тоглогч бүр.
- **Харьцуулалт:** энэ өрсөлдөгч ба Pool-ийн дундаж (diff heatmap). Жишээ нь "энэ баг B apartments-д Pool-оос 2 дахин их нас бардаг".
- **Хурдан асуулт:** "B дээр хаана үхдэг вэ" гэвэл Map, Side, Callout-оор шүүсэн нэг товшилт.

### VIZ-10. Utility-ийн газрын зураг (P2, M, SB-3-тай хамт)

Өрсөлдөгчийн Map ба Side бүрийн smoke, molotov, flash буусан цэгүүдийг харуулна. Шидсэн байрлалаар нь (trajectory-ийн эхний цэг) lineup болгон бүлэглэж, хугацааг нь харуулна. Set play болон Strat руу линктэй.

### VIZ-11. Map-ийн хамрах хүрээ ба pool-ийн солигдол (P1, S)

> **Төлөв:** 🟡 `b5c5e70` (improvement-01). Spot-ийн хувилбар Map бүрээр (`match_map_reviews.spots_version`). Map pool-ийн огноотой тохиргоо TM-6-д (`36ec17f`). Шинэ Map-ийн checklist, patch-ийн дараах Spot шалгалт үлдсэн.

- **Map pool-ийн тохиргоо:** hard-code хийсэн `ACTIVE_DUTY`-г (`mapstrategy.py:53`) огноотой тохиргоогоор солино. Жишээ нь `de_cache: 2026-07-08–`, `de_overpass: 2025-07-16–2026-07-08` (TM-6, DATA-7).
- **Шинэ Map:** pool-д Map орж ирэх бүрт radar PNG, Valve-ийн calibration (`radar.py`), Spot polygon-ыг бэлдэх checklist. Одоогийн 7 Map бүгд бэлэн.
- **Patch-ийн дараа:** Cache-д олон patch гарсан, дата цөөн. Тиймээс түүний Spot, Dust II-ийн mid-ийг дахин шалгана (`12-research-sources.md`).
- **Spot-ийн хувилбар:** `spots.version()`-ийг Map бүрээр тусад нь болгоно (`spots.py:97-104`, `review.py:144-145`). Тэгвэл нэг Map-ийн Spot засахад зөвхөн тэр Map-ийн Review rebuild хийгдэнэ.

### VIZ-12. Дуу чимээний давхарга (P2, S)

Хадгалсан `footsteps` хүснэгтээс (Map бүрт ~17 K мөр, одоо огт уншдаггүй) хөлийн чимээний тойргийг зурна. Хэн хаана дуу гаргасан, хэн чимээгүй rotate хийсэн нь харагдана. Demo дахин татах шаардлагагүй.

### VIZ-13. Клип гаргах (P2, M)

Сонгосон хугацааны canvas-ийг `MediaRecorder`-ээр WebM болгож browser-т бичнэ. Сервер дээр render хийхгүй. Note эсвэл Briefing-д хавсаргана.

## Дараалал

1. VIZ-2 (S), VIZ-6 (S), VIZ-11 (S): хурдан ашиг.
2. VIZ-1 (refactor).
3. VIZ-5 ба VIZ-3: anti-strat-д хамгийн их хэрэгтэй.
4. VIZ-9, VIZ-4.
5. VIZ-7 (round search, L): `round_states` хүснэгт тооцоолох шаардлагатай.
6. VIZ-8: RV-7-той хамт.
7. VIZ-10, VIZ-12, VIZ-13 (P2).

## Хүлээгдэх үр дүн

- "Өрсөлдөгчийн Mirage-ийн бүх Full buy T раундыг давхарлаж үзэх" ажил 3 товшилтод багтана (одоо боломжгүй).
- "B apartments-д 0:20-д 3+ T байсан раундууд" гэсэн хайлт 2 секундэд үр дүн өгнө.
- Тоглогч coach-ийн явуулсан линкээр утаснаасаа тухайн агшныг шууд үзнэ.

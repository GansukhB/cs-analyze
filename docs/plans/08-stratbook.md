# 08. Stratbook: манай Strat, lineup, гүйцэтгэлийн хэмжилт

> Item-ийн ID: `SB-…`. Нэр томъёо: Stratbook, Strat (Staff бичдэг), Set play (датагаас олддог), Scrim, Self-scout (`CONTEXT.md`). Grilling Q16: P1. ADR 0010, 0011.

## Зорилго

Багийн өөрийн стратеги одоо Google Drive, Discord-д тарсан байна. Түүнийг өгөгдөлтэй холбосон нэг газар болгох:

- Strat бүр нэр, үүрэг, гранатын lineup, жишээ Round-той.
- Official тоглолт болон Scrim-д хэдэн удаа тоглогдож, хэдэн хувь нь хожсон нь автоматаар тоологдоно.

Ингэснээр coach "энэ execute ажилладаг уу", "бид хэт урьдчилан таамаглагдахуйц болсон уу", "veto-д Map бүр дээр хэдэн бэлэн Strat байна" гэдгийг тоогоор хардаг болно.

## Зах зээл дээрх байдал (`12-research-sources.md`)

| Хэрэгсэл | Юу санал болгодог |
|---|---|
| Skybox EDGE Tier 1 (€1,299/сар) | "Private Playbook": багийн өөрийн тактикийг 1,000 багт автоматаар хянадаг |
| cs2.cam | Хожлын хувьтай private playbook, XLSX/PDF export, Strategic Board |
| RoundIQ | Strat Builder, teleport командтай "Stuff Book" |
| Guild Order | Map, Side, Callout-аар tag-тай strat book |
| Metastack | Google Drive-ийг орлох зорилготой |

Нууцлалын эрсдэл бодитой: 2021 онд Heroic-ийн стратегийн хавтас задарсныг Google Drive-ийн хандалтын бүртгэлээр мөрдсөн.

Датанд холбогдсон, гүйцэтгэлийг нь хэмждэг, хямд stratbook зах зээлд ховор.

## Одоогийн байдал

- Stratbook огт байхгүй.
- **Set play-ийн илрүүлэлт байгаа** (`playbook.py:531-619`):
  - Freeze end-ээс хойш эхний 40 s-д smoke, molotov-ийн (төрөл, Callout) хосуудыг Apriori-аар олдог.
  - Round бүр тухайн багцын хос бүр median-аасаа 5 s дотор буусан бол тэр багцыг дэмжинэ гэж тооцогдоно.
  - 4+ Round, хамгийн ихдээ 3 багц.
  - Энэ нь Strat-ийг Round-тай тааруулах суурь болно.
- **Гранатын бүтэн trajectory** bundle-ийн `grenades` хүснэгтэд бий (Map бүрт ~2 сая мөр). Одоо зөвхөн Replay-д ашигладаг.
- **`grenade_thrown` event** (шидсэн агшин, хүн) parse хийгддэггүй (DATA-5).

## Шийдэл

### SB-1. Stratbook ба Strat-ийн загвар (P1, M)

> **Төлөв:** ✅ `7e09024` (improvement-01). Strat-ийн загвар, Map × Side grid, засвар, хувилбар, жишээ раунд.

- **`strats`:**
  - `id`, `workspace_id`, `team_id` (my team), `game_map_id`, `side`
  - `name`, `kind`: default | execute | fake | retake | CT setup | pistol | anti-eco | force
  - `description`
  - `roles` JSON: slot бүрт хэн юу хийх. Тоглогч (Steam id) эсвэл үүргийн slot (PL-4).
  - `timings`, `variations`, `calls` (дуудлагын үг)
  - `tags`, `status`: draft | active | retired
  - `visibility`: Staff | team
  - `created_by_id`, timestamps
- **`strat_grenades`:** `strat_id`, `lineup_id` (SB-3), `slot`, `order`, `at_s` (freeze end-ээс хойших секунд).
- **`strat_examples`:** `strat_id`, `match_map_id`, `round`. Official эсвэл Scrim, гараар эсвэл автоматаар (SB-4).
- **`strat_versions`:** өөрчлөлт бүрийн хуулбар.
- **UI:**
  - `/stratbook`: Map ба Side-ийн grid, шүүлтүүр.
  - Strat-ийн хуудас:
    - тайлбар
    - slot бүрийн үүрэг
    - lineup-ийн карт
    - жишээ Round-уудыг ghost горимоор (VIZ-5)
    - гүйцэтгэлийн тоо (SB-4)

### SB-2. Set play-ээс Strat (P1, M)

> **Төлөв:** ✅ `c20e602` (improvement-01). Playbook-ийн Set play-ээс нэг товчоор Strat ба эсрэг Strat.

- **Өөрийн Set play-ээс:** official болон Scrim-ээс олдсон Set play бүрт "Strat болгож хадгалах" товч. Гранат, жишээ Round, timing урьдчилан бөглөгдөнө.
- **Өрсөлдөгчийн Set play-ээс:** Playbook дахь Set play бүрт "эсрэг Strat" линк. Тэр нь манай CT Setup эсвэл retake-ийн Strat-ийг холбоно. GP-3-ийн "манай төлөвлөгөө" хэсэгт харагдана.
- **ADR 0010:** өрсөлдөгчийн Set play зөвхөн official тоглолтоос гарна. Scrim-ийн түнш багийнх орохгүй.

### SB-3. Lineup-ийн сан (P1, M; DATA-5-ийн `grenade_thrown`-оос сайжирна)

> **Төлөв:** ✅ `c8d7629` (improvement-01). Lineup-ийн сан (spot, aim, нислэг, хэн, setpos). Jump/run-throw тэмдэглэгээ үлдсэн.

- **Эх дата:**
  - Bundle-ийн `grenades` trajectory-ийн эхний цэг.
  - Шидсэн tick дээрх ticks-ийн X, Y, Z, yaw, pitch.
  - `grenade_thrown` бэлэн болмогц: яг шидсэн tick, үсэрсэн эсэх (`is_airborne`).
- **Бүлэглэх:** Map бүрт буусан cell + шидсэн байрлалаар.
- **Lineup-ийн карт:**
  - шидэх байрлал, онилох yaw/pitch
  - jump-throw, run-throw эсэх
  - буух Callout ба Spot, нислэгийн хугацаа
- **Practice server-т:** `setpos`, `setang` командыг хуулах товч. Ингэвэл тоглоом дотор давтана (RoundIQ, Refrag NADR-ын санаа).
- **Хэрэглээ:**
  - Манай lineup-ууд Strat-д холбогдоно.
  - Өрсөлдөгчийнх нь utility-ийн газрын зурагт (VIZ-10).

### SB-4. Strat-ийн гүйцэтгэлийг хэмжих (P1, M–L)

> **Төлөв:** ✅ `63b2fc9` (improvement-01). Гранатаар раунд тааруулах, батлах/хасах, гүйцэтгэл (80% муж, buy, official/Scrim), map-ын хамрах хүрээ veto лабораторид.

- **Тааруулах:** Official болон Scrim-ийн Round бүрийг Strat-уудтай ижил төстэй байдлаар тааруулна:
  - Strat-ийн гранатууд тодорхой цонхонд буусан эсэх. Set play-ийн 5 s-ийн дүрмийг дахин ашиглана.
  - Freeze end + 20 s дэх тоглогчдын байрлал (Setup).
  - Таарсан Round нь `strat_examples`-д "автомат" гэж орно. Staff баталгаажуулах эсвэл хасах боломжтой.
- **Strat бүрийн тайлан:**
  - хэдэн удаа тоглогдсон, хожлын хувь (интервалтай, PL-3)
  - Buy type, өрсөлдөгчийн түвшингээр (FC-1) задаргаа
  - сүүлд хэзээ тоглогдсон, Scrim ба official-ийн ялгаа
- **Map бүрийн хамрах хүрээ:** active Strat-ийн тоо, сүүлийн 30 хоногт туршсан нь. Энэ нь veto лабораторийн "бэлэн байдал" болно (GP-10).
- **Урьдчилан таамаглагдах байдал:** official тоглолтод нэг Strat-ийг хэт давтах нь Self-scout-ийн индексийг өсгөнө (GP-11).

### SB-5. Strat-ийг бусад багуудад хайх (P2, M; VIZ-7-ийн дараа)

> **Төлөв:** ✅ `3d0a10a` (improvement-01). Strat-ийн гранатаар бусад бүх багийн раундаас хайна: аль баг тоглодог, хожил (Wilson 80%), раундуудыг ghost горимд.

- Strat-ийн хурууны хээгээр (гранат ба байрлал) Pool-ийн Round-уудаас хайна.
- **Үр дүн:** өөр ямар баг үүнийг тоглодог, тэдний амжилт.
- **Ашиглалт:**
  - Шинэ санааг дасгал хийхээс өмнө үнэлнэ.
  - Өрсөлдөгчид энэ Strat-ийг мэддэг байж болзошгүйг анхааруулна.
- Skybox-ийн "Private Playbook"-той ижил санаа, гэхдээ манай датан дээр.

### SB-6. Хуваалцах ба танилцуулах (P1, S–M)

> **Төлөв:** ✅ `86d0a18` (improvement-01). Strat-ийн граната lineup-тай, хэвлэх картад setpos; Briefing-д Map бүрийн хуваалцсан идэвхтэй Strat-ын линк.

- Strat-ийг багтаа хуваалцана. Player User read-only уншина (WS-4).
- Хэвлэх карт: Map, Side, slot бүрийн үүрэг, lineup.
- Briefing дахь "манай төлөвлөгөө" мөрөөс Strat руу линк (WS-5, GP-3).

### SB-7. Нууцлал (P1, S)

> **Төлөв:** ✅ `7e09024` (improvement-01). Засвар зөвхөн Staff, багт хуваалцах, бүх уншилт/хэвлэлт/засварын бүртгэл. Watermark (P2) үлдсэн.

- **Хамгийн эмзэг дата:** засах эрх зөвхөн Staff-д. Strat бүрийг тусад нь хуваалцана. Нийтийн линк гаргахгүй.
- **Audit log:** хэн нээсэн, хэвлэсэн, export хийсэн (WS-7). Задрал гарвал эх сурвалжийг олох хэрэгсэл.
- **P2:** export-д хэрэглэгчийн нэрийн watermark.

### SB-8. Стратегийн самбар (P2, M)

> **Төлөв:** ✅ `662ed55` (improvement-01). Strat-ийн самбар radar дээр: тоглогч (талаар дугаарласан), smoke/molotov жинхэнэ радиусаар, flash, сум, үг; world units-аар хадгалагдана.

Radar дээр тоглогчдын байрлал, utility-г зурж шинэ Strat төлөвлөнө. Зурсныг Strat-тай хамт хадгална. VIZ-8-ийн зурах хэрэгслийг дахин ашиглана.

## Дараалал

1. SB-1, SB-7.
2. SB-2.
3. SB-3: DATA-5-аас өмнө trajectory-ээр эхний хувилбар.
4. SB-6.
5. SB-4.
6. SB-5, SB-8 (P2).

## Хүлээгдэх үр дүн

- Map бүрт манай active Strat-ууд нэг дор, жишээ Round, lineup, гүйцэтгэлийн тоотойгоо байна.
- Scrim бүрийн дараа "B execute 3: 7 удаа, 5 хожил; хамгийн сүүлд Пүрэв гарагт" гэдэг автоматаар шинэчлэгдэнэ.
- Тоглогч Strat-аа утсан дээрээ уншиж, lineup-ийн `setpos`-ийг practice server-т хуулна.

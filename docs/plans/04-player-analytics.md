# 04. Тоглогчийн анализ: давуу, сул тал, форм, үүрэг

> Item-ийн ID: `PL-…`. Нэр томъёо: Player, Lineup, Swing, Finding, Pool, Strength, Weakness, Development plan (`CONTEXT.md`). Статистикийн нийтлэг аргыг TM-1 (`05-team-analytics.md`) тодорхойлно. Энэ файл түүнийг ашиглана.

## Зорилго

Coach-ийн хоёр асуултад тоо, жишиг, нотолгоотойгоор хариулах:

1. **Өөрийн тоглогч бүр** юугаараа сайн, юун дээр ажиллах ёстой вэ? Эдгээр тоо Development plan-ийн KPI болно (`07-review-development.md`).
2. **Өрсөлдөгчийн тоглогч бүрийг** хэрхэн тоглох вэ: хаана, юугаараа аюултай, хаана сул вэ? Энэ нь Playbook-ийн matchup болон Briefing-д орно.

Тоо бүрийг ижил үүрэгтэй тоглогчидтой (role peers) харьцуулна. Дээжийн хэмжээ, итгэлийн интервал, Replay-ийн нотолгоог хамт харуулна. Нэг тоглолтын азаар гарсан тоог "сул тал" гэж хэлэхгүй.

## Одоогийн байдал (кодын аудит, 2026-10-21)

- **Тоглогчийн хуудас байхгүй.**
  - Тоглогчийн мэдээлэл тарсан: Team page-ийн chip (линк биш, `TeamPlayer`-д Steam id байхгүй, `schemas.py:351-355`), Game Plan-ийн Players tab (зөвхөн Fixture дотор), Match Map-ийн PlayersTable, MatchOverview-ийн Swing.
  - Форм, trend, Map бүрээр задлах боломж байхгүй.
- **Үүрэг** (`roles.py`): 7 үүрэг (awper, entry, support, lurker, trader, anchor, rotator).
  - Score нь Side бүрийн league baseline-тай харьцуулсан z-ийн жигнэсэн дундаж. SD-ийн floor нь max(10%·mean, 0.01).
  - Fit: strong ≥0.6, solid ≥−0.2, below par ≥−0.8. Confidence: 12 Round-оос бага бол none, 40-өөс бага бол thin.
  - Олдсон алдаанууд:
    - entry-ийн KPI `open_round_win_pct` огт тооцоологддоггүй (`roles.py:96`).
    - Үүргийг тодорхойлдог signal нь түүнийг дүгнэх KPI-тай давхацдаг (тойрог логик). Жишээ нь Bart4k "lurker (split)" гэж ангилагдаад, бага lurk хийсэн гэж муу дүн авдаг.
    - Anchor-ийн KPI-д ADR орсон (тайлбар нь эсрэгээр хэлдэг).
    - Үүргийг багийн хэмжээнд хуваарилдаггүй. 5star-д CT anchor, support "дутуу" гэж гардаг.
- **Player plan** (`playerplan.py:619-743`): тогтмол босготой заавар.
  - Signature weapon: kill-ийн ≥30%, 5+ kill.
  - Utility ≥1.4/Round, flash assist ≥0.08/Round.
  - Duel ≥4, net ≤−6 эсвэл ≥+4.
  - Өөрчлөлт |Δ| ≥8, 40+ Round-оор.
- **Linchpin:** тоглогч эхний 30 s-д нас барсан Round-ын багийн хожлын хувийг бусад Round-тай харьцуулдаг. Бараг бүх тоглогч босгыг давдаг. 5star-ийн бүх тоглогч 20.2–33.2, MongolZ-ийн 4 тоглогч 22+ гэж гарсан тул энэ нь noise. Side болон Buy type-аар ч хольцтой.
- **Duel matrix:** зөвхөн Head-to-head Match Map-аас тооцдог.
  - Тоглогчийг Steam id биш, нэрээр нь тааруулдаг: duel matrix (`gameplan.py:419-435`), roster continuity (`1062-1080`), Lineup-ийн шүүлтүүр (`playerplan.py:90-92,522`, `roles.py:1100-1102`).
- **Trade-ийн гурван тодорхойлолт:**
  - Ingest: алуурчин 5 s дотор үхвэл traded.
  - Roles: багийн гишүүн нас барснаас 5 s дотор хийсэн дурын kill.
  - awpy-ийн KAST: 3 s.
- **Review:** Match Map бүрт тоглогчийн Swing, Finding. `review_pool`-ийн Player line Map дээр 24 Round, бүх Map-д 40 Round, Pool-д 8+ тоглогч шаарддаг.
- **Aim ба Sighting:** schema 13 нь `aim` (pitch, scoped, ducking, walking 16 Hz + shot бүр), `sightings` хүснэгттэй. Локал 113 Map-ийн зөвхөн 6-д нь бий. Тэдгээрийг ашигладаг нь Review-ийн 4 код л.
- **Шинэ тоглогч:** өмнөх багийнх нь датагаар үнэлдэг (`lineup.elsewhere`). Энэ зөв.

## Шийдэл

### PL-1. Тодорхойлолтуудыг нэгтгэх (P0, S)

> **Төлөв:** ✅ `acc633c` (improvement-01).

- **Trade:** CONTEXT.md-ийн нэг тодорхойлолтыг (5 s) ingest, `roles`, Review, KAST бүгдэд хэрэглэнэ. awpy-ийн 3 s KAST-ийг override хийнэ.
- **Pistol:** зөвхөн Round 1 ба 13 (`mapstrategy.pistol_rounds`-ийг засаж, `test_gameplan.py:133-134`-ийн буруу дүрмийг түгжсэн тестийг засна). Одоо overtime-ийн хагас бүрийн эхний Round pistol болж тоологддог тул локалд 226 жинхэнэ pistol дээр 41 Round нэмэгдсэн.
- **Тоглогчийг таних:** хаа сайгүй Steam id-аар (дээрх гурван газар).
- `open_round_win_pct`-ийг тооцох эсвэл хасах.

**Хүлээгдэх үр дүн:** нэг тоглогчийн trade-ийн тоо Review, Players tab, Roles tab гурав дээр ижил гарна.

### PL-2. Тоглогчийн хуудас `/players/:steamid` (P0, M; дараа нь өргөтгөнө)

> **Төлөв:** ✅ `dd45be3` (improvement-01). v1. Өргөтгөлүүд нь PL-3-аас хойшхи item-уудад.

- **Толгой:** нэрс (alias), багуудын түүх (`map_rosters`-аас), Side бүрийн үүрэг (PL-4), нийт Map, сүүлд тоглосон огноо.
- **Хэсгүүд:**
  1. **Форм:** Match Map бүрийн цагийн шугам. Үзүүлэлтүүд нь Swing/Round (тоглогчийн гол тоо, Review-ээс), KAST, ADR, opening duel W/L, trade. 5 ба 10 Map-ын гулсах дундажийг интервалын туузтай харуулна. Тэмдэглэгээ: LAN эсвэл online, өрсөлдөгчийн Rating (FC-1-ийн дараа).
  2. **Map × Side хүснэгт:** Round-ын тоо, Swing/Round, KPI бүр. Тоо бүрийн хажууд role peers доторх percentile (PL-3).
  3. **Strength, Weakness:** PL-3-ийн аргаар. Мөр бүрт тоо, peer percentile, Evidence (Round, Match Map) ба Replay-ийн линк.
  4. **Байрлал:** Map, Side бүрт 20 s дэх дуртай Spot (`round_snapshots`), kill/death heatmap (`heatmap.ts`-ийг тоглогчийн шүүлтүүртэй), route.
  5. **Зэвсэг:** signature weapon, AWP-ийн хувь, pistol Round-ын үзүүлэлт.
  6. **Finding-ийн давтамж:** Mistake, Missed chance бүрийн 24 Round тутмын тоо role peers-тэй харьцуулсан. Development plan-ийн гол эх сурвалж.
  7. **Aim:** Sighting, aim байгаа Map-аас (PL-5).
- **API:** `GET /players/{steamid}?map=&side=&since=`, `GET /players/{steamid}/form`. Апп дахь тоглогчийн нэр бүр энэ хуудас руу линктэй болно.
- **Эрх:** Staff бүх тоглогчийг харна. Player User зөвхөн өөрийгөө харна (`01-workspace-access.md`).

### PL-3. Давуу, сул талыг тодорхойлох статистик (P1, M; TM-1-ийн хэрэглээ)

> **Төлөв:** ✅ `7ada7cb` (improvement-01). Role KPI: хувь нь Beta prior (тоглогчийг хассан cohort), тасралтгүй нь n/(n+k). Map бүрийн жишиг, цагийн жин (τ = 90 хоног) үлдсэн.

Одоогийн "z ≥ 0.8, SD-ийн floor 10%" дүрмийг дараах аргаар солино:

- **Жишиг:** ижил үүрэгтэй тоглогчид (PL-4-ийн soft role-оор жигнэнэ), Side бүрээр. Дээж хангалттай бол Map бүрээр.
- **Хувь (rate):** beta-binomial empirical Bayes. Prior-ийг peers дээр тааруулна, posterior нь (x+α)/(n+α+β).
- **Тасралтгүй тоо:** n/(n+k)-ээр shrink хийнэ. k-г өөрийн Pool дээрх split-half reliability-аас уншина.
- **Бодит дээж:**
  - Нэг Map доторх Round-ууд хоорондоо хамааралтай (ρ ≈ 0.074, Parshakov 2026). Тиймээс N_eff = N / (1+(N−1)ρ). 12 Round-ын хагас бодитоор ~6.6 бие даасан Round болно.
  - Цагийн жин exp(−Δt/τ), τ = 90 хоног.
- **Тэмдэглэх дүрэм:**
  - Тоглогч бүрийн бүх KPI дээр local false sign rate < 0.1 (эсвэл BH-FDR q = 0.1).
  - Хамгийн багадаа 8 үйл явдал, 3 Match Map.
  - Эрэмбэлэхдээ нөлөөг Round-аар (Swing-тэй ижил нэгжээр) хэмжинэ.
- **Интервал:** Match Map-аар bootstrap хийнэ.

**Хүлээгдэх үр дүн:** тоглогчийн Strength/Weakness-ийн жагсаалт долоо хоног бүр санамсаргүй солигдохгүй. Одоо 5star-ийн 5 тоглогч бүгд "linchpin" гэж гардаг шиг үзэгдэл алга болно.

### PL-4. Үүрэг v2 (P1, M)

> **Төлөв:** 🟡 `30848b0` (improvement-01). Staff-ийн зарласан үүрэг (Side, Map), soft role-ийн хувь. GMM ба Round бүрийн slot assignment (Hungarian) үлдсэн.

- **Онцлог:**
  - opening duel оролдлого
  - анхны контактын цаг
  - trade
  - шидсэн utility, flash assist
  - багийн төвөөс ба хамгийн ойрын багийн гишүүнээс хол байх
  - хөдөлгөөн
  - 20 s, 40 s болон plant үеийн байрлал
- **Ангилах арга:** Map × Side бүрт GMM-ээр soft үүрэг (хувь) тооцно. Тоглогч бүрт нэг шошго биш, хувиар илэрхийлнэ.
- **Багийн хуваарилалт:** Round бүрийн 5 тоглогчийг багийн slot загвартай Hungarian algorithm-оор тааруулна (Bialkowski нар). Ингэснээр "Nuke дээр B anchor хэн бэ" гэдэг тогтвортой болно.
- **Тойрог логикийг арилгах:** үүргийг тодорхойлдог signal ба дүгнэх KPI-г салгана. Тоглогчийг өөрийн cohort-оос хасна.
- **Staff-ын зарласан үүрэг:** Staff өөрийн тоглогчийн үүргийг Map бүрээр тохируулж болно ("declared role"). Тэр нь жишигт truth болно. Өрсөлдөгчид inferred үүрэг хэрэглэнэ.
- **UI:** Roles tab болон Player page-д дүгнэлтийг хөдөлгөж буй KPI мөрүүдийг харуулна. "Split" үүрэгтэй хоёр тоглогчийг хооронд нь харьцуулахгүй.
- **Үүрэг бүрийн KPI** (`12-research-sources.md`: R2b, R3):

| Үүрэг | Гол KPI |
|---|---|
| Entry / spacetaker (T) | Opening оролдлогын хувь, opening-ийн хожил, traded-death % (үхэхэд нь trade хийгдсэн эсэх) |
| Lurker (T) | Багийн төвөөс зай, хожуу ба ар талаас хийсэн kill, амьд үлдэлт, rotate-ийг саатуулсан хугацаа |
| Anchor (CT) | Тусламж ирэх хүртэл барьсан хугацаа, retake-д оролцсон, site hit-ийн үеийн амьд үлдэлт |
| Rotator (CT) | Rotate хийх хугацаа, trade |
| AWPer | Opening kill %, нас барахдаа AWP алдсан тоо, Round тутмын AWP kill |
| Support | Flash assist, Round тутмын utility, team-flash-ийн хувь |
| Trader | Trade kill, trade хийх хугацаа |

### PL-5. Aim ба механикийн үзүүлэлт (P1, M; Sighting-тай Map хэрэгтэй)

> **Төлөв:** 🟡 `9d8ac98` (improvement-01). Engagement-ийн TTD, crosshair, counter-strafe, эхний сум; percentile. VisibilityChecker ба smoke шалгалт үлдсэн.

Leetify-ийн тодорхойлолтыг өөрийн датанд тааруулна (`12-research-sources.md`):

- **Time to damage:** анхны Sighting-аас анхны damage хүртэлх хугацааны median. 1 s-ээс урт тохиолдлыг хасна.
- **Crosshair placement:** эсрэг тоглогч анх харагдах агшинд тоглогчийн харж буй чиглэл ба эсрэг тоглогчийн толгой руу чиглэсэн векторын хоорондох өнцөг. Нүдний өндөр зогсож 64, сууж 46.
- **Counter-strafe %:** харагдаж буй эсрэг тоглогч руу rifle-аар буудахдаа зэвсгийн дээд хурдны 34%-иас доош хурдтай байсан хувь.
- **Бусад:** эхний сумны онолт, spray-ийн онолт (3+ сум), хөдөлж буудсан хувь. Бүгд зэвсгийн ангиллаар тооцогдоно. Одоогийн `moving_shots` бүх зэвсэгт ганц 40%-ийн босго хэрэглэдэг тул засна.
- **Цэвэр engagement л тооцно:** цайраагүй, smoke дундуур биш байх.
- **Sighting-ийн найдвартай байдал:** ойролцоо утга (ADR 0006: kill-ийн 58%-д л өмнө нь харсан байсан). Тиймээс awpy-ийн `VisibilityChecker` (map-ийн triangle-тай ray cast)-аар шалгана.
- **Харуулах босго:** 100-аас дээш engagement.
- **Хамаарал:** локалд Sighting 6 Map-д л бий. DATA-1 (upload), DATA-4 (Scout дахин) хэрэгтэй.

### PL-6. Eco-adjusted duel ба Swing-ийн дүрэм (P1, M; RV-2-той хамт)

> **Төлөв:** ✅ `3cade6c` (improvement-01). Зэвсгийн ангиллын duel table, тоглогчийн duel хүлээлтээс дээш, Rating-ийн түвшнээр Swing (одоогийн rank-аар).

- **Duel table:** equipment-ийн ангиллын хос (sniper, tier-1 rifle, tier-2 rifle, SMG/shotgun, сайжруулсан pistol, анхны pistol) × Map × Side бүрээр хожих магадлалыг Pool дээр тооцно. Энэ нь HLTV Rating 3.0-ийн eco adjustment-тай ижил санаа. Pistol-той тоглогчийг rifle-аар алах нь rifle vs rifle-ээс бага үнэлэгдэнэ.
- **Swing per Round:** тоглогчийн гол тоо хэвээр. Тооцох дүрмийн өөрчлөлтийг `07-review-development.md` RV-2-д бичсэн (HLTV-ийн 2025–26 оны дүрэм, Leetify-ийн traded-death credit).
- **Өрсөлдөгчөөр задлах** (FC-1-ийн дараа): "Top-30 багийн эсрэг Swing per Round" гэх мэт.

### PL-7. Өрсөлдөгчийн тоглогчийн карт (P1, M)

> **Төлөв:** ✅ `893a30c` (improvement-01). Players tab-ийн картад KPI, Swing-ийн хүрээ, Finding-ийн давтамж; Playbook-ийн тоглогч бүрт Review-ийн мөр, Briefing-д хамт.

Өрсөлдөгчийн Lineup-ийн тоглогч бүрт "X-ийн эсрэг яаж тоглох вэ":

- Map, Side бүрийн үүрэг. CT дээр 20 s дэх Spot, T дээр route.
- **Opening-ийн хандлага:** Round-уудын хэдэн хувьд эхний duel-ийг авдаг, хаана.
- **Зэвсэг:** AWP-ийн хувь, Deagle.
- **Utility-ийн зуршил.**
- **Сул тал** (PL-3-аар баталгаажсан): жишээ нь retake-д бага оролцдог, trade хийгдэлгүй үхэх нь их, crosshair алдаатай.
- **Бусад:** clutch-ийн хандлага, эдийн засгийн зан (save эсвэл force), сүүлийн үеийн форм.
- Мөр бүр Evidence strength-тэй. Playbook-ийн matchup болон Briefing-д энэ карт орно.

### PL-8. Linchpin v2 (P1, S)

> **Төлөв:** ✅ `bed8d61` (improvement-01).

- Тоглогч бүрийн эрт үхлийн нөлөөг багийн дундаж нөлөөтэй харьцуулна. Side болон Buy type-аар давхаргалсан permutation test хийнэ.
- Ач холбогдолтой гарсан тоглогчийг л харуулна. Эсвэл Swing-ээр эрэмбэлнэ.
- `decision._levers`-д үүнийг ашиглана (одоо noise-ийн оройг сонгодог).

### PL-9. Шинэ тоглогч, шилжилтийн scouting (P2, M)

- Сонгон шалгаруулалтын тоглогчийг бусад багт тоглосон бүх Match Map-аар нь role peers-тэй харьцуулна.
- FACEIT-ийн форм нэмнэ (DATA-6).
- "Манай системд тохирох уу": манай дутуу үүрэгтэй тааруулж, тодорхойгүй байдлыг харуулна.

### PL-10. Тогтвортой байдал ба дарамт (P2, S)

- Map бүрийн Swing-ийн хэлбэлзэл (consistency).
- Чухал Round-ууд: match point, pistol, 1vX, ойрхон оноо.
- LAN эсвэл online, өрсөлдөгчийн түвшингээр задлах.

## Дараалал

1. PL-1 (S) хамгийн түрүүнд. Бусад бүх тоо үүнээс хамаарна.
2. PL-2-ийн эхний хувилбар (форм, Map × Side, Finding-ийн давтамж) одоогийн датаар.
3. TM-1-ийн статистикийн модуль → PL-3 → PL-4 → PL-7.
4. PL-6: RV-2-той хамт.
5. PL-5: Sighting-тай Map хангалттай болсон үед.
6. PL-8 бие даасан, PL-9 ба PL-10 сүүлд.

## Хүлээгдэх үр дүн

- Coach тоглогч бүрийн хуудсанд 3 Strength, 3 Weakness, сүүлийн 10 Map-ын формыг интервалтай харна. Нэг Weakness бүр Development plan-ийн KPI болж хувирна.
- Өрсөлдөгчийн тоглогч бүрийн карт Briefing-д автоматаар орж, мөр бүр Evidence strength-тэй байна.

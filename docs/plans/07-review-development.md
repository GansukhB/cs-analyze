# 07. Review ба өөрийн багийн хөгжил

> Item-ийн ID: `RV-…`. Нэр томъёо: Review, Win probability, Swing, Finding (Key play, Mistake, Missed chance, Utility effect), Summary, Pattern, Focus point, Scrim, Development plan (`CONTEXT.md`). ADR 0006, 0007, 0010.

## Зорилго

Хөгжлийн хүрээг (loop) битүү болгох:

**тоглолт / Scrim → Review → Focus point → Development plan ба дасгалын төлөвлөгөө → Scrim → KPI → дараагийн тоглолт → төлөвлөгөөний шалгалт (GP-8)**

Одоо хүрээний эхний хагас (Review, Summary, Focus point) сайн ажиллаж байна. Хоёр дахь хагас (дасгал, хөгжил, хэмжилт) огт байхгүй. Ийм битүү хүрээг холбосон хэрэгсэл зах зээлд олдсонгүй (`12-research-sources.md`). Tier-2 багт тусгай analyst ховор тул автоматжуулалтын үнэ цэнэ хамгийн өндөр.

Нэмэлт болзол: Review-ийн тоо зөв байх ёстой. Буруу Swing буруу Focus point руу, түүнээс буруу дасгал руу хөтөлнө.

## Одоогийн байдал (кодын аудит, 2026-10-21)

**Win probability** (`winprob.py`, `app/data/winprob.json`, 113 Map дээр 2026-10-09-нд fit хийсэн):

- **Онцлог:** амьд тоглогчид, freeze end-ийн equipment, bomb, үлдсэн цаг, kit, Map-ын offset.
- **Model:** pre-plant болон post-plant гэсэн хоёр ridge logistic.
- **Match Map-аар бүлэглэсэн CV:**

| Үе | Log loss (baseline) | Brier | AUC | ECE |
|---|---|---|---|---|
| Pre-plant | 0.473 (0.536) | 0.159 | 0.84 | 0.016 |
| Post-plant | 0.244 (0.267) | 0.075 | 0.95 | 0.011 |

- **Freeze end дээр CT-г хэт үнэлдэг:** force vs full-д 0.293 гэж таамаглахад бодит нь 0.207.
- **Тооцдоггүй зүйлс:** HP, байрлал, үлдсэн utility, bomb-ийн тээгч, эхэлсэн defuse.
- **Калибровк:** кодод тайлагнадаггүй.

**АЛДАА: defuse эхэлсэн үед CT-ийн Win probability 0 болж унадаг.**

- Terminal дүрэм нь defuse эхэлснийг мэддэггүй (`winprob.py:119`). Тиймээс kit-гүй 10 s, kit-тэй 5 s-ээс бага хугацаа үлдээд дууссан defuse +1.0 Swing авдаг (`review.py:792,812-815`).
- 264 defuse-ийн 28.8% нь ≥0.95 Swing авсан. Median нь 0.049.
- Дагалдах алдаа:
  - Defuse хийгдсэн Round-уудын T-ийн advantage_lost-ийн 124-өөс 71 нь худал.
  - CT-ийн 71 худал comeback.
  - Defuse Key play-ийн 55-аас 48 нь, clutch-ийн 28 нь хөөрөгдсөн Swing-тэй.
  - Тоглогчийн Pool гажсан.

**Swing:**

- Kill-ийн Swing-ийг алуурчин, damage-ийн туслагч (≤0.5), цайруулагч (0.20) хооронд хуваадаг. Хохирогч бүх алдагдлыг үүрнэ.
- **Хэнд ч оноогдохгүй үлдэгдэл:** bomb дэлбэрэх, цаг дуусах. Round тутамд дунджаар 0.081, defuse хийгдсэн Round-д 0.317.
- **Teamkill** хоёр удаа тоологддог.
- **Flash-ийн хувь** блайндын доод хязгааргүй.

**Finding:**

- 32 код, 113 Review-д 18,844 Finding (Round тутамд 7.5).
- **Loadout шаарддаг код** (`no_gun_in_hand`, `unused_utility`, `saw_no_shot`, `unscoped_awp`): зөвхөн 9 Map дээр ажилладаг. Хуудас зөвхөн Sighting байхгүйг хэлдэг, Loadout байхгүйг хэлдэггүй. `review_pool` нь Sighting-ийн кодуудыг л хязгаарладаг тул эдгээр кодын давтамж тоглолтын бус, датаны хүртээмжийн нөлөөг харуулдаг.
- **`lost_weapon_save`:** 1,636-ийн 20% нь хагас эсвэл Map-ын сүүлийн Round-д гардаг. Тэр үед буу дараагийн Round руу шилжихгүй тул худал.
- **Хэт олон удаа гардаг код:** `entry`, `big_frag` Round-уудын 60–75%-д гардаг тул бага мэдээлэл өгнө.
- **Нэг ч удаа гараагүй код:** `unscoped_awp`.
- **`moving_shots`:** бүх зэвсэгт нэг 40%-ийн босго хэрэглэдэг.

**Summary:**

- Босго нь өнөөдрийн датан дээр тооцоолсон, in-sample.
- Swing-гүй Pattern (`time_out`, `kitless`, `team_flash`, …) Focus point болж чаддаггүй (`review_summary.py:436,458`).
- Retake-ийн 4 өөр тодорхойлолт (TM-1).

**Тест:**

- 32 detector-оос ~5-д нь л шууд тест бий.
- `winprob.fit`, defuse-ийн timeline, Swing-ийн нийлбэрийн тест байхгүй.

**Хөгжлийн хэрэгсэл:**

- Тэмдэглэл, bookmark, playlist, Development plan, Scrim-ийн log, дасгалын төлөвлөгөө огт байхгүй.
- Finding-ийг "буруу" гэж тэмдэглэх арга байхгүй.

## Шийдэл

### А. Review-ийн зөв байдал

#### RV-1. Defuse-ийн уналтыг засах (P0, S)

> **Төлөв:** ✅ `85f0c9e` (improvement-01).

- **Түр засвар:** амжилттай болсон defuse-ийг дуусахаас 5 s (kit) эсвэл 10 s (kit-гүй) өмнөөс "явагдаж байгаа" гэж үзэж, Swing-ийг тэр төлөвөөс тооцно.
- **Бүрэн засвар:** DATA-5-ийн `bomb_begindefuse` ирэхэд яг эхэлсэн цагийг хэрэглэнэ.
- `REVIEW_SCHEMA`-г ахиулж, Review-ийг rebuild хийнэ (`npm run review:rebuild`). Timeline-ийн тест нэмнэ.

**Хүлээгдэх үр дүн:** ≥0.95 Swing-тэй defuse 28.8%-иас бодит хэмжээнд (хэдэн хувь) буурна. Clutch, comeback, advantage_lost-ийн худал Finding алга болно.

#### RV-2. Swing-ийн дүрэм v2 (P1, M)

> **Төлөв:** ✅ `4879185` (improvement-01). Round бүр багийн WP-ийн өөрчлөлттэй тэнцэнэ (settle), trade-ийн 20%, teamkill, ≥1 s flash, Swing/раунд-ын 80% муж.

HLTV Rating 3.0-ийн 2025–26 оны өөрчлөлт ба Leetify-ээс (`12-research-sources.md`):

- **Kill:**
  - Kill-ийн Swing хэзээ ч сөрөг болохгүй (өмнөх ба дараах төлөвийг нэгтгэнэ).
  - Bomb-ийг зогсоох боломжгүй болсон үеийн (exit frag) kill 0 Swing авна: <10 s эсвэл kit-тэй <5 s, хэн нэг нь defuse хийгээгүй бол.
- **Round-ын төгсгөлийн үлдэгдэл:**
  - Хуваарилалт (HLTV 2025-10): clutch хийсэн 1×, kill-ийн WPA-тай тоглогчид 2×, defuser 1×, амьд үлдсэн 1×.
  - Plant-ийн дараах үлдэгдэл зөвхөн plant-ийн дараах kill-үүдэд оногдоно.
  - Ингэвэл Round тутмын 0.081 оноогдоогүй үлдэгдэл арилна.
- **Trade:**
  - Trade хийгдсэн үхэлд credit өгнө (Leetify: 20%), trade хийж чадаагүйд торгууль.
  - Trade-ийн цонх хаа сайгүй 5 s (PL-1).
- **Бусад засвар:**
  - Teamkill-ийг нэг удаа тоолно.
  - Flash-ийн хувь ≥1 s блайнд шаардана. `flash_kill`-тэй ижил дүрэм.
- **Тооцооны чанар:**
  - Тоглогчийн Swing/Round-ыг Match Map-аар bootstrap хийсэн интервалтай харуулна.
  - Invariant тест: credit-ийн нийлбэр нь ΔWP-тэй тэнцүү байх.

#### RV-3. Тестийн хамрах хүрээ (P0/P1, M)

> **Төлөв:** 🟡 `39c3bdc` (improvement-01). Swing zero-sum invariant ба team_flash, team_flashed_death, saw_first_lost (`1de4855`); time_out, kitless, defuse_chance, advantage_lost, unfinished, blind_unpunished, late_execute, early_rotate, lurker. Entry, multikill, retake, bomb_lost, unscoped_awp, nade_damage_kill, fire_delay, empty_utility үлдсэн.

- 32 detector бүрт нэг fixture Round.
- Defuse-ийн timeline, Swing-ийн нийлбэрийн invariant.
- Synthetic дата дээр `winprob.fit`.
- Playbook-ийн habit: Setup, stack, site, rush, retake, opening, matchup.

Detector өөрчлөх бүрт тестээр баталгаажуулна (OPS-9).

#### RV-4. Win probability v2 (P1, M; ADR 0007-ийн committed table хэвээр)

> **Төлөв:** ✅ `2c22da7` (improvement-01). HP, utility, сүүлийн kill, defuse race, buy-ийн хос; калибровкийн тайлан; patch-ийн үеэр fit (`review:fit --since`, DATA-7).

- **Онцлог:**
  - HP, armor, амьд kit
  - үлдсэн utility (Loadout 8 Hz)
  - bomb-ийн тээгч эсвэл унасан bomb, эхэлсэн defuse
  - site болон bomb хүртэлх nav зай
  - defuse race: fuse-ийн үлдсэн цаг − хамгийн ойрын CT-ийн хүрэх хугацаа − defuse-ийн хугацаа. Huang нарын судалгаагаар post-plant-ийн log loss-ыг 7–8% бууруулсан.
  - сүүлийн kill-ийг хийсэн тал
  - Map × Side-ийн intercept, global руу pool хийсэн
- **Round-ын эхлэл:** buy-ийн хосыг онцлог болгож оруулна эсвэл freeze end-д тусдаа model хийнэ. Ингэвэл force/full-ийн хазайлтыг засна.
- **Калибровкийн тайлан:** `winprob.fit`-д CV Brier, AUC, ECE ба reliability-г үе, Map, buy-ийн хос, цагийн bucket бүрээр тооцож `winprob.json`-д хадгална.
- **Patch-ийн үе** (DATA-7): Valve-ийн өөрчлөлтүүдээс хойш refit хийнэ. CT-ийн award, C4-ийн өөрчлөлт post-plant-д нөлөөлнө.
- **Model-ийн төрөл:** logistic хэвээр. Swing-д гөлгөр байдал чухал, tree model шаталсан гажуудал үүсгэдэг. GBM-ийг Match-аар бүлэглэсэн CV-д илт сайн гарвал л авна.

#### RV-5. Датаны хүртээмж ба хуучин тодорхойлолтыг засах (P1, S)

> **Төлөв:** ✅ `b80d507` (improvement-01). Loadout-ын хүртээмж, entry/big_frag-ийн босго, lost_weapon_save, зэвсгийн ангиллын moving_shots, unscoped_awp, review:thresholds.

- **Хүртээмжийн тэмдэг:** payload ба хуудсанд `loadout` ба `needs_loadout`-ийг нэмнэ. `review_pool.read` нь тухайн код гарах боломжтой tally-уудыг л уншина.
- **`lost_weapon_save`:** хагас ба Map-ын сүүлийн Round-ыг алгасаж, дараагийн Round-ын мөнгөөр жигнэнэ.
- **Swing-гүй Pattern:** `ZERO_SWING_VALUE`-ийг Summary-д хэрэглэнэ. Ингэвэл Focus point болж чадна.
- **Хэт олон гардаг код:** `entry`, `big_frag`-ийн босгыг өсгөх эсвэл утгыг нь дахин тодорхойлно.
- **`moving_shots`:** зэвсгийн ангилал бүрт өөр босго.
- **`unscoped_awp`:** баталгаажуулна.
- **Summary-ийн босго:** percentile-ийн тооцоог баримтжуулж, version-тай болгоно.

### Б. Review-ийн шинэ боломжууд

#### RV-6. Scrim-ийн log ба хөгжлийн KPI (P1, M; DATA-1-ийн дараа)

> **Төлөв:** ✅ `5580fec` (improvement-01). /scrims log ба тоглогчийн форм дахь Scrim (дундажид орохгүй).

- **My team-ийн Scrim-ийн жагсаалт:** огноо, түнш, Map, оноо, Summary, Focus point.
- **Тоглогч бүрийн KPI-ийн цагийн шугам** (PL-2):
  - official ба Scrim тусдаа шугамаар
  - role peers-ийн хүрээ
  - "Scrim-ийн форм official-д шилждэг үү" гэсэн харьцуулалт
- **ADR 0010:** Scrim-ийн KPI Pool-д, өрсөлдөгчийн habit-д хэзээ ч орохгүй. Зөвхөн манай багийн хөгжлийн дэлгэц дээр харагдана.

#### RV-7. Тэмдэглэл, bookmark, playlist, Finding-ийг маргах (P1, M)

> **Төлөв:** ✅ `db48695` (improvement-01). Note, Dispute, Playlist; ghost горим (VIZ-5); Dispute-ийн давтамж Workspace хуудсанд.

- **Note:**
  - Staff-ын тэмдэглэл. Round, агшин, Finding, тоглогчид хавсарна. Workspace-д хадгалагдана, tag-тай.
  - Тоглогчид хаягласан Note-ийг тэр тоглогч `/me` дээр харна (WS-4).
- **"Энэ Finding буруу":** Staff тэмдэглэж, шалтгаанаа сонгоно (жишээ нь lurker-ийн ганц үхэл, санаатай save).
  - Код бүрийн маргааны давтамжийг `/system`-д харуулна.
  - Давтамж өндөр кодын босгыг дахин үзнэ. Detector-ийг тааруулах цорын ганц бодит feedback.
- **Playlist:** Review, Playbook, хайлтын (VIZ-7) Round-уудыг дараалуулж, тайлбартай болгож тоглогчидтой хуваалцана. Ghost горимоор үзэх боломжтой (VIZ-5).

#### RV-8. Timeout audit ба opening duel-ийн бүртгэл (P1, M; DATA-5-ийн timeout-оос)

> **Төлөв:** ✅ `9791fa4` (improvement-01). Timeout audit, timeout аваагүй 3+ алдагдал, Pool-ын харьцуулалт; opening duel (тоглогчийн хуудсанд ч).

- **Timeout audit:**
  - Аль ч багийн timeout бүр, түүний өмнөх дараалсан Round-ууд, өмнөх ба дараах Win probability.
  - 3+ Round дараалан алдсан ч timeout аваагүй тохиолдлыг тэмдэглэнэ.
  - Судалгаагаар 3+ Round-ын streak-ийн дараа завсарлага нь эсрэг талын дараагийн Round-ын хожлын магадлалыг 11.7–13 нэгжээр өсгөдөг (Gómez Seeber 2024).
- **Opening duel-ийн бүртгэл** (тоглогч бүрээр):
  - оролдлого, хожлын хувь
  - trade хийгдсэн эсвэл хийгдээгүй
  - дараа нь баг 5v4 эсвэл 4v5-ийг хожсон эсэх
  - MOUZ-ийн analyst innersh1ne pro багт хамгийн хэрэгтэй гэж нэрлэсэн тоо (`12-research-sources.md`).

#### RV-9. Development plan (P1, M; CONTEXT.md-ийн нэр томъёо)

> **Төлөв:** ✅ `2128635` (improvement-01). Зорилгын санал Pool-оос тодорхой давсан Mistake-ээр, явц нь 80%-ийн интервалтай.

- **Тоглогч бүрт блок бүрд (4 долоо хоног) 2–3 зорилго.** Зорилго бүр:
  - KPI: PL-ийн хэмжүүрээс, жишээ нь 24 Round тутмын untraded үхэл, opening-ийн хожил, crosshair-ийн алдаа
  - суурь утга, зорилтот утга, хугацаа
  - Weakness эсвэл давтагддаг Focus point-оос автоматаар санал болгоно. Staff сонгоно.
- **Явц:** Match ба Scrim-ээс автоматаар шинэчлэгдэнэ. Интервалтай, PL-3-ийн аргаар тул санамсаргүй хэлбэлзэлд хариу өгөхгүй.
- **Хяналт (check-in):** Staff-ын тэмдэглэл. Performance coach-ийн хувийн тэмдэглэлийг зөвхөн Staff харна.
- **Харагдах байдал:** тоглогч өөрийнхөө төлөвлөгөөг харна (WS-4).
- **`development_goals`:** `player_id`, `workspace_id`, `kpi`, `baseline`, `target`, `start_on`, `due_on`, `status`, `notes`.

#### RV-10. Review-ийн хуралдааны agenda (P1, M)

> **Төлөв:** ✅ `3fde5b4` (improvement-01). /matches/:id/agenda, хэвлэгдэнэ.

Match-ийн Summary ба Focus point-оос 45–60 минутын хуралдааны цагтай agenda (R3-ийн загвар):

1. Онооны урсгал, Win probability-ийн график, Swing-ийн тэргүүлэгчид.
2. Map-ыг шийдсэн 3 Focus point (Round-аар хэмжсэн) клиптэй, олон Map-д давтагдсан Pattern-ууд.
3. Үе шат: pistol ба хувиргалт, хүлээгдэхээс өөр buy, хагас бүр, streak ба timeout audit (RV-8).
4. Манай Setup ба тэдний execute, аль T төлөвлөгөө ажилласан.
5. Тоглогчид: байрлалын норм ба KPI, хамгийн сайн ба муу Swing-тэй үйлдэл. Сайн болсон зүйлийг заавал оруулна (Tiaan).
6. Тэдний тохируулга. Rematch-д зориулж Scouting-ийн файлд нэмнэ.
7. **Үйлдэл:**
   - дасгалд багийн хамгийн ихдээ 3 зүйл
   - тоглогч бүрийн Development plan-д 1–2 зүйл
   - playlist

Хуралдаанд аль хэсгийг үзсэнийг тэмдэглэнэ.

#### RV-11. Дасгалын төлөвлөгөө (P2, M)

> **Төлөв:** ✅ `ad726e5` (improvement-01). `/week`: tier-2 долоо хоногийн загвар, Review хийх тоглолт, Development зорилго, Scrim-ийн Focus point, сүүлийн Briefing-ийн бэлтгэлээр дүүргэнэ.

- **Долоо хоногийн календар** (R3-ийн tier-2 загвар):

| Өдөр | Агуулга |
|---|---|
| Даваа | Review, Development plan-ий хяналт |
| Мягмар–Лхагва | Онол, Scrim, Review, retake/prefire |
| Пүрэв | Өрсөлдөгчийн бэлтгэл, veto түгжих, pistol-ийн дасгал |
| Баасан | Тоглолт |
| Бямба | Scrim, дараагийн өрсөлдөгч |
| Ням | Амралт |

- **Зорилго болгох:** Focus point-уудыг Scrim-ийн зорилго ("энэ долоо хоногт B retake-ийн trade-ийн зай") болон хувь хүний даалгавар болгоно. Prefire, retake, utility-ийн дасгалыг Refrag гэх мэт гадны хэрэгсэлтэй холбоно.
- **Хэмжих:** даалгаврыг тэмдэглэж, дараагийн Scrim-үүдэд KPI сайжирсан эсэхийг шалгана.

#### RV-12. Үүргийг тооцсон ба ахисан түвшний detector (P2, M тус бүр)

> **Төлөв:** 🟡 `a87f872` (improvement-01). Lurker (`4c14eb4`); хожуу execute (20 с-ээс бага үлдэхэд site-д хүрсэн, тоо дутаагүй, хожигдсон) ба эрт rotate (T орохоос 5–20 с-ийн өмнө site-аа орхисон). Smoke-ийн LOS, stack-ийн уншлага, re-peek, dry peek, crossfire үлдсэн.etector үлдсэн.

- **Үүргийг тооцох (PL-4):** lurker-ийн ганц үхлийг default-аар `untraded` Mistake гэж үзэхгүй.
- **Шинэ detector-ууд:**
  - харах шугамыг таслаагүй smoke
  - rotate хэт эрт эсвэл хэт хожуу
  - хожуу execute
  - stack-ийн уншлага
  - алдсаны дараа дахин peek хийх
  - utility-гүй dry peek, харагдалгүй үхэх (Sighting)
  - crossfire

`REVIEW_SCHEMA`-г ахиулна.

## Дараалал

1. RV-1 (P0, S): одоо буруу байгаа тоо, хамгийн түрүүнд.
2. RV-3-ийн эхний хэсэг (defuse, Swing-ийн invariant).
3. RV-5 (S).
4. RV-2 ба RV-4 хамтдаа нэг `REVIEW_SCHEMA` дор, rebuild нэг удаа.
5. DATA-1-ийн дараа RV-6. RV-7.
6. DATA-5-ийн дараа RV-8.
7. RV-9 ба RV-10 (WS-4-тэй хамт).
8. RV-11, RV-12.

## Хүлээгдэх үр дүн

- Defuse, clutch, comeback-ийн Swing бодит болно. Калибровк `winprob.json`-д тайлагнагдана.
- Coach Scrim-ийн дараа Review-ийн agenda-г нэг товшилтоор бэлдэнэ.
- Тоглогч бүр Development plan-даа 2–3 KPI-тай, явц нь Scrim бүрийн дараа шинэчлэгдэнэ.
- Finding-ийн маргааны давтамжаар detector-уудыг бодит feedback-ээр тааруулна.

# CS2 demo-оос юу гаргаж болох вэ

Энэ тэмдэглэлд гурван зүйлийг ялгав: аль хэдийн хийсэн, хийж болох, demo-д огт байдаггүй. Баримтуудыг 2026-10-04-нд cstat-ийн `quantumx-vs-alter-ego-m1-ancient.dem`-ийг demoparser2-оор уншиж, мөн MySQL дахь schema 11-ийн Tick Data bundle-ийг шалгаж баталгаажуулсан. Хүснэгт дэх тоонууд нэг map-аас авсан.

Нэр томъёо нь `CONTEXT.md`-д бий (Tick Data, Setup, Set play, Buy type, Playbook).

## 1. Хийсэн: parse хийж, хадгалж, ашиглаж байгаа

**Event-ийн хүснэгтүүд (MySQL мөрүүд):**

| Дата | Хаана хадгалагддаг | Юунд ашигладаг |
|---|---|---|
| Раунд (эхлэл, freeze end, төгсгөл, хожсон тал, шалтгаан, bomb тавьсан цэг ба tick) | `rounds` | Бүх тайлан, Playbook |
| Kill (буу, headshot, зай, хананы цаанаас, smoke дундуур, сохорсон, байрлал, callout) | `kill_events` | Дуэль, нээлт, trade, heatmap |
| Гэмтэл (HP/armor, hitgroup, callout) | `damage_events` | ADR, тоглогчийн задаргаа |
| Bomb (plant, defuse, detonate, pickup, drop) | `bomb_events` | Цэгийн байрлал, retake |
| Smoke, molotov (хугацаа), flash, HE (дэлбэрэлт), шидсэн ба буусан байрлал, **буусан callout** | `grenade_throws` | Utility тайлан, Set play |
| Тоглогч × раунд: K/D/A, гэмтэл, KAST, trade, нээлт | `player_rounds` | Үүрэг, linchpin, matchup |
| **Эдийн засаг** (freeze end-ийн мөнгө, equip value, armor, helmet, defuser, үндсэн буу) | `player_rounds`, `rounds.ct_buy`/`t_buy` | Buy type, AWP тоглогч |
| **Snapshot** (20 дахь секунд ба bomb тавих үеийн амьд тоглогчийн байрлал) | `round_snapshots` | Setup, stack, цэг дээр хэдэн хүн байсан |
| Тоглогч × map-ын нэгтгэл: буу, utility, байрлал, зам, дуэль | `player_map_*` | Тоглогч, Heatmap, Movement табууд |

**Tick Data-аас ingest-ийн үед таслах зүйлс:**
- Replay: раунд бүрийн бичлэг.
- Алхсан зам (`walks`).
- Callout-ийн шошго ба давхарын хуваарь (`geometry`).

**Tick Data bundle** (`tick_datasets.bundle`, ~10 MB/map) дотор awpy-ийн бүх хүснэгт, мөн flash/HE ба `economy` хүснэгт байна. Demo-г устгасны дараа ч map-ыг үүнээс дахин parse хийж болно (ADR 0002). Эдийн засаггүй хуучин bundle байвал demo-г дахин татна (ADR 0003).

**Tick бүрийн багана (`ticks`):** `health, flash_duration, place, side, team_clan_name, X, Y, Z, yaw, tick, steamid, name, round_num`.

## 2. Хадгалсан ч анализд ашиглаагүй

Эдгээр нь bundle-д аль хэдийн бий. Demo-г дахин татах, parse хийх шаардлагагүй. Зөвхөн ingest-ийн үед таслах код бичихэд хангалттай.

| Хүснэгт | Мөр/map | Одоо | Гаргаж болох анализ |
|---|---|---|---|
| `footsteps` (хөлийн чимээ, радиус) | ~13,600 | Огт ашиглаагүй | Хэн хаана дуу гаргадаг, чимээгүй rotate, мэдээлэл авах арга |
| `shots` (буудлага бүр, зэвсэг) | ~2,800 | Зөвхөн Replay | Оновчлол (буудсан ба онсон), spray эсвэл tap, хананы цаанаас буудах |
| `grenades` (гранатын нислэгийн бүх цэг) | ~2,200,000 | Зөвхөн Replay | Lineup (яг хаанаас шиддэг), шидэлтийн зам |
| `ticks`-ийн `health`, `yaw`, байрлал | ~1,500,000 | Replay, Setup | Хурд (байрлалаас бодно), тулааны үеийн HP, хаашаа харж зогсдог |

## 3. Хийж болох: demo-д байгаа ч parse хийдэггүй

Эдгээрийг нэмэхэд parse-ийг өөрчлөх хэрэгтэй. cstat-ийн 77 map-ын `.dem` дискэн дээр байгаа тул `npm run data:cstat`-аар ~11 минутад дахин уншина. Бусад тоглолтыг HLTV-ээс дахин татна. Нэг раундад нэг удаа хэрэгтэй шинжийг economy шиг тусдаа жижиг хүснэгтээр уншина. Tick бүрээр хэрэгтэйг нь `PLAYER_PROPS`-д нэмнэ, гэхдээ ~1.5 сая мөрд багана нэмэгдэнэ гэдгийг тооцох хэрэгтэй.

### Tick бүрийн тоглогчийн шинж (бүгд уншигдаж байгааг шалгасан)

| demoparser2 нэр | Юу харуулах вэ |
|---|---|
| `spotted`, `approximate_spotted_by` | Хэн хэнийг харж байгаа: эхний харц, мэдээлэл хэрхэн дамждаг |
| `in_bomb_zone` | Цэг дээр байгаа эсэх. A / төв / B хуваарийн тооцоог солих боломжтой |
| `in_buy_zone` | Худалдан авалтын бүсэд байгаа эсэх |
| `active_weapon_name` | Тухайн агшинд гартаа барьж буй зэвсэг |
| `active_weapon_ammo`, `total_ammo_left` | Сум, reload хийж байгаа эсэх |
| `is_scoped`, `zoom_lvl` | AWP/scout-ийн scope-той барьдаг өнцгүүд |
| `ducking`, `is_walking`, `is_airborne` | Чимээгүй алхаж байгаа, сууж байгаа, үсэрч peek хийж байгаа эсэх |
| `pitch` | Босоо чиглэл. `yaw`-тай хамт crosshair-ийн өндрийг харна |
| `is_defusing`, `has_defuser` | Retake ба defuse хийх зан байдал |
| `armor_value`, `has_helmet` | Tick бүрийн хуяг |
| `balance`, `inventory` | Tick бүрийн мөнгө ба авч явсан зүйлс. Одоо зөвхөн freeze end-д |
| `flash_max_alpha` | Flash-ийн хүч |
| `damage_total`, `utility_damage_total`, `enemies_flashed_total`, `cash_earned_this_round`, `kills_this_round` | Серверийн өөрийн тооцсон статистик |
| `is_alive`, `life_state`, `move_type` | Амьд эсэх, хөдөлгөөний горим |
| `ping` | Сүлжээний хоцрогдол |

Controller-ийн `CSPerRoundStats_t`-д раунд бүрийн `m_iEnemiesFlashed`, `m_iUtilityDamage`, `m_iMoneySaved`, `m_iKillReward`, `m_iLiveTime` байна. Нийт 968 талбар бий, тэдгээрийн 619 нь тоглогчтой холбоотой.

### Ашиглагддаггүй event-үүд (нэг map дахь тоо)

| Event | Тоо | Юу харуулах вэ |
|---|---|---|
| `item_pickup` | 1,077 | Хэн юу худалдаж авсан, хэн хэнд буу шидэж өгсөн, унасан буу авсан. Жишээ нь AWP-ийг хэнд өгдөг |
| `grenade_thrown` | 316 | Гранат шидсэн агшин ба шидсэн хүн. Одоо зөвхөн дэлбэрэлт байгаа |
| `player_ping` | 43 | Тоглогчийн дэлгэц дээр тэмдэглэсэн байрлал: багийн доторх харилцааны ул мөр |
| `chat_message` | 106 | Чатын бичвэр |
| `decoy_started` | 2 | Decoy ашиглалт |
| `player_spawn` | 178 | Төрсөн агшин |
| `round_announce_match_point`, `round_announce_last_round_half`, `round_time_warning` | цөөн | Match point, хагасын сүүлийн раунд, цаг дуусах дохио |
| `hltv_chase` | — | GOTV камер хаана зогссон (ач холбогдол багатай) |

### Анализын санаанууд (Playbook-д ач холбогдлын дарааллаар)

1. **Эхний харц ба мэдээлэл** (`spotted_by`): раунд бүрт хэн хэнийг анх хаана харсан, мэдээлэл авсны дараа rotate хийхэд хэр хугацаа зарцуулдаг.
2. **Буу шидэж өгөх хэв маяг** (`item_pickup`): AWP-ийг хэн авдаг, eco-гийн дараа хэнийг зэвсэглэдэг, хэн "буу хадгалагч" вэ.
3. **Чимээ** (`footsteps`, аль хэдийн хадгалсан): чимээгүй rotate, хаана дуу гаргаж fake хийдэг.
4. **CT setup-ийг нарийвчлах** (`in_bomb_zone`, `is_scoped`, `active_weapon_name`): AWP-тэй тоглогч аль өнцгийг scope-той барьдаг, цэг дээр яг хэдэн хүн байгаа.
5. **Оновчлол ба буудлагын хэв маяг** (`shots`, аль хэдийн хадгалсан): тоглогч бүрийн онолт, spray тоглолт.
6. **Lineup** (`grenades`, аль хэдийн хадгалсан): Set play-ийн гранатыг яг хаанаас шиддэг.
7. **Чимээгүй хөдөлгөөн** (`is_walking`, `ducking`): lurker ба зам тойрох хэв маяг.
8. **Utility-ийн бүтээмж** (`utility_damage_total`, `enemies_flashed_total`): тоглогч бүрийн гранатын үр дүн.

## 4. Хийх боломжгүй эсвэл найдваргүй

- **Багийн доторх дуут яриа:** GOTV demo-д бичигддэггүй.
- **Хурдны вектор** (`velocity_X/Y`): demoparser хоосон буцаадаг. Харин байрлалын өөрчлөлтөөс бодож гаргаж болно.
- **`aim_punch_angle`, `is_strafing`:** уншигдаагүй.
- **Тоглогчийн тохиргоо** (crosshair, mouse sensitivity, видео тохиргоо): demo-д байхгүй.
- **Стратегийн нэр, дуудлага:** demo-д байхгүй. Зөвхөн Set play шиг давтамжаас таамаглана.
- **Хуучин demo-д `player_sound` ба `weapon_fire` дутуу байдаг:** awpy footsteps/shots-ыг хоосон бичдэг (awpy#396). Ийм demo-д 2-р хэсгийн анализ хийх боломжгүй.

## 5. Мэдэгдэж байгаа асуудал

- **Хоёр хэсэгт хуваагдсан demo** (`-p1`/`-p2`): тоглолт дундаа дахин эхэлсэн map-ыг HLTV хоёр файлд хуваадаг. `archive.parse_demo_name` дагаварыг танихгүй тул хоёр хэсэг хоёулаа map 1 болж, сүүлд нь parse хийгдсэн нь нөгөөгөө дардаг. Одоо Falcons vs Astralis-ийн Ancient (зөвхөн p1 буюу 3 раунд) болон The Huns vs NAS-ийн Ancient (зөвхөн p2) буруу байна. Засах хоёр арга бий: хоёр хэсгийг нэгтгэх, эсвэл олон раундтайг нь үлдээх. Шийдээгүй.

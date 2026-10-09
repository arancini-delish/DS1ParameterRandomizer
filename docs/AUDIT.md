# Audit & Catalogue Register

Tracks every audit needed before a randomization feature can ship. Status: `todo` / `wip` / `done` / `blocked`.
Reference: https://soulsmodding.wikidot.com/param:main, `ds1paramdefs/Meta`, `ds1paramdefs/Community Row Names`.

Each item needs: enumerate rows, define subtypes, list exclusions/pins, verify in-game where noted.

## A. Data-format / tooling audits

| # | Audit | Status | Owner | Notes / findings |
|---|---|---|---|---|
| 1 | soulstruct DSR param + FMG round-trip fidelity (all 50+ params, padding/bitfields). | done | | 41 params load. soulstruct output is not byte-identical to vanilla (most params differ by a few bytes, likely name-table layout) but row values round-trip for all 41 params. Vanilla has repeated row IDs that soulstruct drops: default_AIStandardInfoBank 8080, 8090; ObjectParam 4000, 4100, 4112, 9499, 9500, 9509; SpEffectVfxParam 1; LockCamParam 200. `GameParams.save` keeps untouched params as original bytes and refuses to re-serialize these four. Game boots with soulstruct-written GameParam and item.msgbnd (2026-10-09). |
| 2 | Defs vs soulstruct-bundled paramdefs vs Meta field names — reconcile naming mismatches (e.g. `HitBulletID` casing, `Diffence` spellings). | done | | All 41 params: soulstruct fields match `ds1paramdefs/Defs` once normalised (tested). soulstruct quirks handled in `GameParams`: bit-width suffixes / stray spaces in internal names (`hasTarget : 1`, `hairColor_B `), and bit-padding fields not flagged `is_pad` (always zero in vanilla, excluded). Meta uses the same plain names. |
| 3 | Meta `Refs` completeness per param — list fields that are references but lack `Refs` (ThrowParam, ObjectParam, NpcThinkParam, SpEffect chain fields, Bullet `autoSearchNPCThinkID`, Goods/Weapon behaviour variation). | wip | | soulstruct annotates 15 references Meta lacks: ReinforceParamWeapon/Protector SpEffects + materialSetId, Magic.replaceMagicId, SpEffectVfx transform armor (added as `EXTRA_REFS`); Magic/Goods/Accessory `behaviorId` (0 in every vanilla row, skipped). Meta ref names needing aliases: BehaviorParam_Pc, QwcChangeParam. Still to check: ThrowParam, ObjectParam and other fields with no annotation in either source. |
| 4 | Enum coverage: `Enum=` on Bullet/SpEffect/NpcParam fields; build missing enums (e.g. `EmittePosType`, `followType`, `stateInfo`) from the soulsmodding wiki (`soulsmodding.wikidot.com/param:main`). | todo | | |
| 5 | TAE event type table for DS1R (which event IDs invoke Atk/Bullet/PC behaviour/SpEffect; arg layout). | todo | | |
| 6 | Lua bytecode constant extraction reliability across all AI luabnds. | todo | | |
| 7 | Free row-ID ranges per param that the engine tolerates (are appended IDs loaded? any ID-range semantics e.g. SpEffect ranges, BehaviorParam ID composition). | todo | | |

## B. Reference-source audits (graph edges)

| # | Audit | Status | Owner | Notes / findings |
|---|---|---|---|---|
| 8 | All param→param refs (Meta + computed). | wip | | 3a: 83,605 edges from Meta, soulstruct extras and behavior variations (`ds1rand/graph/params.py`). Weapon/armor refs encode upgrade level (resolve to `value - value % 100`). 291 vanilla references point at missing rows or variations (pinned in tests; listed by `tools/build_graph.py --unresolved`). 72 ambiguous edges: Bullet.atkId_Bullet where both an AtkParam_Pc and AtkParam_Npc row exist; resolve by who fires the bullet once external sources are in. |
| 9 | BehaviorParam / BehaviorParam_PC ID composition and every consumer (NPC variation, weapon variation, magic, goods, accessories with refCategory=0). | wip | | Behavior row IDs are 100000000 (PC) / 200000000 (NPC) + variationId*1000 + behaviorJudgeId, but 41 PC and 247 NPC rows (small IDs) do not follow it, so edges match the `variationId` field. 23 NpcParam variations have no behaviors: severed parts (tails, heads, Bed of Chaos worm) match after rounding down to 100 (edges marked `inferred`, unconfirmed); the rest are test/passive NPCs. Confirm with TAE in 3c. Magic/Goods/Accessory `behaviorId` unused. |
| 10 | EMEVD: every instruction that takes a Bullet/SpEffect/ItemLot/ObjAct/NpcParam ID, across common + all maps. | wip | | 3b: `ds1rand/graph/emevd.py`, 807 edges from common + m10-m18 (m99 test maps skipped). RunEvent arguments substituted byte-wise (read offsets count from after slot + event ID). Covered: Add/Remove/IfCharacterSpecialEffect, AwardItemLot*, SnugglyItemDrop, ShootProjectile (BehaviorParam or _PC by owner), CreateHazard, SetAIParamID, KillBoss, item checks/removal by item_type. Trap/hazard behaviors (e.g. BehaviorParam 5000, 5070) are only reachable from events: 19 of the 247 NPC behavior rows that break the ID formula. `obj_act_id` args are MSB ObjAct entity IDs, linked via MSB instead. Not yet surveyed: instructions without param-like argument names. |
| 11 | MSB: enemies, objects, traps, collision-linked IDs; per-map enemy instance counts. | wip | | 3b: `ds1rand/graph/msb.py`, 12,054 edges from m10-m18. Characters (incl. dummies) -> NpcParam / NpcThinkParam / CharaInitParam + model node; objects -> ObjectParam by model number (no row is normal); treasures -> ItemLotParam; ObjAct events -> ObjActParam. 136 unresolved, mostly treasure lots with no ItemLotParam row (e.g. 1000060), assumed vanilla leftovers; to verify in game. Per-map enemy instance counts are available from the msb edges. |
| 12 | TAE: per character + c0000 behaviour invokes; spray/repeated-invoke patterns. | todo | | |
| 13 | AI Lua: SpEffect/behaviour IDs referenced by AI (e.g. buff checks via `HasSpecialEffectId`). | todo | | |
| 14 | EXE-hardcoded IDs (curated): status-effect SpEffects, humanity/hollow, covenant, item-use, stateInfo semantics, speffect ranges with special engine treatment. | todo | | |
| 15 | Hit material (HitMtrlParam) SpEffects, ObjActParam, ThrowParam, KnockBackParam, LockCamParam usage. | todo | | |

## C. Semantic catalogue audits (subtypes)

| # | Audit | Status | Owner | Notes / findings |
|---|---|---|---|---|
| 16 | **SpEffect** — buckets: ring passive, weapon/armor passive, player buff, weapon buff (enchant), status buildup (poison/toxic/bleed/curse/frost-like), damage-over-time, heal/regen, enemy buff/debuff, AI state flags, area/env effects, triggers (`replaceSpEffectId`, cycle, conditionHp), stateInfo-driven specials, visual-only (SpEffectVfx). Field groups: which fields are "effect payload" vs "plumbing" (duration, target flags, effectTarget*, magParamChange/miracleParamChange). | todo | | |
| 17 | **Bullet** — linear, lobbed (gravity), homing (followType/autoSearch), orbit/delayed (NpcThink), ground-trace chain, AOE ground spawn (EmittePosType), point-blank, spray, lingering/cloud, explode-on-hit spawner, multi-shot (numShoot/spread), shooter-buff carrier, trap bullets, invisible/utility bullets. Field groups: visuals (sfx IDs, model), motion, lifetime, hit behaviour, chaining. | todo | | |
| 18 | **Bullet visuals (FFX residency)** — which `sfxId_*` are in common FFX vs character/map-specific FFXBNDs; player-safe pool vs enemy-only pool; spell vs non-spell visual pools. Same for sounds if referenced. | todo | | |
| 19 | **AtkParam_Pc / AtkParam_Npc** — damage types, status payload, knockback, guard break, which are spell/projectile/melee/trap; scaling relationships with Magic/weapons. | todo | | |
| 20 | **Magic** — school, cast animation (`refType`), subtype, slots/uses/stat req distribution, pinned utilities (Homeward, Cast Light, Repair, Darkmoon/covenant spells, Aural Decoy, Hidden Body, Fall Control?), enemy-only Magic rows if any. | todo | | |
| 21 | **EquipParamGoods** — throwables (firebomb, knives, dung pie, alluring skull, prism stone…), consumables using bullets/SpEffects (buffs, resins); key items to pin. | todo | | |
| 22 | **EquipParamWeapon ammo & catalysts** — arrows/bolts (ammo types), bow/crossbow association, weapons with on-hit SpEffects and passive SpEffects, catalyst/talisman spell buff fields. | todo | | |
| 23 | **EquipParamAccessory** — ring list, refCategory per ring, key/quest rings, rings with hardcoded engine behaviour (pins), ring msg IDs. | todo | | |
| 24 | **NpcParam** — enemy categories (regular, elite, boss, NPC/invader, summon, mimic, passive), per-enemy fields safe to modify (speeds, turn rate, poise, resistances, stamina), shared NpcParam rows across maps. | todo | | |
| 25 | **NpcThinkParam** — sight/hearing radius & angles, battle-goal IDs, nearby-ally call, return distances; which rows are shared and which drive bosses/scripted fights. | todo | | |
| 26 | **MoveParam** — walk/run/turn speeds per movement set; who shares them. | todo | | |
| 27 | **Enemy & environment spells/projectiles** — which bullets each enemy can fire (via TAE+Behavior), trap bullets per map, boss-specific mechanics to pin (e.g. scripted bullets in boss arenas). | todo | | |
| 28 | **Cost/power baselines** — vanilla power curve per spell subtype & school (damage per cast, casts, slots, stat req, cast time) and per projectile class (damage vs price/weight) — used to fit cost models. | todo | | |
| 29 | **Message IDs** — FMG entries for every randomizable item (names, summaries, descriptions), text length limits. | todo | | |

## D. Validation audits (in-game)

| # | Audit | Status | Owner | Notes / findings |
|---|---|---|---|---|
| 30 | Sample per subtype: swapping two rows within a subtype produces working behaviour (spot-check list kept in AUDIT.md). | todo | | |
| 31 | Appended (cloned) row IDs load and function for Bullet/Atk/SpEffect/Magic. | wip | | Appended Bullet 900000 (unused copy) loads without breaking boot. Still to check: appended rows actually used in-game, and Atk/SpEffect/Magic. |
| 32 | Online/save safety notes (offline-only recommendation). | todo | | |

## In-game spot-check log

| Date | Feature / subtype | Rows tested | Result | Notes |
|---|---|---|---|---|
| 2026-10-09 | Phase 1 I/O boot test (`tools/make_boot_test.py`) | All EquipParamWeapon weights, appended Bullet 900000, Darksign + Estus names/summary | Pass | Game boots, all edits visible. |

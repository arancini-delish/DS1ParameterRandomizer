# DS1R Parameter Randomizer — Roadmap

## Context
The current prototype (WitchyBND XML round-trip, `param_categorizer.py` heuristics, a working `ring_randomizer.py`, a single-window PySide6 UI in `main.py`) mutates whatever param files are on disk. That makes runs non-idempotent (re-running randomizes an already-randomized game) and the shallow Magic→Bullet→Atk→SpEffect walk misses most of the real reference web (shared SpEffects/Bullets across spells, ammo, traps, enemies, events). Goal: rebuild on soulstruct, drive everything from a **shipped vanilla baseline + a static, fully audited reference graph**, classify every row into swappable subtypes, compute per-feature minimum row budgets, then randomize per feature (rings, spells, projectiles, enemy behaviour) through a tabbed UI with distribution profiles and shareable presets.

Decisions made: ship full vanilla rows in-repo; parse **everything** that can reference params (params, EMEVD, MSB, TAE, AI Lua, curated EXE-hardcoded IDs); first execution step writes `docs/ROADMAP.md` + `docs/AUDIT.md` from this plan.

## Existing assets to reuse
- `ds1paramdefs/Defs/*.xml` — field types/defaults (soulstruct also bundles DSR paramdefs; Defs is the cross-check).
- `ds1paramdefs/Meta/*.xml` — `AltName`, `Wiki`, `Enum`, and **`Refs`** (incl. conditional refs like `Bullet(refCategory=1)`) → seed edges of the graph. Gaps found: no Refs for ThrowParam, ObjectParam, NpcThinkParam targets, BehaviorParam ID composition, SpEffect `replaceSpEffectId`/cycle fields need checking.
- `ds1paramdefs/Community Row Names/*.json` — row names; `Shared Param Enums.json`, `Commutative Params.json`.
- `ring_randomizer.py` — effect tier tables, `RING_EFFECT_TO_SUMMARY_TEXT_MAPPING_AND_DISPLAY_FUNC`, `STATE_INFO_ID_TO_SUMMARY_TEXT_MAPPING`, `RING_IDS_TO_IGNORE`, tier/template distribution logic → port almost verbatim into the rings feature.
- `magic_randomizer.py` — `UsageCount`, `SlotUsage`, `StatRequirement`, `MAGIC_TIER_TO_SCORE` cost model → basis of the spell cost model.
- `param_categorizer.py` / `constants.py` — `SpellTypes` and classifier heuristics (spray anim IDs, ground-trace chain detection, lingering/point-blank/lobbed thresholds) → become initial classifier rules, validated by the audit.
- `default_vals/RingSpEffectParam.csv`, `default_linear_magic_*.csv` — blank templates.
- `main.py` preset-combo + distribution-validation pattern → generalize into a reusable `DistributionEditor` widget.
- Retired (removed): `witchy_util.py`, `WitchyBnd/`, `params/` and `msgs/` extraction caches, `id_to_names/` (superseded by Community Row Names). The prototype modules listed above now live in `legacy/` until ported.

## Target layout
```
ds1rand/
  io/            soulstruct wrappers: gameparam.py, msg.py, emevd.py, msb.py, tae.py (new reader), lua.py (constant extractor)
  defs/          paramdef+meta loader -> FieldSpec(type, default, enum, refs, semantic tags)
  baseline/      vanilla snapshot load, hashing, disk-vs-baseline diff + discrepancy report
  graph/         RefGraph (nodes = (param,row) + external sources), edge extractors per source, usage queries
  catalogue/     subtype classifiers, curated YAML (pins, hardcoded IDs, overrides), budget computation
  features/      rings/, spells/, projectiles/, enemies/  (each: model, cost model, randomizer, msg writer)
  alloc/         row allocator: min budgets, decoupling via row cloning into free IDs, surplus pool for chains
  presets/       schema (pydantic/dataclass), versioning, share-string codec
  ui/            PySide6 app: global preset bar, per-feature tabs, DistributionEditor, log/report pane
data/
  baseline/      vanilla rows (compressed JSON per param) + msg baseline + manifest with source hashes
  catalogue/     generated graph.json, classifications.json, budgets.json (+ curated *.yaml)
tools/           build_baseline.py, build_graph.py, audit_report.py (HTML/MD coverage report)
tests/
```

## Phases

### Phase 0 — Repo docs & housekeeping (done)
- `docs/ROADMAP.md` and `docs/AUDIT.md` written.
- soulstruct submodule replaced by a pinned dependency (`soulstruct==2.6.0`, Python >=3.13) in `pyproject.toml`.
- Package skeleton `ds1rand/` created per the target layout; prototype moved to `legacy/`; game files and extraction caches git-ignored.

### Phase 1 — soulstruct I/O port (done)
- `io/install.py`: `GameInstall` paths; `DS1R_GAME_DIR` overrides the default Steam location.
- `io/gameparam.py`: `GameParams` over soulstruct's DSR `GameParamBND`. Fields by paramdef internal name (`row["atkId_Bullet"]`, `row_values()`), `add_row(copy_from=)`, `next_free_id()`. `save()` re-serializes only params that changed and writes untouched params as their original bytes; it refuses to re-serialize a param with vanilla duplicate row IDs (`duplicate_ids`) because soulstruct drops them.
- `io/msg.py`: `ItemText` over `item.msgbnd.dcx`. Reads prefer the DSR patch FMG; writes update base and patch. `menu.msgbnd.dcx` not needed yet.
- Tests (`tests/`, skip without an install): unchanged save is byte-identical per param, edits only re-serialize the edited param, row values survive soulstruct round trip, added rows persist, text writes reach base + patch.
- Boot-tested in game with `tools/make_boot_test.py` (re-serialized params, appended row, edited base + patch text).

### Phase 2 — Vanilla baseline (done)
- `data/baseline/`: `manifest.json` (source SHA-256 of GameParam, item.msgbnd and DarkSoulsRemastered.exe, soulstruct version, per-param row counts and vanilla duplicate row IDs), `params/<Name>.json` (every row, one per line, fields by `ds1paramdefs/Defs` name, padding excluded), `text/item.json` (every item FMG string, base and patch). Full rows are committed, so per-row hashes were dropped.
- `ds1rand/defs/paramdef.py`: minimal loader for `ds1paramdefs/Defs` (field types, bit widths, defaults); a test asserts the baseline's fields equal the Defs fields for every param.
- `ds1rand/baseline/store.py`: `Baseline` load/write and capture from loaded game files.
- `ds1rand/baseline/compare.py`: `diff_params` / `diff_text` (changed, added, removed rows/strings), `restore_params` / `restore_text`, and file states VANILLA / OURS / MODIFIED. OURS = a `<file>.ds1rand.json` sidecar marker holding the SHA-256 of the file ds1rand wrote. Choosing abort / restore / keep for MODIFIED files is left to the randomize pipeline and UI.
- `tools/build_baseline.py` (inputs must be vanilla) and `tools/check_install.py [--rows]`.
- Output always = baseline + our edits: load disk, report, restore to baseline, then apply edits. This is the idempotence fix.
- Provenance: built from a Steam-verified DSR install (2026-10-09). The verified GameParam is byte-identical to the maintainer's earlier `.bak`; values also spot-checked against known vanilla (starting-class weapons, weapon AR/weight, spell casts).

### Phase 3 — Static reference graph (the core) (done; curation of unreferenced rows continues in AUDIT 14)
Edge extractors, each tagged with source + semantic role (e.g. `bullet.hitBullet`, `atk.targetSpEffect`, `emevd.ShootBullet`, `tae.InvokeBullet`):
1. **Param→param** from Meta `Refs` (including conditional refs evaluated per row).
2. **Computed IDs** not in Meta: BehaviorParam (`2xx` NPC = `behaviorVariationId*1000 + judgeId`), BehaviorParam_PC (weapon `behaviorVariationId`), arrow/bolt ammo → bullet via behaviour variation, SpEffect `replaceSpEffectId`/cycle/next fields, Goods throwables, ObjActParam, ThrowParam, NpcThinkParam, CharaInit.
3. **EMEVD** (soulstruct): ShootBullet / ShootProjectile, SetSpEffect/CancelSpEffect, ApplySpEffect to entities, item award (ItemLot), ObjAct triggers.
4. **MSB** (soulstruct): enemy parts → NpcParam/NpcThinkParam/CharaInit, objects, traps (bullet-firing objects, ObjAct), map-specific ID ranges.
5. **TAE** (new reader in `io/tae.py`; DS1 TAE format, only parse event type + args): InvokeAttackBehavior / InvokeBulletBehavior / InvokePCBehavior / ApplySpEffect-style events, per character (`chr/cXXXX.anibnd.dcx`) and player (`c0000`). Links animations → BehaviorParam judge IDs → Atk/Bullet/SpEffect. Also identifies "spray" style spells (repeated bullet invokes) without hardcoded anim IDs.
6. **AI Lua** (`script/*.luabnd.dcx`, compiled Lua 5.0): `io/lua.py` constant extractor from bytecode (no full decompile) for numeric literals → candidate SpEffect/anim/behaviour IDs; optional DSLuaDecompiler output for manual audit. Low-confidence edges flagged as such.
7. **Curated** `catalogue/hardcoded.yaml`: EXE-hardcoded SpEffect/Bullet/Atk IDs (humanity, hollowing, covenant, poison/toxic/bleed/curse buildup effects, hit-material SpEffects, stateInfo semantics, homeward/return spells, ring passives such as Ring of Fog/Rusted Iron).
- Delivered in stages, one PR each: 3a param→param (Meta, soulstruct extras, behavior variations), 3b EMEVD + MSB, 3c TAE, 3d AI Lua, 3e curated hardcoded IDs.
- 3a (done): `ds1rand/defs/meta.py` (Meta loader), `ds1rand/graph/model.py` (`RefGraph`: `refs_of`, `users_of`, `reach`, `reached_by`; edges carry field, source and confidence `certain`/`ambiguous`/`inferred`; unresolved references kept for the audit), `ds1rand/graph/params.py`, `tools/build_graph.py`.
- Param edges are rebuilt from the baseline on demand (0.3 s), so they are not committed. Edges from game files (EMEVD, MSB, TAE, Lua) need the install to extract, so 3b onwards commits those under `data/catalogue/`. `features_of` / `is_shared` move to Phase 4, which defines features.
- 3b (done): `ds1rand/graph/emevd.py`, `ds1rand/graph/msb.py`, `ds1rand/graph/build.py` (`build_graph` = param edges + committed `data/catalogue/{emevd,msb}.json`; `extract_external` re-extracts and records every source file's SHA-256 in `data/catalogue/sources.json`). Provenance: the maintainer's install had item/enemy randomizers applied, so map files were read from their `.bak` copies (all from the same 2026-06-20 backup pass as the GameParam `.bak` proven identical to Steam-verified vanilla) and `common.emevd.dcx`, untouched since install. `tools/build_graph.py --extract --prefer-bak` reproduces it.
- 3c (done): `ds1rand/io/tae.py` (DSR TAE 0x1000B reader; soulstruct only reads 0x1000C) and `ds1rand/graph/tae.py` (animation -> behavior/SpEffect edges, model -> animation edges; event parameter meanings measured against vanilla data, see AUDIT 5). Committed as `data/catalogue/tae.json`. Removed 3a's inferred severed-part variation fallback: TAE shows those models invoke no behaviors.
- 3d (done): `ds1rand/io/lua.py` (Lua 5.0 chunk reader + literal call-argument scan) and `ds1rand/graph/lua.py` (AI goal scripts -> SpEffect / ItemLot, NpcThinkParam -> goal scripts). Committed as `data/catalogue/lua.json`. Since 3d all external sources are extracted from the Steam-verified live install (`sources.json` records live file names); the earlier `.bak`-based extraction is byte-identical.
- 3e (done): `data/catalogue/hardcoded.toml` + `ds1rand/graph/hardcoded.py` (curated engine references, seeded with soulstruct's engine-applied SpEffect ranges); engine rules in `ds1rand/graph/params.py` (upgrade paths, inferred item lot chains); `build.orphans()` / `tools/build_graph.py --orphans` list rows nothing references. Phase 4 must treat unreferenced rows as pinned, not free, until classified.

### Phase 4 — Catalogue & classification (done)
- Delivered in stages: 4a feature usage and sharing, 4b subtype classifiers + coverage, 4c minimum budgets and free pool.
- 4a (done): `ds1rand/catalogue/usage.py` tags every param row with the features that use it (ring, player_spell, player_weapon, player_goods, player_armor, player_animation, enemy, environment, engine) by walking usage edges from each feature's roots; grants (item lots, shops, materials, upgrade paths, EMEVD inventory checks) are not usage. `tools/catalogue_report.py [--shared PARAM]`. Findings: 80 Bullets are shared, 67 of them between player spells and NPC caster copies (e.g. Soul Arrow Bullet 3000 with Magic 13000); human NPCs attack through their weapons' player behaviors, so 703 AtkParam_Pc / 1153 BehaviorParam_PC rows are shared with `enemy`.
- 4b part 1 (done): `ds1rand/catalogue/subtypes.py`. Bullet subtype = motion (orbit, attached, ground, stationary, homing, lobbed, linear) + qualifiers (lingering, instant, multi, stream), with payload flags (damage, target_effect, shooter_effect, spawns_child) and `bullet_chain` for hit-bullet chains. Magic subtype = school / cast animation category (`refType`, which decides delivery: spray, mist, weapon buff, ...), named from the vanilla spells using each; the root bullet's class refines it. All 514 used Bullets and 104 used Magic rows are classified.
- 4b part 2 (done): `ds1rand/catalogue/effects.py`. SpEffect subtype = context (how it is reached) / kind (which field groups deviate from vanilla neutral values), with the engine-implemented `stateInfo` kept separately so swaps preserve it; AtkParam subtype = delivery / element (+status). `tools/catalogue_report.py` prints all subtype distributions.
- 4c (done): `ds1rand/catalogue/budget.py`. `decoupling` partitions each shared row's features into groups that must share a row: only param fields holding row IDs can be repointed to a copy; references from game files, the engine and computed IDs (behavior variation + judge) are fixed, and features sharing a referencing row's copy share downstream. Full decoupling needs 72 Bullet, 113 SpEffect, 45 + 8 AtkParam, 79 weapon, 12 ring, 11 goods copies; rows that cannot be separated: 1153 BehaviorParam_PC and 665 AtkParam_Pc (player weapons used by NPC phantoms through shared behavior variations), 8 ammo Bullets, 43 SpEffects. `unit_footprint` gives one root's chain (Soul Arrow: 1 Magic, 1 Bullet, 1 AtkParam_Pc). New rows: `IdAllocator` over `NEW_ID_BLOCKS` respecting reference field widths; `RowBudget` caps new rows per param (None = unbounded, 0 = reuse only: decoupling then falls short and downstream complexity drops). `tools/catalogue_report.py --cap N`. Possible extension: whole-variation copies (new variationId) to separate weapon behaviors used by both player and NPCs.
- Every node in scope gets `feature` (ring, player_spell, enemy_spell, env_spell, player_projectile, enemy_projectile, env_projectile, enemy_behaviour, weapon, other/pinned) and `subtype` (see register). Rows used by multiple features are recorded with all usages.
- Classifiers are rule-based (port of current heuristics) + curated overrides YAML; any row unclassified or matching >1 subtype is surfaced in the audit report — **no randomization feature ships until its coverage = 100% of reachable rows** (or explicitly pinned).
- **Minimum budgets**: per feature, the number of distinct rows of each param needed so that every user of that feature gets its own decoupled chain (e.g. spell X needs 1 Magic + 3 Bullet + 1 Atk + 2 SpEffect). Computed from graph reach, stored in `budgets.json`.
- **Free pool**: rows unused by anything (orphans), plus free ID ranges appendable to each param (soulstruct allows adding rows) → surplus count per param.

### Phase 5 — Allocation layer (done)
- `ds1rand/alloc/store.py`: `RowStore`, the working copy randomizers edit: starts as the vanilla baseline, records only changed and new rows (with the vanilla row each new row descends from).
- `ds1rand/alloc/allocator.py`: `allocate(graph, baseline, store, enabled, budget, params=...)` copies shared rows for the features being randomized and repoints their references:
  - features not enabled are merged and keep the original rows (no copies);
  - the original ID stays with the group holding fixed references: game files, engine, computed IDs, ambiguous fields (one value, two possible targets), and a feature's own roots (items the player owns by ID: weapons, armor, rings, goods, spells);
  - caps (`RowBudget`) merge the lowest-priority copy groups back until every param fits (priority = order of `enabled`); rows whose referencing field is too narrow for any new ID block stay coupled;
  - copies get IDs that fit every referencing field (spell roots <= 32767), multiples of 100 for weapons/armor; repointing keeps upgrade-level offsets;
  - `params` limits copying to what the randomizers edit (enemy behaviour: 1 copy; player spells: 67 Bullet, 30 AtkParam_Pc, 18 SpEffect copies, 33 Magic repointed);
  - `Allocation.owned(feature)` / `coupled(feature)` / `row_for(row, feature)` tell randomizers what they may edit alone.
- `ds1rand/alloc/write.py`: `build_gameparam` loads the disk GameParam, refuses foreign modifications, restores vanilla, applies the store; `write_gameparam` saves and writes the ds1rand marker. Re-running on our own output gives identical rows.
- Surplus rows for compounding chains: Phase 6 randomizers take them from `IdAllocator` + `RowStore.add` within `RowBudget.plan(...)['surplus']`.
- Finding: the curated engine entry for NG+ SpEffects (7400-7599) is referenced by NpcParam.GameClearSpEffectID, so the engine claim may be redundant (AUDIT 14).

### Running on top of other mods (done)
- Order: item → enemy → fog gate → ds1rand. Findings and design in `docs/MOD_COMPAT.md`; `tools/diff_install.py` measures what an install changes.
- The vanilla baseline is now the reference, not a requirement: a run's base is the files as the other mods left them (saved as `<file>.ds1rand-base` on our first write; re-runs rebuild from it, or strip our recorded patches if another mod ran after us). Classification, usage and allocation run on the base and the graph built from the installed files.
- Output is written as field patches with `ParamBinary` (byte-level, keeps rows with repeated IDs, e.g. the fog gate's duplicate scaling SpEffects); the marker (format 2) records every patch. `ds1rand/session.py` is the entry point randomizers use.

### Phase 6 — Feature randomizers
- 6.1 Rings (done): `ds1rand/features/rings.py`, ported from the prototype: tier distribution (Easy/Standard/Hard/Misery presets) -> effect-level template -> effects drawn per level; each ring's SpEffect reset to the plain-ring template (computed from the base; equals the prototype's CSV) plus its effects; summary text lists the effects. Pins: the prototype's five rings. Rings keep their IDs; ring SpEffects are copied when shared, and with `isolate_npcs` (default) NPC phantoms get their own accessory/SpEffect copies and keep vanilla rings. Allocation is limited to the ring footprint (`Session.footprint`, `allocate(rows=...)`). `tools/randomize.py --rings [PRESET] [--seed N] [--in-place]` (default output: out/randomized/).
- 6.2 Spells (done, v1): `ds1rand/features/spells.py`. Spells keep school and cast animation category (sorcery projectiles may move between normal and charged casts); the payload comes from a donor of the same category, delivery and owner group (player / NPC caster copies), copied into new rows (root in the narrow ID block); visuals from another spell (same school by default) and an added on-hit status effect are optional chances; a power tier plus costs drawn from the category's vanilla values set a power factor (prototype usage curve, 2 slots, stat requirement, charged cast) that scales damage and buff magnitudes (clamped 0.4-2.5). Utility spells pinned (Homeward etc.). NPC caster spells randomized without costs. Each feature now has its own random stream (`{seed}-rings`, `{seed}-spells`). UI Spells tab and preset section. v2: visuals from a curated pool of every spell bullet (any school by default; sometimes an impact visual too); speed / homing changes for moving root bullets (x0.6-1.6 speed, homing x0.5-2 or added to straight shots, costing power); chained effects: the end of the chain may spawn another spell's chain (up to 6 bullets, no orbiting/attached/stream bullets) with the parent at 80% power and the child at 50% of the spell's power. Not yet: environmental "spells" (trap bullets: done in 6.3), new spell names/long descriptions.
- 6.3 Projectiles (done, pending in-game check): `ds1rand/features/projectiles.py`, sharing the chain engine with spells (`ds1rand/features/chains.py`: new-row chain copies, visuals, speed/homing, chained effects, added status). Slots: arrow / great arrow / bolt behaviors (BehaviorParam_PC; behaviors firing the same bullet share one result; NPC archers use the same behaviors), the attack throwables (knives, firebombs, dung pie), enemy BehaviorParam bullets (grouped by TAE character model) and trap behaviors (environment-only usage). Donors of the same kind / character model (`cross_enemy` lifts the model restriction); visual and chained-effect pools are non-spell by default (`spell_effects` adds the spell pools). Power: player tiers scale throwable damage or ammo attack corrections (the bow's rating), and throwables carry fewer per tier (99/99/40/20); enemy and trap donors are rescaled to the replaced projectile's vanilla damage x tier, limits applied around that. Three distributions (player; enemy and environment invert the difficulty). Preset section, UI Projectiles tab, `--no-projectiles`. Not yet: price/weight costing for ammo and goods, names for changed throwables.
  - Update (after 6.4): enemy and trap projectiles draw donors, visuals and chained effects from every projectile and spell whose particle effects are loaded where they appear (effect residency table, AUDIT 18), not only their own model's; options `cross_enemy` (on) and `enemy_spells` (on).
- 6.4 Enemy behaviour (done, pending in-game check): `ds1rand/features/enemies.py`.
  - Each placed enemy type (NpcParam row) draws a tier (Sluggish / Normal / Alert / Relentless; presets Easy to Misery) and one factor per enabled group from the tier's range.
  - Groups: turn speed, detection (sight / hearing / smell distances and angles), pursuit (leash distances, target memory), movement (walk / run animation swaps on MoveParam copies), poise, stamina.
  - Values stay within the vanilla extremes per field; sentinels (9999 = unlimited / instant) are kept.
  - Think rows follow the enemy type placed with them most.
  - Categories: regular (on), bosses and humans (off by default). Bosses come from the event scripts' boss health bars (new EMEVD entity edges).
  - Preset section, UI Enemy Behaviour tab, `--no-enemies`.
1. **Rings** — port `ring_randomizer.py` onto the new model; exclusion list (key/quest rings: Covenant of Artorias, Darkmoon Séance, Orange Charred, plus user-configurable keep list); effect score tiers + distribution; rewrite Accessory summary/description FMGs (replace or append mode).
2. **Spells** — player/enemy/environment; preserve subtype + school (sorcery/pyro/miracle, `ezStateBehaviorType`) + cast animation; randomize bullet visuals (sfx IDs limited to FFX resident for the caster — see audit), chaining, SpEffects, damage; cost model from `magic_randomizer.py` (power score ↔ casts, slots, stat req, cast speed/anim). Pinned utility: Homeward, Darkmoon/Sunlight Blade? (audit), Cast Light, Repair, Aural Decoy etc. per catalogue. Update Magic names/descriptions.
3. **Projectiles** — non-spell bullets (arrows/bolts, throwables, enemy ranged, traps); same chaining engine, non-spell sfx pool; player cost model (ammo/goods price, weight, damage vs. bow/crossbow association); separate distributions for player/enemy/environment.
4. **Enemy behaviour** — NpcParam / NpcThinkParam / MoveParam fields: turn speed, detection (sight/hearing radius & angle), move speed, aggression/battle-goal related fields, poise/stamina; each field toggleable with min/max/distribution; per-enemy-category exclusions (bosses, NPCs, scripted).
5. **Weapons** (done, pending in-game check): `ds1rand/features/weapons.py`.
   - Each weapon row (infusion rows included) draws a rarity tier that sets a target value relative to vanilla. Of 48 random candidates, the closest one wins.
   - Value combines attack rating at reference stats (scaling only counts for damage it scales), weight, requirements, guard and added effects.
   - Commons come out around 0.85x vanilla, Legendaries around 1.3x.
   - Optional moveset trades within type, on-hit and while-held effects (shared passives module) and elemental conversion.
   - Rarity, moveset and effects are written into the long description.
   - Shields value guard most.
   - Starting gear is capped to class stats, and NPCs keep vanilla copies.
   - Preset section, UI Weapons tab, `--no-weapons`.
   - Amendment: split damage counts for less in the value (a 50/50 split of 300 is worth about 200 of one type), and Rare / Legendary weapons get x1.05 / x1.1 base damage.
   - v2: moveset trades across all melee types (default 50%, per family). A weapon taking another moveset starts from the stats of a weapon using it (same infusion path where it exists), with base damage x sqrt(reach of the moveset's animation set / reach of its own) (a dagger moving like an ultra greatsword hits about 1.7x harder, the reverse about 0.6x). Then its tier applies as usual.
   - The original scope follows.
5. **Weapons** (tab) — rarity tiers with a cost model, like rings and spells:
   - Rarer weapons may get better flat damage, scaling, friendlier stat requirements, guard values, weight and triggered SpEffects.
   - Common weapons trade several of these off, so they are less desirable.
   - Each infusion row (Crystal, Divine, ...) is randomized as a weapon of its own, with its own stats and SpEffects.
   - Scaling is priced by the damage it can scale: a high letter only goes to a stat that scales a damage type the weapon actually deals (strength/dexterity -> physical, intelligence/faith -> magic above a negligible amount). This keeps the letters shown meaningful and usable.
   - Weapons may trade movesets with other weapons of their type (stamina and motion values stay with the moveset).
   - Triggered SpEffects come from any fitting SpEffect, not only existing weapon ones, with text written into the description as with rings.
   - Shields get their own defense randomization (guard cut rates, stability, status guard).
   - Pins: fists (900000), catalysts and talismans, ammo.
   - Constraint: every starting class can use its starting weapons and shield with its starting stats.
   - See AUDIT 33-38.
6. **Armor** (done, pending in-game check): `ds1rand/features/armor.py`.
   - Rarity per set (or per piece). v2: pieces are generated from scratch, not scaled. Each stat is drawn as a percentile of its slot's vanilla values (spiky draws favour extremes, e.g. a light hat with huge poise and no slash defense). The rating (weighted mean percentile + effect) is placed by tier within the slot's vanilla rating distribution, so overall ratings match vanilla's.
   - A ring-style passive goes into a free slot (vanilla effects are kept). Rarity and effect head the long description.
   - NPCs keep vanilla copies. Preset section, UI Armor tab, `--no-armor`.
   - The original scope follows.
6. **Armor** (tab) — rarity tiers:
   - Rarer armor may get better weight, poise, defenses / resistances and triggered SpEffects.
   - SpEffects come from any fitting SpEffect, with ring-style text in the description.
   - See AUDIT 39-40.
7. **Body / face data** (done, pending in-game check): `ds1rand/features/appearance.py`.
   - Four strengths, 0-400% (0 = vanilla, 100% = every value drawn anew within the field's vanilla extremes, above 100% the fresh value's distance from the neutral point is multiplied, e.g. 300% = 3x; clipped to the field type: body scales s8, face values u8): NPC faces, character creation face templates, the nine physiques per sex, NPC body proportions. Hair style switches choice with probability = strength.
   - NPCs sharing a template's face get a copy. UI "Body & Face" tab with sliders, preset section, `--no-appearance`.
   - The original scope follows.
7. **Body / face data** (tab):
   - Randomizes NPC face data and the player's character creation templates, with one strength slider for each. Existing saves keep their face and physique.
   - NPC body proportions get their own slider; player body too, if character creation reads it from params (AUDIT 42).
   - At full strength every value is drawn within sensible extremes (the vanilla range per field).
   - See AUDIT 41-42.

### Phase 7 — UI & presets (prototype done; grows with each Phase 6 feature)
- `ds1rand/presets/schema.py`: versioned `Preset` (seed + one section per feature: rings, spells, projectiles), JSON files and share strings (`DS1R1-` + base64url(zlib(JSON))); unknown keys ignored, missing keys default, newer versions refused. Built-in global presets Easy / Standard / Hard / Misery.
- `ds1rand/run.py`: `run(preset, install, out_dir)` / `validate(install)`, shared by `tools/randomize.py` (now `--preset`, `--preset-file`, `--share`, `--print-share`) and the UI.
- `ds1rand/ui` (`python -m ds1rand.ui`): global preset bar with import/export of files and share strings, game folder, seed, output (out folder or in place); tabs Rings (enable, `DistributionEditor` for tier weights with presets and shares, NPC isolation, summaries, results table), Spells, Projectiles, Enemy Behaviour (disabled until built), Install (bases, other mods' changes, conflicts); Validate / Randomize run in a worker thread; log pane; last game folder and preset remembered (QSettings).
- Still to come: per-feature tabs as Phase 6 features land, an Audit tab (graph/coverage browser), a spoiler/changes log file.

### Phase 8 — Packaging
- PyInstaller build; ship `data/` alongside.

## Audit
The audit and catalogue register lives in [AUDIT.md](AUDIT.md). No feature randomizer ships until its catalogue coverage is complete.

## Verification
- `pytest`: param/FMG round-trip; baseline diff (identical, our-output, foreign-mod cases); graph invariants (every ref target exists, no dangling, reach sets stable vs snapshot); classifier coverage = 100% for enabled features; allocator never repoints an anchor referenced from EMEVD/MSB/TAE/Lua; same seed + preset ⇒ byte-identical output; running twice ⇒ identical output (idempotence).
- `tools/audit_report.py` produces coverage report (unclassified/ambiguous rows, missing Refs, low-confidence Lua edges) — drives AUDIT.md.
- Manual in-game checklist per feature (boot, equip randomized rings & read descriptions, cast one spell per subtype, fire each ammo type, fight sample enemies per category, trap areas).
- UI smoke: launch `python -m ds1rand.ui`, load/export/import share string, randomize to a scratch copy of the game dir.

## Milestone order
0 docs → 1 I/O → 2 baseline → 3 graph (params+computed, then EMEVD/MSB, then TAE, then Lua) → 4 catalogue (SpEffect, Bullet, Atk, Magic first) → 6.1 rings on new stack (first end-to-end) → 7 UI shell + presets → 5 allocator → 6.2 spells → 6.3 projectiles → 6.4 enemy behaviour → 6.5 weapons → 6.6 armor → 6.7 body / face data → 8 packaging.

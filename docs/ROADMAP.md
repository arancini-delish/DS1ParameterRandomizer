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

### Phase 3 — Static reference graph (the core) (3a param edges, 3b EMEVD + MSB, 3c TAE done)
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

### Phase 4 — Catalogue & classification
- Every node in scope gets `feature` (ring, player_spell, enemy_spell, env_spell, player_projectile, enemy_projectile, env_projectile, enemy_behaviour, weapon, other/pinned) and `subtype` (see register). Rows used by multiple features are recorded with all usages.
- Classifiers are rule-based (port of current heuristics) + curated overrides YAML; any row unclassified or matching >1 subtype is surfaced in the audit report — **no randomization feature ships until its coverage = 100% of reachable rows** (or explicitly pinned).
- **Minimum budgets**: per feature, the number of distinct rows of each param needed so that every user of that feature gets its own decoupled chain (e.g. spell X needs 1 Magic + 3 Bullet + 1 Atk + 2 SpEffect). Computed from graph reach, stored in `budgets.json`.
- **Free pool**: rows unused by anything (orphans), plus free ID ranges appendable to each param (soulstruct allows adding rows) → surplus count per param.

### Phase 5 — Allocation layer (`alloc/`)
- Decouple shared rows: when feature A randomizes a row also used by feature B, clone into a new ID and repoint only A's references (param refs only — never rewrite EMEVD/MSB/TAE/Lua; rows referenced from those are fixed-ID and become "anchors" that keep their ID).
- Reserve minimum budgets per enabled feature first; surplus distributed by user weighting to compound chains (hit-bullets, child bullets, extra target SpEffects, Atk on-hit effects).
- Spec-then-write model (from current `ReferencedObject.spec` idea): randomizers emit specs; allocator resolves IDs; writer applies once.

### Phase 6 — Feature randomizers
1. **Rings** — port `ring_randomizer.py` onto the new model; exclusion list (key/quest rings: Covenant of Artorias, Darkmoon Séance, Orange Charred, plus user-configurable keep list); effect score tiers + distribution; rewrite Accessory summary/description FMGs (replace or append mode).
2. **Spells** — player/enemy/environment; preserve subtype + school (sorcery/pyro/miracle, `ezStateBehaviorType`) + cast animation; randomize bullet visuals (sfx IDs limited to FFX resident for the caster — see audit), chaining, SpEffects, damage; cost model from `magic_randomizer.py` (power score ↔ casts, slots, stat req, cast speed/anim). Pinned utility: Homeward, Darkmoon/Sunlight Blade? (audit), Cast Light, Repair, Aural Decoy etc. per catalogue. Update Magic names/descriptions.
3. **Projectiles** — non-spell bullets (arrows/bolts, throwables, enemy ranged, traps); same chaining engine, non-spell sfx pool; player cost model (ammo/goods price, weight, damage vs. bow/crossbow association); separate distributions for player/enemy/environment.
4. **Enemy behaviour** — NpcParam / NpcThinkParam / MoveParam fields: turn speed, detection (sight/hearing radius & angle), move speed, aggression/battle-goal related fields, poise/stamina; each field toggleable with min/max/distribution; per-enemy-category exclusions (bosses, NPCs, scripted).

### Phase 7 — UI & presets
- Main window: global preset bar (built-in: Vanilla-ish / Standard / Chaos / custom), game dir, seed, "Validate install" (runs baseline diff), Randomize, report pane.
- Tabs: Rings, Spells, Projectiles, Enemy Behaviour, plus **Audit** tab (read-only graph/coverage browser — useful for development).
- Reusable `DistributionEditor` (weights per tier/score bucket, normalised, preset-able) and `FieldRangeEditor` for enemy fields.
- Preset schema versioned (dataclasses → JSON); share codec = JSON → zlib → base64url string with version + seed; import/export file and clipboard. Global preset sets all tab presets; tab-level overrides allowed.
- Output: spoiler/changes log (per feature, human readable).

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
0 docs → 1 I/O → 2 baseline → 3 graph (params+computed, then EMEVD/MSB, then TAE, then Lua) → 4 catalogue (SpEffect, Bullet, Atk, Magic first) → 6.1 rings on new stack (first end-to-end) → 7 UI shell + presets → 5 allocator → 6.2 spells → 6.3 projectiles → 6.4 enemy behaviour → 8 packaging.

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

### Phase 1 — soulstruct I/O port
- `io/gameparam.py`: load/save `GameParam.parambnd.dcx` via soulstruct's DSR `GameParamBND`; expose rows as typed dicts keyed by field name; ID allocation helpers (append new rows).
- `io/msg.py`: `item.msgbnd.dcx` (and `menu.msgbnd.dcx` if needed) — Accessory/Magic/Goods/Weapon name, summary, description FMGs.
- Round-trip test: load → save unchanged → byte/row-identical; game boots.

### Phase 2 — Vanilla baseline
- `tools/build_baseline.py`: from a clean DSR install, dump every param's rows + relevant FMGs into `data/baseline/` with a manifest (game version, file SHA256, per-row hashes).
- `baseline/diff.py`: on every run, read disk params, diff against baseline → report: identical / previously-randomized-by-us (detect via a signature row or manifest written on output) / unknown modifications (flag, let user choose: abort, overwrite from baseline, or keep modded rows pinned).
- Output always = baseline + our edits. This is the idempotence fix.

### Phase 3 — Static reference graph (the core)
Edge extractors, each tagged with source + semantic role (e.g. `bullet.hitBullet`, `atk.targetSpEffect`, `emevd.ShootBullet`, `tae.InvokeBullet`):
1. **Param→param** from Meta `Refs` (including conditional refs evaluated per row).
2. **Computed IDs** not in Meta: BehaviorParam (`2xx` NPC = `behaviorVariationId*1000 + judgeId`), BehaviorParam_PC (weapon `behaviorVariationId`), arrow/bolt ammo → bullet via behaviour variation, SpEffect `replaceSpEffectId`/cycle/next fields, Goods throwables, ObjActParam, ThrowParam, NpcThinkParam, CharaInit.
3. **EMEVD** (soulstruct): ShootBullet / ShootProjectile, SetSpEffect/CancelSpEffect, ApplySpEffect to entities, item award (ItemLot), ObjAct triggers.
4. **MSB** (soulstruct): enemy parts → NpcParam/NpcThinkParam/CharaInit, objects, traps (bullet-firing objects, ObjAct), map-specific ID ranges.
5. **TAE** (new reader in `io/tae.py`; DS1 TAE format, only parse event type + args): InvokeAttackBehavior / InvokeBulletBehavior / InvokePCBehavior / ApplySpEffect-style events, per character (`chr/cXXXX.anibnd.dcx`) and player (`c0000`). Links animations → BehaviorParam judge IDs → Atk/Bullet/SpEffect. Also identifies "spray" style spells (repeated bullet invokes) without hardcoded anim IDs.
6. **AI Lua** (`script/*.luabnd.dcx`, compiled Lua 5.0): `io/lua.py` constant extractor from bytecode (no full decompile) for numeric literals → candidate SpEffect/anim/behaviour IDs; optional DSLuaDecompiler output for manual audit. Low-confidence edges flagged as such.
7. **Curated** `catalogue/hardcoded.yaml`: EXE-hardcoded SpEffect/Bullet/Atk IDs (humanity, hollowing, covenant, poison/toxic/bleed/curse buildup effects, hit-material SpEffects, stateInfo semantics, homeward/return spells, ring passives such as Ring of Fog/Rusted Iron).
- Output `data/catalogue/graph.json`. `graph` API: `users_of(node)`, `reach(node)`, `features_of(node)`, `is_shared(node)`.

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

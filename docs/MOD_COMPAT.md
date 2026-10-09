# Running on top of the item, enemy and fog gate randomizers

Order: item randomizer → enemy randomizer → fog gate randomizer → ds1rand (always last).

Measured 2026-10-09 with `tools/diff_install.py`: each mod run alone on a Steam-verified install, then all three in
order (`out/install_snapshots/{vanilla,item,enemy,fog,all}.json`, report `out/install_reports/all.md`).

## What each mod changes

| Mod | Files | GameParam |
|---|---|---|
| Item randomizer | `param/GameParam` only (+ seed folder with param copies and cheat sheets) | ItemLotParam (841 changed, 270 added, 291 removed), ShopLineupParam (319 changed), CharaInitParam (20 changed: starting classes 3000-3009, 2000-2009, 9019/9119) |
| Enemy randomizer | GameParam, all 17 map EMEVDs, all 18 MSBs, all 17 map AI luabnds, `sfx/FRPG_SfxBnd_CommonEffects.ffxbnd.dcx` | NpcParam: 890 rows added (per-placement copies of existing rows, e.g. 120000 → 120001), 112 changed |
| Fog gate randomizer ("boss lords scale") | GameParam, common + all map EMEVDs, 17 MSBs, all 17 talk ESDs, `menu.msgbnd` | Area scaling, most likely: 201 SpEffectParam rows added (7200+), NpcParam spEffectID*/GameClearSpEffectID set to them, GameAreaParam boss souls (19) |

Attribution of NpcParam / SpEffectParam / GameAreaParam between the enemy and fog gate mods is from their logs and row
ranges; only the combined GameParam was captured.

## Findings

1. **The mods compose on the current files.** The combined GameParam contains the item randomizer's changes after the
   enemy and fog gate runs, so each mod reads the file on disk, not a vanilla backup. They create `<file>.bak` only
   when none exists: the pre-existing `.bak` files (vanilla, from 2026-06-20) were left alone; fog gate added `.bak`
   for `common.emevd`, the talk ESDs and `menu.msgbnd`.
2. **No overlap with the spell / projectile / ring params.** Bullet, Magic, AtkParam_Pc/Npc, BehaviorParam(_PC) and
   EquipParamAccessory are untouched; SpEffectParam only gains new rows (7200+), no vanilla row changes. Item text
   (`item.msgbnd`) is untouched.
3. **Overlap with enemy behaviour.** NpcParam is heavily changed (890 new rows, scaling SpEffects on existing ones).
   An enemy-behaviour randomizer must work on the installed NpcParam rows, including the new ones.
4. **The allocator touches CharaInitParam**, which the item randomizer changes (starting equipment), when NPC copies
   of weapons/armor are made. Field-level conflicts are possible there.
5. **The reference graph changes.** MSB placements move to new NpcParam rows and different models (1677 links added,
   1658 removed); 95 NpcThinkParam rows lose their users; 79 SpEffect rows change features (new scaling effects become
   `enemy`, event SpEffects move). No Bullet or Magic row changes feature. So the vanilla catalogue is right for the
   spell/projectile/ring params, but enemy-related usage must come from the installed files.
6. **FFX availability changes.** The enemy randomizer rewrites the common effects binder (to make enemy effects load
   anywhere). Projectile visual swaps (AUDIT 18) must check the installed binder, not assume vanilla residency.
7. **The combined GameParam has repeated SpEffect row IDs with different contents**: 7240, 7280, 7320 and 7360 (in
   the fog gate's scaling range) each appear twice. soulstruct keeps only the first of each when re-serializing, so
   `GameParams.save` refuses to re-serialize SpEffectParam on this install, and any SpEffect edit (spell copies,
   ring effects) would be blocked or would change the other mod's behaviour.
8. **EMEVD robustness.** The enemy randomizer's EMEVDs pass more RunEvent arguments than soulstruct's parsed format
   holds; `ds1rand/graph/emevd.py` now packs the extras as 32-bit words.

## Proposed design (replaces "refuse modified installs")

- **Base = the files as the other mods left them**, not vanilla. On the first ds1rand write, save that state next to
  the file (`<file>.ds1rand-base`). On re-runs:
  - disk is ours (marker matches): rebuild from `.ds1rand-base`;
  - disk was changed after our write (another mod re-run on top of ours): strip our previous edits using the patch
    list recorded in the marker (restore each field we wrote if it still holds our value; drop rows in our new-ID
    blocks), and take the result as the new base;
  - no marker: disk is the base.
- **Run on the installed state.** Build the graph with `build_install_graph` and classify / allocate on the installed
  params (a `Baseline` built from the base file), so new NpcParam rows, moved placements and new SpEffects are seen.
  The committed vanilla catalogue stays as the reference for audits and for detecting foreign changes.
- **Write field-level patches**, not whole rows: randomizers set fields; the writer applies only those fields to the
  base rows, and records them (old value, new value) in the marker. Randomizers compute from base values, never from
  disk values, so nothing compounds.
- **Byte-level param writing for params with repeated IDs** (needed now for SpEffectParam): patch fields in the
  original row data and insert new rows into the original binary (rows sorted by ID, duplicates kept in place), instead
  of re-serializing through soulstruct.
- **Conflicts**: a field we want to patch that another mod already changed from vanilla (e.g. CharaInitParam starting
  equipment) keeps the other mod's value by default and is reported; the allocator then treats that reference as
  fixed.

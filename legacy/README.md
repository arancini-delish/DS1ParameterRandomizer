# Legacy prototype

The original WitchyBND-based prototype, kept only as reference for porting into `ds1rand/`. It is not importable or runnable as-is (`witchy_util` and `id_to_names` were removed).

| File | Port target |
|---|---|
| `ring_randomizer.py` | `ds1rand/features/rings` — effect tiers, summary text, ignore list |
| `magic_randomizer.py` | `ds1rand/features/spells` — spell cost model |
| `param_categorizer.py`, `constants.py` | `ds1rand/catalogue` — spell subtype heuristics |
| `projectile_randomizer.py`, `sp_effect_randomizer.py` | `ds1rand/alloc` / `features` — spec-then-write model |
| `main.py` | `ds1rand/ui` — preset combo and distribution validation |
| `default_vals/*.csv` | `ds1rand/features` — blank row templates |

Delete this folder once the ports are complete.

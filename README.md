# DS1ParameterRandomizer
Custom tailored parameter randomizer for Dark Souls 1: Remastered.

Work in progress. See [docs/ROADMAP.md](docs/ROADMAP.md) for the plan and [docs/AUDIT.md](docs/AUDIT.md) for the catalogue/audit tracker.

## Layout
- `ds1rand/` — the new package (one subpackage per roadmap phase).
- `ds1paramdefs/` — community paramdefs, Meta (field names, wiki notes, `Refs`) and row names.
- `data/baseline/`, `data/catalogue/` — generated vanilla baseline and reference graph/catalogue.
- `tools/` — build scripts (baseline, graph, audit report).
- `tests/`
- `legacy/` — original prototype, reference only.

## Setup
Requires Python 3.13+.

```bash
uv sync
```

## Usage
Run the item, enemy and fog gate randomizers first (if you use them), then:

```bash
uv run python -m ds1rand.ui
```

or from the command line:

```bash
uv run python tools/randomize.py --preset Standard --seed 1
```

Output goes to `out/randomized/` unless you choose to write into the game folder; copy its `param` and `msg` folders
(including the `.ds1rand-base` / `.ds1rand.json` files) over the game's.

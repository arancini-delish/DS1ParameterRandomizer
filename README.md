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

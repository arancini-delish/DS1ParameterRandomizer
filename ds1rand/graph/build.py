"""Assembling the full reference graph.

Param -> param edges are rebuilt from the baseline on demand. Edges from game files other than params (EMEVD, MSB, TAE, AI Lua)
need vanilla game files to extract, so they are extracted once with `extract_external` and committed under
`data/catalogue/`, together with `sources.json` (SHA-256 of every file read); `build_graph` loads them from there.

Other mods (item/enemy randomizers) rewrite event and map files in place and keep the vanilla file as `<name>.bak`.
`prefer_bak` reads those backups instead; check they are vanilla before relying on that.
"""
from __future__ import annotations

import json
from pathlib import Path

from ds1rand.baseline.store import Baseline, sha256_file
from ds1rand.graph.emevd import event_files, extract_emevd_edges
from ds1rand.graph.hardcoded import add_hardcoded_edges
from ds1rand.graph.lua import extract_lua_edges, luabnd_files
from ds1rand.graph.model import RefGraph
from ds1rand.graph.msb import extract_msb_edges, map_files
from ds1rand.graph.params import extract_param_edges
from ds1rand.graph.tae import anibnd_files, extract_tae_edges
from ds1rand.io.install import GameInstall

CATALOGUE_DIR = Path(__file__).resolve().parents[2] / "data" / "catalogue"
SOURCES_FILE = "sources.json"
HARDCODED_FILE = "hardcoded.toml"


def _stem(path: Path) -> str:
    return path.name.split(".")[0]


# Committed file name -> (function listing the game files in an install, extractor). Extractors take
# (files, baseline, prior graph) and run in this order; `prior` holds the param edges and every earlier source.
EXTERNAL_SOURCES = {
    "emevd.json": (
        lambda install: event_files(install.root / "event"),
        lambda files, baseline, prior: extract_emevd_edges(files, row_ids(baseline)),
    ),
    "msb.json": (
        lambda install: map_files(install.root / "map" / "MapStudio"),
        lambda files, baseline, prior: extract_msb_edges(files, row_ids(baseline)),
    ),
    "tae.json": (lambda install: anibnd_files(install.root / "chr"), extract_tae_edges),
    "lua.json": (lambda install: luabnd_files(install.root / "script"), extract_lua_edges),
}


def row_ids(baseline: Baseline) -> dict[str, set[int]]:
    return {name: set(pb.rows) for name, pb in baseline.params.items()}


def source_files(install: GameInstall, prefer_bak: bool = False) -> dict[str, dict[str, Path]]:
    """Committed file name -> {file stem: file to read} for every external source."""
    sources = {}
    for file_name, (list_files, _) in EXTERNAL_SOURCES.items():
        files = {}
        for path in list_files(install):
            backup = path.with_name(path.name + ".bak")
            files[_stem(path)] = backup if prefer_bak and backup.is_file() else path
        sources[file_name] = files
    return sources


def source_hashes(sources: dict[str, dict[str, Path]]) -> dict[str, dict[str, dict[str, str]]]:
    return {
        file_name: {stem: {"file": path.name, "sha256": sha256_file(path)} for stem, path in files.items()}
        for file_name, files in sources.items()
    }


def extract_sources(
    sources: dict[str, dict[str, Path]], baseline: Baseline
) -> tuple[dict[str, RefGraph], RefGraph]:
    """Extract every external source from `sources` (see `source_files`); returns the per-source graphs and the full
    graph (param edges + every source, without curated hardcoded references)."""
    full = extract_param_edges(baseline)
    graphs = {}
    for file_name, (_, extract) in EXTERNAL_SOURCES.items():
        graphs[file_name] = extract(sources[file_name], baseline, full)
        _merge(full, graphs[file_name])
    return graphs, full


def extract_external(
    install: GameInstall, baseline: Baseline, catalogue_dir: Path = CATALOGUE_DIR, prefer_bak: bool = False
) -> dict[str, RefGraph]:
    """Extract every external source from vanilla game files and write it, with `sources.json`, to `catalogue_dir`."""
    sources = source_files(install, prefer_bak)
    graphs, _ = extract_sources(sources, baseline)
    for file_name, graph in graphs.items():
        graph.write(catalogue_dir / file_name)
    (catalogue_dir / SOURCES_FILE).write_text(json.dumps(source_hashes(sources), indent=1) + "\n", encoding="utf-8")
    return graphs


def build_install_graph(
    install: GameInstall, catalogue_dir: Path = CATALOGUE_DIR, installed: Baseline | None = None
) -> tuple[Baseline, RefGraph]:
    """The reference graph of the files actually installed, which other mods may have changed: params from the
    installed GameParam (or `installed`, e.g. the base ds1rand builds on), external sources re-extracted from the
    installed files, plus curated hardcoded references. Returns the params (as a `Baseline`, so all catalogue code works
    on them) and the graph."""
    from ds1rand.io.gameparam import GameParams

    if installed is None:
        installed = Baseline.from_game_files(GameParams.from_path(install.gameparam), None, {})
    _, graph = extract_sources(source_files(install), installed)
    if (catalogue_dir / HARDCODED_FILE).is_file():
        add_hardcoded_edges(catalogue_dir / HARDCODED_FILE, installed, graph)
    return installed, graph


def build_graph(baseline: Baseline | None = None, catalogue_dir: Path = CATALOGUE_DIR) -> RefGraph:
    """Param edges from the baseline, every committed external source, and the curated hardcoded references."""
    baseline = baseline or Baseline.load()
    graph = extract_param_edges(baseline)
    for file_name in EXTERNAL_SOURCES:
        path = catalogue_dir / file_name
        if path.is_file():
            _merge(graph, RefGraph.load(path))
    if (catalogue_dir / HARDCODED_FILE).is_file():
        add_hardcoded_edges(catalogue_dir / HARDCODED_FILE, baseline, graph)
    return graph


ORPHAN_PARAMS = (
    "SpEffectParam", "Bullet", "AtkParam_Pc", "AtkParam_Npc", "BehaviorParam", "BehaviorParam_PC", "Magic",
    "EquipParamWeapon", "EquipParamProtector", "EquipParamAccessory", "EquipParamGoods", "NpcParam", "NpcThinkParam",
    "ItemLotParam", "ObjActParam",
)


def orphans(graph: RefGraph, baseline: Baseline, params=ORPHAN_PARAMS) -> dict[str, list[int]]:
    """Rows (other than row 0) that nothing in the graph references: dead data or engine use not yet catalogued."""
    used = {(e.dst.name, e.dst.id) for e in graph.edges if e.dst.kind == "param"}
    return {p: [r for r in sorted(baseline.params[p].rows) if r and (p, r) not in used] for p in params}


def _merge(graph: RefGraph, other: RefGraph) -> None:
    for edge in other.edges:
        graph.add(edge)
    graph.unresolved.extend(other.unresolved)

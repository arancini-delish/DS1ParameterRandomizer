"""Assembling the full reference graph.

Param -> param edges are rebuilt from the baseline on demand. Edges from game files other than params (EMEVD, MSB, TAE)
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
from ds1rand.graph.model import RefGraph
from ds1rand.graph.msb import extract_msb_edges, map_files
from ds1rand.graph.params import extract_param_edges
from ds1rand.graph.tae import anibnd_files, extract_tae_edges
from ds1rand.io.install import GameInstall

CATALOGUE_DIR = Path(__file__).resolve().parents[2] / "data" / "catalogue"
SOURCES_FILE = "sources.json"


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


def extract_external(
    install: GameInstall, baseline: Baseline, catalogue_dir: Path = CATALOGUE_DIR, prefer_bak: bool = False
) -> dict[str, RefGraph]:
    """Extract every external source from vanilla game files and write it, with `sources.json`, to `catalogue_dir`."""
    sources = source_files(install, prefer_bak)
    prior = extract_param_edges(baseline)
    graphs = {}
    for file_name, (_, extract) in EXTERNAL_SOURCES.items():
        graphs[file_name] = extract(sources[file_name], baseline, prior)
        graphs[file_name].write(catalogue_dir / file_name)
        _merge(prior, graphs[file_name])
    (catalogue_dir / SOURCES_FILE).write_text(json.dumps(source_hashes(sources), indent=1) + "\n", encoding="utf-8")
    return graphs


def build_graph(baseline: Baseline | None = None, catalogue_dir: Path = CATALOGUE_DIR) -> RefGraph:
    """Param edges from the baseline plus every committed external source."""
    graph = extract_param_edges(baseline or Baseline.load())
    for file_name in EXTERNAL_SOURCES:
        path = catalogue_dir / file_name
        if path.is_file():
            _merge(graph, RefGraph.load(path))
    return graph


def _merge(graph: RefGraph, other: RefGraph) -> None:
    for edge in other.edges:
        graph.add(edge)
    graph.unresolved.extend(other.unresolved)

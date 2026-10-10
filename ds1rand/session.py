"""`Session`: one ds1rand run on an install, on top of whatever other mods left (see docs/MOD_COMPAT.md).

    session = Session.open(install)          # resolve bases, build the graph from the installed files
    allocation = session.allocate(["player_spell"], params={...})
    session.store.set(...)                   # randomizers edit rows (computed from base values)
    session.text[("Magic_name", 3000)] = "..."
    session.write({"seed": 1})               # field patches onto the bases, base copies, markers

Everything is computed from the base (the files as the other mods left them): classification, usage and allocation
see the other mods' new rows and placements. The vanilla baseline is kept for reporting what the other mods changed.
Rows with repeated IDs in the base are protected: they cannot be edited or copied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from ds1rand.alloc.allocator import Allocation, allocate
from ds1rand.alloc.store import RowStore
from ds1rand.alloc.write import (
    BaseResolution, apply_params, apply_text, resolve_base, strip_params, strip_text, write_output,
)
from ds1rand.baseline.compare import diff_params, diff_text
from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.budget import IdAllocator, RowBudget
from ds1rand.graph.build import build_install_graph
from ds1rand.graph.model import RefGraph
from ds1rand.io.gameparam import GameParams, RawGameParam
from ds1rand.io.install import GameInstall
from ds1rand.io.msg import ItemText
from ds1rand.io.parambinary import ParamBinary


@dataclass
class Session:
    install: GameInstall
    vanilla: Baseline
    gameparam_base: BaseResolution
    text_base: BaseResolution
    base: Baseline
    graph: RefGraph
    store: RowStore
    ids: IdAllocator
    text: dict[tuple[str, int], str] = field(default_factory=dict)

    @classmethod
    def open(cls, install: GameInstall | None = None) -> Session:
        install = install or GameInstall.default()
        install.validate()
        gameparam_base = resolve_base(install.gameparam, strip_params)
        text_base = resolve_base(install.item_msgbnd, strip_text)
        base = Baseline.from_game_files(
            GameParams.from_bytes(gameparam_base.data), ItemText.from_bytes(text_base.data), {}
        )
        raw = RawGameParam.from_bytes(gameparam_base.data)
        protected = {}
        for name in raw.names:
            duplicates = ParamBinary(raw.param_bytes(name)).duplicate_ids
            if duplicates:
                protected[name] = duplicates
        _, graph = build_install_graph(install, installed=base)
        return cls(install, Baseline.load(), gameparam_base, text_base, base, graph, RowStore(base, protected),
                   IdAllocator(base))

    @property
    def conflicts(self) -> list[str]:
        """Patches from the previous run that another mod has since overridden (their values were kept)."""
        return self.gameparam_base.conflicts + self.text_base.conflicts

    def foreign_changes(self) -> dict[str, list]:
        """What the base differs from vanilla in (the other mods' changes)."""
        return {"params": diff_params(GameParams.from_bytes(self.gameparam_base.data), self.vanilla),
                "text": diff_text(ItemText.from_bytes(self.text_base.data), self.vanilla)}

    def allocate(
        self, enabled, budget: RowBudget | None = None, params: set[str] | None = None, rows: set | None = None
    ) -> Allocation:
        return allocate(self.graph, self.base, self.store, enabled, budget, self.ids, params, rows)

    @cached_property
    def usage(self):
        """Features using each node of the installed graph (see `catalogue.usage`)."""
        from ds1rand.catalogue.usage import compute_usage

        return compute_usage(self.graph, self.base, all_nodes=True)

    @cached_property
    def effects(self):
        """Which particle effects the installed sfx bundles load where (see `catalogue.ffx`)."""
        from ds1rand.catalogue.ffx import EffectResidency

        return EffectResidency.from_sfx_dir(self.install.root / "sfx")

    def footprint(self, feature: str, params: set[str] | None = None) -> set:
        """Param rows `feature` uses (optionally only in `params`)."""
        return {n for n, f in self.usage.items()
                if n.kind == "param" and feature in f and (params is None or n.name in params)}

    def write(self, info: dict | None = None, out_dir: Path | str | None = None) -> dict:
        """Write GameParam and item text (only if they have changes, or a previous ds1rand output must be replaced).
        With `out_dir`, the files (and their base copies and markers) go there, mirroring the install's layout, instead
        of into the game folder. Returns the patch records written."""
        written = {}
        for path, relative, resolution, apply, changes in (
            (self.install.gameparam, GameInstall.GAMEPARAM, self.gameparam_base,
             lambda b: apply_params(b, self.store), self.store.changes()),
            (self.install.item_msgbnd, GameInstall.ITEM_MSGBND, self.text_base,
             lambda b: apply_text(b, self.text), self.text),
        ):
            if not changes and resolution.state == "external":
                continue
            data, patches = apply(resolution.data)
            if out_dir is not None:
                path = Path(out_dir) / relative
                path.parent.mkdir(parents=True, exist_ok=True)
            write_output(path, data, resolution.data, patches, info)
            written[path.name] = patches
        return written

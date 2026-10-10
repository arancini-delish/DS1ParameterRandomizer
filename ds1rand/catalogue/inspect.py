"""Inspecting the catalogue of a session: one row's references, usage, subtype and changes; coverage per param.

Used by the UI Audit tab (and handy from a Python shell):

    session = Session.open(install)
    print(describe_row(session, "Bullet", 3000).text())
    for row in coverage(session): ...
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import cache

from ds1rand.catalogue.effects import EffectClassifier
from ds1rand.catalogue.subtypes import classify_bullet, classify_magic
from ds1rand.catalogue.usage import FEATURES
from ds1rand.defs.meta import load_row_names
from ds1rand.graph.build import ORPHAN_PARAMS
from ds1rand.graph.model import Node
from ds1rand.session import Session

# Params whose rows have in-game names (item text category ID; patch FMGs are merged in by `row_name`).
NAME_TEXT = {"EquipParamGoods": 10, "EquipParamWeapon": 11, "EquipParamProtector": 12, "EquipParamAccessory": 13,
             "Magic": 14}
PATCH_TEXT = {10: 111, 11: 112, 12: 113, 13: 114, 14: 118}


@dataclass
class Reference:
    field: str
    node: str
    source: str
    confidence: str


@dataclass
class RowReport:
    param: str
    row_id: int
    name: str
    exists: bool
    new: bool = False
    features: list[str] = field(default_factory=list)
    subtype: str = ""
    refs: list[Reference] = field(default_factory=list)  # what this row references
    users: list[Reference] = field(default_factory=list)  # what references this row
    changes: dict[str, tuple] = field(default_factory=dict)  # field -> (vanilla, base, this run)

    def text(self) -> str:
        lines = [f"{self.param} {self.row_id}" + (f" - {self.name}" if self.name else "")]
        if not self.exists:
            return lines[0] + "\n(no such row)"
        if self.new:
            lines.append("New row added by this run (not in the reference graph).")
        lines.append(f"Used by: {', '.join(self.features) or 'nothing (orphan or unreached)'}")
        if self.subtype:
            lines.append(f"Subtype: {self.subtype}")
        for title, refs in (("References", self.refs), ("Referenced by", self.users)):
            lines += ["", f"{title} ({len(refs)}):"]
            lines += [f"  {r.field:40} {r.node:40} {r.source} ({r.confidence})" for r in refs] or ["  none"]
        lines += ["", f"Changes ({len(self.changes)}):"]
        lines += [f"  {f:32} vanilla {_fmt(v)}  base {_fmt(b)}  this run {_fmt(n)}"
                  for f, (v, b, n) in self.changes.items()] or ["  none"]
        return "\n".join(lines)


def _fmt(value) -> str:
    if value is None:
        return "-"
    return f"{value:g}" if isinstance(value, float) else str(value)


def row_name(session: Session, param: str, row_id: int) -> str:
    if param in NAME_TEXT:
        category = NAME_TEXT[param]
        patch = session.base.text.get(PATCH_TEXT[category], ("", {}))[1]
        name = patch.get(row_id) or session.base.text.get(category, ("", {}))[1].get(row_id)
        if name:
            return name
    return load_row_names(param).get(row_id, "")


@cache
def _classifier(session_id: int, session: Session) -> EffectClassifier:
    return EffectClassifier(session.base, session.graph)


def subtype(session: Session, param: str, row_id: int) -> str:
    base = session.base
    if row_id not in base.params[param].rows:
        return ""
    if param == "Bullet":
        return classify_bullet(base.params["Bullet"].row_values(row_id)).subtype
    if param == "Magic":
        return classify_magic(base, row_id).subtype
    if param == "SpEffectParam":
        return _classifier(id(session), session).speffect(row_id).subtype
    if param in ("AtkParam_Pc", "AtkParam_Npc"):
        return _classifier(id(session), session).attack(param, row_id)
    return ""


def describe_row(session: Session, param: str, row_id: int) -> RowReport:
    base_rows = session.base.params[param].rows
    store = session.store
    exists = row_id in base_rows or store.exists(param, row_id)
    report = RowReport(param, row_id, row_name(session, param, row_id), exists)
    if not exists:
        return report
    report.new = row_id not in base_rows
    node = Node.param(param, row_id)
    report.features = sorted(session.usage.get(node, ()), key=FEATURES.index)
    report.subtype = subtype(session, param, row_id)
    report.refs = [Reference(e.field, str(e.dst), e.source, e.confidence) for e in session.graph.refs_of(node)]
    report.users = [Reference(e.field, str(e.src), e.source, e.confidence) for e in session.graph.users_of(node)]
    vanilla_param = session.vanilla.params.get(param)
    vanilla = vanilla_param.row_values(row_id) if vanilla_param and row_id in vanilla_param.rows else {}
    base = session.base.params[param].row_values(row_id) if not report.new else {}
    now = store.values(param, row_id)
    for name, value in now.items():
        if value != base.get(name, value if not report.new else None) or vanilla.get(name, value) != value:
            report.changes[name] = (vanilla.get(name), base.get(name), value)
    return report


@dataclass
class CoverageRow:
    param: str
    rows: int
    used: int
    shared: int
    per_feature: Counter
    unresolved: int
    changed: int


def coverage(session: Session, params=ORPHAN_PARAMS) -> list[CoverageRow]:
    """Per param: rows, rows used by any feature, rows shared by several, rows per feature, unresolved references
    from the param, and rows this session changed or added."""
    unresolved = Counter(u.src.name for u in session.graph.unresolved if u.src.kind == "param")
    changes = session.store.changes()
    by_param: dict[str, list[set[str]]] = {}
    for node, features in session.usage.items():
        if node.kind == "param" and features:
            by_param.setdefault(node.name, []).append(features)
    rows = []
    for param in params:
        tags = by_param.get(param, [])
        rows.append(CoverageRow(
            param, len([r for r in session.base.params[param].rows if r]), len(tags),
            sum(len(t) > 1 for t in tags), Counter(f for t in tags for f in t), unresolved[param],
            len(changes.get(param, {})),
        ))
    return rows

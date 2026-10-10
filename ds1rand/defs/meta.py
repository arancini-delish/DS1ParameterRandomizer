"""Loading the community param metadata in `ds1paramdefs/Meta` and `Shared Param Enums.json`.

Meta files are named like the Defs files and describe one param type each (several params can share a type, e.g.
AtkParam_Pc and AtkParam_Npc). Per field they give an English name, wiki text, enum, and `Refs`: which params the
field's value is a row ID of, optionally only when another field has a given value, e.g.
`Refs="AtkParam_Pc(refType=0),Bullet(refType=1),SpEffectParam(refType=2)"`.
"""
from __future__ import annotations

import functools
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

PARAMDEFS_DIR = Path(__file__).resolve().parents[2] / "ds1paramdefs"
META_DIR = PARAMDEFS_DIR / "Meta"

_REF_RE = re.compile(r"^(\w+)(?:\((\w+)=(-?\d+)\))?$")


@dataclass(frozen=True)
class RefTarget:
    param: str  # as written in Meta; may need normalising to a real param name (see `graph.params.PARAM_ALIASES`)
    condition_field: str | None = None
    condition_value: int | None = None

    def applies(self, row: dict) -> bool:
        return self.condition_field is None or row.get(self.condition_field) == self.condition_value


@dataclass(frozen=True)
class FieldMeta:
    name: str
    alt_name: str = ""
    wiki: str = ""
    enum: str | None = None
    is_bool: bool = False
    refs: tuple[RefTarget, ...] = ()


@dataclass
class ParamMeta:
    def_name: str  # Meta/Defs file stem, e.g. "BulletParam"
    wiki: str
    fields: dict[str, FieldMeta]
    enums: dict[str, dict[int, str]] = field(default_factory=dict)  # enums local to this meta file


def parse_refs(text: str) -> tuple[RefTarget, ...]:
    targets = []
    for part in text.split(","):
        match = _REF_RE.match(part.strip())
        if not match:
            raise ValueError(f"Cannot parse Refs entry {part!r}")
        param, cond_field, cond_value = match.groups()
        targets.append(RefTarget(param, cond_field, int(cond_value) if cond_value is not None else None))
    return tuple(targets)


def _parse(path: Path) -> ParamMeta:
    root = ET.parse(path).getroot()
    fields = {}
    for element in root.find("Field"):
        a = element.attrib
        fields[element.tag] = FieldMeta(
            name=element.tag,
            alt_name=a.get("AltName", ""),
            wiki=a.get("Wiki", ""),
            enum=a.get("Enum"),
            is_bool="IsBool" in a,
            refs=parse_refs(a["Refs"]) if "Refs" in a else (),
        )
    enums = {}
    for enum in root.iter("Enum"):
        enums[enum.get("Name")] = {int(o.get("Value")): o.get("Name") for o in enum.iter("Option")}
    self_element = root.find("Self")
    wiki = self_element.get("Wiki", "") if self_element is not None else ""
    return ParamMeta(path.stem, wiki, fields, enums)


@functools.cache
def load_meta(directory: Path = META_DIR) -> dict[str, ParamMeta]:
    """All Meta files, keyed by file stem (same stem as the matching `Defs` file)."""
    return {path.stem: _parse(path) for path in sorted(directory.glob("*.xml"))}


@functools.cache
def load_shared_enums(path: Path = PARAMDEFS_DIR / "Shared Param Enums.json") -> dict[str, dict[int, str]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {e["Name"]: {int(o["ID"]): o["Name"] for o in e["Options"]} for e in data["List"]}


@functools.cache
def load_row_names(param: str) -> dict[int, str]:
    """Community row names (`Community Row Names/<param>.json`; machine-translated from the Japanese row names)."""
    path = PARAMDEFS_DIR / "Community Row Names" / f"{param}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {e["ID"]: e["Entries"][0] for e in data["Entries"] if e.get("Entries")}

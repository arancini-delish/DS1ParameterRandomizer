"""Loading the paramdefs in `ds1paramdefs/Defs` (field types, defaults, bit widths)."""
from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ds1rand.paths import PARAMDEFS_DIR

DEFS_DIR = PARAMDEFS_DIR / "Defs"

# e.g. "s32 atkId_Bullet = -1", "u8 hasTarget:1", "dummy8 pad[3]", "f32 life = -1"
_DEF_RE = re.compile(r"^(\w+)\s+(\w+)\s*(?:\[(\d+)\])?\s*(?::\s*(\d+))?\s*(?:=\s*(.+))?$")


@dataclass(frozen=True)
class FieldDef:
    name: str
    type: str  # s8/u8/s16/u16/s32/u32/f32/dummy8/fixstr/fixstrW
    array_length: int | None
    bit_count: int | None
    default: str | None
    display_name: str  # Japanese, from the paramdef
    description: str

    @property
    def is_pad(self) -> bool:
        return self.type == "dummy8"


@dataclass(frozen=True)
class ParamDef:
    param_type: str  # e.g. BULLET_PARAM_ST
    fields: tuple[FieldDef, ...]
    stem: str  # Defs file stem, e.g. "BulletParam"; the matching Meta file has the same stem

    @property
    def value_fields(self) -> list[FieldDef]:
        """Fields excluding padding, in binary order."""
        return [f for f in self.fields if not f.is_pad]


def _parse(path: Path) -> ParamDef:
    root = ET.parse(path).getroot()
    fields = []
    for element in root.iter("Field"):
        match = _DEF_RE.match(element.get("Def").strip())
        if not match:
            raise ValueError(f"{path.name}: cannot parse field Def {element.get('Def')!r}")
        type_, name, length, bits, default = match.groups()
        fields.append(FieldDef(
            name=name,
            type=type_,
            array_length=int(length) if length else None,
            bit_count=int(bits) if bits else None,
            default=default.strip() if default else None,
            display_name=element.findtext("DisplayName", ""),
            description=element.findtext("Description", ""),
        ))
    return ParamDef(root.findtext("ParamType"), tuple(fields), path.stem)


@functools.cache
def load_paramdefs(directory: Path = DEFS_DIR) -> dict[str, ParamDef]:
    """All paramdefs, keyed by param type (e.g. "BULLET_PARAM_ST")."""
    defs = (_parse(path) for path in sorted(directory.glob("*.xml")))
    return {d.param_type: d for d in defs}

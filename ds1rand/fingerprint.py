"""Game files fingerprint: a short code to check that two installs load the same game (e.g. before co-op).

Seamless Co-op (and vanilla multiplayer) needs every player's world to match. The item, enemy and fog gate
randomizers and ds1rand change params, text, events, maps, AI scripts and effects; if two players ran them with
different seeds, settings or in a different order, the games disagree and joining can fail (e.g. a guest spawns next to
the host but never properly joins). Both players validate their install and compare codes: equal codes mean the
gameplay files are identical. Per-group codes show which kind of file differs.

Hashed: the files the game loads (never `.bak` copies or ds1rand's `.ds1rand-base` / `.ds1rand.json` companions).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

GROUPS: dict[str, tuple[str, ...]] = {
    "params": ("param/GameParam/*.parambnd.dcx",),
    "text": ("msg/*/item.msgbnd.dcx", "msg/*/menu.msgbnd.dcx"),
    "events": ("event/*.emevd.dcx",),
    "maps": ("map/MapStudio/*.msb",),
    "scripts": ("script/*.luabnd.dcx", "script/talk/*.talkesdbnd.dcx"),
    "effects": ("sfx/*.ffxbnd.dcx",),
}
CODE_LENGTH = 10


@dataclass
class Fingerprint:
    code: str
    groups: dict[str, str] = field(default_factory=dict)
    files: int = 0

    def text(self) -> str:
        return f"Game files fingerprint: {self.code}  (" + ", ".join(f"{g} {c}" for g, c in self.groups.items()) + ")"


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(root: Path) -> Fingerprint:
    root = Path(root)
    overall = hashlib.sha256()
    result = Fingerprint("")
    for group, patterns in GROUPS.items():
        digest = hashlib.sha256()
        files = sorted({p for pattern in patterns for p in root.glob(pattern) if p.is_file()})
        for path in files:
            relative = path.relative_to(root).as_posix().lower()
            digest.update(f"{relative}:{_file_hash(path)}\n".encode())
        result.files += len(files)
        result.groups[group] = digest.hexdigest()[:6].upper()
        overall.update(f"{group}:{digest.hexdigest()}\n".encode())
    result.code = overall.hexdigest()[:CODE_LENGTH].upper()
    return result

"""The vanilla baseline shipped in `data/baseline/`: every param row and every item FMG string.

Layout:
    manifest.json        source file hashes, soulstruct version, per-param type, row count and vanilla duplicate row IDs
    params/<Name>.json   {"param", "fields", "rows": {row_id: [values in `fields` order]}}, one row per line
    text/item.json       {fmg_entry_id: {"stem", "entries": {text_id: string}}}

Field names are the paramdef names from `ds1paramdefs/Defs`, padding excluded (see `GameParams.field_names`). Only ints
and floats occur, and JSON round-trips both exactly.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ds1rand.io.gameparam import GameParams
from ds1rand.io.msg import ItemText

DEFAULT_BASELINE_DIR = Path(__file__).resolve().parents[2] / "data" / "baseline"
FORMAT_VERSION = 1


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class ParamBaseline:
    name: str
    fields: list[str]
    rows: dict[int, list[Any]]

    def row_values(self, row_id: int) -> dict[str, Any]:
        return dict(zip(self.fields, self.rows[row_id]))


@dataclass
class Baseline:
    manifest: dict[str, Any]
    params: dict[str, ParamBaseline]
    # FMG binder entry ID -> (stem, {text_id: string})
    text: dict[int, tuple[str, dict[int, str]]] = field(default_factory=dict)

    @property
    def duplicate_ids(self) -> dict[str, int]:
        return {name: info["duplicate_ids"] for name, info in self.manifest["params"].items() if info["duplicate_ids"]}

    @classmethod
    def from_game_files(cls, params: GameParams, text: ItemText | None, sources: dict[str, str]) -> Baseline:
        """Capture a baseline from loaded vanilla files. `sources` maps source file names to their SHA-256."""
        import soulstruct

        param_baselines = {}
        for name in params.names:
            rows = {row_id: list(params.row_values(name, row_id).values()) for row_id in params[name].rows}
            param_baselines[name] = ParamBaseline(name, params.field_names(name), rows)
        manifest = {
            "format": FORMAT_VERSION,
            "soulstruct": getattr(soulstruct, "__version__", "unknown"),
            "sources": sources,
            "params": {
                name: {
                    "param_type": params[name].param_type,
                    "rows": len(pb.rows),
                    "duplicate_ids": params.duplicate_ids.get(name, 0),
                }
                for name, pb in param_baselines.items()
            },
        }
        text_baseline = {}
        if text is not None:
            text_baseline = {fmg_id: (text.fmg_stem(fmg_id), text.fmg_entries(fmg_id)) for fmg_id in text.fmg_ids}
        manifest["text"] = sorted(text_baseline)
        return cls(manifest, param_baselines, text_baseline)

    @classmethod
    def load(cls, directory: Path | str = DEFAULT_BASELINE_DIR) -> Baseline:
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["format"] != FORMAT_VERSION:
            raise ValueError(f"Baseline format {manifest['format']} != supported {FORMAT_VERSION}")
        params = {}
        for name in manifest["params"]:
            data = json.loads((directory / "params" / f"{name}.json").read_text(encoding="utf-8"))
            params[name] = ParamBaseline(name, data["fields"], {int(k): v for k, v in data["rows"].items()})
        text = {}
        text_path = directory / "text" / "item.json"
        if text_path.is_file():
            data = json.loads(text_path.read_text(encoding="utf-8"))
            text = {int(k): (v["stem"], {int(i): s for i, s in v["entries"].items()}) for k, v in data.items()}
        return cls(manifest, params, text)

    def write(self, directory: Path | str = DEFAULT_BASELINE_DIR) -> None:
        directory = Path(directory)
        (directory / "params").mkdir(parents=True, exist_ok=True)
        (directory / "manifest.json").write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")
        for name, pb in self.params.items():
            lines = [
                f'{json.dumps(str(row_id))}: {json.dumps(values, separators=(",", ":"))}'
                for row_id, values in sorted(pb.rows.items())
            ]
            body = ",\n".join(lines)
            header = f'"param": {json.dumps(name)},\n"fields": {json.dumps(pb.fields)}'
            (directory / "params" / f"{name}.json").write_text(
                "{\n" + header + ',\n"rows": {\n' + body + "\n}}\n", encoding="utf-8"
            )
        if self.text:
            (directory / "text").mkdir(exist_ok=True)
            data = {
                str(fmg_id): {"stem": stem, "entries": {str(k): v for k, v in sorted(entries.items())}}
                for fmg_id, (stem, entries) in sorted(self.text.items())
            }
            (directory / "text" / "item.json").write_text(
                json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )

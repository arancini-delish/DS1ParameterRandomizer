"""Writing on top of other mods: byte-level params, base resolution, stripping and sessions (docs/MOD_COMPAT.md)."""
import shutil
from collections import Counter
from pathlib import Path

import pytest

from ds1rand.alloc.store import ProtectedRowError, RowStore
from ds1rand.alloc.write import (
    apply_params, apply_text, base_path, read_marker, resolve_base, strip_params, strip_text, write_output,
)
from ds1rand.baseline.store import Baseline
from ds1rand.io.gameparam import GameParams, RawGameParam
from ds1rand.io.install import GameInstall
from ds1rand.io.msg import ItemText
from ds1rand.io.parambinary import DuplicateRowError, ParamBinary, _Row


@pytest.fixture(scope="module")
def vanilla_bytes(vanilla_gameparam) -> bytes:
    return vanilla_gameparam.read_bytes()


@pytest.fixture(scope="module")
def modded_base(vanilla_bytes) -> bytes:
    """Vanilla with a foreign edit and a repeated SpEffect ID, like the fog gate randomizer leaves."""
    raw = RawGameParam.from_bytes(vanilla_bytes)
    speffects = ParamBinary(raw.param_bytes("SpEffectParam"))
    speffects.rows.append(_Row(7240, speffects._row(1000).data, b""))
    speffects.rows.append(_Row(7240, speffects._row(1400).data, b""))
    raw.set_param_bytes("SpEffectParam", speffects.to_bytes())
    lots = ParamBinary(raw.param_bytes("ItemLotParam"))
    lots.set_values(1000000, {"lotItemNum01": 9})  # foreign change outside anything ds1rand edits
    raw.set_param_bytes("ItemLotParam", lots.to_bytes())
    return raw.to_bytes()


def rows_of(data: bytes, param: str) -> Counter:
    return Counter((row.id, row.data) for row in ParamBinary(RawGameParam.from_bytes(data).param_bytes(param)).rows)


def edited_store(base: bytes) -> RowStore:
    baseline = Baseline.from_game_files(GameParams.from_bytes(base), None, {})
    store = RowStore(baseline, {"SpEffectParam": {7240}})
    store.set("Bullet", 3000, {"life": 9.0})
    store.add("SpEffectParam", 9_000_000, copy_from=1000)
    store.set("SpEffectParam", 9_000_000, {"effectEndurance": 300.0})
    return store


def test_param_binary_keeps_duplicates_and_round_trips(vanilla_bytes):
    raw = RawGameParam.from_bytes(vanilla_bytes)
    for name in raw.names:
        binary = ParamBinary(raw.param_bytes(name))
        assert ParamBinary(binary.to_bytes()).rows == sorted(binary.rows, key=lambda r: r.id), name
    objects = ParamBinary(raw.param_bytes("ObjectParam"))
    assert objects.duplicate_ids == {4000, 4100, 4112, 9499, 9500, 9509}
    with pytest.raises(DuplicateRowError):
        objects.set_values(4000, {"hp": 1})


def test_apply_keeps_foreign_rows_and_duplicates(modded_base):
    out, record = apply_params(modded_base, edited_store(modded_base))
    assert record["Bullet"]["patched"]["3000"]["life"][1] == 9.0
    assert record["SpEffectParam"]["added"] == [9_000_000]
    result = RawGameParam.from_bytes(out)
    speffects = ParamBinary(result.param_bytes("SpEffectParam"))
    assert speffects.duplicate_ids == {7240}  # both copies survive
    assert speffects.values(9_000_000)["effectEndurance"] == 300.0
    assert ParamBinary(result.param_bytes("ItemLotParam")).values(1000000)["lotItemNum01"] == 9  # foreign edit kept


def test_protected_rows_cannot_be_edited(modded_base):
    store = edited_store(modded_base)
    with pytest.raises(ProtectedRowError):
        store.set("SpEffectParam", 7240, {"effectEndurance": 1.0})


def test_strip_restores_the_base(modded_base):
    out, record = apply_params(modded_base, edited_store(modded_base))
    stripped, conflicts = strip_params(out, record)
    assert conflicts == []
    for param in ("Bullet", "SpEffectParam", "ItemLotParam"):
        assert rows_of(stripped, param) == rows_of(modded_base, param), param


def test_strip_keeps_later_foreign_changes(modded_base):
    out, record = apply_params(modded_base, edited_store(modded_base))
    raw = RawGameParam.from_bytes(out)
    bullets = ParamBinary(raw.param_bytes("Bullet"))
    bullets.set_values(3000, {"life": 4.0})  # another mod re-ran on top of our output
    raw.set_param_bytes("Bullet", bullets.to_bytes())
    stripped, conflicts = strip_params(raw.to_bytes(), record)
    assert ParamBinary(RawGameParam.from_bytes(stripped).param_bytes("Bullet")).values(3000)["life"] == 4.0
    assert len(conflicts) == 1 and "Bullet[3000].life" in conflicts[0]


def test_resolve_base_states(modded_base, tmp_path):
    path = tmp_path / "GameParam.parambnd.dcx"
    path.write_bytes(modded_base)
    assert resolve_base(path, strip_params).state == "external"

    out, record = apply_params(modded_base, edited_store(modded_base))
    write_output(path, out, modded_base, record, {"seed": 1})
    assert read_marker(path)["seed"] == 1 and base_path(path).read_bytes() == modded_base
    rebuilt = resolve_base(path, strip_params)
    assert (rebuilt.state, rebuilt.data) == ("rebuilt", modded_base)

    # Another mod rewrites the file on top of our output: our edits are stripped, theirs kept.
    raw = RawGameParam.from_bytes(out)
    lots = ParamBinary(raw.param_bytes("ItemLotParam"))
    lots.set_values(1000000, {"lotItemNum01": 3})
    raw.set_param_bytes("ItemLotParam", lots.to_bytes())
    path.write_bytes(raw.to_bytes())
    stripped = resolve_base(path, strip_params)
    assert stripped.state == "stripped" and stripped.conflicts == []
    result = RawGameParam.from_bytes(stripped.data)
    assert ParamBinary(result.param_bytes("ItemLotParam")).values(1000000)["lotItemNum01"] == 3
    assert 9_000_000 not in ParamBinary(result.param_bytes("SpEffectParam"))
    assert rows_of(stripped.data, "Bullet") == rows_of(modded_base, "Bullet")


def test_text_apply_and_strip(install):
    base = install.item_msgbnd.read_bytes()
    out, record = apply_text(base, {("Magic_name", 3000): "Test Arrow", ("Magic_name", 999_999): "New"})
    assert ItemText.from_bytes(out).get("Magic_name", 3000) == "Test Arrow"
    stripped, conflicts = strip_text(out, record)
    original, restored = ItemText.from_bytes(base), ItemText.from_bytes(stripped)
    assert conflicts == []
    for fmg_id in original.fmg_ids:
        assert restored.fmg_entries(fmg_id) == original.fmg_entries(fmg_id)


class _RedirectedInstall(GameInstall):
    """The real install for events/maps/animations/AI, with GameParam and item text redirected to copies."""

    def __init__(self, root: Path, files: Path):
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "_files", files)

    @property
    def gameparam(self) -> Path:
        return self._files / "GameParam.parambnd.dcx"

    @property
    def item_msgbnd(self) -> Path:
        return self._files / "item.msgbnd.dcx"


def test_session_round_trip(install, modded_base, tmp_path):
    from ds1rand.session import Session

    redirected = _RedirectedInstall(install.root, tmp_path)
    redirected.gameparam.write_bytes(modded_base)
    shutil.copy(install.item_msgbnd, redirected.item_msgbnd)

    session = Session.open(redirected)
    assert session.gameparam_base.state == "external"
    assert session.store.protected["SpEffectParam"] >= {7240}
    assert any(d.name == "ItemLotParam" for d in session.foreign_changes()["params"])
    allocation = session.allocate(["player_spell"], params={"Magic", "Bullet", "AtkParam_Pc", "SpEffectParam"})
    new_bullet = allocation.row_for(next(n for n in allocation.groups if n.name == "Bullet" and n.id == 3000),
                                     "player_spell")
    session.store.set("Bullet", new_bullet, {"life": 2.5})
    session.text[("Magic_name", 3000)] = "Session Arrow"
    session.write({"seed": 7})

    again = Session.open(redirected)
    assert again.gameparam_base.state == "rebuilt" and again.gameparam_base.data == modded_base
    written = GameParams.from_path(redirected.gameparam)
    assert written.row_values("Magic", 3000)["refId"] == new_bullet
    assert written.row_values("Bullet", new_bullet)["life"] == 2.5
    assert ItemText.from_path(redirected.item_msgbnd).get("Magic_name", 3000) == "Session Arrow"
    assert rows_of(redirected.gameparam.read_bytes(), "ItemLotParam") == rows_of(modded_base, "ItemLotParam")

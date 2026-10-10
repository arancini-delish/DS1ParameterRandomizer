"""Co-op safety: the game files fingerprint, and runs leaving multiplayer items (vanilla and Seamless Co-op) alone."""
import random

from ds1rand.catalogue.budget import RESERVED_IDS, IdAllocator
from ds1rand.fingerprint import fingerprint
from ds1rand.graph.model import Node
from ds1rand.presets.schema import BUILTIN, Preset
from ds1rand.run import run

MULTIPLAYER_GOODS = (100, 101, 102, 103, 106, 108, 109, 111, 112, 113, 114, 115, 116, 117, 118)
SEAMLESS_COOP_GOODS = range(389000, 389009)


def _tree(root, files):
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def test_fingerprint_matches_identical_installs_only(tmp_path):
    files = {"param/GameParam/GameParam.parambnd.dcx": b"params", "msg/ENGLISH/item.msgbnd.dcx": b"text",
             "event/m10_00_00_00.emevd.dcx": b"events", "map/MapStudio/m10_00_00_00.msb": b"map"}
    _tree(tmp_path / "a", files)
    _tree(tmp_path / "b", files)
    a, b = fingerprint(tmp_path / "a"), fingerprint(tmp_path / "b")
    assert a == b and a.files == 4 and len(a.code) == 10
    # Backups and ds1rand companions are not loaded by the game: they do not count.
    _tree(tmp_path / "b", {"param/GameParam/GameParam.parambnd.dcx.bak": b"old",
                           "param/GameParam/GameParam.parambnd.dcx.ds1rand-base": b"base"})
    assert fingerprint(tmp_path / "b") == a
    _tree(tmp_path / "b", {"event/m10_00_00_00.emevd.dcx": b"other events"})
    c = fingerprint(tmp_path / "b")
    assert c.code != a.code and c.groups["events"] != a.groups["events"] and c.groups["params"] == a.groups["params"]


def test_seamless_coop_goods_ids_are_never_allocated(redirected_install):
    from ds1rand.session import Session

    session = Session.open(redirected_install)
    ids = IdAllocator(session.base)
    assert set(SEAMLESS_COOP_GOODS) <= set(RESERVED_IDS["EquipParamGoods"])
    allocated = {ids.allocate("EquipParamGoods") for _ in range(50)}
    assert not allocated & set(RESERVED_IDS["EquipParamGoods"])


def test_runs_leave_multiplayer_items_alone(redirected_install, tmp_path):
    preset = Preset.from_dict(BUILTIN["Misery"].to_dict())
    preset.seed = 3
    result = run(preset, redirected_install, out_dir=tmp_path / "out", log=lambda _: None, spoiler=False)
    session = result.session
    changes = session.store.changes()
    goods = changes.get("EquipParamGoods", {})
    assert not set(MULTIPLAYER_GOODS) & set(goods) and not set(SEAMLESS_COOP_GOODS) & set(goods)
    # Nothing the multiplayer items use (their SpEffects and anything beyond) changes either.
    for good in MULTIPLAYER_GOODS:
        if good not in session.base.params["EquipParamGoods"].rows:
            continue
        values = session.base.params["EquipParamGoods"].row_values(good)
        if values["refCategory"] == 2 and values["refId"] > 0:
            speffect = Node.param("SpEffectParam", values["refId"])
            for node in {speffect} | session.graph.reach(speffect):
                if node.kind == "param":
                    assert node.id not in changes.get(node.name, {}), (good, node)

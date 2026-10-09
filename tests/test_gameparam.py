import struct

import pytest

from ds1rand.io.gameparam import DuplicateRowsLostError, GameParams


@pytest.fixture
def params(vanilla_gameparam) -> GameParams:
    return GameParams.from_path(vanilla_gameparam)


def _row_dicts(param):
    return {row_id: row.to_dict(ignore_defaults=False, binary_fields_only=True) for row_id, row in param.items()}


def test_loads_all_params(params):
    assert len(params.names) == 41
    assert "Bullet" in params.names and "SpEffectParam" in params.names


def test_internal_field_names(params):
    bullet_id = next(iter(params["Bullet"].rows))
    values = params.row_values("Bullet", bullet_id)
    assert "atkId_Bullet" in values and "HitBulletID" in values
    assert values["atkId_Bullet"] == params.row("Bullet", bullet_id)["atkId_Bullet"]


def test_vanilla_duplicate_row_ids_are_recorded(params):
    assert params.duplicate_ids == {
        "default_AIStandardInfoBank": 2,
        "ObjectParam": 6,
        "SpEffectVfxParam": 1,
        "LockCamParam": 1,
    }


def test_soulstruct_round_trip_preserves_rows(params):
    """soulstruct output is not byte-identical to vanilla, but every row value must survive a write and re-read."""
    for name in params.names:
        param = params[name]
        reread = type(param).from_bytes(bytes(param))
        assert _row_dicts(reread) == _row_dicts(param), name


def test_unchanged_save_keeps_original_bytes(params, vanilla_gameparam, tmp_path):
    out = tmp_path / "GameParam.parambnd.dcx"
    assert params.save(out) == []
    original = {e.stem: bytes(e) for e in GameParams.from_path(vanilla_gameparam)._bnd.entries}
    saved = {e.stem: bytes(e) for e in GameParams.from_path(out)._bnd.entries}
    assert saved == original


def test_edit_only_reserializes_changed_param(params, vanilla_gameparam, tmp_path):
    bullet_id = next(row_id for row_id, row in params["Bullet"].items() if row["life"] > 0)
    params.row("Bullet", bullet_id)["life"] = 12.5
    out = tmp_path / "GameParam.parambnd.dcx"
    assert params.save(out) == ["Bullet"]

    vanilla = GameParams.from_path(vanilla_gameparam)
    saved = GameParams.from_path(out)
    assert saved.row("Bullet", bullet_id)["life"] == 12.5
    saved.row("Bullet", bullet_id)["life"] = vanilla.row("Bullet", bullet_id)["life"]
    assert _row_dicts(saved["Bullet"]) == _row_dicts(vanilla["Bullet"])
    for stem in vanilla.names:
        if stem != "Bullet":
            assert saved._original[stem] == vanilla._original[stem], stem


def test_editing_param_with_duplicates_refuses_to_save(params, tmp_path):
    object_id = next(iter(params["ObjectParam"].rows))
    params.row("ObjectParam", object_id)["hp"] += 1
    with pytest.raises(DuplicateRowsLostError):
        params.save(tmp_path / "GameParam.parambnd.dcx")


def test_add_row_copies_and_saves(params, tmp_path):
    source_id = next(iter(params["Bullet"].rows))
    new_id = params.next_free_id("Bullet", 900_000)
    params.add_row("Bullet", new_id, copy_from=source_id)
    with pytest.raises(KeyError):
        params.add_row("Bullet", new_id)
    out = tmp_path / "GameParam.parambnd.dcx"
    params.save(out)
    saved = GameParams.from_path(out)
    assert saved.row_values("Bullet", new_id) == params.row_values("Bullet", source_id)
    header_count = struct.unpack_from("<H", saved._original["Bullet"], 0x0A)[0]
    assert header_count == len(saved["Bullet"])

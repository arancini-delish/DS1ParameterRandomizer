from pathlib import Path

import pytest

from ds1rand.baseline.compare import (
    FileState,
    check_gameparam,
    diff_params,
    diff_text,
    restore_params,
    restore_text,
    write_marker,
)
from ds1rand.baseline.store import Baseline, sha256_file
from ds1rand.io.gameparam import GameParams
from ds1rand.io.msg import ItemText


@pytest.fixture(scope="module")
def baseline() -> Baseline:
    return Baseline.load()


def _vanilla_copy(path: Path, sha: str | None) -> Path:
    """`path` or its `.bak`, whichever matches the baseline source hash."""
    for candidate in (path, path.with_name(path.name + ".bak")):
        if sha and candidate.is_file() and sha256_file(candidate) == sha:
            return candidate
    pytest.skip(f"No copy of {path.name} matching the baseline hash")


@pytest.fixture(scope="module")
def vanilla_gameparam(install, baseline) -> Path:
    return _vanilla_copy(install.gameparam, baseline.manifest["sources"].get("GameParam.parambnd.dcx"))


@pytest.fixture(scope="module")
def vanilla_item_msgbnd(install, baseline) -> Path:
    if not baseline.text:
        pytest.skip("No text baseline")
    return _vanilla_copy(install.item_msgbnd, baseline.manifest["sources"].get("item.msgbnd.dcx"))


def test_baseline_shape(baseline):
    assert len(baseline.params) == 41
    assert baseline.duplicate_ids == {
        "default_AIStandardInfoBank": 2, "ObjectParam": 6, "SpEffectVfxParam": 1, "LockCamParam": 1,
    }
    bullet = baseline.params["Bullet"]
    assert "atkId_Bullet" in bullet.fields
    assert all(len(values) == len(bullet.fields) for values in bullet.rows.values())


def test_write_load_round_trip(baseline, tmp_path):
    baseline.write(tmp_path)
    reloaded = Baseline.load(tmp_path)
    assert reloaded.manifest == baseline.manifest
    assert {n: (p.fields, p.rows) for n, p in reloaded.params.items()} == {
        n: (p.fields, p.rows) for n, p in baseline.params.items()
    }
    assert reloaded.text == baseline.text


def test_vanilla_matches_baseline(vanilla_gameparam, baseline):
    _, report = check_gameparam(vanilla_gameparam, baseline)
    assert report.state is FileState.VANILLA and report.diffs == []


def test_diff_and_restore_params(vanilla_gameparam, baseline):
    params = GameParams.from_path(vanilla_gameparam)
    bullet_id, other_id = list(params["Bullet"].rows)[:2]
    params.row("Bullet", bullet_id)["life"] = 99.0
    params.remove_row("Bullet", other_id)
    params.add_row("Bullet", params.next_free_id("Bullet", 900_000))

    diffs = {d.name: d for d in diff_params(params, baseline)}
    assert list(diffs) == ["Bullet"]
    assert diffs["Bullet"].changed == {bullet_id: {"life": (baseline.params["Bullet"].row_values(bullet_id)["life"], 99.0)}}
    assert diffs["Bullet"].removed == [other_id] and diffs["Bullet"].added == [900_000]

    assert restore_params(params, baseline) == ["Bullet"]
    assert diff_params(params, baseline) == []


def test_restored_param_saves_and_reloads_as_vanilla(vanilla_gameparam, baseline, tmp_path):
    params = GameParams.from_path(vanilla_gameparam)
    weapon_id = next(iter(params["EquipParamWeapon"].rows))
    params.row("EquipParamWeapon", weapon_id)["weight"] = 0.1
    out = tmp_path / "GameParam.parambnd.dcx"
    params.save(out)

    edited, report = check_gameparam(out, baseline)
    assert report.state is FileState.MODIFIED
    restore_params(edited, baseline)
    edited.save(out)
    _, report = check_gameparam(out, baseline)
    assert report.state is FileState.VANILLA


def test_marker_identifies_our_output(vanilla_gameparam, baseline, tmp_path):
    params = GameParams.from_path(vanilla_gameparam)
    params.row("Bullet", next(iter(params["Bullet"].rows)))["life"] = 99.0
    out = tmp_path / "GameParam.parambnd.dcx"
    params.save(out)
    write_marker(out, {"seed": 1})
    assert check_gameparam(out, baseline)[1].state is FileState.OURS

    out.write_bytes(out.read_bytes() + b"\0")  # changed after we wrote it
    assert check_gameparam(out, baseline)[1].state is FileState.MODIFIED


def test_diff_and_restore_text(vanilla_item_msgbnd, baseline):
    text = ItemText.from_path(vanilla_item_msgbnd)
    assert diff_text(text, baseline) == []
    text.set("Accessory_name", 100, "Changed")
    assert {d.fmg_id for d in diff_text(text, baseline)} == {13, 113}
    assert sorted(restore_text(text, baseline)) == [13, 113]
    assert diff_text(text, baseline) == []

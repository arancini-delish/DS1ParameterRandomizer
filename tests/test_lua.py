import pytest

from ds1rand.io.lua import Call, Function, load_chunk, method_calls

# Opcodes and operand packing (Lua 5.0): OP bits 0-5, C 6-14, B 15-23, A 24-31, Bx 6-23.
LOADK, GETGLOBAL, SELF, CALL = 1, 5, 11, 25


def ins(op, a=0, b=0, c=0, bx=None):
    return op | (a << 24) | ((bx << 6) if bx is not None else (b << 15) | (c << 6))


def test_method_call_with_literal_arguments():
    # ai:HasSpecialEffectId(TARGET_SELF, 5401) with `ai` in register 0
    constants = ["HasSpecialEffectId", "TARGET_SELF", 5401.0]
    code = [
        ins(SELF, a=1, b=0, c=250 + 0),  # R1 = ai.HasSpecialEffectId, R2 = ai
        ins(GETGLOBAL, a=3, bx=1),  # R3 = TARGET_SELF
        ins(LOADK, a=4, bx=2),  # R4 = 5401
        ins(CALL, a=1, b=4, c=2),  # R1(R2, R3, R4)
    ]
    assert method_calls(Function(constants, code, [])) == [Call("HasSpecialEffectId", True, ("TARGET_SELF", 5401))]


def test_nested_functions_are_scanned():
    inner = Function(["GetRateItem", 5000.0], [ins(GETGLOBAL, a=0, bx=0), ins(LOADK, a=1, bx=1), ins(CALL, a=0, b=2, c=1)], [])
    assert method_calls(Function([], [], [inner])) == [Call("GetRateItem", False, (5000,))]


def test_rejects_other_formats():
    with pytest.raises(ValueError):
        load_chunk(b"\x1bLuaQ" + bytes(32))


def test_reads_dsr_ai_scripts(install):
    from soulstruct.containers import Binder

    binder = Binder.from_path(install.root / "script" / "m10_01_00_00.luabnd.dcx")
    chunks = [bytes(e) for e in binder.entries if bytes(e).startswith(b"\x1bLua")]
    assert chunks and all(load_chunk(c).code for c in chunks)
    assert any(c.name == "AddSubGoal" for chunk in chunks for c in method_calls(load_chunk(chunk)))

"""Minimal reader for the Lua 5.0 bytecode in DSR AI scripts (`script/*.luabnd.dcx`), for finding param IDs.

No decompiler is needed: the only question is which literal numbers are passed to which methods, e.g.
`ai:HasSpecialEffectId(TARGET_SELF, 5401)`. `method_calls` walks each function's instructions in order, tracking which
registers hold a method name (`SELF`), a global name (`GETGLOBAL`) or a constant (`LOADK`), and reports every `CALL`
whose function register holds a method or global name, with the constant/global value of each argument (None if not a
literal). Control flow is ignored; arguments are normally loaded just before the call, so this is reliable in practice.

Chunk format (DSR): header "\\x1bLua" 0x50, little-endian, int 4, size_t 8, instruction 4, op/A/B/C bits 6/8/9/9,
number 8 (double), then an 8-byte test number (22 bytes). Instruction fields: OP bits 0-5, C bits 6-14, B bits 15-23, A bits 24-31, Bx bits 6-23.
RK operands >= 250 index the constant table.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

SIGNATURE = b"\x1bLuaP"
RK_CONSTANT = 250

MOVE, LOADK, GETGLOBAL, SELF, CALL, TAILCALL, CLOSURE = 0, 1, 5, 11, 25, 26, 34
# Opcodes that do not write register A (or write it in a way covered separately).
_NO_WRITE = {7, 8, 9, 20, 21, 22, 23, 24, 27, 31, 32, 33}  # SETGLOBAL SETUPVAL SETTABLE JMP EQ LT LE TEST RETURN SETLIST(O) CLOSE


@dataclass(frozen=True, slots=True)
class Call:
    name: str  # method or global function name
    is_method: bool
    args: tuple[int | float | str | None, ...]  # literal argument values (method calls exclude `self`)


@dataclass
class Function:
    constants: list
    code: list[int]
    protos: list[Function]

    def walk(self):
        yield self
        for proto in self.protos:
            yield from proto.walk()


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def unpack(self, fmt: str):
        values = struct.unpack_from("<" + fmt, self.data, self.pos)
        self.pos += struct.calcsize("<" + fmt)
        return values if len(values) > 1 else values[0]

    def string(self) -> str | None:
        size = self.unpack("Q")
        if size == 0:
            return None
        raw = self.data[self.pos:self.pos + size - 1]
        self.pos += size
        return raw.decode("shift_jis_2004", errors="replace")

    def function(self) -> Function:
        self.string()  # source
        self.unpack("i")  # line defined
        self.unpack("4B")  # nups, numparams, is_vararg, maxstacksize
        line_count = self.unpack("i")
        self.pos += 4 * line_count  # line info
        for _ in range(self.unpack("i")):  # local variables
            self.string()
            self.unpack("ii")
        for _ in range(self.unpack("i")):  # upvalue names
            self.string()
        constants = []
        for _ in range(self.unpack("i")):
            kind = self.unpack("B")
            if kind == 3:
                constants.append(self.unpack("d"))
            elif kind == 4:
                constants.append(self.string())
            elif kind == 0:
                constants.append(None)
            else:
                raise ValueError(f"Unknown Lua constant type {kind}")
        protos = [self.function() for _ in range(self.unpack("i"))]
        code_count = self.unpack("i")
        code = list(struct.unpack_from(f"<{code_count}I", self.data, self.pos))
        self.pos += 4 * code_count
        return Function(constants, code, protos)


def load_chunk(data: bytes) -> Function:
    if not data.startswith(SIGNATURE):
        raise ValueError("Not a Lua 5.0 chunk")
    reader = _Reader(data)
    reader.pos = 14 + 8  # header bytes, then the 8-byte test number
    return reader.function()


def _number(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def method_calls(function: Function) -> list[Call]:
    """Calls with literal arguments in `function` and every nested function."""
    calls = []
    for fn in function.walk():
        k = fn.constants
        regs: dict[int, tuple[str, object]] = {}  # register -> ("k" | "method" | "global", value)

        def rk(x):
            return ("k", _number(k[x - RK_CONSTANT])) if x >= RK_CONSTANT else regs.get(x)

        for ins in fn.code:
            op, c, b, a, bx = ins & 0x3F, (ins >> 6) & 0x1FF, (ins >> 15) & 0x1FF, ins >> 24, (ins >> 6) & 0x3FFFF
            if op == LOADK:
                regs[a] = ("k", _number(k[bx]))
            elif op == GETGLOBAL:
                regs[a] = ("global", k[bx])
            elif op == MOVE:
                if b in regs:
                    regs[a] = regs[b]
                else:
                    regs.pop(a, None)
            elif op == SELF:
                key = rk(c)
                regs[a + 1] = ("self", None)
                if key and key[0] == "k":
                    regs[a] = ("method", key[1])
                else:
                    regs.pop(a, None)
            elif op in (CALL, TAILCALL):
                fn_reg = regs.get(a)
                if fn_reg and fn_reg[0] in ("method", "global") and isinstance(fn_reg[1], str):
                    is_method = fn_reg[0] == "method"
                    first = a + 2 if is_method else a + 1
                    last = a + b - 1 if b else max([r for r in regs if r >= first], default=first - 1)
                    args = tuple(
                        regs[r][1] if r in regs and regs[r][0] in ("k", "global") else None
                        for r in range(first, last + 1)
                    )
                    calls.append(Call(fn_reg[1], is_method, args))
                for r in [r for r in regs if r >= a]:
                    del regs[r]
            elif op not in _NO_WRITE:
                regs.pop(a, None)
    return calls

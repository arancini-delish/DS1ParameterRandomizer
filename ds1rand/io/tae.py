"""Minimal reader for Dark Souls: Remastered TAE (animation event) files, version 0x1000B.

soulstruct only reads version 0x1000C (later games). DSR keeps the PTDE layout: little-endian, 32-bit offsets.
Only what the reference graph needs is read: each animation's ID and, per event, its type, start/end time and the
first `PARAM_WORDS` 32-bit words of its parameters (event parameter layouts vary by type; callers interpret them).

Layout (offsets from file start):
    0x00  "TAE "        0x08  u32 version (0x1000B)     0x0C  u32 file size
    0x50  u32 TAE ID    0x54  u32 animation count       0x58  u32 animation table offset
Animation table: (u32 animation ID, u32 animation offset) per animation. At the animation offset:
    u32 event count, u32 event headers offset, u32 group count, u32 groups offset, u32 time count, u32 times offset,
    u32 animation file offset
Event header (12 bytes): u32 start time offset, u32 end time offset, u32 event data offset (times are f32).
Event data: u32 type, u32 parameters offset, then the parameters.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

VERSION = 0x1000B
PARAM_WORDS = 4


@dataclass(frozen=True, slots=True)
class TAEEvent:
    type: int
    start: float
    end: float
    params: tuple[int, ...]  # first PARAM_WORDS words as signed 32-bit ints (fewer at the end of the file)

    def param_floats(self) -> tuple[float, ...]:
        return struct.unpack(f"<{len(self.params)}f", struct.pack(f"<{len(self.params)}i", *self.params))


@dataclass(frozen=True, slots=True)
class TAEAnimation:
    id: int
    events: tuple[TAEEvent, ...]


@dataclass(frozen=True, slots=True)
class TAE:
    id: int
    animations: tuple[TAEAnimation, ...]

    @classmethod
    def from_bytes(cls, data: bytes) -> TAE:
        if data[:4] != b"TAE ":
            raise ValueError("Not a TAE file")
        version = struct.unpack_from("<I", data, 0x08)[0]
        if version != VERSION:
            raise ValueError(f"Unsupported TAE version {version:#x}, expected {VERSION:#x}")
        tae_id, animation_count, table_offset = struct.unpack_from("<III", data, 0x50)
        animations = []
        for i in range(animation_count):
            animation_id, animation_offset = struct.unpack_from("<II", data, table_offset + 8 * i)
            event_count, headers_offset = struct.unpack_from("<II", data, animation_offset)
            events = []
            for j in range(event_count):
                start_offset, end_offset, data_offset = struct.unpack_from("<3I", data, headers_offset + 12 * j)
                event_type, params_offset = struct.unpack_from("<II", data, data_offset)
                words = min(PARAM_WORDS, (len(data) - params_offset) // 4)
                events.append(TAEEvent(
                    type=event_type,
                    start=struct.unpack_from("<f", data, start_offset)[0],
                    end=struct.unpack_from("<f", data, end_offset)[0],
                    params=struct.unpack_from(f"<{words}i", data, params_offset),
                ))
            animations.append(TAEAnimation(animation_id, tuple(events)))
        return cls(tae_id, tuple(animations))

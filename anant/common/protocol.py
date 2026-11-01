"""ANANT-Link: framed binary protocol between the Jetson (brain) and the Pi (body).

Frame layout (little-endian):

    +------+------+------+-----+-----+---------+---------+
    | 0xAA | 0x55 | type | seq | len | payload | crc16   |
    +------+------+------+-----+-----+---------+---------+
      2 B                 1 B   1 B   1 B       len B     2 B

CRC-16/CCITT-FALSE covers type..payload. The parser is a resynchronising state
machine, so a corrupt or truncated frame costs at most one frame, never the link.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Tuple

SOF = b"\xAA\x55"
MAX_PAYLOAD = 255
ENTRY_SIZE = 3  # (id:u8, value:u16)
MAX_ENTRIES = MAX_PAYLOAD // ENTRY_SIZE


class MsgType(IntEnum):
    # Jetson -> Pi
    HEARTBEAT = 0x01
    JOINTS = 0x10
    EXPRESSION = 0x11
    ESTOP_CLEAR = 0x1E
    ESTOP = 0x1F
    # Pi -> Jetson
    TOUCH = 0x81
    STATUS = 0x82


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Frame:
    msg_type: int
    seq: int
    payload: bytes


def encode(msg_type: int, payload: bytes = b"", seq: int = 0) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    body = struct.pack("<BBB", int(msg_type), seq & 0xFF, len(payload)) + payload
    return SOF + body + struct.pack("<H", crc16_ccitt(body))


class FrameParser:
    """Incremental parser: feed() raw bytes, get back complete valid frames."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0

    def feed(self, data: bytes) -> List[Frame]:
        self._buf.extend(data)
        frames: List[Frame] = []
        while True:
            i = self._buf.find(SOF)
            if i < 0:
                if self._buf and self._buf[-1] == SOF[0]:
                    del self._buf[:-1]
                else:
                    self._buf.clear()
                break
            if i > 0:
                del self._buf[:i]
            if len(self._buf) < 5:
                break
            length = self._buf[4]
            total = 2 + 3 + length + 2
            if len(self._buf) < total:
                break
            body = bytes(self._buf[2:5 + length])
            (crc,) = struct.unpack("<H", bytes(self._buf[5 + length:total]))
            if crc == crc16_ccitt(body):
                frames.append(Frame(body[0], body[1], body[3:]))
                del self._buf[:total]
            else:
                self.crc_errors += 1
                del self._buf[:1]  # resync on next SOF
        return frames


# ---- payload helpers -------------------------------------------------------

def pack_joints(angles: Dict[int, float]) -> bytes:
    """{joint_id: degrees} -> payload. Angles are sent as deci-degrees (u16)."""
    if len(angles) > MAX_ENTRIES:
        raise ValueError("too many joints for one frame")
    out = bytearray()
    for jid, deg in angles.items():
        out += struct.pack("<BH", jid, max(0, min(65535, int(round(deg * 10)))))
    return bytes(out)


def unpack_joints(payload: bytes) -> Dict[int, float]:
    return {jid: v / 10.0 for jid, v in struct.iter_unpack("<BH", payload[: len(payload) // 3 * 3])}


def pack_touch(events: List[Tuple[int, int]]) -> bytes:
    """[(zone_id, pressure 0..4095)] -> payload. pressure 0 means released."""
    if len(events) > MAX_ENTRIES:
        raise ValueError("too many touch events for one frame")
    return b"".join(struct.pack("<BH", z, max(0, min(4095, int(p)))) for z, p in events)


def unpack_touch(payload: bytes) -> List[Tuple[int, int]]:
    return list(struct.iter_unpack("<BH", payload[: len(payload) // 3 * 3]))


def pack_expression(expr_id: int, transition_ms: int = 300) -> bytes:
    return struct.pack("<BH", expr_id, max(0, min(65535, transition_ms)))


def unpack_expression(payload: bytes) -> Tuple[int, int]:
    return struct.unpack("<BH", payload[:3])


STATUS_ESTOP = 0x01
STATUS_WATCHDOG = 0x02


def pack_status(uptime_ms: int, flags: int, crc_errors: int) -> bytes:
    return struct.pack("<IBH", uptime_ms & 0xFFFFFFFF, flags, min(crc_errors, 65535))


def unpack_status(payload: bytes) -> Dict[str, int]:
    up, flags, errs = struct.unpack("<IBH", payload[:7])
    return {"uptime_ms": up, "estop": bool(flags & STATUS_ESTOP),
            "watchdog": bool(flags & STATUS_WATCHDOG), "crc_errors": errs}

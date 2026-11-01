"""Jetson-side client of the ANANT-Link: commands out, touch telemetry in."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple, Union

from anant.common import protocol as P
from anant.common.config import load_expressions, load_joints

log = logging.getLogger("anant.bridge")
TouchCb = Callable[[List[Tuple[int, int]]], None]


class Bridge:
    def __init__(self, transport, heartbeat_hz: float = 10.0) -> None:
        self.t = transport
        self.joints = {j["name"]: j for j in load_joints()["joints"]}
        self.expr = load_expressions()
        self.status: Dict[str, int] = {}
        self._parser = P.FrameParser()
        self._wlock = threading.Lock()
        self._seq = 0
        self._touch_cb: Optional[TouchCb] = None
        self._run = False
        self._hb_period = 1.0 / heartbeat_hz

    def on_touch(self, cb: TouchCb) -> None:
        self._touch_cb = cb

    def start(self) -> None:
        self._run = True
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def stop(self) -> None:
        self._run = False

    # -- tx ---------------------------------------------------------------
    def _send(self, mtype: int, payload: bytes = b"") -> None:
        with self._wlock:
            self._seq = (self._seq + 1) & 0xFF
            self.t.write(P.encode(mtype, payload, self._seq))

    def _id(self, key: Union[int, str]) -> int:
        return key if isinstance(key, int) else self.joints[key]["id"]

    def send_joints(self, angles: Dict[Union[int, str], float]) -> None:
        by_id = {self._id(k): v for k, v in angles.items()}
        items = list(by_id.items())
        for i in range(0, len(items), P.MAX_ENTRIES):
            self._send(P.MsgType.JOINTS, P.pack_joints(dict(items[i:i + P.MAX_ENTRIES])))

    def set_normalized(self, name: str, v: float) -> None:
        """Move a joint to v in [0,1] across its calibrated range."""
        j = self.joints[name]
        self.send_joints({name: j["min"] + max(0.0, min(1.0, v)) * (j["max"] - j["min"])})

    def go_home(self, *names: str) -> None:
        self.send_joints({n: self.joints[n]["home"] for n in names})

    def set_expression(self, name: str, ms: int = 300) -> None:
        e = self.expr["by_name"].get(name) or self.expr["by_name"]["neutral"]
        self._send(P.MsgType.EXPRESSION, P.pack_expression(e["id"], ms))

    def estop(self) -> None:
        self._send(P.MsgType.ESTOP)

    def clear_estop(self) -> None:
        self._send(P.MsgType.ESTOP_CLEAR)

    # -- threads ----------------------------------------------------------
    def _heartbeat(self) -> None:
        while self._run:
            self._send(P.MsgType.HEARTBEAT)
            time.sleep(self._hb_period)

    def _reader(self) -> None:
        while self._run:
            for fr in self._parser.feed(self.t.read(512)):
                if fr.msg_type == P.MsgType.TOUCH and self._touch_cb:
                    try:
                        self._touch_cb(P.unpack_touch(fr.payload))
                    except Exception:
                        log.exception("touch callback failed")
                elif fr.msg_type == P.MsgType.STATUS:
                    self.status = P.unpack_status(fr.payload)

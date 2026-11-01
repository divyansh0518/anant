"""WebSocket server that receives Meta Quest 3 tracking frames and drives the robot."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import threading
import time
from typing import Optional

from anant.common.config import load_joints, load_system
from anant.xr.retarget import Retargeter

log = logging.getLogger("anant.xr")


class XRServer:
    MAX_HZ = 30.0

    def __init__(self, bridge, host: str = "0.0.0.0", port: int = 8765) -> None:
        self.bridge, self.host, self.port = bridge, host, port
        self.rt = Retargeter({j["name"]: j for j in load_joints()["joints"]})
        self.last_active = 0.0
        self._last_send = 0.0

    @property
    def active(self) -> bool:
        return time.monotonic() - self.last_active < 0.5

    async def _handler(self, ws, path=None) -> None:
        log.info("Quest connected")
        try:
            async for msg in ws:
                try:
                    frame = json.loads(msg)
                except ValueError:
                    continue
                now = time.monotonic()
                if now - self._last_send < 1.0 / self.MAX_HZ:
                    continue
                cmds = self.rt.update(frame)
                if cmds:                       # deadman held and tracking valid
                    self._last_send = self.last_active = now
                    self.bridge.send_joints(cmds)
        finally:
            log.info("Quest disconnected -> arms hold position")

    async def serve(self) -> None:
        import websockets
        async with websockets.serve(self._handler, self.host, self.port):
            log.info("XR teleoperation listening on ws://%s:%d", self.host, self.port)
            await asyncio.Future()

    def start_in_thread(self) -> None:
        threading.Thread(target=lambda: asyncio.run(self.serve()), daemon=True).start()


def main() -> None:
    from anant.common.transport import make_transport
    from anant.jetson.bridge import Bridge
    ap = argparse.ArgumentParser(description="Standalone XR teleoperation server")
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--port")
    ap.add_argument("--ws-port", type=int, default=8765)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    cfg = load_system()
    bridge = Bridge(make_transport(cfg["link"], "jetson", sim=args.sim, port=args.port))
    bridge.start()
    asyncio.run(XRServer(bridge, cfg["xr"]["host"], args.ws_port).serve())


if __name__ == "__main__":
    main()

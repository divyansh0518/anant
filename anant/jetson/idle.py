"""Life-like idle behaviour: blinking and small eye saccades."""
from __future__ import annotations

import random
import threading
import time


class IdleBehavior:
    def __init__(self, bridge) -> None:
        self.b = bridge
        self.enabled = True
        self._run = False

    def start(self) -> None:
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._run = False

    def _blink(self) -> None:
        j = self.b.joints
        self.b.send_joints({"eyelid_l": j["eyelid_l"]["min"], "eyelid_r": j["eyelid_r"]["min"]})
        time.sleep(0.14)
        self.b.go_home("eyelid_l", "eyelid_r")

    def _loop(self) -> None:
        next_blink = time.monotonic() + random.uniform(2, 5)
        next_sacc = time.monotonic() + random.uniform(1, 3)
        while self._run:
            now = time.monotonic()
            if self.enabled and now >= next_blink:
                self._blink()
                next_blink = now + random.uniform(2.5, 6)
            if self.enabled and now >= next_sacc:
                j = self.b.joints
                self.b.send_joints({"eye_yaw": j["eye_yaw"]["home"] + random.uniform(-6, 6),
                                    "eye_pitch": j["eye_pitch"]["home"] + random.uniform(-3, 3)})
                next_sacc = now + random.uniform(1, 3.5)
            time.sleep(0.05)

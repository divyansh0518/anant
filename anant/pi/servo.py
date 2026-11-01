"""Servo bank: slew-rate-limited control of 30+ servos over PCA9685 boards."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

log = logging.getLogger("anant.pi.servo")


@dataclass
class Joint:
    id: int
    name: str
    board: int
    channel: int
    min: float
    max: float
    home: float
    speed: float                    # max deg/s
    current: float = 0.0
    target: float = 0.0
    speed_now: float = field(default=0.0)
    last_written: Optional[float] = None


class ServoBank:
    def __init__(self, joints_cfg: dict, sim: bool = False) -> None:
        default_speed = joints_cfg.get("default_speed_dps", 120)
        self.joints: Dict[int, Joint] = {}
        for j in joints_cfg["joints"]:
            self.joints[j["id"]] = Joint(
                id=j["id"], name=j["name"], board=j["board"], channel=j["channel"],
                min=j["min"], max=j["max"], home=j["home"], speed=j.get("speed", default_speed),
                current=j["home"], target=j["home"], speed_now=j.get("speed", default_speed))
        self.by_name = {j.name: j for j in self.joints.values()}
        self.sim = sim
        self.frozen = False
        self._kits = {}
        if not sim:
            from adafruit_servokit import ServoKit
            for idx, addr in enumerate(joints_cfg["pca9685_addresses"]):
                self._kits[idx] = ServoKit(channels=16, address=addr)
        for j in self.joints.values():
            self._write(j, force=True)

    # -- targets ----------------------------------------------------------
    def clamp(self, j: Joint, deg: float) -> float:
        return max(j.min, min(j.max, deg))

    def set_target(self, jid: int, deg: float, duration: Optional[float] = None) -> None:
        j = self.joints.get(jid)
        if j is None or self.frozen:
            return
        j.target = self.clamp(j, deg)
        if duration:
            j.speed_now = min(j.speed, abs(j.target - j.current) / max(duration, 0.05))
        else:
            j.speed_now = j.speed

    def set_targets(self, targets: Dict[int, float], duration: Optional[float] = None) -> None:
        for jid, deg in targets.items():
            self.set_target(jid, deg, duration)

    def set_named(self, targets: Dict[str, float], duration: Optional[float] = None) -> None:
        for name, deg in targets.items():
            j = self.by_name.get(name)
            if j:
                self.set_target(j.id, deg, duration)

    # -- safety -----------------------------------------------------------
    def hold(self) -> None:
        """Stop all motion where it is (does not cut torque, so arms don't drop)."""
        for j in self.joints.values():
            j.target = j.current

    def freeze(self) -> None:
        self.hold()
        self.frozen = True

    def unfreeze(self) -> None:
        self.frozen = False

    def release(self) -> None:
        """Cut PWM to every servo (limp). Use only with the robot supported."""
        for j in self.joints.values():
            if not self.sim:
                self._kits[j.board].servo[j.channel].angle = None

    # -- control loop -----------------------------------------------------
    def update(self, dt: float) -> None:
        for j in self.joints.values():
            err = j.target - j.current
            if abs(err) > 1e-3:
                step = j.speed_now * dt
                j.current = j.target if abs(err) <= step else j.current + (step if err > 0 else -step)
                self._write(j)

    def _write(self, j: Joint, force: bool = False) -> None:
        if not force and j.last_written is not None and abs(j.current - j.last_written) < 0.1:
            return
        j.last_written = j.current
        if not self.sim:
            self._kits[j.board].servo[j.channel].angle = j.current

"""Human-to-robot motion retargeting for Meta Quest 3 hand tracking.

Input frames are expressed in a *body frame* (origin at the operator's head, yaw-aligned,
x right / y up / z forward, metres), so looking around never moves the arms.

Arm: the wrist position is scaled to the robot's reach and solved with a closed-form
two-link IK (law of cosines) -> shoulder pitch/roll + elbow flexion. Shoulder yaw is
held at home (a 7-DoF solver is future work). Wrist roll comes from palm orientation,
fingers from per-finger curl, and the neck follows head yaw/pitch/roll.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

FINGERS = ["thumb", "index", "middle", "ring", "pinky"]


@dataclass
class ArmGeometry:
    robot_upper: float = 0.30
    robot_fore: float = 0.28
    human_reach: float = 0.60                                  # operator shoulder-to-wrist reach (m)
    shoulder_offset: Tuple[float, float, float] = (0.18, -0.20, 0.0)   # right shoulder in body frame; x mirrored for left


def quat_rotate(q: List[float], v: List[float]) -> np.ndarray:
    """Rotate vector v by unit quaternion q = [x, y, z, w]."""
    x, y, z, w = q
    u = np.array([x, y, z])
    v = np.asarray(v, float)
    return 2 * u.dot(v) * u + (w * w - u.dot(u)) * v + 2 * w * np.cross(u, v)


def solve_arm(wrist: List[float], side: int, g: ArmGeometry) -> Tuple[float, float, float]:
    """Returns (shoulder_pitch, shoulder_roll, elbow_flexion) in degrees. side: +1 right, -1 left."""
    sh = np.array([g.shoulder_offset[0] * side, g.shoulder_offset[1], g.shoulder_offset[2]])
    v = (np.asarray(wrist, float) - sh) * (g.robot_upper + g.robot_fore) / g.human_reach
    d = float(np.linalg.norm(v))
    reach = g.robot_upper + g.robot_fore
    d = max(0.08, min(reach - 1e-3, d))
    u = v / max(np.linalg.norm(v), 1e-6)

    # elbow flexion: 0 deg = straight arm
    cos_e = (g.robot_upper ** 2 + g.robot_fore ** 2 - d ** 2) / (2 * g.robot_upper * g.robot_fore)
    elbow = 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, cos_e))))

    # angle between shoulder->wrist line and the upper arm
    cos_a = (g.robot_upper ** 2 + d ** 2 - g.robot_fore ** 2) / (2 * g.robot_upper * d)
    alpha = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))

    line_pitch = math.degrees(math.atan2(u[2], -u[1]))          # 0 = hanging down, +90 = forward
    pitch = line_pitch - alpha                                    # elbow sits below the line (sagittal plane)
    roll = math.degrees(math.asin(max(-1.0, min(1.0, u[0] * side))))  # outward abduction
    return pitch, max(0.0, roll), elbow


def wrist_roll(q: List[float]) -> float:
    n = quat_rotate(q, [0.0, 1.0, 0.0])                           # palm normal
    return math.degrees(math.atan2(n[0], n[1]))


class Retargeter:
    def __init__(self, joints: Dict[str, dict], geometry: Optional[ArmGeometry] = None, smoothing: float = 0.35) -> None:
        self.j = joints
        self.g = geometry or ArmGeometry()
        self.alpha = smoothing
        self._prev: Dict[str, float] = {}

    def _servo(self, name: str, delta_deg: float) -> float:
        j = self.j[name]
        return max(j["min"], min(j["max"], j["home"] + j.get("sign", 1) * delta_deg))

    def _lerp(self, name: str, t: float) -> float:
        j = self.j[name]
        return j["min"] + max(0.0, min(1.0, t)) * (j["max"] - j["min"])

    def _smooth(self, out: Dict[str, float]) -> Dict[str, float]:
        for k, v in out.items():
            p = self._prev.get(k, v)
            out[k] = p + self.alpha * (v - p)
            self._prev[k] = out[k]
        return out

    def update(self, frame: dict) -> Dict[str, float]:
        """Returns {joint_name: servo_deg}. Empty when the deadman is released or tracking is lost."""
        if not frame.get("enable"):
            self._prev.clear()
            return {}
        out: Dict[str, float] = {}
        head = frame.get("head")
        if head:
            yaw, pitch, roll = head
            out["neck_yaw"] = self._servo("neck_yaw", yaw)
            out["neck_pitch"] = self._servo("neck_pitch", pitch)
            out["neck_roll"] = self._servo("neck_roll", roll)
        for side_name, side, pre in (("right", 1, "r_"), ("left", -1, "l_")):
            hand = frame.get(side_name)
            if not hand or not hand.get("tracked"):
                continue
            pitch, rollab, elbow = solve_arm(hand["p"], side, self.g)
            out[pre + "shoulder_pitch"] = self._servo(pre + "shoulder_pitch", pitch)
            out[pre + "shoulder_roll"] = self._servo(pre + "shoulder_roll", rollab)
            out[pre + "elbow"] = self._servo(pre + "elbow", elbow)
            out[pre + "wrist_roll"] = self._servo(pre + "wrist_roll", wrist_roll(hand["q"]) * side)
            for finger, curl in zip(FINGERS, hand.get("curls", [])):
                out[pre + finger] = self._lerp(pre + finger, curl)
        return self._smooth(out)

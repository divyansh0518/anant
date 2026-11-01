import math

from anant.common.config import load_joints, load_expressions
from anant.pi.servo import ServoBank
from anant.xr.retarget import ArmGeometry, Retargeter, solve_arm


def test_config_consistency():
    cfg = load_joints()
    ids = [j["id"] for j in cfg["joints"]]
    assert len(ids) == len(set(ids)) >= 30
    for j in cfg["joints"]:
        assert j["id"] == j["board"] * 16 + j["channel"]
        assert j["min"] <= j["home"] <= j["max"]
    names = {j["name"] for j in cfg["joints"]}
    for e in load_expressions()["by_name"].values():
        assert set(e["joints"]) <= names


def test_servo_slew_limit_and_clamp():
    bank = ServoBank(load_joints(), sim=True)
    j = bank.by_name["r_elbow"]
    bank.set_target(j.id, 500)                       # clamped to max
    assert j.target == j.max
    bank.update(0.1)
    assert math.isclose(j.current, j.home + j.speed * 0.1, rel_tol=1e-6)
    bank.freeze()
    bank.set_target(j.id, 10)                        # ignored while frozen
    assert j.target == j.current


def test_arm_ik_straight_down_and_forward():
    g = ArmGeometry()
    reach = (g.robot_upper + g.robot_fore) * 0.99
    # arm hanging straight down: pitch ~0, elbow ~straight
    down = [g.shoulder_offset[0], g.shoulder_offset[1] - reach * g.human_reach / (g.robot_upper + g.robot_fore), 0]
    pitch, roll, elbow = solve_arm(down, +1, g)
    assert abs(pitch) < 15 and elbow < 30
    # arm straight forward at shoulder height: pitch ~90
    fwd = [g.shoulder_offset[0], g.shoulder_offset[1], 0.58]
    pitch, roll, elbow = solve_arm(fwd, +1, g)
    assert 70 < pitch < 110


def test_deadman_blocks_commands():
    rt = Retargeter({j["name"]: j for j in load_joints()["joints"]})
    frame = {"enable": False, "head": [0, 0, 0], "right": {"tracked": True, "p": [0.2, -0.1, 0.4], "q": [0, 0, 0, 1], "curls": [0] * 5}}
    assert rt.update(frame) == {}
    frame["enable"] = True
    out = rt.update(frame)
    assert "r_elbow" in out and "neck_yaw" in out and "l_elbow" not in out

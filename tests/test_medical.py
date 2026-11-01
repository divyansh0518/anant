from pathlib import Path

from anant.common.config import config_dir
from anant.jetson.medical import DEEP_PRESSURE, ScenarioEngine


def make(tmp_path):
    said = []
    eng = ScenarioEngine(config_dir() / "scenarios", lambda t, e: said.append((t, e)),
                         session_dir=str(tmp_path), hud=lambda s: said.append(("HUD", s)))
    return eng, said


def test_scenarios_load_and_match():
    eng, _ = make(Path("/tmp"))
    assert {"acute_appendicitis", "aortic_stenosis", "situs_inversus_totalis"} <= set(eng.scenarios)
    assert eng.find("please load scenario appendicitis") == "acute_appendicitis"


def test_palpation_rebound_and_session_log(tmp_path):
    eng, said = make(tmp_path)
    eng.start("acute_appendicitis")
    eng.handle_touch("abd_rlq", DEEP_PRESSURE + 100)
    assert said[-1][1] == "pain"
    eng.handle_touch("abd_rlq", 0)                     # release after deep press -> rebound
    assert "let go" in said[-1][0]
    eng.handle_touch("abd_ruq", 2000)                  # non-tender zone: silent
    n = len(said)
    eng.handle_touch("abd_ruq", 2000)
    assert len(said) == n
    path = eng.end()
    assert path.exists() and "rebound_tenderness" in path.read_text()


def test_auscultation_mode(tmp_path):
    eng, said = make(tmp_path)
    eng.start("situs_inversus_totalis")
    eng.set_auscultation(True)
    eng.handle_touch("chest_r5ics", 900)
    assert "RIGHT" in said[-1][1]

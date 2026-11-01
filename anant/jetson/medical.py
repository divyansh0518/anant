"""Medical training mode: scenario-driven simulated patient with touch-aware examination."""
from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("anant.medical")

LIGHT_PRESSURE = 500   # palpation registers
DEEP_PRESSURE = 1800   # deep palpation / rebound candidate

SayFn = Callable[[str, str], None]  # (text, expression)


class ScenarioEngine:
    def __init__(self, scenarios_dir: Path, say: SayFn, projector=None, session_dir: str = "data/sessions",
                 sounds_dir: str = "assets/sounds", hud: Callable[[str], None] = print) -> None:
        self.scenarios: Dict[str, dict] = {}
        for p in sorted(Path(scenarios_dir).glob("*.json")):
            sc = json.loads(p.read_text(encoding="utf-8"))
            self.scenarios[sc["id"]] = sc
        self.say, self.projector, self.hud = say, projector, hud
        self.session_dir, self.sounds_dir = Path(session_dir), Path(sounds_dir)
        self.active: Optional[dict] = None
        self.auscultation = False
        self.log: List[dict] = []
        self._peak: Dict[str, int] = {}
        self._cool: Dict[str, float] = {}
        self._t0 = 0.0

    # -- scenario lifecycle ----------------------------------------------
    def find(self, text: str) -> Optional[str]:
        text = text.lower()
        for sid, sc in self.scenarios.items():
            words = [w for w in sid.split("_") if len(w) > 3]
            if sid.replace("_", " ") in text or any(w in text for w in words):
                return sid
        return None

    def start(self, sid: str) -> dict:
        self.active, self.auscultation = self.scenarios[sid], False
        self.log, self._peak, self._cool, self._t0 = [], {}, {}, time.monotonic()
        self._event("session_start", scenario=sid)
        if self.projector:
            self.projector.clear()
        return self.active

    def end(self) -> Optional[Path]:
        if not self.active:
            return None
        self._event("session_end")
        out = None
        self.session_dir.mkdir(parents=True, exist_ok=True)
        out = self.session_dir / f"{self.active['id']}_{int(time.time())}.json"
        out.write_text(json.dumps({"scenario": self.active["id"], "events": self.log,
                                   "teaching_points": self.active.get("teaching_points", [])}, indent=2))
        if self.projector:
            self.projector.clear()
        self.active = None
        return out

    def _event(self, kind: str, **kw) -> None:
        self.log.append({"t": round(time.monotonic() - self._t0, 2), "event": kind, **kw})

    # -- examiner interactions -------------------------------------------
    def patient_prompt(self) -> str:
        p = self.active["patient"]
        return (f"You are role-playing a simulated patient for medical students. You are {p['name']}, "
                f"{p['age']}-year-old {p['sex']}. Presenting complaint: {p['chief_complaint']} "
                f"Background (reveal only when asked directly): {p['history']} "
                "Rules: never state or hint the diagnosis, use lay language, answer only what is asked, "
                "at most two short sentences. Begin every reply with one tag from "
                "[neutral] [sad] [pain] [surprised] [thinking] reflecting how you feel.")

    def log_student(self, text: str) -> None:
        self._event("student_said", text=text)

    def vitals_text(self) -> str:
        v = self.active["vitals"]
        return ", ".join(f"{k} {val}" for k, val in v.items())

    def show_teaching_layers(self) -> List[str]:
        layers = self.active.get("teaching_layers", [])
        shown = self.projector.show(layers) if self.projector else layers
        self._event("projector", layers=shown)
        return shown

    def set_auscultation(self, on: bool) -> None:
        self.auscultation = on
        self._event("mode", auscultation=on)

    # -- touch handling ---------------------------------------------------
    def _cooled(self, key: str, seconds: float) -> bool:
        now = time.monotonic()
        if now - self._cool.get(key, 0) < seconds:
            return False
        self._cool[key] = now
        return True

    def handle_touch(self, zone: str, pressure: int) -> None:
        if not self.active:
            return
        sc = self.active
        if pressure > 0:
            self._peak[zone] = max(self._peak.get(zone, 0), pressure)
            if pressure < LIGHT_PRESSURE:
                return
            if self.auscultation:
                info = sc.get("auscultation", {}).get(zone)
                if info and self._cooled(f"a:{zone}", 4.0):
                    self._event("auscultation", zone=zone, finding=info["description"])
                    self.hud(f"[AUSCULTATION @ {zone}] {info['description']}")
                    wav = self.sounds_dir / info.get("audio", "")
                    if info.get("audio") and wav.exists():
                        subprocess.Popen(["aplay", "-q", str(wav)])
            else:
                info = sc.get("palpation", {}).get(zone)
                if info is None or not self._cooled(f"p:{zone}", 2.0):
                    return
                self._event("palpation", zone=zone, pressure=pressure, tenderness=info["tenderness"])
                if info["tenderness"] > 0:
                    text = info.get("deep_say") if pressure >= DEEP_PRESSURE and info.get("deep_say") else info["say"]
                    self.say(text, info.get("expression", "pain"))
        else:  # release
            peak = self._peak.pop(zone, 0)
            info = sc.get("palpation", {}).get(zone)
            if (info and not self.auscultation and peak >= DEEP_PRESSURE and info.get("rebound")
                    and self._cooled(f"r:{zone}", 2.0)):
                self._event("rebound_tenderness", zone=zone)
                self.say(info["rebound_say"], "pain")

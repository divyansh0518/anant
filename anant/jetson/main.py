"""Jetson Nano: perception, language, voice, medical simulation and XR teleoperation ("the brain")."""
from __future__ import annotations

import argparse
import logging
import queue
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

from anant.common.config import config_dir, load_expressions, load_system, load_yaml, load_zones
from anant.common.transport import make_transport
from anant.jetson.bridge import Bridge
from anant.jetson.idle import IdleBehavior
from anant.jetson.llm import LLM, split_expression
from anant.jetson.medical import ScenarioEngine
from anant.jetson.memory import Memory

log = logging.getLogger("anant.jetson")

COMPANION_PROMPT = (
    "You are ANANT, a friendly, curious, full-size humanoid robot built by students. "
    "Speak naturally in at most two short sentences. Begin every reply with exactly one tag from "
    "{tags} describing your facial expression. You are talking to {person}. "
    "What you remember about them: {facts}.")

TOUCH_REACTIONS = {
    "forehead": ("Hehe, that tickles!", "happy"), "hand_r": ("Nice to shake hands with you.", "happy"),
    "hand_l": ("Nice to shake hands with you.", "happy"), "cheek_l": ("Aww!", "happy"),
    "cheek_r": ("Aww!", "happy"), "shoulder_r": ("Oh, hello there!", "surprised"),
}


class App:
    def __init__(self, args, cfg) -> None:
        self.args, self.cfg = args, cfg
        self.expr = load_expressions()
        self.zones = load_zones()
        self.tags = " ".join(f"[{n}]" for n in self.expr["by_name"])
        self.mode = "companion"
        self.person = "friend"
        self.speak_lock = threading.Lock()
        self.touch_q: "queue.Queue[List[Tuple[int, int]]]" = queue.Queue()
        self._touch_cool = 0.0

        self.bridge = Bridge(make_transport(cfg["link"], "jetson", sim=args.sim, port=args.port))
        self.memory = Memory()
        self.llm = LLM(**cfg["llm"])

        v = cfg["voice"]
        if args.text:
            from anant.jetson.voice import ConsoleListener, ConsoleSpeaker
            self.listener, self.speaker = ConsoleListener(), ConsoleSpeaker()
        else:
            from anant.jetson.voice import Listener, Speaker
            self.listener = Listener(v["vosk_model_path"], v["sample_rate"])
            self.speaker = Speaker(v["tts_binary"], v["tts_voice"], v["tts_rate"],
                                   on_mouth=lambda a: self.bridge.set_normalized("jaw", a), listener=self.listener)

        self.projector = None
        if cfg["projector"].get("enabled") and not args.no_projector:
            from anant.jetson.projector import AnatomyProjector
            self.projector = AnatomyProjector(load_yaml("anatomy_overlays.yaml"), cfg["projector"])
            self.projector.start()

        self.engine = ScenarioEngine(config_dir() / "scenarios", self.say, self.projector)
        self.idle = IdleBehavior(self.bridge)
        self.face = self.camera = None
        if not args.no_camera:
            from anant.jetson.vision import Camera, FaceID
            self.face, self.camera = FaceID(), Camera(**{k: cfg["camera"][k] for k in ("index", "width", "height")})
        self.xr = None
        if args.xr:
            from anant.xr.server import XRServer
            self.xr = XRServer(self.bridge, cfg["xr"]["host"], cfg["xr"]["port"])
            self.xr.start_in_thread()

    # -- output -----------------------------------------------------------
    def say(self, text: str, expression: str = "neutral", blocking: bool = True) -> None:
        if not self.speak_lock.acquire(blocking=blocking):
            return
        try:
            self.bridge.set_expression(expression)
            self.speaker.say(text)
        finally:
            self.speak_lock.release()

    # -- touch ------------------------------------------------------------
    def _touch_worker(self) -> None:
        while True:
            for zid, pressure in self.touch_q.get():
                name = self.zones["by_id"].get(zid, f"zone{zid}")
                if self.mode == "medical":
                    self.engine.handle_touch(name, pressure)
                elif pressure > 0 and time.monotonic() - self._touch_cool > 3.0 and name in TOUCH_REACTIONS:
                    self._touch_cool = time.monotonic()
                    text, e = TOUCH_REACTIONS[name]
                    self.say(text, e, blocking=False)

    # -- perception -------------------------------------------------------
    def _vision_worker(self) -> None:
        last_seen: Optional[str] = None
        while True:
            frame = self.camera.read()
            who = self.face.identify(frame) if frame is not None else None
            if who and who != "unknown":
                if who != last_seen and self.mode == "companion":
                    self.person = who
                    facts = self.memory.facts(who)
                    self.say(f"Welcome back, {who}!" if facts else f"Hello {who}!", "happy", blocking=False)
                last_seen = who
            elif who is None:
                last_seen = None
            time.sleep(self.cfg["camera"]["identify_interval_s"])

    # -- dialogue ---------------------------------------------------------
    def handle_command(self, text: str) -> bool:
        t = text.lower()
        e = self.engine
        if "medical mode" in t:
            self.mode = "medical"
            self.say("Medical training mode. Say load scenario, followed by a name.", "neutral")
        elif "companion mode" in t or "normal mode" in t:
            if e.active:
                e.end()
            self.mode = "companion"
            self.say("Back to companion mode.", "happy")
        elif t.startswith("load scenario") or "load scenario" in t:
            sid = e.find(t)
            if sid:
                self.mode = "medical"
                sc = e.start(sid)
                self.say(f"Hello doctor. {sc['patient']['chief_complaint']}", "pain")
            else:
                self.say("I could not find that scenario: " + ", ".join(e.scenarios), "thinking")
        elif self.mode == "medical" and e.active and "end session" in t:
            path = e.end()
            self.say(f"Session saved to {path}", "neutral")
        elif self.mode == "medical" and e.active and "auscultat" in t:
            e.set_auscultation("stop" not in t)
            self.say("Auscultation on." if e.auscultation else "Palpation mode.", "neutral")
        elif self.mode == "medical" and e.active and "palpat" in t:
            e.set_auscultation(False)
            self.say("Palpation mode.", "neutral")
        elif self.mode == "medical" and e.active and "vital" in t:
            self.say(e.vitals_text(), "neutral")
        elif self.mode == "medical" and e.active and "anatomy" in t:
            if "hide" in t or "clear" in t:
                e.projector and e.projector.clear()
            else:
                e.show_teaching_layers()
        elif "emergency stop" in t or t.strip() == "stop":
            self.bridge.estop()
            self.say("Emergency stop engaged.", "surprised")
        elif "resume" in t:
            self.bridge.clear_estop()
            self.say("Resuming.", "neutral")
        else:
            return False
        return True

    def respond(self, text: str) -> None:
        if self.mode == "medical" and self.engine.active:
            self.engine.log_student(text)
            system = self.engine.patient_prompt()
            who = "student"
        else:
            system = COMPANION_PROMPT.format(tags=self.tags, person=self.person,
                                             facts=self.memory.facts_text(self.person))
            who = self.person
        history = self.memory.recent(who, 6)
        self.bridge.set_expression("thinking")
        reply = self.llm.chat([{"role": "system", "content": system}] + history + [{"role": "user", "content": text}])
        expression, spoken = split_expression(reply, list(self.expr["by_name"]))
        self.memory.add_turn(who, "user", text)
        self.memory.add_turn(who, "assistant", spoken)
        self.say(spoken, expression)

    def run(self) -> None:
        self.bridge.start()
        self.bridge.on_touch(self.touch_q.put)
        self.idle.start()
        threading.Thread(target=self._touch_worker, daemon=True).start()
        if self.camera:
            threading.Thread(target=self._vision_worker, daemon=True).start()
        self.say("ANANT online.", "happy")
        try:
            while True:
                text = self.listener.listen()
                if not text:
                    continue
                if not self.handle_command(text):
                    self.respond(text)
        except KeyboardInterrupt:
            pass
        finally:
            self.bridge.estop()
            self.idle.stop()
            self.bridge.stop()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sim", action="store_true", help="TCP loopback instead of serial (pair with anant-pi --sim)")
    ap.add_argument("--port", help="serial port override")
    ap.add_argument("--text", action="store_true", help="keyboard/console instead of microphone/speaker")
    ap.add_argument("--no-camera", action="store_true")
    ap.add_argument("--no-projector", action="store_true")
    ap.add_argument("--xr", action="store_true", help="also run the Meta Quest 3 teleoperation server")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    App(args, load_system()).run()


if __name__ == "__main__":
    main()

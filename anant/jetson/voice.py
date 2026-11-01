"""Real-time voice interaction: offline STT (Vosk), TTS (eSpeak NG) with speech-synchronised jaw."""
from __future__ import annotations

import json
import logging
import math
import queue
import random
import subprocess
import time
from typing import Callable, Optional

log = logging.getLogger("anant.voice")


class Listener:
    """Half-duplex microphone: muted while the robot speaks so it never hears itself."""

    def __init__(self, model_path: str, sample_rate: int = 16000, device=None) -> None:
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._rec = KaldiRecognizer(Model(model_path), sample_rate)
        self.muted = False
        self._stream = sd.RawInputStream(samplerate=sample_rate, blocksize=4000, device=device,
                                         dtype="int16", channels=1, callback=self._cb)
        self._stream.start()

    def _cb(self, indata, frames, t, status) -> None:
        if not self.muted:
            self._q.put(bytes(indata))

    def listen(self, timeout: float = 15.0) -> Optional[str]:
        with self._q.mutex:
            self._q.queue.clear()
        self._rec.Reset()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._rec.AcceptWaveform(data):
                text = json.loads(self._rec.Result()).get("text", "").strip()
                if text:
                    return text
        return None


class Speaker:
    def __init__(self, binary: str = "espeak-ng", voice: str = "en-in", rate: int = 165,
                 on_mouth: Optional[Callable[[float], None]] = None, listener: Optional[Listener] = None) -> None:
        self.binary, self.voice, self.rate = binary, voice, rate
        self.on_mouth, self.listener = on_mouth, listener

    def say(self, text: str) -> None:
        if self.listener:
            self.listener.muted = True
        try:
            proc = subprocess.Popen([self.binary, "-v", self.voice, "-s", str(self.rate), text])
            t0 = time.monotonic()
            while proc.poll() is None:
                if self.on_mouth:  # syllable-rate jaw motion with jitter while audio plays
                    ph = (time.monotonic() - t0) * 2 * math.pi * 4.5
                    self.on_mouth(max(0.0, 0.5 + 0.5 * math.sin(ph)) * random.uniform(0.6, 1.0))
                time.sleep(0.07)
        finally:
            if self.on_mouth:
                self.on_mouth(0.0)
            if self.listener:
                time.sleep(0.25)  # let room echo die away
                self.listener.muted = False


class ConsoleSpeaker:
    """Text-mode stand-in for development without audio hardware."""

    def __init__(self, on_mouth=None, listener=None) -> None:
        pass

    def say(self, text: str) -> None:
        print(f"ANANT: {text}")


class ConsoleListener:
    muted = False

    def listen(self, timeout: float = 0) -> Optional[str]:
        try:
            return input("you> ").strip() or None
        except EOFError:
            raise KeyboardInterrupt

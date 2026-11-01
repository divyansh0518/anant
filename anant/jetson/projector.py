"""Projector-based anatomy visualisation: pulsing organ overlays mapped onto the torso."""
from __future__ import annotations

import logging
import threading
import time
from typing import Iterable, List

import numpy as np

log = logging.getLogger("anant.projector")


class AnatomyProjector:
    def __init__(self, layers_cfg: dict, proj_cfg: dict) -> None:
        self.layers = layers_cfg["layers"]
        self.cfg = proj_cfg
        self._active: List[str] = []
        self._lock = threading.Lock()
        self._run = False

    def show(self, names: Iterable[str]) -> List[str]:
        valid = [n for n in names if n in self.layers]
        with self._lock:
            self._active = valid
        return valid

    def clear(self) -> None:
        self.show([])

    def start(self) -> None:
        self._run = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._run = False

    @staticmethod
    def ellipse_points(c, r, n: int = 48) -> np.ndarray:
        a = np.linspace(0, 2 * np.pi, n, endpoint=False)
        return np.stack([c[0] + r[0] * np.cos(a), c[1] + r[1] * np.sin(a)], axis=1).astype(np.float32)

    def homography(self):
        import cv2
        unit = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])
        return cv2.getPerspectiveTransform(unit, np.float32(self.cfg["quad"]))

    def render(self, active: List[str], t: float = 0.0) -> np.ndarray:
        import cv2
        w, h = self.cfg["size"]
        canvas = np.zeros((h, w, 3), np.uint8)
        H = self.homography()
        pulse = 0.55 + 0.45 * (0.5 + 0.5 * np.sin(t * 3.0))
        for name in active:
            L = self.layers[name]
            pts = self.ellipse_points(L["c"], L["r"]).reshape(-1, 1, 2)
            px = cv2.perspectiveTransform(pts, H).reshape(-1, 2).astype(np.int32)
            col = tuple(int(c * pulse) for c in L["color"])
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [px], col)
            canvas = cv2.addWeighted(overlay, 0.6, canvas, 0.4, 0)
            cv2.polylines(canvas, [px], True, tuple(L["color"]), 2, cv2.LINE_AA)
            x, y = px.mean(axis=0).astype(int)
            cv2.putText(canvas, L["label"], (int(x) + 12, int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 1, cv2.LINE_AA)
        return canvas

    def _loop(self) -> None:
        import cv2
        win = "ANANT anatomy"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.moveWindow(win, *self.cfg["window_pos"])
        cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        t0 = time.monotonic()
        while self._run:
            with self._lock:
                active = list(self._active)
            cv2.imshow(win, self.render(active, time.monotonic() - t0))
            cv2.waitKey(66)
        cv2.destroyWindow(win)

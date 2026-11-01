"""Face recognition for person-aware interaction (dlib embeddings via face_recognition)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("anant.vision")


class FaceID:
    def __init__(self, db_path: str = "data/faces.json", tolerance: float = 0.5) -> None:
        import numpy as np
        import face_recognition  # noqa: F401  (import check)
        self.np, self.fr = np, face_recognition
        self.path = Path(db_path)
        self.tolerance = tolerance
        self.db: Dict[str, List[List[float]]] = {}
        if self.path.exists():
            self.db = json.loads(self.path.read_text())

    def _encode(self, frame_bgr):
        import cv2
        small = cv2.resize(frame_bgr, (0, 0), fx=0.5, fy=0.5)
        rgb = small[:, :, ::-1]
        boxes = self.fr.face_locations(rgb, model="hog")
        return self.fr.face_encodings(rgb, boxes)

    def enroll(self, name: str, frame_bgr) -> bool:
        encs = self._encode(frame_bgr)
        if len(encs) != 1:
            return False
        self.db.setdefault(name, []).append(encs[0].tolist())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.db))
        return True

    def identify(self, frame_bgr) -> Optional[str]:
        """Returns a known name, 'unknown', or None when no face is visible."""
        encs = self._encode(frame_bgr)
        if not encs:
            return None
        best_name, best_d = "unknown", 1e9
        for name, vecs in self.db.items():
            d = float(self.np.min(self.fr.face_distance(self.np.array(vecs), encs[0])))
            if d < best_d:
                best_name, best_d = name, d
        return best_name if best_d <= self.tolerance else "unknown"


class Camera:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480) -> None:
        import cv2
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self) -> None:
        self.cap.release()

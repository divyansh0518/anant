"""Silicone resistive touch skin reader (ADS1115 over I2C) with baseline calibration."""
from __future__ import annotations

import logging
import queue
from typing import Dict, List, Tuple

log = logging.getLogger("anant.pi.touch")


class TouchSkin:
    def __init__(self, zones_cfg: dict, sim: bool = False) -> None:
        self.zones = zones_cfg["zones"]
        self.threshold = zones_cfg.get("touch_threshold", 250)
        self.delta = zones_cfg.get("report_delta", 120)
        self.sim = sim
        self.baseline: Dict[int, int] = {z["id"]: 0 for z in self.zones}
        self.last_sent: Dict[int, int] = {z["id"]: 0 for z in self.zones}
        self._sim_q: "queue.Queue[Tuple[int, int]]" = queue.Queue()
        self._sim_state: Dict[int, int] = {z["id"]: 0 for z in self.zones}
        self._channels = {}
        if not sim:
            self._init_hardware()
            self.calibrate()

    def _init_hardware(self) -> None:
        import board
        import busio
        try:
            from adafruit_ads1x15.ads1115 import ADS1115
            from adafruit_ads1x15.analog_in import AnalogIn
        except ImportError:  # older/newer library layouts
            import adafruit_ads1x15.ads1115 as ADS
            from adafruit_ads1x15.analog_in import AnalogIn
            ADS1115 = ADS.ADS1115
        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        adcs = {}
        for z in self.zones:
            if z["ads"] not in adcs:
                adc = ADS1115(i2c, address=z["ads"])
                adc.data_rate = 860
                adcs[z["ads"]] = adc
            self._channels[z["id"]] = AnalogIn(adcs[z["ads"]], z["channel"])

    def _raw(self, zid: int) -> int:
        if self.sim:
            return self._sim_state[zid]
        return max(0, self._channels[zid].value) >> 3  # 15-bit signed -> 0..4095

    def calibrate(self, samples: int = 30) -> None:
        """Average the unloaded skin to remove per-zone offset (call with nobody touching)."""
        for z in self.zones:
            zid = z["id"]
            self.baseline[zid] = int(sum(self._raw(zid) for _ in range(samples)) / samples)
        log.info("touch baseline: %s", self.baseline)

    def inject(self, zone_id: int, pressure: int) -> None:
        """Simulation hook used by --sim stdin input."""
        self._sim_q.put((zone_id, pressure))

    def poll(self) -> List[Tuple[int, int]]:
        """Return changed zones as [(zone_id, pressure)]; pressure 0 means released."""
        while not self._sim_q.empty():
            zid, p = self._sim_q.get()
            if zid in self._sim_state:
                self._sim_state[zid] = p
        events: List[Tuple[int, int]] = []
        for z in self.zones:
            zid = z["id"]
            p = max(0, self._raw(zid) - self.baseline[zid])
            p = p if p >= self.threshold else 0
            prev = self.last_sent[zid]
            if (p == 0) != (prev == 0) or abs(p - prev) >= self.delta:
                self.last_sent[zid] = p
                events.append((zid, p))
        return events

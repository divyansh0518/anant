"""Raspberry Pi 4B: real-time motor and sensor controller ("the body")."""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time

from anant.common import protocol as P
from anant.common.config import load_expressions, load_joints, load_system, load_zones
from anant.common.transport import make_transport
from anant.pi.servo import ServoBank
from anant.pi.touch import TouchSkin

log = logging.getLogger("anant.pi")


def _stdin_touch_thread(skin: TouchSkin) -> None:
    """Sim input: type 't <zone_id> <pressure>' to emulate touch on the skin."""
    for line in sys.stdin:
        parts = line.split()
        if len(parts) == 3 and parts[0] == "t":
            skin.inject(int(parts[1]), int(parts[2]))


def run(sim: bool, port: str = None) -> None:
    cfg = load_system()
    bank = ServoBank(load_joints(), sim=sim)
    skin = TouchSkin(load_zones(), sim=sim)
    expr = load_expressions()
    link = make_transport(cfg["link"], "pi", sim=sim, port=port)
    parser = P.FrameParser()
    if sim:
        threading.Thread(target=_stdin_touch_thread, args=(skin,), daemon=True).start()

    control_dt = 1.0 / cfg["pi"]["control_hz"]
    touch_dt = 1.0 / cfg["pi"]["touch_hz"]
    watchdog_s = cfg["pi"]["watchdog_s"]
    t0 = time.monotonic()
    last = t0
    last_hb = t0
    next_touch = t0
    next_status = t0
    estop = False
    wd_tripped = False
    log.info("ANANT body controller running (%s)", "SIM" if sim else "HARDWARE")

    try:
        while True:
            now = time.monotonic()
            for fr in parser.feed(link.read(512)):
                if fr.msg_type == P.MsgType.HEARTBEAT:
                    last_hb = now
                    if wd_tripped:
                        wd_tripped = False
                        log.info("link restored")
                elif fr.msg_type == P.MsgType.ESTOP:
                    estop = True
                    bank.freeze()
                    log.warning("E-STOP")
                elif fr.msg_type == P.MsgType.ESTOP_CLEAR:
                    estop = False
                    bank.unfreeze()
                    log.info("E-STOP cleared")
                elif fr.msg_type == P.MsgType.JOINTS and not (estop or wd_tripped):
                    bank.set_targets(P.unpack_joints(fr.payload))
                elif fr.msg_type == P.MsgType.EXPRESSION and not (estop or wd_tripped):
                    eid, ms = P.unpack_expression(fr.payload)
                    name = expr["by_id"].get(eid)
                    if name:
                        bank.set_named(expr["by_name"][name]["joints"], duration=ms / 1000.0)

            if now - last_hb > watchdog_s and not wd_tripped:
                wd_tripped = True
                bank.hold()
                log.warning("heartbeat lost -> holding position")

            bank.update(now - last)
            last = now

            if now >= next_touch:
                next_touch = now + touch_dt
                events = skin.poll()
                if events:
                    link.write(P.encode(P.MsgType.TOUCH, P.pack_touch(events)))

            if now >= next_status:
                next_status = now + 1.0
                flags = (P.STATUS_ESTOP if estop else 0) | (P.STATUS_WATCHDOG if wd_tripped else 0)
                link.write(P.encode(P.MsgType.STATUS,
                                    P.pack_status(int((now - t0) * 1000), flags, parser.crc_errors)))

            sleep = control_dt - (time.monotonic() - now)
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        pass
    finally:
        bank.hold()
        link.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sim", action="store_true", help="no hardware; TCP loopback link")
    ap.add_argument("--port", help="serial port override")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run(args.sim, args.port)


if __name__ == "__main__":
    main()

import random

from anant.common import protocol as P


def test_roundtrip_joints():
    angles = {0: 90.0, 16: 12.5, 43: 179.9}
    fr = P.FrameParser().feed(P.encode(P.MsgType.JOINTS, P.pack_joints(angles), seq=7))
    assert len(fr) == 1 and fr[0].seq == 7
    assert P.unpack_joints(fr[0].payload) == angles


def test_touch_and_status_and_expression():
    ev = [(13, 2100), (6, 0)]
    assert P.unpack_touch(P.pack_touch(ev)) == ev
    assert P.unpack_expression(P.pack_expression(4, 250)) == (4, 250)
    st = P.unpack_status(P.pack_status(1234, P.STATUS_WATCHDOG, 3))
    assert st == {"uptime_ms": 1234, "estop": False, "watchdog": True, "crc_errors": 3}


def test_resync_after_garbage_and_corruption():
    good = P.encode(P.MsgType.HEARTBEAT, b"")
    bad = bytearray(P.encode(P.MsgType.JOINTS, P.pack_joints({1: 50.0})))
    bad[-3] ^= 0xFF
    p = P.FrameParser()
    frames = p.feed(b"\x00\x13\xAA" + bytes(bad) + good + good)
    assert len(frames) == 2 and p.crc_errors >= 1


def test_byte_by_byte_and_fuzz():
    stream = b"".join(P.encode(P.MsgType.JOINTS, P.pack_joints({i: i}), seq=i) for i in range(20))
    p = P.FrameParser()
    got = []
    for b in stream:
        got += p.feed(bytes([b]))
    assert [f.seq for f in got] == list(range(20))
    rnd = random.Random(1)
    P.FrameParser().feed(bytes(rnd.randrange(256) for _ in range(5000)))  # must not raise

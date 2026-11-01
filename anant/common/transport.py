"""Byte transports for the ANANT-Link: real UART/USB serial, or TCP for simulation."""
from __future__ import annotations

import socket
import time
from typing import Any, Dict


class SerialTransport:
    def __init__(self, port: str, baud: int = 921600) -> None:
        import serial  # pyserial
        self._ser = serial.Serial(port, baud, timeout=0.02, write_timeout=0.2)

    def read(self, n: int = 512) -> bytes:
        return self._ser.read(n)

    def write(self, data: bytes) -> None:
        self._ser.write(data)

    def close(self) -> None:
        self._ser.close()


class TcpTransport:
    """Loopback link so the whole stack runs on a laptop with no hardware."""

    def __init__(self, role: str, host: str = "127.0.0.1", port: int = 7777) -> None:
        self.role, self.host, self.port = role, host, port
        self._conn = None
        self._srv = None
        if role == "server":
            self._srv = socket.socket()
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv.bind((host, port))
            self._srv.listen(1)
            self._srv.settimeout(0.02)

    def _ensure(self) -> bool:
        if self._conn:
            return True
        try:
            if self.role == "server":
                conn, _ = self._srv.accept()
            else:
                conn = socket.create_connection((self.host, self.port), timeout=0.5)
            conn.settimeout(0.02)
            self._conn = conn
            return True
        except OSError:
            return False

    def _drop(self) -> None:
        try:
            if self._conn:
                self._conn.close()
        finally:
            self._conn = None

    def read(self, n: int = 512) -> bytes:
        if not self._ensure():
            time.sleep(0.02)
            return b""
        try:
            data = self._conn.recv(n)
        except socket.timeout:
            return b""
        except OSError:
            self._drop()
            return b""
        if data == b"":
            self._drop()
        return data

    def write(self, data: bytes) -> None:
        if not self._ensure():
            return
        try:
            self._conn.sendall(data)
        except OSError:
            self._drop()

    def close(self) -> None:
        self._drop()
        if self._srv:
            self._srv.close()


def make_transport(link_cfg: Dict[str, Any], side: str, sim: bool = False, port: str = None):
    """side: 'jetson' or 'pi'. In sim mode the Pi is the TCP server."""
    if sim:
        role = "server" if side == "pi" else "client"
        return TcpTransport(role, link_cfg.get("sim_host", "127.0.0.1"), link_cfg.get("sim_port", 7777))
    return SerialTransport(port or link_cfg[f"{side}_port"], link_cfg.get("baud", 921600))

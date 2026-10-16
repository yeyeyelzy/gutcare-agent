"""Fail-closed ClamAV daemon adapter using the official INSTREAM protocol."""

import socket
import struct
from typing import Protocol


class MalwareScanner(Protocol):
    def scan(self, content: bytes) -> bool: ...


class ScannerUnavailable(RuntimeError):
    pass


class ClamAvScanner:
    def __init__(self, host: str, port: int = 3310, timeout_seconds: int = 30) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout_seconds

    def scan(self, content: bytes) -> bool:
        try:
            with socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            ) as client:
                client.settimeout(self._timeout)
                client.sendall(b"zINSTREAM\0")
                for offset in range(0, len(content), 64 * 1024):
                    chunk = content[offset : offset + 64 * 1024]
                    client.sendall(struct.pack("!I", len(chunk)))
                    client.sendall(chunk)
                client.sendall(struct.pack("!I", 0))
                response = bytearray()
                while not response.endswith(b"\0"):
                    part = client.recv(4096)
                    if not part:
                        raise ScannerUnavailable("clamd closed the scan connection")
                    response.extend(part)
                    if len(response) > 8192:
                        raise ScannerUnavailable("clamd response exceeded limit")
        except (OSError, TimeoutError) as exc:
            raise ScannerUnavailable("clamd is unavailable") from exc

        result = bytes(response[:-1]).decode("ascii", errors="replace")
        if result.endswith(": OK"):
            return True
        if result.endswith(" FOUND"):
            return False
        raise ScannerUnavailable("clamd returned an invalid scan response")

from __future__ import annotations

import socket

import pytest

from gutcare.files.scanner import ClamAvScanner, ScannerUnavailable


class _InvalidResponseSocket:
    def __enter__(self) -> _InvalidResponseSocket:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def settimeout(self, _timeout: int) -> None:
        return None

    def sendall(self, _data: bytes) -> None:
        return None

    def recv(self, _size: int) -> bytes:
        return b"unexpected daemon response\0"


def test_clamd_socket_failure_is_unavailable_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_connect(*_args: object, **_kwargs: object) -> socket.socket:
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", fail_connect)
    with pytest.raises(ScannerUnavailable):
        ClamAvScanner("clamav").scan(b"valid-file-content")


def test_clamd_invalid_response_is_unavailable_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: _InvalidResponseSocket(),
    )
    with pytest.raises(ScannerUnavailable):
        ClamAvScanner("clamav").scan(b"valid-file-content")

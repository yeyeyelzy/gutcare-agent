"""Test-only loopback HTTP bridge for exercising the real FastAPI app on Windows."""

from __future__ import annotations

import asyncio
import hmac
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx

if os.environ.get("GUTCARE_AUTH_E2E_BRIDGE") != "1":
    raise SystemExit("test-only HTTP bridge requires explicit opt-in")

from gutcare.app import create_app  # noqa: E402
from gutcare.config import Settings  # noqa: E402

app = create_app(settings=Settings(_env_file=None))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "GutCareAuthE2E/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_PATCH(self) -> None:
        self._dispatch()

    def do_DELETE(self) -> None:
        self._dispatch()

    def _dispatch(self) -> None:
        path = urlsplit(self.path).path
        if path == "/__test/shutdown" and self.command == "POST":
            expected = os.environ.get("GUTCARE_AUTH_E2E_BRIDGE_STOP_TOKEN", "")
            provided = self.headers.get("X-Test-Stop", "")
            if not expected or not hmac.compare_digest(provided, expected):
                self.send_error(404)
                return
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 1_000_000:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else b""
        if urlsplit(self.path).query:
            path += "?" + urlsplit(self.path).query
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower()
            in {"accept", "authorization", "content-type", "x-request-id", "x-app-version"}
        }
        response = asyncio.run(self._request(path, headers, body))
        self.send_response(response.status_code)
        for name in ("content-type", "cache-control"):
            value = response.headers.get(name)
            if value:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(response.content)))
        self.send_header("Connection", "close")
        self.end_headers()
        if response.content:
            self.wfile.write(response.content)
        self.close_connection = True

    async def _request(self, path: str, headers: dict[str, str], body: bytes) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://asgi.local") as client:
            return await client.request(self.command, path, headers=headers, content=body)


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, _request: object, _client_address: object) -> None:
        return


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("expected one port argument")
    port = int(sys.argv[1])
    if not 1 <= port <= 65535:
        raise SystemExit("invalid loopback port")
    server = QuietThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    try:
        print("READY", flush=True)
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

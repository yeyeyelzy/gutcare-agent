"""Claim and dispatch frozen F02 medical parse requests to the Agent service."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

logger = logging.getLogger("gutcare.files.medical_parse_dispatcher")


class MedicalParseDispatcher:
    def __init__(
        self,
        business_url: str,
        agent_url: str,
        service_token: str,
        agent_token: str,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not all((business_url, agent_url, service_token, agent_token)):
            raise ValueError("F02 dispatch endpoints and service tokens are required")
        self.business_url = business_url.rstrip("/")
        self.agent_url = agent_url.rstrip("/")
        self.service_token = service_token
        self.agent_token = agent_token
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def _request(
        self,
        url: str,
        token: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}
        except HTTPError as exc:
            # Do not read or log a response body that could contain patient material.
            return exc.code, {}

    def dispatch_one(self) -> bool:
        status, response = self._request(
            f"{self.business_url}/internal/v1/agent/medical-parse-requests/claim",
            self.service_token,
            {},
        )
        if status != 200:
            logger.warning("F02 claim unavailable http_status=%s", status)
            return False
        raw_request_id = response.get("request_id")
        if raw_request_id is None:
            return False
        try:
            request_id = str(UUID(str(raw_request_id)))
        except (TypeError, ValueError):
            logger.error("F02 claim returned an invalid request envelope")
            return True

        for attempt in range(3):
            try:
                status, _ = self._request(
                    f"{self.agent_url}/internal/v1/medical-parse-requests",
                    self.agent_token,
                    {"request_id": request_id, "schema_version": "1.0"},
                    idempotency_key=request_id,
                )
            except (URLError, TimeoutError, OSError):
                if attempt == 2:
                    logger.warning("F02 Agent dispatch transport unavailable")
                    return True
            else:
                if status == 202:
                    return True
                if status < 500 and status != 429:
                    logger.warning("F02 Agent dispatch not accepted http_status=%s", status)
                    return True
                if attempt == 2:
                    logger.warning("F02 Agent dispatch not accepted http_status=%s", status)
                    return True
            time.sleep(0.25 * (attempt + 1))
        return True


def main() -> None:
    dispatcher = MedicalParseDispatcher(
        os.environ.get("F02_BUSINESS_API_URL", ""),
        os.environ.get("F02_AGENT_API_URL", ""),
        os.environ.get("AGENT_SERVICE_TOKEN", ""),
        os.environ.get("AGENT_INTERNAL_TOKEN", ""),
        max(0.1, float(os.environ.get("F02_WORKER_POLL_SECONDS", "2"))),
        float(os.environ.get("F02_DISPATCH_TIMEOUT_SECONDS", "15")),
    )
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    while True:
        try:
            dispatched = dispatcher.dispatch_one()
        except (URLError, TimeoutError, OSError):
            logger.warning("F02 dispatch transport unavailable")
            dispatched = False
        except Exception:
            # Never log payloads, response bodies, document data or credentials.
            logger.warning("F02 dispatch cycle failed")
            dispatched = False
        if not dispatched:
            time.sleep(dispatcher.poll_seconds)


if __name__ == "__main__":
    main()

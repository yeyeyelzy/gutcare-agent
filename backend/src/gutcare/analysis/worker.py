"""Single-process business claim-and-dispatch loop for F08.

This worker has no database connection. The internal business API remains the
only claimant and the Agent receives only the task dispatch envelope.
"""

from __future__ import annotations

import json
import logging
import os
import time
from argparse import ArgumentParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

logger = logging.getLogger("gutcare.analysis.worker")


class DispatchWorker:
    def __init__(
        self,
        business_url: str,
        agent_url: str,
        service_token: str,
        agent_token: str,
        poll_seconds: float = 2.0,
        timeout_seconds: float = 15.0,
    ):
        if not all((business_url, agent_url, service_token, agent_token)):
            raise ValueError("F08 dispatch endpoints and service tokens are required")
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
            # Never include response bodies: they can contain request material.
            return exc.code, {}

    def dispatch_one(self) -> bool:
        status, response = self._request(
            f"{self.business_url}/internal/v1/agent/analysis-tasks/claim",
            self.service_token,
            {},
        )
        if status != 200:
            logger.warning("F08 claim unavailable http_status=%s", status)
            return False
        task = response.get("task")
        if task is None:
            return False
        try:
            task_id = str(UUID(str(task["task_id"])))
            analysis_type = task["analysis_type"]
            attempt = int(task["attempt"])
            if analysis_type not in {"comprehensive_health_analysis", "periodic_summary"}:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            logger.error("F08 claim returned an invalid dispatch envelope")
            return True

        dispatch = {
            "task_id": task_id,
            "analysis_type": analysis_type,
            "schema_version": "1.0",
            "deadline_at": None,
        }
        status = 0
        for retry in range(3):
            try:
                status, _ = self._request(
                    f"{self.agent_url}/internal/v1/tasks",
                    self.agent_token,
                    dispatch,
                    idempotency_key=f"f08:{task_id}:{attempt}",
                )
            except (URLError, TimeoutError, OSError):
                if retry == 2:
                    logger.warning("F08 Agent dispatch transport unavailable task_id=%s", task_id)
                    return True
            else:
                if status < 500 or retry == 2:
                    break
            time.sleep(0.25 * (retry + 1))
        if status not in (200, 202):
            logger.warning("F08 Agent dispatch not accepted http_status=%s", status)
        else:
            logger.info("F08 dispatch accepted task_id=%s", task_id)
        return True

    def run(self, once: bool = False) -> None:
        while True:
            try:
                worked = self.dispatch_one()
            except (URLError, TimeoutError, OSError, ValueError):
                logger.warning("F08 dispatch transport unavailable")
                worked = False
            if once:
                return
            if not worked:
                time.sleep(self.poll_seconds)


def main() -> None:
    parser = ArgumentParser(description="F08 API-only claim and Agent dispatcher")
    parser.add_argument("--once", action="store_true", help="claim and dispatch at most one task")
    args = parser.parse_args()
    business_url = os.environ.get("F08_BUSINESS_API_URL", "http://api:8000")
    agent_url = os.environ.get("F08_AGENT_API_URL", "http://agent:8100")
    service_token = os.environ.get("AGENT_SERVICE_TOKEN", "")
    agent_token = os.environ.get("AGENT_INTERNAL_TOKEN", "")
    try:
        worker = DispatchWorker(
            business_url,
            agent_url,
            service_token,
            agent_token,
            poll_seconds=float(os.environ.get("F08_WORKER_POLL_SECONDS", "2")),
            timeout_seconds=float(os.environ.get("F08_WORKER_TIMEOUT_SECONDS", "15")),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker.run(once=args.once)


if __name__ == "__main__":
    main()

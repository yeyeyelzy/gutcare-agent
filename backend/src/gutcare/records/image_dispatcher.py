"""Durable outbound dispatcher for F03/F04 Agent work envelopes."""

import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

Sender = Callable[[dict[str, Any], str], None]
MAX_ATTEMPTS = 8
AGENT_PATH = "/internal/v1/record-image-recognition/requests"
BUSINESS_CLAIM_PATH = "/internal/v1/agent/record-image-recognition/claim"
logger = logging.getLogger(__name__)


class PermanentDispatchError(Exception):
    """Agent rejected an envelope permanently (for example, schema mismatch)."""


def make_agent_sender(agent_url: str, token: str, timeout_seconds: float = 15.0) -> Sender:
    if not agent_url or not token:
        raise ValueError("F03/F04 Agent dispatch URL and token are required")
    endpoint = agent_url.rstrip("/") + AGENT_PATH

    def send(payload: dict[str, Any], idempotency_key: str) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Idempotency-Key": idempotency_key,
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                if response.status not in (200, 202):
                    raise RuntimeError("unexpected Agent dispatch status")
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise
            raise PermanentDispatchError(f"Agent rejected dispatch: HTTP {exc.code}") from None

    return send


def make_business_claimer(
    business_url: str, token: str, timeout_seconds: float = 15.0
) -> Callable[[], bool]:
    """Claim one frozen request through the business API; never query request facts here."""
    if not business_url or not token:
        raise ValueError("F03/F04 business API URL and service token are required")
    endpoint = business_url.rstrip("/") + BUSINESS_CLAIM_PATH

    def claim() -> bool:
        request = Request(
            endpoint,
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise RuntimeError("unexpected business claim status")
            result = json.loads(response.read())
        return bool(result.get("request"))

    return claim


def retry_delay_seconds(attempt: int) -> int:
    """Bounded exponential retry delay; only a controlled code is persisted."""
    return int(min(3600, 5 * (2 ** max(0, attempt - 1))))


def dispatch_batch(sessions: sessionmaker[Any], sender: Sender, batch_size: int = 50) -> int:
    """Send leased outbox envelopes; a crash is recovered by lease expiry."""
    dispatched = 0
    for _ in range(batch_size):
        with sessions.begin() as db:
            row = (
                db.execute(
                    text("""
                        WITH candidate AS (
                            SELECT id FROM analysis.record_image_dispatch_outbox
                            WHERE (status='pending' AND available_at<=now())
                               OR (status='processing' AND lease_until<now())
                            ORDER BY available_at,created_at
                            FOR UPDATE SKIP LOCKED LIMIT 1
                        )
                        UPDATE analysis.record_image_dispatch_outbox AS o
                        SET status='processing', attempts=o.attempts+1,
                            lease_until=now()+interval '2 minutes'
                        FROM candidate c WHERE o.id=c.id
                        RETURNING o.id,o.request_id,o.patient_id,o.payload,o.attempts
                    """)
                )
                .mappings()
                .first()
            )
            if row is None:
                break
            db.execute(
                text("SELECT set_config('app.patient_id',:p,true)"),
                {"p": str(row["patient_id"])},
            )
            payload = row["payload"]
            if isinstance(payload, str):
                import json

                payload = json.loads(payload)
            attempt = int(row["attempts"])

        idempotency_key = f"record-image:{row['request_id']}:{payload['attempt']}"
        try:
            sender(payload, idempotency_key)
        except PermanentDispatchError:
            with sessions.begin() as db:
                db.execute(
                    text("SELECT set_config('app.patient_id',:p,true)"),
                    {"p": str(row["patient_id"])},
                )
                db.execute(
                    text("""
                        UPDATE analysis.record_image_dispatch_outbox
                        SET status='dead_letter',lease_until=NULL,
                            last_error_code='DISPATCH_REJECTED'
                        WHERE id=:id AND patient_id=:p
                    """),
                    {"id": row["id"], "p": row["patient_id"]},
                )
            continue
        except Exception:
            with sessions.begin() as db:
                db.execute(
                    text("SELECT set_config('app.patient_id',:p,true)"),
                    {"p": str(row["patient_id"])},
                )
                if attempt >= MAX_ATTEMPTS:
                    db.execute(
                        text("""
                            UPDATE analysis.record_image_dispatch_outbox
                            SET status='dead_letter',lease_until=NULL,
                                last_error_code='DISPATCH_FAILED'
                            WHERE id=:id AND patient_id=:p
                        """),
                        {"id": row["id"], "p": row["patient_id"]},
                    )
                else:
                    db.execute(
                        text("""
                            UPDATE analysis.record_image_dispatch_outbox
                            SET status='pending',available_at=now()+(:delay*interval '1 second'),
                                lease_until=NULL,last_error_code='DISPATCH_FAILED'
                            WHERE id=:id AND patient_id=:p
                        """),
                        {
                            "delay": retry_delay_seconds(attempt),
                            "id": row["id"],
                            "p": row["patient_id"],
                        },
                    )
            continue

        with sessions.begin() as db:
            db.execute(
                text("SELECT set_config('app.patient_id',:p,true)"),
                {"p": str(row["patient_id"])},
            )
            db.execute(
                text("""
                    UPDATE analysis.record_image_dispatch_outbox
                    SET status='dispatched',lease_until=NULL,last_error_code=NULL
                    WHERE id=:id AND patient_id=:p
                """),
                {"id": row["id"], "p": row["patient_id"]},
            )
        dispatched += 1
    return dispatched


def request_id_from_payload(payload: dict[str, Any]) -> UUID:
    """Small validation hook for adapters; never accepts image bytes or free text."""
    return UUID(str(payload["request_id"]))


def main() -> None:
    database_url = os.environ.get("ANALYSIS_WORKER_DATABASE_URL", "")
    if not database_url:
        raise SystemExit("ANALYSIS_WORKER_DATABASE_URL is required")
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    sender = make_agent_sender(
        os.environ.get("F03_F04_AGENT_API_URL", ""),
        os.environ.get("AGENT_INTERNAL_TOKEN", ""),
        float(os.environ.get("F03_F04_DISPATCH_TIMEOUT_SECONDS", "15")),
    )
    claimer = make_business_claimer(
        os.environ.get("F03_F04_BACKEND_API_URL", ""),
        os.environ.get("AGENT_SERVICE_TOKEN", ""),
        float(os.environ.get("F03_F04_CLAIM_TIMEOUT_SECONDS", "15")),
    )
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        sessions = sessionmaker(engine, expire_on_commit=False)
        poll_seconds = max(0.1, float(os.environ.get("F03_F04_WORKER_POLL_SECONDS", "2")))
        logging.basicConfig(
            level=os.environ.get("LOG_LEVEL", "INFO"),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        while True:
            try:
                claimed = claimer()
                dispatched = dispatch_batch(sessions, sender)
            except Exception:
                # Never log request payloads, capabilities, remote response bodies or credentials.
                logger.warning("F03/F04 dispatch cycle failed")
                claimed = False
                dispatched = 0
            if not claimed and not dispatched:
                time.sleep(poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

"""Durable outbound dispatcher for F03/F04 Agent work envelopes."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

Sender = Callable[[dict[str, Any], str], None]
MAX_ATTEMPTS = 8


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

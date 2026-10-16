"""Standalone F12 outbox dispatcher. Uses the notification-only database role."""

# SQL statements encode the state transition atomically.
# ruff: noqa: E501

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def dispatch_batch(
    sessions: sessionmaker[Any], batch_size: int = 50, patient_id: UUID | None = None
) -> int:
    dispatched = 0
    for _ in range(batch_size):
        # Claim and commit a lease before dispatch. A crashed process is recoverable
        # after two minutes; concurrent workers skip rows already locked by peers.
        with sessions.begin() as db:
            patient_filter = "AND patient_id=:patient_id" if patient_id is not None else ""
            claim_sql = text(f"""
                WITH candidate AS (
                    SELECT id FROM health.notification_outbox
                    WHERE ((status='pending' AND available_at <= now())
                       OR (status='processing' AND lease_expires_at < now()))
                      {patient_filter}
                    ORDER BY available_at, created_at
                    FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE health.notification_outbox AS o
                SET status='processing', attempts=o.attempts+1,
                    lease_expires_at=now()+interval '2 minutes'
                FROM candidate c WHERE o.id=c.id
                RETURNING o.id, o.patient_id, o.event_type, o.target_type, o.target_id,
                          o.occurred_at, o.priority, o.deduplication_key, o.payload, o.attempts
            """)
            parameters = {"patient_id": patient_id} if patient_id is not None else {}
            row = db.execute(claim_sql, parameters).mappings().first()
            if row is None:
                break
            db.execute(
                text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(row["patient_id"])}
            )
            attempt = int(row["attempts"])
        try:
            with sessions.begin() as db:
                db.execute(
                    text("SELECT set_config('app.patient_id', :p, true)"),
                    {"p": str(row["patient_id"])},
                )
                pref = (
                    db.execute(
                        text(
                            "SELECT ordinary_in_app_enabled, quiet_start, quiet_end, timezone FROM health.notification_preference WHERE patient_id=:p"
                        ),
                        {"p": row["patient_id"]},
                    )
                    .mappings()
                    .first()
                )
                if row["priority"] != "risk" and pref and not pref["ordinary_in_app_enabled"]:
                    db.execute(
                        text(
                            "UPDATE health.notification_outbox SET status='suppressed', lease_expires_at=NULL WHERE id=:id"
                        ),
                        {"id": row["id"]},
                    )
                    continue
                if row["priority"] != "risk" and pref and pref["quiet_start"] and pref["quiet_end"]:
                    try:
                        local = datetime.now(ZoneInfo(pref["timezone"]))
                    except ZoneInfoNotFoundError:
                        local = datetime.now(UTC)
                    now_time = local.timetz().replace(tzinfo=None)
                    start, end = pref["quiet_start"], pref["quiet_end"]
                    quiet = (
                        start <= now_time < end
                        if start < end
                        else now_time >= start or now_time < end
                    )
                    if quiet:
                        next_local = local.replace(
                            hour=end.hour, minute=end.minute, second=0, microsecond=0
                        )
                        if start >= end and now_time >= start:
                            next_local += timedelta(days=1)
                        db.execute(
                            text(
                                "UPDATE health.notification_outbox SET status='pending', available_at=:at, lease_expires_at=NULL WHERE id=:id"
                            ),
                            {"at": next_local.astimezone(UTC), "id": row["id"]},
                        )
                        continue
                category = {
                    "analysis_completed": "analysis",
                    "advice_created": "advice",
                    "risk_alert_created": "risk",
                    "checkin_reminder": "medication_reminder",
                }[row["event_type"]]
                db.execute(
                    text("""
                    INSERT INTO health.patient_notification
                    (patient_id,outbox_id,event_type,category,priority,target_type,target_id,target_unavailable,deduplication_key,occurred_at)
                    VALUES (:p,:o,:e,:c,:pr,:tt,:tid,false,:dk,:at)
                """),
                    {
                        "p": row["patient_id"],
                        "o": row["id"],
                        "e": row["event_type"],
                        "c": category,
                        "pr": row["priority"],
                        "tt": row["target_type"],
                        "tid": row["target_id"],
                        "dk": row["deduplication_key"],
                        "at": row["occurred_at"],
                    },
                )
                db.execute(
                    text(
                        "UPDATE health.notification_outbox SET status='dispatched', lease_expires_at=NULL WHERE id=:id"
                    ),
                    {"id": row["id"]},
                )
                dispatched += 1
        except Exception:
            # The dispatch transaction has rolled back before retry state is written.
            with sessions.begin() as db:
                db.execute(
                    text("SELECT set_config('app.patient_id', :p, true)"),
                    {"p": str(row["patient_id"])},
                )
                if attempt >= 8:
                    db.execute(
                        text(
                            "UPDATE health.notification_outbox SET status='dead_letter', last_error_code='DISPATCH_FAILED', lease_expires_at=NULL WHERE id=:id"
                        ),
                        {"id": row["id"]},
                    )
                else:
                    delay_seconds = min(3600, 5 * (2 ** (attempt - 1)))
                    db.execute(
                        text(
                            "UPDATE health.notification_outbox SET status='pending', available_at=now()+(:delay * interval '1 second'), last_error_code='DISPATCH_FAILED', lease_expires_at=NULL WHERE id=:id"
                        ),
                        {"delay": delay_seconds, "id": row["id"]},
                    )
    return dispatched


def main() -> None:
    url = os.environ.get("NOTIFICATION_WORKER_DATABASE_URL")
    if not url:
        raise SystemExit("NOTIFICATION_WORKER_DATABASE_URL is required")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        dispatch_batch(sessionmaker(engine, expire_on_commit=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

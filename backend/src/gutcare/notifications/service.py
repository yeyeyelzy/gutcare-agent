"""Patient-scoped F12 notification API service."""

import base64
import re
from datetime import UTC, datetime, time
from typing import cast
from uuid import UUID

from sqlalchemy import desc, select, text, tuple_
from sqlalchemy.orm import Session, sessionmaker

from gutcare.auth.models import PatientProfile, UserAccount
from gutcare.auth.service import AuthContext
from gutcare.notifications.models import NotificationPreference, PatientNotification
from gutcare.shared.errors import Problem


class NotificationService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _patient(db: Session, context: AuthContext) -> UUID:
        db.execute(
            text("SELECT set_config('app.user_id', :id, true)"), {"id": str(context.user_id)}
        )
        profile = db.scalar(select(PatientProfile).where(PatientProfile.user_id == context.user_id))
        account = db.get(UserAccount, context.user_id)
        if (
            profile is None
            or profile.deleted_at is not None
            or account is None
            or account.status != "active"
        ):
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(profile.id)})
        return profile.id

    @staticmethod
    def _cursor(created: datetime, ident: UUID) -> str:
        raw = f"{created.astimezone(UTC).isoformat()}|{ident}"
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    @staticmethod
    def _decode(cursor: str) -> tuple[datetime, UUID]:
        try:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", cursor):
                raise ValueError
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            created, ident = raw.split("|", 1)
            dt = datetime.fromisoformat(created)
            if dt.tzinfo is None:
                raise ValueError
            return dt.astimezone(UTC), UUID(ident)
        except (ValueError, UnicodeDecodeError):
            raise Problem(400, "INVALID_CURSOR", "Notification cursor is invalid") from None

    @staticmethod
    def _dto(db: Session, row: PatientNotification) -> dict[str, object]:
        live = False
        if row.target_type and row.target_id:
            target_tables = {
                "analysis_task": "analysis.analysis_task",
                "advice": "analysis.health_advice",
                "risk_alert": "safety.risk_alert",
                "medication_checkin": "health.medication_checkin",
            }
            table = target_tables[row.target_type]
            live = bool(
                db.scalar(
                    text(
                        f"SELECT EXISTS (SELECT 1 FROM {table} "
                        "WHERE id=:id AND patient_id=:patient_id)"
                    ),
                    {"id": row.target_id, "patient_id": row.patient_id},
                )
            )
        unavailable = row.target_unavailable or not live
        return {
            "id": str(row.id),
            "event_type": row.event_type,
            "category": row.category,
            "priority": row.priority,
            "occurred_at": row.occurred_at.isoformat(),
            "created_at": row.created_at.isoformat(),
            "read_at": row.read_at.isoformat() if row.read_at else None,
            "target": {"type": row.target_type, "id": str(row.target_id)}
            if not unavailable
            else None,
            "target_unavailable": unavailable,
        }

    def list_notifications(
        self,
        context: AuthContext,
        limit: int,
        cursor: str | None,
        category: str | None,
        unread_only: bool,
    ) -> dict[str, object]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            q = select(PatientNotification).where(PatientNotification.patient_id == patient)
            if category:
                q = q.where(PatientNotification.category == category)
            if unread_only:
                q = q.where(PatientNotification.read_at.is_(None))
            if cursor:
                created, ident = self._decode(cursor)
                q = q.where(
                    tuple_(PatientNotification.created_at, PatientNotification.id)
                    < (created, ident)
                )
            rows = db.scalars(
                q.order_by(
                    desc(PatientNotification.created_at), desc(PatientNotification.id)
                ).limit(limit + 1)
            ).all()
            more = len(rows) > limit
            rows = rows[:limit]
            return {
                "items": [self._dto(db, r) for r in rows],
                "next_cursor": self._cursor(rows[-1].created_at, rows[-1].id)
                if more and rows
                else None,
            }

    def get(self, context: AuthContext, ident: UUID) -> dict[str, object]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            row = db.scalar(
                select(PatientNotification).where(
                    PatientNotification.patient_id == patient, PatientNotification.id == ident
                )
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._dto(db, row)

    def unread_count(self, context: AuthContext) -> dict[str, int]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            count = db.scalar(
                select(text("count(*)"))
                .select_from(PatientNotification)
                .where(
                    PatientNotification.patient_id == patient, PatientNotification.read_at.is_(None)
                )
            )
            return {"count": int(count or 0)}

    def mark_read(self, context: AuthContext, ident: UUID) -> dict[str, object]:
        return self.mark_many(context, [ident])[0]

    def mark_many(self, context: AuthContext, ids: list[UUID]) -> list[dict[str, object]]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            now = datetime.now(UTC)
            rows = list(
                db.scalars(
                    select(PatientNotification)
                    .where(
                        PatientNotification.patient_id == patient, PatientNotification.id.in_(ids)
                    )
                    .order_by(PatientNotification.id)
                    .with_for_update()
                )
            )
            if len(rows) != len(set(ids)):
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            for row in rows:
                if row.read_at is None:
                    row.read_at = now
            return [self._dto(db, row) for row in rows]

    def get_preferences(self, context: AuthContext) -> dict[str, object]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            pref = db.get(NotificationPreference, patient)
            return {
                "ordinary_in_app_enabled": pref.ordinary_in_app_enabled if pref else True,
                "quiet_start": pref.quiet_start.isoformat() if pref and pref.quiet_start else None,
                "quiet_end": pref.quiet_end.isoformat() if pref and pref.quiet_end else None,
                "timezone": pref.timezone if pref else "UTC",
            }

    def set_preferences(
        self, context: AuthContext, payload: dict[str, object]
    ) -> dict[str, object]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            pref = db.get(NotificationPreference, patient)
            if pref is None:
                pref = NotificationPreference(patient_id=patient)
                db.add(pref)
            pref.ordinary_in_app_enabled = bool(payload["ordinary_in_app_enabled"])
            pref.quiet_start = cast(time | None, payload.get("quiet_start"))
            pref.quiet_end = cast(time | None, payload.get("quiet_end"))
            pref.timezone = str(payload["timezone"])
            pref.updated_at = datetime.now(UTC)
            return {
                "ordinary_in_app_enabled": pref.ordinary_in_app_enabled,
                "quiet_start": pref.quiet_start.isoformat() if pref.quiet_start else None,
                "quiet_end": pref.quiet_end.isoformat() if pref.quiet_end else None,
                "timezone": pref.timezone,
            }

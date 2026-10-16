"""Patient-scoped F14 mood record operations."""

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from gutcare.auth.models import PatientConsent, PatientProfile
from gutcare.auth.service import AuthContext
from gutcare.mood.models import MoodRecord
from gutcare.records.models import RecordIdempotency
from gutcare.shared.errors import Problem

TAGS = {"calm", "content", "joyful", "sad", "anxious", "irritable", "overwhelmed", "tired", "other"}


def _encode_cursor(occurred_at: datetime, record_id: UUID) -> str:
    return urlsafe_b64encode(f"{occurred_at.isoformat()}|{record_id}".encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        timestamp, record_id = (
            urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode().split("|", 1)
        )
        value = datetime.fromisoformat(timestamp)
        if value.tzinfo is None:
            raise ValueError
        return value, UUID(record_id)
    except (ValueError, UnicodeError) as exc:
        raise Problem(422, "VALIDATION_ERROR", "Invalid cursor") from exc


class MoodService:
    def __init__(self, sessions: sessionmaker[Session], idempotency_hmac_key: str | None) -> None:
        self._sessions = sessions
        self._idempotency_hmac_key = (
            idempotency_hmac_key.encode("utf-8") if idempotency_hmac_key else None
        )

    def _request_hash(self, data: dict[str, Any]) -> str:
        key = self._idempotency_hmac_key
        if key is None:
            raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
        canonical = json.dumps(
            {**data, "occurred_at": data["occurred_at"].isoformat()},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(key, canonical, hashlib.sha256).hexdigest()

    @staticmethod
    def _patient(db: Session, context: AuthContext) -> UUID:
        db.execute(
            text("SELECT set_config('app.user_id', :id, true)"), {"id": str(context.user_id)}
        )
        profile = db.scalar(
            select(PatientProfile).where(
                PatientProfile.user_id == context.user_id, PatientProfile.deleted_at.is_(None)
            )
        )
        if profile is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(profile.id)})
        return profile.id

    @staticmethod
    def _write_consents(db: Session, patient_id: UUID) -> None:
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock_shared(hashtextextended("
                "'gutcare.patient-consent-fence:' || :p, 0))"
            ),
            {"p": str(patient_id)},
        )
        for kind in ("health_data_processing", "mood_data_processing"):
            current = db.scalar(
                select(PatientConsent)
                .where(PatientConsent.patient_id == patient_id, PatientConsent.consent_type == kind)
                .order_by(desc(PatientConsent.decided_at), desc(PatientConsent.id))
                .limit(1)
            )
            if current is None or not current.granted:
                raise Problem(
                    409, "CONSENT_REQUIRED", "Required data processing consent is missing"
                )

    @staticmethod
    def _dto(record: MoodRecord, *, detail: bool) -> dict[str, Any]:
        result = {
            "id": record.id,
            "occurred_at": record.occurred_at,
            "mood_level": record.mood_level,
            "emotion_tags": record.emotion_tags,
            "record_version": record.record_version,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        if detail:
            result["note"] = record.note
        return result

    def create(
        self, context: AuthContext, data: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        request_hash = self._request_hash(data)
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            self._write_consents(db, patient)
            db.execute(
                pg_insert(RecordIdempotency)
                .values(
                    patient_id=patient,
                    operation="mood-records",
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
                .on_conflict_do_nothing(constraint="uq_record_idempotency_scope")
            )
            idem = db.scalar(
                select(RecordIdempotency)
                .where(
                    RecordIdempotency.patient_id == patient,
                    RecordIdempotency.operation == "mood-records",
                    RecordIdempotency.idempotency_key == idempotency_key,
                )
                .with_for_update()
            )
            assert idem is not None
            if idem.request_hash != request_hash:
                raise Problem(
                    409, "IDEMPOTENCY_CONFLICT", "Idempotency key was used for another request"
                )
            if idem.resource_id:
                prior = db.scalar(
                    select(MoodRecord).where(
                        MoodRecord.id == idem.resource_id,
                        MoodRecord.patient_id == patient,
                        MoodRecord.deleted_at.is_(None),
                    )
                )
                if prior is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                return self._dto(prior, detail=True)
            record = MoodRecord(patient_id=patient, **data)
            db.add(record)
            db.flush()
            idem.resource_id = record.id
            return self._dto(record, detail=True)

    def list(
        self,
        context: AuthContext,
        *,
        cursor: str | None,
        limit: int,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]:
        if (since and (since.tzinfo is None or since.utcoffset() is None)) or (
            until and (until.tzinfo is None or until.utcoffset() is None)
        ):
            raise Problem(422, "VALIDATION_ERROR", "since and until must include a timezone")
        if since and until and since >= until:
            raise Problem(422, "VALIDATION_ERROR", "since must be earlier than until")
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            query = select(MoodRecord).where(
                MoodRecord.patient_id == patient, MoodRecord.deleted_at.is_(None)
            )
            if since:
                query = query.where(MoodRecord.occurred_at >= since)
            if until:
                query = query.where(MoodRecord.occurred_at < until)
            if cursor:
                timestamp, record_id = _decode_cursor(cursor)
                query = query.where(
                    (MoodRecord.occurred_at < timestamp)
                    | ((MoodRecord.occurred_at == timestamp) & (MoodRecord.id < record_id))
                )
            rows = list(
                db.scalars(
                    query.order_by(MoodRecord.occurred_at.desc(), MoodRecord.id.desc()).limit(
                        limit + 1
                    )
                )
            )
            more = len(rows) > limit
            rows = rows[:limit]
            return {
                "items": [self._dto(row, detail=False) for row in rows],
                "next_cursor": _encode_cursor(rows[-1].occurred_at, rows[-1].id)
                if more and rows
                else None,
            }

    def get(self, context: AuthContext, record_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            record = db.scalar(
                select(MoodRecord).where(
                    MoodRecord.id == record_id,
                    MoodRecord.patient_id == patient,
                    MoodRecord.deleted_at.is_(None),
                )
            )
            if record is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._dto(record, detail=True)

    def patch(
        self, context: AuthContext, record_id: UUID, version: int, changes: dict[str, Any]
    ) -> dict[str, Any]:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            record = db.scalar(
                select(MoodRecord)
                .where(
                    MoodRecord.id == record_id,
                    MoodRecord.patient_id == patient,
                    MoodRecord.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if record is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if record.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Mood record has changed")
            self._write_consents(db, patient)
            if changes:
                for key, value in changes.items():
                    setattr(record, key, value)
                record.record_version += 1
                record.updated_at = datetime.now(UTC)
            db.flush()
            return self._dto(record, detail=True)

    def delete(self, context: AuthContext, record_id: UUID, version: int) -> None:
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            record = db.scalar(
                select(MoodRecord)
                .where(
                    MoodRecord.id == record_id,
                    MoodRecord.patient_id == patient,
                    MoodRecord.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if record is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if record.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Mood record has changed")
            record.deleted_at = record.updated_at = datetime.now(UTC)
            record.record_version += 1

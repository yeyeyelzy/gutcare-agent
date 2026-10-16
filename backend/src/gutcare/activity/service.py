"""Patient scoped activity, mixed history and SQL aggregated trends."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, literal, or_, select, text, tuple_, union_all
from sqlalchemy.orm import Session, sessionmaker

from gutcare.activity.models import ActivityRecord
from gutcare.analysis.advice_models import HealthAdvice
from gutcare.auth.models import PatientProfile, UserAccount
from gutcare.auth.service import AuthContext
from gutcare.medication.models import MedicationCheckin
from gutcare.mood.models import MoodRecord
from gutcare.records.models import DietItem, DietRecord, StoolRecord, SymptomItem, SymptomRecord
from gutcare.shared.errors import Problem


class ActivityService:
    def __init__(self, sessions: sessionmaker[Session], cursor_secret: str | None) -> None:
        self._sessions = sessions
        self._secret = cursor_secret.encode() if cursor_secret else None

    @staticmethod
    def _patient(db: Session, context: AuthContext) -> PatientProfile:
        db.execute(
            text("SELECT set_config('app.user_id', :id, true)"), {"id": str(context.user_id)}
        )
        profile = db.scalar(
            select(PatientProfile).where(
                PatientProfile.user_id == context.user_id, PatientProfile.deleted_at.is_(None)
            )
        )
        account = db.get(UserAccount, context.user_id)
        if profile is None or account is None or account.status != "active":
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        db.execute(text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(profile.id)})
        return profile

    def _encode(self, value: dict[str, Any]) -> str:
        if self._secret is None:
            raise Problem(500, "INTERNAL_ERROR", "Cursor signing is unavailable")
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        sig = hmac.new(self._secret, raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw + sig).decode().rstrip("=")

    def _decode(self, cursor: str) -> dict[str, Any]:
        try:
            if self._secret is None or len(cursor) > 512:
                raise ValueError
            packed = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            raw, signature = packed[:-32], packed[-32:]
            if not hmac.compare_digest(
                signature, hmac.new(self._secret, raw, hashlib.sha256).digest()
            ):
                raise ValueError
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            IndexError,
        ):
            raise Problem(400, "INVALID_CURSOR", "History cursor is invalid") from None

    @staticmethod
    def _time_filter(value: datetime | None) -> str | None:
        return value.astimezone(UTC).isoformat() if value is not None else None

    @staticmethod
    def _check_filters(data: dict[str, Any], filters: dict[str, Any]) -> None:
        if data.get("filters") != filters:
            raise Problem(400, "INVALID_CURSOR", "History cursor does not match filters")

    @staticmethod
    def _dto(row: ActivityRecord) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "activity_type": row.activity_type,
            "description": row.description,
            "intensity": row.intensity,
            "subjective_feeling": row.subjective_feeling,
            "duration_minutes": row.duration_minutes,
            "occurred_at": row.occurred_at.isoformat(),
            "record_version": row.record_version,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def create(self, context: AuthContext, payload: dict[str, Any]) -> dict[str, Any]:
        with self._sessions.begin() as db:
            profile = self._patient(db, context)
            row = ActivityRecord(patient_id=profile.id, **payload)
            db.add(row)
            db.flush()
            return self._dto(row)

    def get(self, context: AuthContext, ident: UUID) -> dict[str, Any]:
        with self._sessions.begin() as db:
            profile = self._patient(db, context)
            row = db.scalar(
                select(ActivityRecord).where(
                    ActivityRecord.patient_id == profile.id,
                    ActivityRecord.id == ident,
                    ActivityRecord.deleted_at.is_(None),
                )
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._dto(row)

    def update(
        self, context: AuthContext, ident: UUID, version: int, changes: dict[str, Any]
    ) -> dict[str, Any]:
        with self._sessions.begin() as db:
            profile = self._patient(db, context)
            row = db.scalar(
                select(ActivityRecord)
                .where(
                    ActivityRecord.patient_id == profile.id,
                    ActivityRecord.id == ident,
                    ActivityRecord.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version conflict")
            for key, value in changes.items():
                if key != "record_version":
                    setattr(row, key, value)
            if (
                (row.activity_type == "other") != (row.description is not None)
                or not 1 <= row.duration_minutes <= 1440
                or row.occurred_at.tzinfo is None
            ):
                raise Problem(422, "VALIDATION_ERROR", "Activity fields are inconsistent")
            row.record_version += 1
            row.updated_at = datetime.now(UTC)
            db.flush()
            return self._dto(row)

    def delete(self, context: AuthContext, ident: UUID, version: int) -> None:
        with self._sessions.begin() as db:
            profile = self._patient(db, context)
            row = db.scalar(
                select(ActivityRecord)
                .where(
                    ActivityRecord.patient_id == profile.id,
                    ActivityRecord.id == ident,
                    ActivityRecord.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version conflict")
            row.deleted_at = datetime.now(UTC)
            row.updated_at = row.deleted_at
            row.record_version += 1

    def list_activities(
        self,
        context: AuthContext,
        limit: int,
        cursor: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]:
        if (
            (since is not None and since.tzinfo is None)
            or (until is not None and until.tzinfo is None)
            or (since is not None and until is not None and until <= since)
        ):
            raise Problem(422, "VALIDATION_ERROR", "Invalid activity time range")
        with self._sessions.begin() as db:
            profile = self._patient(db, context)
            query = select(ActivityRecord).where(
                ActivityRecord.patient_id == profile.id, ActivityRecord.deleted_at.is_(None)
            )
            if since:
                query = query.where(ActivityRecord.occurred_at >= since)
            if until:
                query = query.where(ActivityRecord.occurred_at < until)
            if cursor:
                data = self._decode(cursor)
                self._check_filters(
                    data,
                    {"since": self._time_filter(since), "until": self._time_filter(until)},
                )
                try:
                    stamp, ident = datetime.fromisoformat(data["occurred_at"]), UUID(data["id"])
                    if stamp.tzinfo is None:
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    raise Problem(400, "INVALID_CURSOR", "Activity cursor is invalid") from None
                query = query.where(
                    tuple_(ActivityRecord.occurred_at, ActivityRecord.id) < (stamp, ident)
                )
            rows = db.scalars(
                query.order_by(desc(ActivityRecord.occurred_at), desc(ActivityRecord.id)).limit(
                    limit + 1
                )
            ).all()
            more = len(rows) > limit
            rows = rows[:limit]
            return {
                "items": [self._dto(row) for row in rows],
                "next_cursor": self._encode(
                    {
                        "occurred_at": rows[-1].occurred_at.astimezone(UTC).isoformat(),
                        "id": str(rows[-1].id),
                        "filters": {
                            "since": self._time_filter(since),
                            "until": self._time_filter(until),
                        },
                    }
                )
                if more and rows
                else None,
            }

    def timeline(
        self,
        context: AuthContext,
        limit: int,
        cursor: str | None,
        categories: list[str] | None,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]:
        if (
            (since is not None and since.tzinfo is None)
            or (until is not None and until.tzinfo is None)
            or (since is not None and until is not None and until <= since)
        ):
            raise Problem(422, "VALIDATION_ERROR", "Invalid history time range")
        with self._sessions.begin() as db:
            patient = self._patient(db, context)
            category_sources = [
                (
                    "diet",
                    select(
                        DietRecord.id.label("id"),
                        DietRecord.occurred_at.label("occurred_at"),
                        literal("diet").label("type"),
                    ).where(DietRecord.patient_id == patient.id, DietRecord.deleted_at.is_(None)),
                ),
                (
                    "stool",
                    select(
                        StoolRecord.id.label("id"),
                        StoolRecord.occurred_at.label("occurred_at"),
                        literal("stool").label("type"),
                    ).where(StoolRecord.patient_id == patient.id, StoolRecord.deleted_at.is_(None)),
                ),
                (
                    "symptom",
                    select(
                        SymptomRecord.id.label("id"),
                        SymptomRecord.occurred_at.label("occurred_at"),
                        literal("symptom").label("type"),
                    ).where(
                        SymptomRecord.patient_id == patient.id, SymptomRecord.deleted_at.is_(None)
                    ),
                ),
                (
                    "medication_checkin",
                    select(
                        MedicationCheckin.id.label("id"),
                        MedicationCheckin.scheduled_for.label("occurred_at"),
                        literal("medication_checkin").label("type"),
                    ).where(MedicationCheckin.patient_id == patient.id),
                ),
                (
                    "activity",
                    select(
                        ActivityRecord.id.label("id"),
                        ActivityRecord.occurred_at.label("occurred_at"),
                        literal("activity").label("type"),
                    ).where(
                        ActivityRecord.patient_id == patient.id, ActivityRecord.deleted_at.is_(None)
                    ),
                ),
                (
                    "mood",
                    select(
                        MoodRecord.id.label("id"),
                        MoodRecord.occurred_at.label("occurred_at"),
                        literal("mood").label("type"),
                    ).where(
                        MoodRecord.patient_id == patient.id,
                        MoodRecord.deleted_at.is_(None),
                    ),
                ),
                (
                    "advice",
                    select(
                        HealthAdvice.id.label("id"),
                        HealthAdvice.created_at.label("occurred_at"),
                        literal("advice").label("type"),
                    ).where(
                        HealthAdvice.patient_id == patient.id, HealthAdvice.archived_at.is_(None)
                    ),
                ),
            ]
            allowed = {key for key, _ in category_sources}
            if categories and set(categories) - allowed:
                raise Problem(422, "VALIDATION_ERROR", "Unsupported timeline category")
            sources = [
                query for key, query in category_sources if not categories or key in categories
            ]
            cte = union_all(*sources).cte("timeline")
            query = select(cte.c.id, cte.c.occurred_at, cte.c.type)
            if since:
                query = query.where(cte.c.occurred_at >= since)
            if until:
                query = query.where(cte.c.occurred_at < until)
            if cursor:
                data = self._decode(cursor)
                self._check_filters(
                    data,
                    {
                        "since": self._time_filter(since),
                        "until": self._time_filter(until),
                        "categories": sorted(set(categories)) if categories else None,
                    },
                )
                try:
                    stamp, category, ident = (
                        datetime.fromisoformat(data["occurred_at"]),
                        data["type"],
                        UUID(data["id"]),
                    )
                    if stamp.tzinfo is None or category not in allowed:
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    raise Problem(400, "INVALID_CURSOR", "History cursor is invalid") from None
                query = query.where(
                    or_(
                        cte.c.occurred_at < stamp,
                        and_(cte.c.occurred_at == stamp, cte.c.type > category),
                        and_(cte.c.occurred_at == stamp, cte.c.type == category, cte.c.id > ident),
                    )
                )
            rows = db.execute(
                query.order_by(desc(cte.c.occurred_at), cte.c.type, cte.c.id).limit(limit + 1)
            ).all()
            more = len(rows) > limit
            rows = rows[:limit]
            items = [
                {
                    "id": str(r.id),
                    "type": r.type,
                    "occurred_at": r.occurred_at.isoformat(),
                    "target": {
                        "type": {
                            "diet": "diet_record",
                            "stool": "stool_record",
                            "symptom": "symptom_record",
                            "medication_checkin": "medication_checkin",
                            "activity": "activity_record",
                            "mood": "mood_record",
                            "advice": "advice",
                        }[r.type],
                        "id": str(r.id),
                    },
                }
                for r in rows
            ]
            return {
                "items": items,
                "next_cursor": self._encode(
                    {
                        "occurred_at": rows[-1].occurred_at.astimezone(UTC).isoformat(),
                        "type": rows[-1].type,
                        "id": str(rows[-1].id),
                        "filters": {
                            "since": self._time_filter(since),
                            "until": self._time_filter(until),
                            "categories": sorted(set(categories)) if categories else None,
                        },
                    }
                )
                if more and rows
                else None,
            }

    def trends(
        self, context: AuthContext, start: datetime, end: datetime, bucket: str
    ) -> dict[str, Any]:
        with self._sessions.begin() as db:
            profile = self._patient(db, context)
            if (
                start.tzinfo is None
                or end.tzinfo is None
                or end <= start
                or bucket not in {"day", "week"}
            ):
                raise Problem(422, "VALIDATION_ERROR", "Invalid trend range or bucket")
            # Each aggregate is executed by PostgreSQL; records are never materialized in Python.
            bucket_expr = func.date_trunc(
                bucket, func.timezone(profile.timezone, ActivityRecord.occurred_at)
            )
            stmt = (
                select(
                    bucket_expr.label("bucket"),
                    func.count().label("record_count"),
                    func.coalesce(func.sum(ActivityRecord.duration_minutes), 0).label("duration"),
                )
                .where(
                    ActivityRecord.patient_id == profile.id,
                    ActivityRecord.deleted_at.is_(None),
                    ActivityRecord.occurred_at >= start,
                    ActivityRecord.occurred_at < end,
                )
                .group_by(bucket_expr)
                .order_by(bucket_expr)
            )
            activity = [
                {
                    "bucket": row.bucket.isoformat(),
                    "count": row.record_count,
                    "duration_minutes": row.duration,
                }
                for row in db.execute(stmt)
            ]
            stool_bucket = func.date_trunc(
                bucket, func.timezone(profile.timezone, StoolRecord.occurred_at)
            )
            stool_stmt = (
                select(
                    stool_bucket.label("bucket"),
                    func.count().label("record_count"),
                    func.count()
                    .filter(
                        StoolRecord.bristol_type.is_not(None),
                        StoolRecord.confirmation_status == "confirmed",
                    )
                    .label("bristol_confirmed"),
                    func.count()
                    .filter(
                        or_(
                            StoolRecord.bristol_type.is_(None),
                            StoolRecord.confirmation_status != "confirmed",
                        )
                    )
                    .label("bristol_unknown"),
                )
                .where(
                    StoolRecord.patient_id == profile.id,
                    StoolRecord.deleted_at.is_(None),
                    StoolRecord.occurred_at >= start,
                    StoolRecord.occurred_at < end,
                )
                .group_by(stool_bucket)
                .order_by(stool_bucket)
            )
            stool = [
                {
                    "bucket": row.bucket.isoformat(),
                    "has_data": row.record_count > 0,
                    "count": row.record_count,
                    "bristol_confirmed_count": row.bristol_confirmed,
                    "bristol_unknown_count": row.bristol_unknown,
                }
                for row in db.execute(stool_stmt)
            ]
            symptom_bucket = func.date_trunc(
                bucket, func.timezone(profile.timezone, SymptomRecord.occurred_at)
            )
            symptom_stmt = (
                select(
                    symptom_bucket.label("bucket"),
                    func.count(func.distinct(SymptomRecord.id)).label("record_count"),
                    func.avg(SymptomItem.severity).label("mean_severity"),
                    SymptomRecord.symptom_status.label("status"),
                )
                .join(
                    SymptomItem,
                    and_(
                        SymptomItem.symptom_record_id == SymptomRecord.id,
                        SymptomItem.patient_id == SymptomRecord.patient_id,
                    ),
                )
                .where(
                    SymptomRecord.patient_id == profile.id,
                    SymptomRecord.deleted_at.is_(None),
                    SymptomRecord.occurred_at >= start,
                    SymptomRecord.occurred_at < end,
                )
                .group_by(symptom_bucket, SymptomRecord.symptom_status)
                .order_by(symptom_bucket, SymptomRecord.symptom_status)
            )
            symptom_rows = list(db.execute(symptom_stmt))
            symptom = [
                {
                    "bucket": row.bucket.isoformat(),
                    "has_data": True,
                    "count": row.record_count,
                    "mean_severity": float(row.mean_severity)
                    if row.mean_severity is not None
                    else None,
                    "status": row.status,
                }
                for row in symptom_rows
            ]
            diet_bucket = func.date_trunc(
                bucket, func.timezone(profile.timezone, DietRecord.occurred_at)
            )
            diet_stmt = (
                select(
                    diet_bucket.label("bucket"),
                    DietItem.category_code.label("category"),
                    func.count().label("record_count"),
                )
                .join(
                    DietItem,
                    and_(
                        DietItem.diet_record_id == DietRecord.id,
                        DietItem.patient_id == DietRecord.patient_id,
                    ),
                )
                .where(
                    DietRecord.patient_id == profile.id,
                    DietRecord.deleted_at.is_(None),
                    DietRecord.occurred_at >= start,
                    DietRecord.occurred_at < end,
                    DietItem.confirmed_by_patient.is_(True),
                )
                .group_by(diet_bucket, DietItem.category_code)
                .order_by(diet_bucket, DietItem.category_code)
            )
            diet = [
                {
                    "bucket": row.bucket.isoformat(),
                    "category": row.category,
                    "count": row.record_count,
                }
                for row in db.execute(diet_stmt)
            ]
            checkin_bucket = func.date_trunc(
                bucket, func.timezone(profile.timezone, MedicationCheckin.scheduled_for)
            )
            med_stmt = (
                select(
                    checkin_bucket.label("bucket"),
                    MedicationCheckin.status.label("status"),
                    func.count().label("record_count"),
                )
                .where(
                    MedicationCheckin.patient_id == profile.id,
                    MedicationCheckin.scheduled_for >= start,
                    MedicationCheckin.scheduled_for < end,
                )
                .group_by(checkin_bucket, MedicationCheckin.status)
                .order_by(checkin_bucket, MedicationCheckin.status)
            )
            medications = [
                {"bucket": row.bucket.isoformat(), "status": row.status, "count": row.record_count}
                for row in db.execute(med_stmt)
            ]
            # Serialize the consent snapshot and mood aggregate with consent withdrawal.
            # This uses the same patient fence as AuthService.record_consent, but shared so
            # concurrent patient reads can proceed together.
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended("
                    "'gutcare.patient-consent-fence:' || :patient_id, 0))"
                ),
                {"patient_id": str(profile.id)},
            )
            consent_rows = db.execute(
                text(
                    "SELECT DISTINCT ON (consent_type) consent_type, granted "
                    "FROM health.patient_consent WHERE patient_id=:patient "
                    "AND consent_type IN ('health_data_processing','mood_data_processing') "
                    "ORDER BY consent_type, decided_at DESC, id DESC"
                ),
                {"patient": profile.id},
            ).all()
            current_consents = {row.consent_type: row.granted for row in consent_rows}
            missing_consents = [
                kind
                for kind in ("health_data_processing", "mood_data_processing")
                if not current_consents.get(kind, False)
            ]
            if missing_consents:
                mood: dict[str, Any] = {
                    "availability": "consent_required",
                    "reason_code": "CONSENT_REQUIRED",
                    "missing_consents": missing_consents,
                }
            else:
                mood_bucket = func.date_trunc(
                    bucket, func.timezone(profile.timezone, MoodRecord.occurred_at)
                )
                mood_stmt = (
                    select(
                        mood_bucket.label("period_start"),
                        (mood_bucket + text("interval '1 day'")).label("day_end"),
                        func.count().label("record_count"),
                        *[
                            func.count()
                            .filter(MoodRecord.mood_level == level)
                            .label(f"level_{level}")
                            for level in range(1, 6)
                        ],
                    )
                    .where(
                        MoodRecord.patient_id == profile.id,
                        MoodRecord.deleted_at.is_(None),
                        MoodRecord.occurred_at >= start,
                        MoodRecord.occurred_at < end,
                    )
                    .group_by(mood_bucket)
                    .order_by(mood_bucket)
                )
                mood_buckets = []
                for row in db.execute(mood_stmt):
                    period_start = row.period_start.date()
                    period_end = (
                        row.day_end.date() if bucket == "day" else period_start + timedelta(days=7)
                    )
                    counts = {str(level): getattr(row, f"level_{level}") for level in range(1, 6)}
                    mood_buckets.append(
                        {
                            "period_start": period_start.isoformat(),
                            "period_end": period_end.isoformat(),
                            "has_data": row.record_count > 0,
                            "record_count": row.record_count,
                            "mood_level_counts": counts,
                        }
                    )
                mood = {"availability": "available", "buckets": mood_buckets}
            return {
                "timezone": profile.timezone,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "bucket": bucket,
                "activity": {"has_data": bool(activity), "items": activity},
                "stool": {"has_data": bool(stool), "items": stool},
                "symptom": {"has_data": bool(symptom), "items": symptom},
                "diet_confirmed_categories": {"has_data": bool(diet), "items": diet},
                "medication_checkins": {"has_data": bool(medications), "items": medications},
                "mood": mood,
            }

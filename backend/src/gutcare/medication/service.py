"""Application services and deterministic recurrence expansion for F06."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from gutcare.auth.models import PatientProfile
from gutcare.auth.service import AuthContext
from gutcare.files.models import MedicalDocument
from gutcare.medication.models import (
    MedicationCheckin,
    MedicationIdempotency,
    MedicationPlan,
    MedicationSchedule,
    MedicationSourceRef,
)
from gutcare.shared.errors import Problem

DAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
RRULE_PART = re.compile(r"^([A-Z]+)=([A-Z0-9,]+)$")


def parse_rrule(value: str | None) -> dict[str, Any]:
    if value is None or value.strip() == "":
        return {"FREQ": "DAILY", "INTERVAL": 1}
    if not isinstance(value, str) or len(value) > 256 or value.startswith("RRULE:"):
        raise Problem(422, "VALIDATION_ERROR", "Invalid recurrence rule")
    result: dict[str, Any] = {}
    for part in value.split(";"):
        match = RRULE_PART.fullmatch(part)
        if match is None or match.group(1) in result:
            raise Problem(422, "VALIDATION_ERROR", "Invalid recurrence rule")
        result[match.group(1)] = match.group(2)
    if set(result) - {"FREQ", "INTERVAL", "BYDAY", "COUNT", "UNTIL"}:
        raise Problem(422, "VALIDATION_ERROR", "Unsupported recurrence rule field")
    freq = result.get("FREQ")
    if freq not in {"DAILY", "WEEKLY"}:
        raise Problem(422, "VALIDATION_ERROR", "FREQ must be DAILY or WEEKLY")
    interval = result.get("INTERVAL", "1")
    if not interval.isdigit() or not 1 <= int(interval) <= 365:
        raise Problem(422, "VALIDATION_ERROR", "INTERVAL must be between 1 and 365")
    result["INTERVAL"] = int(interval)
    if "BYDAY" in result:
        days = result["BYDAY"].split(",")
        if (
            freq != "WEEKLY"
            or not days
            or any(day not in DAY_CODES for day in days)
            or len(set(days)) != len(days)
        ):
            raise Problem(422, "VALIDATION_ERROR", "BYDAY is only supported for WEEKLY")
        result["BYDAY"] = {DAY_CODES[day] for day in days}
    if "COUNT" in result:
        if (
            not result["COUNT"].isdigit()
            or not 1 <= int(result["COUNT"]) <= 10000
            or "UNTIL" in result
        ):
            raise Problem(
                422, "VALIDATION_ERROR", "COUNT must be 1..10000 and cannot combine with UNTIL"
            )
        result["COUNT"] = int(result["COUNT"])
    if "UNTIL" in result:
        try:
            result["UNTIL"] = datetime.strptime(result["UNTIL"], "%Y%m%d").date()
        except ValueError as exc:
            raise Problem(422, "VALIDATION_ERROR", "UNTIL must be YYYYMMDD") from exc
    return result


def occurrence_dates(rule: dict[str, Any], start: date, end: date) -> list[date]:
    dates: list[date] = []
    until = rule.get("UNTIL")
    maximum = min(end, until) if isinstance(until, date) else end
    count = rule.get("COUNT")
    day_filter: set[int] = (
        rule.get("BYDAY", {start.weekday()}) if rule["FREQ"] == "WEEKLY" else set()
    )
    day = start
    while day <= maximum and (count is None or len(dates) < count):
        elapsed = (day - start).days
        include = False
        if rule["FREQ"] == "DAILY":
            include = elapsed % rule["INTERVAL"] == 0
        else:
            weeks = elapsed // 7
            include = weeks % rule["INTERVAL"] == 0 and day.weekday() in day_filter
        if include:
            dates.append(day)
        day += timedelta(days=1)
    return dates


def resolve_local_datetime(day: date, clock: time, timezone_name: str) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise Problem(422, "VALIDATION_ERROR", "timezone must be a valid IANA timezone") from exc
    local = datetime.combine(day, clock.replace(tzinfo=None))
    for minute in range(181):
        candidate = local + timedelta(minutes=minute)
        first = candidate.replace(tzinfo=zone, fold=0)
        if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == candidate:
            return first
        second = candidate.replace(tzinfo=zone, fold=1)
        if second.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == candidate:
            return second
    raise Problem(422, "VALIDATION_ERROR", "Local time cannot be resolved in timezone")


class MedicationService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    @staticmethod
    def _scope(session: Session, patient_id: UUID) -> None:
        session.execute(
            text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(patient_id)}
        )

    @classmethod
    def _patient(cls, session: Session, context: AuthContext) -> UUID:
        session.execute(
            text("SELECT set_config('app.user_id', :id, true)"), {"id": str(context.user_id)}
        )
        profile = session.scalar(
            select(PatientProfile).where(
                PatientProfile.user_id == context.user_id, PatientProfile.deleted_at.is_(None)
            )
        )
        if profile is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        cls._scope(session, profile.id)
        return profile.id

    @staticmethod
    def _dto(row: Any, source_ref: MedicationSourceRef | None = None) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "patient_id": str(row.patient_id),
            "medication_name": row.medication_name,
            "dosage_text": row.dosage_text,
            "route_code": row.route_code,
            "start_date": row.start_date.isoformat() if row.start_date else None,
            "end_date": row.end_date.isoformat() if row.end_date else None,
            "source_type": row.source_type,
            "source_document_id": str(source_ref.live_document_id)
            if source_ref and source_ref.live_document_id
            else None,
            "source_deleted": bool(source_ref and source_ref.source_deleted_at),
            "confirmation_status": row.confirmation_status,
            "plan_status": row.plan_status,
            "record_version": row.record_version,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    @staticmethod
    def _schedule_dto(row: MedicationSchedule) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "plan_id": str(row.plan_id),
            "local_time": row.local_time.isoformat(),
            "timezone": row.timezone,
            "rrule": row.rrule,
            "valid_from": row.valid_from.isoformat(),
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            "enabled": row.enabled,
            "record_version": row.record_version,
        }

    @staticmethod
    def _checkin_dto(row: MedicationCheckin) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "schedule_id": str(row.schedule_id),
            "local_date": row.local_date.isoformat(),
            "scheduled_for": row.scheduled_for.isoformat(),
            "status": row.status,
            "taken_at": row.taken_at.isoformat() if row.taken_at else None,
            "note": row.note,
            "record_version": row.record_version,
        }

    def _idempotent(
        self,
        session: Session,
        patient_id: UUID,
        route: str,
        key: str,
        payload: dict[str, Any],
        model: Any,
    ) -> Any | None:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"{patient_id}:{route}:{key}"},
        )
        prior = session.scalar(
            select(MedicationIdempotency)
            .where(
                MedicationIdempotency.patient_id == patient_id,
                MedicationIdempotency.route == route,
                MedicationIdempotency.idempotency_key == key,
            )
            .with_for_update()
        )
        if prior:
            if prior.request_hash != digest:
                raise Problem(
                    409, "IDEMPOTENCY_CONFLICT", "Idempotency key was used with different content"
                )
            return prior.response_snapshot
        return digest

    @classmethod
    def _plan_dto(cls, session: Session, row: MedicationPlan) -> dict[str, Any]:
        source = (
            session.scalar(
                select(MedicationSourceRef).where(
                    MedicationSourceRef.id == row.source_ref_id,
                    MedicationSourceRef.patient_id == row.patient_id,
                )
            )
            if row.source_ref_id
            else None
        )
        return cls._dto(row, source)

    def create_plan(
        self, context: AuthContext, payload: dict[str, Any], key: str
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            patient_id = self._patient(session, context)
            digest = self._idempotent(
                session, patient_id, "POST:/medication-plans", key, payload, MedicationPlan
            )
            if not isinstance(digest, str):
                if digest is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                return cast(dict[str, Any], digest)
            source_ref_id = None
            if payload["source_type"] == "medical_document":
                doc = session.scalar(
                    select(MedicalDocument).where(
                        MedicalDocument.id == payload["source_document_id"],
                        MedicalDocument.patient_id == patient_id,
                        MedicalDocument.deleted_at.is_(None),
                    )
                )
                if doc is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                source_ref = session.scalar(
                    select(MedicationSourceRef).where(
                        MedicationSourceRef.patient_id == patient_id,
                        MedicationSourceRef.original_document_id == doc.id,
                    )
                )
                if source_ref is None:
                    source_ref = MedicationSourceRef(
                        patient_id=patient_id,
                        source_kind="medical_document",
                        original_document_id=doc.id,
                        live_document_id=doc.id,
                    )
                    session.add(source_ref)
                    session.flush()
                source_ref_id = source_ref.id
            row = MedicationPlan(
                patient_id=patient_id,
                source_type=payload["source_type"],
                source_ref_id=source_ref_id,
                medication_name=payload["medication_name"],
                dosage_text=payload.get("dosage_text"),
                route_code=payload.get("route_code"),
                start_date=payload.get("start_date"),
                end_date=payload.get("end_date"),
                confirmation_status="pending",
                plan_status="discontinued",
                record_version=1,
            )
            session.add(row)
            session.flush()
            response = self._plan_dto(session, row)
            session.add(
                MedicationIdempotency(
                    patient_id=patient_id,
                    route="POST:/medication-plans",
                    idempotency_key=key,
                    request_hash=digest,
                    resource_id=row.id,
                    response_snapshot=response,
                    response_status=201,
                )
            )
            session.flush()
            return response

    def list_plans(self, context: AuthContext) -> list[dict[str, Any]]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            return [
                self._plan_dto(session, x)
                for x in session.scalars(
                    select(MedicationPlan)
                    .where(MedicationPlan.patient_id == pid, MedicationPlan.deleted_at.is_(None))
                    .order_by(MedicationPlan.created_at.desc())
                ).all()
            ]

    def get_plan(self, context: AuthContext, plan_id: UUID) -> dict[str, Any]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            row = session.scalar(
                select(MedicationPlan).where(
                    MedicationPlan.id == plan_id,
                    MedicationPlan.patient_id == pid,
                    MedicationPlan.deleted_at.is_(None),
                )
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._plan_dto(session, row)

    def list_schedules(self, context: AuthContext, plan_id: UUID) -> list[dict[str, Any]]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            plan = session.scalar(
                select(MedicationPlan).where(
                    MedicationPlan.id == plan_id,
                    MedicationPlan.patient_id == pid,
                    MedicationPlan.deleted_at.is_(None),
                )
            )
            if plan is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            rows = session.scalars(
                select(MedicationSchedule)
                .where(
                    MedicationSchedule.plan_id == plan_id,
                    MedicationSchedule.patient_id == pid,
                    MedicationSchedule.deleted_at.is_(None),
                )
                .order_by(MedicationSchedule.local_time)
            ).all()
            return [self._schedule_dto(row) for row in rows]

    def patch_plan(
        self, context: AuthContext, plan_id: UUID, version: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            row = session.scalar(
                select(MedicationPlan)
                .where(
                    MedicationPlan.id == plan_id,
                    MedicationPlan.patient_id == pid,
                    MedicationPlan.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            nullable = {"dosage_text", "route_code", "start_date", "end_date"}
            if any(
                name in payload and payload[name] is None
                for name in payload
                if name not in nullable
            ):
                raise Problem(422, "VALIDATION_ERROR", "Non-null plan fields cannot be null")
            start_date = payload.get("start_date", row.start_date)
            end_date = payload.get("end_date", row.end_date)
            if start_date and end_date and end_date < start_date:
                raise Problem(422, "VALIDATION_ERROR", "end_date must not precede start_date")
            for field in ("medication_name", "dosage_text", "route_code", "start_date", "end_date"):
                if field in payload:
                    setattr(row, field, payload[field])
            if payload.get("confirmation_status"):
                row.confirmation_status = payload["confirmation_status"]
            if row.plan_status == "active" and row.confirmation_status != "confirmed":
                raise Problem(409, "VALIDATION_ERROR", "Only confirmed plans can be active")
            row.record_version += 1
            row.updated_at = datetime.now(UTC)
            if "start_date" in payload or "end_date" in payload:
                self._skip_outside_plan_pending(session, pid, row)
            return self._plan_dto(session, row)

    def transition_plan(
        self, context: AuthContext, plan_id: UUID, version: int, action: str, key: str | None = None
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            route = f"POST:/medication-plans/{plan_id}/transitions"
            digest: str | None = None
            if key:
                prior = self._idempotent(
                    session,
                    pid,
                    route,
                    key,
                    {"record_version": version, "action": action},
                    MedicationPlan,
                )
                if not isinstance(prior, str):
                    if prior is None:
                        raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                    return cast(dict[str, Any], prior)
                digest = prior
            row = session.scalar(
                select(MedicationPlan)
                .where(
                    MedicationPlan.id == plan_id,
                    MedicationPlan.patient_id == pid,
                    MedicationPlan.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            if action == "activate":
                if row.confirmation_status != "confirmed":
                    raise Problem(
                        409, "VALIDATION_ERROR", "Plan must be confirmed before activation"
                    )
                row.plan_status = "active"
            elif action in {"end", "discontinue"}:
                row.plan_status = "ended" if action == "end" else "discontinued"
                self._skip_future_pending(session, pid, plan_id)
            elif action == "confirm":
                row.confirmation_status = "confirmed"
            elif action == "review":
                if row.plan_status == "active":
                    raise Problem(
                        409, "VALIDATION_ERROR", "End or discontinue the active plan before review"
                    )
                row.confirmation_status = "needs_review"
            else:
                raise Problem(422, "VALIDATION_ERROR", "Unsupported plan transition")
            row.record_version += 1
            row.updated_at = datetime.now(UTC)
            if key and digest:
                response = self._plan_dto(session, row)
                session.add(
                    MedicationIdempotency(
                        patient_id=pid,
                        route=route,
                        idempotency_key=key,
                        request_hash=digest,
                        resource_id=row.id,
                        response_snapshot=response,
                        response_status=200,
                    )
                )
                return response
            return self._plan_dto(session, row)

    def delete_plan(self, context: AuthContext, plan_id: UUID, version: int) -> None:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            row = session.scalar(
                select(MedicationPlan)
                .where(
                    MedicationPlan.id == plan_id,
                    MedicationPlan.patient_id == pid,
                    MedicationPlan.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            row.deleted_at = datetime.now(UTC)
            row.record_version += 1
            row.updated_at = datetime.now(UTC)
            self._skip_future_pending(session, pid, plan_id)

    @staticmethod
    def _skip_future_pending(session: Session, patient_id: UUID, plan_id: UUID) -> None:
        now = datetime.now(UTC)
        rows = session.scalars(
            select(MedicationCheckin)
            .join(
                MedicationSchedule,
                (MedicationSchedule.id == MedicationCheckin.schedule_id)
                & (MedicationSchedule.patient_id == MedicationCheckin.patient_id),
            )
            .where(
                MedicationSchedule.plan_id == plan_id,
                MedicationCheckin.patient_id == patient_id,
                MedicationCheckin.status == "pending",
                MedicationCheckin.scheduled_for > now,
            )
            .with_for_update()
        ).all()
        for checkin in rows:
            checkin.status = "skipped"
            checkin.record_version += 1
            checkin.updated_at = now

    @staticmethod
    def _skip_outside_plan_pending(
        session: Session, patient_id: UUID, plan: MedicationPlan
    ) -> None:
        now = datetime.now(UTC)
        rows = session.scalars(
            select(MedicationCheckin)
            .join(
                MedicationSchedule,
                (MedicationSchedule.id == MedicationCheckin.schedule_id)
                & (MedicationSchedule.patient_id == MedicationCheckin.patient_id),
            )
            .where(
                MedicationSchedule.plan_id == plan.id,
                MedicationCheckin.patient_id == patient_id,
                MedicationCheckin.status == "pending",
                MedicationCheckin.scheduled_for > now,
            )
            .with_for_update()
        ).all()
        for checkin in rows:
            outside = (plan.start_date is not None and checkin.local_date < plan.start_date) or (
                plan.end_date is not None and checkin.local_date > plan.end_date
            )
            if outside:
                checkin.status = "skipped"
                checkin.record_version += 1
                checkin.updated_at = now

    def save_schedule(
        self,
        context: AuthContext,
        plan_id: UUID | None,
        schedule_id: UUID | None,
        version: int | None,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            route = f"POST:/medication-plans/{plan_id}/schedules" if plan_id else ""
            digest: str | None = None
            if idempotency_key and plan_id and not schedule_id:
                prior = self._idempotent(
                    session,
                    pid,
                    route,
                    idempotency_key,
                    payload,
                    MedicationSchedule,
                )
                if not isinstance(prior, str):
                    if prior is None:
                        raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                    return cast(dict[str, Any], prior)
                digest = prior
            plan = (
                session.scalar(
                    select(MedicationPlan).where(
                        MedicationPlan.id == plan_id,
                        MedicationPlan.patient_id == pid,
                        MedicationPlan.deleted_at.is_(None),
                    )
                )
                if plan_id
                else None
            )
            if plan_id and plan is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            parse_rrule(payload.get("rrule"))
            try:
                ZoneInfo(payload["timezone"])
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise Problem(
                    422, "VALIDATION_ERROR", "timezone must be a valid IANA timezone"
                ) from exc
            if schedule_id:
                row = session.scalar(
                    select(MedicationSchedule)
                    .where(
                        MedicationSchedule.id == schedule_id,
                        MedicationSchedule.patient_id == pid,
                        MedicationSchedule.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
                if row is None:
                    raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
                if row.record_version != version:
                    raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            else:
                assert plan is not None
                row = MedicationSchedule(plan_id=plan_id, patient_id=pid, record_version=1)
                session.add(row)
            for field in ("local_time", "timezone", "rrule", "valid_from", "valid_to", "enabled"):
                setattr(row, field, payload.get(field))
            row.record_version += 0 if not schedule_id else 1
            row.updated_at = datetime.now(UTC)
            session.flush()
            response = self._schedule_dto(row)
            if idempotency_key and digest:
                session.add(
                    MedicationIdempotency(
                        patient_id=pid,
                        route=route,
                        idempotency_key=idempotency_key,
                        request_hash=digest,
                        resource_id=row.id,
                        response_snapshot=response,
                        response_status=201,
                    )
                )
            if schedule_id:
                changed_at = datetime.now(UTC)
                pending = session.scalars(
                    select(MedicationCheckin)
                    .where(
                        MedicationCheckin.schedule_id == row.id,
                        MedicationCheckin.status == "pending",
                        MedicationCheckin.scheduled_for > changed_at,
                    )
                    .with_for_update()
                ).all()
                rules = parse_rrule(row.rrule)
                for checkin in pending:
                    active_day = (
                        row.enabled
                        and checkin.local_date >= row.valid_from
                        and (row.valid_to is None or checkin.local_date <= row.valid_to)
                    )
                    if active_day and checkin.local_date in occurrence_dates(
                        rules, row.valid_from, checkin.local_date
                    ):
                        checkin.scheduled_for = resolve_local_datetime(
                            checkin.local_date, row.local_time, row.timezone
                        ).astimezone(UTC)
                    else:
                        checkin.status = "skipped"
                        checkin.record_version += 1
                    checkin.updated_at = changed_at
            return response

    def delete_schedule(self, context: AuthContext, schedule_id: UUID, version: int) -> None:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            row = session.scalar(
                select(MedicationSchedule)
                .where(
                    MedicationSchedule.id == schedule_id,
                    MedicationSchedule.patient_id == pid,
                    MedicationSchedule.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            row.enabled = False
            row.deleted_at = datetime.now(UTC)
            row.record_version += 1
            now = datetime.now(UTC)
            pending = session.scalars(
                select(MedicationCheckin)
                .where(
                    MedicationCheckin.schedule_id == schedule_id,
                    MedicationCheckin.patient_id == pid,
                    MedicationCheckin.status == "pending",
                    MedicationCheckin.scheduled_for > now,
                )
                .with_for_update()
            ).all()
            for checkin in pending:
                checkin.status = "skipped"
                checkin.record_version += 1
                checkin.updated_at = now

    def list_checkins(self, context: AuthContext, start: date, end: date) -> list[dict[str, Any]]:
        if end < start or (end - start).days > 92:
            raise Problem(422, "VALIDATION_ERROR", "Date range must be at most 93 days")
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            rows = session.scalars(
                select(MedicationCheckin)
                .where(
                    MedicationCheckin.patient_id == pid,
                    MedicationCheckin.local_date >= start,
                    MedicationCheckin.local_date <= end,
                )
                .order_by(MedicationCheckin.scheduled_for)
            ).all()
            return [self._checkin_dto(x) for x in rows]

    def list_today_checkins(self, context: AuthContext) -> list[dict[str, Any]]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            profile = session.get(PatientProfile, pid)
            if profile is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            local_today = datetime.now(ZoneInfo(profile.timezone)).date()
            rows = session.scalars(
                select(MedicationCheckin)
                .where(
                    MedicationCheckin.patient_id == pid, MedicationCheckin.local_date == local_today
                )
                .order_by(MedicationCheckin.scheduled_for)
            ).all()
            return [self._checkin_dto(x) for x in rows]

    def update_checkin(
        self, context: AuthContext, checkin_id: UUID, version: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            pid = self._patient(session, context)
            row = session.scalar(
                select(MedicationCheckin)
                .where(MedicationCheckin.id == checkin_id, MedicationCheckin.patient_id == pid)
                .with_for_update()
            )
            if row is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if row.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            row.status = payload["status"]
            row.taken_at = payload.get("taken_at") if row.status == "taken" else None
            row.note = payload.get("note")
            row.updated_at = datetime.now(UTC)
            row.record_version += 1
            return self._checkin_dto(row)


def materialize(
    session_factory: sessionmaker[Session], today: date | None = None, horizon_days: int = 14
) -> int:
    """Idempotently generate the finite forward window; repeat invocation recovers safely."""
    if not 1 <= horizon_days <= 31:
        raise ValueError("horizon_days must be between 1 and 31")
    current = today or datetime.now(UTC).date()
    created = 0
    with session_factory.begin() as session:
        plans = session.scalars(
            select(MedicationPlan).where(
                MedicationPlan.deleted_at.is_(None),
                MedicationPlan.plan_status == "active",
                MedicationPlan.confirmation_status == "confirmed",
            )
        ).all()
        for plan in plans:
            lock_result = session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"medication-materialize:{plan.id}"},
            )
            if not lock_result:
                continue
            session.execute(
                text("SELECT set_config('app.patient_id', :id, true)"), {"id": str(plan.patient_id)}
            )
            schedules = session.scalars(
                select(MedicationSchedule).where(
                    MedicationSchedule.plan_id == plan.id,
                    MedicationSchedule.patient_id == plan.patient_id,
                    MedicationSchedule.enabled.is_(True),
                    MedicationSchedule.deleted_at.is_(None),
                )
            ).all()
            for schedule in schedules:
                rule = parse_rrule(schedule.rrule)
                low = max(current, schedule.valid_from, plan.start_date or schedule.valid_from)
                high = min(
                    current + timedelta(days=horizon_days),
                    schedule.valid_to or current + timedelta(days=horizon_days),
                    plan.end_date or current + timedelta(days=horizon_days),
                )
                if high < low:
                    continue
                for local_day in occurrence_dates(rule, schedule.valid_from, high):
                    if local_day < low:
                        continue
                    instant = resolve_local_datetime(
                        local_day, schedule.local_time, schedule.timezone
                    ).astimezone(UTC)
                    result = cast(
                        CursorResult[Any],
                        session.execute(
                            text(
                                "INSERT INTO health.medication_checkin "
                                "(schedule_id,patient_id,local_date,scheduled_for,status) "
                                "VALUES (:s,:p,:d,:t,'pending') "
                                "ON CONFLICT (schedule_id,local_date) DO NOTHING"
                            ),
                            {
                                "s": schedule.id,
                                "p": plan.patient_id,
                                "d": local_day,
                                "t": instant,
                            },
                        ),
                    )
                    created += result.rowcount or 0
    return created

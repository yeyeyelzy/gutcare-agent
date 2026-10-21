"""Patient scoped record CRUD and deterministic rule evaluation."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import math
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64DecodeError
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from gutcare.auth.models import PatientProfile
from gutcare.auth.service import AuthContext
from gutcare.records.models import (
    AlertEvidence,
    DietItem,
    DietRecord,
    RecordIdempotency,
    RiskAlert,
    RiskRule,
    StoolRecord,
    SymptomItem,
    SymptomRecord,
    SymptomStatusEvent,
)
from gutcare.shared.errors import Problem

logger = structlog.get_logger("gutcare.records")
TYPES: dict[str, type[Any]] = {
    "diet-records": DietRecord,
    "stool-records": StoolRecord,
    "symptom-records": SymptomRecord,
}
RISK_TYPES = {"stool-records", "symptom-records"}
SYMPTOM_CODES = {
    "abdominal_pain",
    "bloating",
    "diarrhea",
    "constipation",
    "nausea",
    "vomiting",
    "acid_reflux",
    "appetite_change",
    "blood_in_stool_concern",
    "other",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _cursor_encode(occurred_at: datetime, resource_id: UUID) -> str:
    raw = f"{occurred_at.isoformat()}|{resource_id}".encode("ascii")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _cursor_decode(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("ascii")
        time_value, id_value = raw.split("|", 1)
        occurred_at = datetime.fromisoformat(time_value)
        if occurred_at.tzinfo is None:
            raise ValueError
        return occurred_at, UUID(id_value)
    except (ValueError, UnicodeError, Base64DecodeError) as exc:
        raise Problem(422, "VALIDATION_ERROR", "Invalid cursor") from exc


RULE_FIELDS = {
    "record_type",
    "bristol_type",
    "blood_reported",
    "urgency_level",
    "duration_minutes",
    "symptom_codes",
    "symptom_severities",
}


def build_risk_facts(record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Project the patient DTO into only explicitly confirmed, typed rule facts."""
    if record_type not in TYPES:
        raise ValueError("unknown record type for risk evaluation")
    facts: dict[str, Any] = {"record_type": record_type}
    if record_type == "stool-records":
        bristol = payload.get("bristol_type")
        if bristol is not None:
            if isinstance(bristol, bool) or not isinstance(bristol, int) or not 1 <= bristol <= 7:
                raise ValueError("invalid bristol_type risk fact")
            facts["bristol_type"] = bristol
        reported = payload.get("blood_reported")
        if reported is not None:
            if not isinstance(reported, bool):
                raise ValueError("invalid blood_reported risk fact")
            facts["blood_reported"] = reported
        urgency = payload.get("urgency_level")
        if urgency is not None:
            if isinstance(urgency, bool) or not isinstance(urgency, int) or not 0 <= urgency <= 10:
                raise ValueError("invalid urgency_level risk fact")
            facts["urgency_level"] = urgency
    elif record_type == "symptom-records":
        duration = payload.get("duration_minutes")
        if duration is not None:
            if (
                isinstance(duration, bool)
                or not isinstance(duration, int)
                or not 0 <= duration <= 10080
            ):
                raise ValueError("invalid duration_minutes risk fact")
            facts["duration_minutes"] = duration
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError("invalid symptom items risk fact")
        codes: list[str] = []
        severities: list[int] = []
        for item in items:
            if not isinstance(item, dict) or item.get("symptom_code") not in SYMPTOM_CODES:
                raise ValueError("invalid symptom code risk fact")
            codes.append(item["symptom_code"])
            severity = item.get("severity")
            if severity is not None:
                if (
                    isinstance(severity, bool)
                    or not isinstance(severity, int)
                    or not 0 <= severity <= 10
                ):
                    raise ValueError("invalid symptom severity risk fact")
                severities.append(severity)
        facts["symptom_codes"] = codes
        facts["symptom_severities"] = severities
    return facts


def _numeric_compare(value: int | float, expected: int | float, op: str) -> bool:
    if op == "gt":
        return value > expected
    if op == "gte":
        return value >= expected
    if op == "lt":
        return value < expected
    return value <= expected


def evaluate_condition(node: Any, facts: dict[str, Any]) -> bool:
    """Evaluate the reviewed, bounded condition DSL; malformed rules are explicit errors."""
    if not isinstance(node, dict) or not node:
        raise ValueError("risk condition must be a non-empty object")
    combinators = set(node) & {"all", "any", "not"}
    if combinators:
        if len(combinators) != 1 or len(node) != 1:
            raise ValueError("risk condition must contain exactly one combinator")
        operator = next(iter(combinators))
        child = node[operator]
        if operator == "not":
            if not isinstance(child, dict):
                raise ValueError("not requires one condition object")
            return not evaluate_condition(child, facts)
        if not isinstance(child, list) or not child or any(not isinstance(x, dict) for x in child):
            raise ValueError(f"{operator} requires a non-empty list of condition objects")
        results = [evaluate_condition(x, facts) for x in child]
        return all(results) if operator == "all" else any(results)

    if set(node) not in ({"field", "op"}, {"field", "op", "value"}):
        raise ValueError("risk condition leaf has unknown or missing keys")
    field, op = node.get("field"), node.get("op")
    if not isinstance(field, str) or field not in RULE_FIELDS:
        raise ValueError("risk condition uses a non-allowlisted field")
    allowed_ops = {"eq", "in", "exists", "gt", "gte", "lt", "lte"}
    if (
        not isinstance(op, str)
        or op not in allowed_ops
        or (op == "exists") != ("value" not in node)
    ):
        raise ValueError("risk condition uses an invalid operator/value shape")
    value = facts.get(field)
    if op == "exists":
        return value is not None
    expected = node["value"]
    if op == "eq":
        return bool(value == expected)
    if op == "in":
        if not isinstance(expected, list):
            raise ValueError("in requires a list value")
        if isinstance(value, list):
            return any(item in expected for item in value)
        return bool(value in expected)
    if (
        isinstance(expected, bool)
        or not isinstance(expected, (int, float))
        or not math.isfinite(expected)
    ):
        raise ValueError("numeric comparison requires finite numeric operands")
    if isinstance(value, list):
        if any(
            isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
            for item in value
        ):
            raise ValueError("numeric comparison requires finite numeric operands")
        return any(_numeric_compare(item, expected, op) for item in value)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("numeric comparison requires finite numeric operands")
    return _numeric_compare(value, expected, op)


class RecordService:
    def __init__(
        self, sessions: sessionmaker[Session], *, allow_test_only_rules: bool = False
    ) -> None:
        self._sessions = sessions
        self._allow_test_only_rules = allow_test_only_rules

    @staticmethod
    def _scope(session: Session, patient_id: UUID) -> None:
        session.execute(
            text("SELECT set_config('app.patient_id', :patient_id, true)"),
            {"patient_id": str(patient_id)},
        )

    @staticmethod
    def _invalidate_record_image_requests(
        session: Session, patient_id: UUID, record_id: UUID
    ) -> None:
        session.execute(
            text("""UPDATE analysis.record_image_recognition_request
                SET status='invalidated', lease_until=NULL,
                    updated_at=now()
                WHERE patient_id=:patient_id AND record_id=:record_id
                  AND status IN ('pending','processing','candidates_ready')"""),
            {"patient_id": patient_id, "record_id": record_id},
        )
        session.execute(
            text("""UPDATE analysis.record_image_candidate
                SET status='invalidated', value='null'::jsonb, locator=NULL
                WHERE patient_id=:patient_id AND status='pending'
                  AND request_id IN (SELECT id FROM analysis.record_image_recognition_request
                    WHERE patient_id=:patient_id AND record_id=:record_id)"""),
            {"patient_id": patient_id, "record_id": record_id},
        )
        session.execute(
            text("""DELETE FROM analysis.record_image_capability
                WHERE patient_id=:patient_id AND request_id IN
                  (SELECT id FROM analysis.record_image_recognition_request
                   WHERE patient_id=:patient_id AND record_id=:record_id)"""),
            {"patient_id": patient_id, "record_id": record_id},
        )

    @staticmethod
    def _validate_image(
        session: Session, patient_id: UUID, record_type: str, payload: dict[str, Any]
    ) -> None:
        if "image_object_id" in payload:
            raise Problem(422, "VALIDATION_ERROR", "Use the record image attachment API")

    def _patient_id(self, session: Session, context: AuthContext) -> UUID:
        session.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(context.user_id)},
        )
        profile = session.scalar(
            select(PatientProfile).where(
                PatientProfile.user_id == context.user_id, PatientProfile.deleted_at.is_(None)
            )
        )
        if profile is None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        return profile.id

    @staticmethod
    def _validate(record_type: str, occurred_at: datetime, payload: dict[str, Any]) -> None:
        if record_type not in TYPES:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        if occurred_at.tzinfo is None:
            raise Problem(422, "VALIDATION_ERROR", "occurred_at must include a timezone")
        if record_type == "diet-records":
            text_value = payload.get("text_description")
            items = payload.get("items", [])
            if not (isinstance(text_value, str) and text_value.strip()) and not items:
                raise Problem(
                    422,
                    "VALIDATION_ERROR",
                    "Diet record needs a description or at least one food item",
                )
            if not isinstance(items, list) or any(
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not item["name"].strip()
                for item in items
            ):
                raise Problem(422, "VALIDATION_ERROR", "Invalid diet items")
        elif record_type == "stool-records":
            bristol = payload.get("bristol_type")
            if bristol is not None and (not isinstance(bristol, int) or not 1 <= bristol <= 7):
                raise Problem(422, "VALIDATION_ERROR", "bristol_type must be between 1 and 7")
        else:
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                raise Problem(
                    422, "VALIDATION_ERROR", "Symptom record needs at least one symptom item"
                )
            for item in items:
                if not isinstance(item, dict) or item.get("symptom_code") not in SYMPTOM_CODES:
                    raise Problem(422, "VALIDATION_ERROR", "Invalid symptom item")
                if (item["symptom_code"] == "other") != (
                    isinstance(item.get("other_description"), str)
                    and bool(item["other_description"].strip())
                ):
                    raise Problem(422, "VALIDATION_ERROR", "Invalid other symptom description")
                if item["symptom_code"] != "other" and item.get("other_description") is not None:
                    raise Problem(422, "VALIDATION_ERROR", "Unexpected other symptom description")
                severity = item.get("severity")
                if severity is not None and (
                    not isinstance(severity, int) or not 0 <= severity <= 10
                ):
                    raise Problem(
                        422, "VALIDATION_ERROR", "Symptom severity must be between 0 and 10"
                    )

    @staticmethod
    def _dto(
        obj: Any, record_type: str, items: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        payload = dict(obj.payload or {})
        if items is not None:
            payload["items"] = items
        for name in (
            "meal_type",
            "text_description",
            "portion_note",
            "bristol_type",
            "color_code",
            "blood_reported",
            "duration_minutes",
            "notes",
            "symptom_status",
        ):
            value = getattr(obj, name, None)
            if value is not None:
                payload[name] = value
        return {
            "id": str(obj.id),
            "occurred_at": obj.occurred_at.isoformat(),
            "payload": payload,
            "record_version": obj.record_version,
            "created_at": obj.created_at.isoformat(),
            "updated_at": obj.updated_at.isoformat(),
        }

    def _items(
        self, session: Session, record_type: str, obj: Any, patient_id: UUID
    ) -> list[dict[str, Any]] | None:
        if record_type == "diet-records":
            diet_rows = session.scalars(
                select(DietItem)
                .where(DietItem.patient_id == patient_id, DietItem.diet_record_id == obj.id)
                .order_by(DietItem.item_position)
            ).all()
            return [
                {
                    "name": x.name,
                    "category_code": x.category_code,
                    "amount_text": x.amount_text,
                    "source_type": x.source_type,
                    "confirmed_by_patient": x.confirmed_by_patient,
                }
                for x in diet_rows
            ]
        if record_type == "symptom-records":
            symptom_rows = session.scalars(
                select(SymptomItem).where(
                    SymptomItem.patient_id == patient_id, SymptomItem.symptom_record_id == obj.id
                )
            ).all()
            return [
                {
                    "symptom_code": x.symptom_code,
                    "severity": x.severity,
                    "body_location": x.body_location,
                    "other_description": x.other_description,
                    "patient_confirmed": x.patient_confirmed,
                }
                for x in symptom_rows
            ]
        return None

    def _replace_items(
        self,
        session: Session,
        record_type: str,
        obj: Any,
        patient_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        if record_type == "diet-records":
            session.query(DietItem).filter_by(patient_id=patient_id, diet_record_id=obj.id).delete()
            for position, item in enumerate(payload.get("items", [])):
                session.add(
                    DietItem(
                        diet_record_id=obj.id,
                        patient_id=patient_id,
                        name=item["name"].strip(),
                        item_position=position,
                        category_code=item.get("category_code"),
                        amount_text=item.get("amount_text"),
                        source_type=item.get("source_type", "patient_manual"),
                        confirmed_by_patient=item.get("confirmed_by_patient", True),
                        source_recognition_request_id=None,
                        source_candidate_group_key=None,
                    )
                )
        elif record_type == "symptom-records":
            session.query(SymptomItem).filter_by(
                patient_id=patient_id, symptom_record_id=obj.id
            ).delete()
            for item in payload.get("items", []):
                session.add(
                    SymptomItem(
                        symptom_record_id=obj.id,
                        patient_id=patient_id,
                        symptom_code=item["symptom_code"],
                        other_description=item.get("other_description"),
                        severity=item.get("severity"),
                        body_location=item.get("body_location"),
                        patient_confirmed=item.get("patient_confirmed", True),
                    )
                )

    def _evaluate(
        self,
        session: Session,
        patient_id: UUID,
        record_type: str,
        record_id: UUID,
        version: int,
        payload: dict[str, Any],
    ) -> None:
        now = _utcnow()
        environments = (
            ("production", "test_only") if self._allow_test_only_rules else ("production",)
        )
        rules = session.scalars(
            select(RiskRule).where(
                RiskRule.review_status == "approved",
                RiskRule.environment.in_(environments),
                RiskRule.reviewed_by.is_not(None),
                RiskRule.reviewed_at.is_not(None),
                RiskRule.expires_at > now,
                func.jsonb_array_length(RiskRule.source_refs) > 0,
                (RiskRule.effective_from.is_(None) | (RiskRule.effective_from <= now)),
                (RiskRule.effective_to.is_(None) | (RiskRule.effective_to > now)),
            )
        ).all()
        facts = build_risk_facts(record_type, payload)
        for rule in rules:
            condition = rule.condition_json
            try:
                matched = evaluate_condition(condition, facts)
            except ValueError as exc:
                logger.critical(
                    "risk_rule_configuration_error",
                )
                raise Problem(
                    503,
                    "RISK_RULE_CONFIGURATION_ERROR",
                    "Safety rule configuration is invalid",
                ) from exc
            if matched:
                key = hashlib.sha256(
                    f"{patient_id}:{rule.rule_code}:{rule.version}:{record_id}:{version}".encode()
                ).hexdigest()
                alert_id = session.scalar(
                    pg_insert(RiskAlert)
                    .values(
                        patient_id=patient_id,
                        rule_id=rule.id,
                        source_record_id=record_id,
                        source_record_version=version,
                        severity=rule.severity,
                        message=rule.message,
                        recommended_action=rule.recommended_action,
                        deduplication_key=key,
                        status="unread",
                        evidence_summary={
                            "record_type": record_type,
                            "record_id": str(record_id),
                            "record_version": version,
                            "rule_environment": rule.environment,
                        },
                    )
                    .on_conflict_do_nothing(index_elements=["patient_id", "deduplication_key"])
                    .returning(RiskAlert.id)
                )
                if alert_id is not None:
                    session.add(
                        AlertEvidence(
                            alert_id=alert_id,
                            patient_id=patient_id,
                            record_type=record_type,
                            record_id=record_id,
                            record_version=version,
                            field_summary={"matched_rule_code": rule.rule_code},
                        )
                    )

    def create(
        self,
        context: AuthContext,
        record_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._validate(record_type, occurred_at, payload)
        request_hash = hashlib.sha256(
            json.dumps(
                {
                    "record_type": record_type,
                    "occurred_at": occurred_at.isoformat(),
                    "payload": payload,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            if record_type in {"diet-records", "stool-records"}:
                session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
                    ),
                    {"p": str(patient_id)},
                )
            self._validate_image(session, patient_id, record_type, payload)
            session.execute(
                pg_insert(RecordIdempotency)
                .values(
                    patient_id=patient_id,
                    operation=record_type,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
                .on_conflict_do_nothing(
                    index_elements=["patient_id", "operation", "idempotency_key"]
                )
            )
            idempotency = session.scalar(
                select(RecordIdempotency)
                .where(
                    RecordIdempotency.patient_id == patient_id,
                    RecordIdempotency.operation == record_type,
                    RecordIdempotency.idempotency_key == idempotency_key,
                )
                .with_for_update()
            )
            if idempotency is None:
                raise Problem(500, "INTERNAL_ERROR", "Unable to reserve idempotency key")
            if idempotency.request_hash != request_hash:
                raise Problem(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was used with different request content",
                )
            if idempotency.resource_id is not None:
                cls = TYPES[record_type]
                prior = session.scalar(
                    select(cls).where(
                        cls.id == idempotency.resource_id,
                        cls.patient_id == patient_id,
                        cls.deleted_at.is_(None),
                    )
                )
                if prior is not None:
                    return self._dto(
                        prior, record_type, self._items(session, record_type, prior, patient_id)
                    )
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            cls = TYPES[record_type]
            values: dict[str, Any] = {
                "patient_id": patient_id,
                "occurred_at": occurred_at,
                "payload": {
                    k: v
                    for k, v in payload.items()
                    if k
                    not in {
                        "items",
                        "meal_type",
                        "text_description",
                        "portion_note",
                        "bristol_type",
                        "color_code",
                        "blood_reported",
                        "duration_minutes",
                        "notes",
                        "symptom_status",
                    }
                },
                "source_type": "patient_manual",
            }
            if record_type == "diet-records":
                values.update(
                    meal_type=payload.get("meal_type"),
                    text_description=payload.get("text_description"),
                    portion_note=payload.get("portion_note"),
                    confirmation_status="confirmed",
                )
            elif record_type == "stool-records":
                values.update(
                    bristol_type=payload.get("bristol_type"),
                    color_code=payload.get("color_code"),
                    blood_reported=payload.get("blood_reported"),
                    confirmation_status="confirmed",
                )
            else:
                values.update(
                    duration_minutes=payload.get("duration_minutes"),
                    notes=payload.get("notes"),
                    symptom_status=payload.get("symptom_status", "ongoing"),
                )
            obj = cls(**values)
            session.add(obj)
            session.flush()
            idempotency.resource_id = obj.id
            self._replace_items(session, record_type, obj, patient_id, payload)
            if record_type == "symptom-records":
                session.add(
                    SymptomStatusEvent(
                        symptom_record_id=obj.id,
                        patient_id=patient_id,
                        status=obj.symptom_status,
                        record_version=obj.record_version,
                    )
                )
            if record_type in RISK_TYPES:
                self._evaluate(
                    session, patient_id, record_type, obj.id, obj.record_version, payload
                )
            session.flush()
            return self._dto(obj, record_type, self._items(session, record_type, obj, patient_id))

    def list(
        self,
        context: AuthContext,
        record_type: str,
        *,
        limit: int,
        cursor: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]:
        if record_type not in TYPES:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            cls = TYPES[record_type]
            query = select(cls).where(cls.patient_id == patient_id, cls.deleted_at.is_(None))
            if since:
                query = query.where(cls.occurred_at >= since)
            if until:
                query = query.where(cls.occurred_at < until)
            if cursor:
                cursor_time, cursor_id = _cursor_decode(cursor)
                query = query.where(
                    (cls.occurred_at < cursor_time)
                    | ((cls.occurred_at == cursor_time) & (cls.id < cursor_id))
                )
            rows: list[Any] = list(
                session.scalars(
                    query.order_by(cls.occurred_at.desc(), cls.id.desc()).limit(limit + 1)
                ).all()
            )
            more = len(rows) > limit
            rows = rows[:limit]
            return {
                "items": [
                    self._dto(x, record_type, self._items(session, record_type, x, patient_id))
                    for x in rows
                ],
                "next_cursor": _cursor_encode(rows[-1].occurred_at, rows[-1].id)
                if more and rows
                else None,
            }

    def get(self, context: AuthContext, record_type: str, record_id: UUID) -> dict[str, Any]:
        if record_type not in TYPES:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            obj = session.scalar(
                select(TYPES[record_type]).where(
                    TYPES[record_type].id == record_id,
                    TYPES[record_type].patient_id == patient_id,
                    TYPES[record_type].deleted_at.is_(None),
                )
            )
            if obj is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._dto(obj, record_type, self._items(session, record_type, obj, patient_id))

    def symptom_status_history(self, context: AuthContext, record_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            record = session.scalar(
                select(SymptomRecord).where(
                    SymptomRecord.id == record_id,
                    SymptomRecord.patient_id == patient_id,
                    SymptomRecord.deleted_at.is_(None),
                )
            )
            if record is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            events = session.scalars(
                select(SymptomStatusEvent)
                .where(
                    SymptomStatusEvent.symptom_record_id == record_id,
                    SymptomStatusEvent.patient_id == patient_id,
                )
                .order_by(SymptomStatusEvent.record_version, SymptomStatusEvent.changed_at)
            ).all()
            return {
                "symptom_record_id": str(record_id),
                "current_status": record.symptom_status,
                "events": [
                    {
                        "status": event.status,
                        "record_version": event.record_version,
                        "changed_at": event.changed_at.isoformat(),
                    }
                    for event in events
                ],
            }

    def patch(
        self,
        context: AuthContext,
        record_type: str,
        record_id: UUID,
        version: int,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate(record_type, occurred_at, payload)
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            if record_type in {"diet-records", "stool-records"}:
                session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
                    ),
                    {"p": str(patient_id)},
                )
            cls = TYPES[record_type]
            obj = session.scalar(
                select(cls)
                .where(cls.id == record_id, cls.patient_id == patient_id, cls.deleted_at.is_(None))
                .with_for_update()
            )
            if obj is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if obj.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            if record_type in {"diet-records", "stool-records"}:
                self._invalidate_record_image_requests(session, patient_id, record_id)
                session.execute(
                    text("""UPDATE analysis.record_image_decision SET source_state='source_deleted'
                        WHERE patient_id=:patient_id AND request_id IN
                        (SELECT id FROM analysis.record_image_recognition_request WHERE patient_id=:patient_id AND record_id=:record_id)"""),
                    {"patient_id": patient_id, "record_id": record_id},
                )
            obj.occurred_at = occurred_at
            self._validate_image(session, patient_id, record_type, payload)
            obj.payload = {
                k: v
                for k, v in payload.items()
                if k
                not in {
                    "items",
                    "meal_type",
                    "text_description",
                    "portion_note",
                    "bristol_type",
                    "color_code",
                    "blood_reported",
                    "duration_minutes",
                    "notes",
                    "symptom_status",
                }
            }
            if record_type == "diet-records":
                obj.meal_type, obj.text_description, obj.portion_note = (
                    payload.get("meal_type"),
                    payload.get("text_description"),
                    payload.get("portion_note"),
                )
            elif record_type == "stool-records":
                obj.bristol_type, obj.color_code, obj.blood_reported = (
                    payload.get("bristol_type"),
                    payload.get("color_code"),
                    payload.get("blood_reported"),
                )
            else:
                previous_status = obj.symptom_status
                obj.duration_minutes, obj.notes = (
                    payload.get("duration_minutes"),
                    payload.get("notes"),
                )
                obj.symptom_status = payload.get("symptom_status", previous_status)
            obj.record_version += 1
            obj.updated_at = _utcnow()
            self._replace_items(session, record_type, obj, patient_id, payload)
            if record_type == "symptom-records" and obj.symptom_status != previous_status:
                session.add(
                    SymptomStatusEvent(
                        symptom_record_id=obj.id,
                        patient_id=patient_id,
                        status=obj.symptom_status,
                        record_version=obj.record_version,
                    )
                )
            if record_type in RISK_TYPES:
                prior = session.scalars(
                    select(RiskAlert).where(
                        RiskAlert.patient_id == patient_id,
                        RiskAlert.source_record_id == record_id,
                        RiskAlert.status.in_(["unread", "read"]),
                    )
                ).all()
                for alert in prior:
                    alert.status, alert.reevaluated_at = "reevaluated", _utcnow()
                risk_payload = dict(payload)
                self._evaluate(
                    session, patient_id, record_type, record_id, obj.record_version, risk_payload
                )
            session.flush()
            return self._dto(obj, record_type, self._items(session, record_type, obj, patient_id))

    def delete(self, context: AuthContext, record_type: str, record_id: UUID, version: int) -> None:
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            if record_type in {"diet-records", "stool-records"}:
                session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock_shared(hashtextextended('gutcare.patient-consent-fence:' || :p,0))"
                    ),
                    {"p": str(patient_id)},
                )
            cls = TYPES.get(record_type)
            if cls is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            obj = session.scalar(
                select(cls)
                .where(cls.id == record_id, cls.patient_id == patient_id, cls.deleted_at.is_(None))
                .with_for_update()
            )
            if obj is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if obj.record_version != version:
                raise Problem(409, "RECORD_VERSION_CONFLICT", "Record version has changed")
            if record_type in {"diet-records", "stool-records"}:
                self._invalidate_record_image_requests(session, patient_id, record_id)
                table = (
                    "diet_record_image" if record_type == "diet-records" else "stool_record_image"
                )
                session.execute(
                    text(f"""UPDATE health.file_object f SET deleted_at=now(),storage_status='deleting'
                        WHERE f.patient_id=:patient_id AND f.id IN (
                          SELECT file_object_id FROM health.{table}
                          WHERE patient_id=:patient_id AND record_id=:record_id AND deleted_at IS NULL)"""),
                    {"patient_id": patient_id, "record_id": record_id},
                )
                session.execute(
                    text(
                        f"UPDATE health.{table} SET deleted_at=now() WHERE patient_id=:patient_id AND record_id=:record_id AND deleted_at IS NULL"
                    ),
                    {"patient_id": patient_id, "record_id": record_id},
                )
                session.execute(
                    text(f"""INSERT INTO integration.file_deletion_job(patient_id,file_object_id,bucket_name,object_key,due_at)
                        SELECT patient_id,id,bucket_name,object_key,now()+interval '7 days' FROM health.file_object
                        WHERE patient_id=:patient_id AND storage_status='deleting' AND id IN (
                          SELECT file_object_id FROM health.{table} WHERE patient_id=:patient_id AND record_id=:record_id)
                        ON CONFLICT DO NOTHING"""),
                    {"patient_id": patient_id, "record_id": record_id},
                )
            obj.deleted_at = _utcnow()
            obj.record_version += 1
            obj.updated_at = _utcnow()
            if record_type in RISK_TYPES:
                alerts = session.scalars(
                    select(RiskAlert).where(
                        RiskAlert.patient_id == patient_id,
                        RiskAlert.source_record_id == record_id,
                        RiskAlert.status.in_(["unread", "read"]),
                    )
                ).all()
                for alert in alerts:
                    alert.status, alert.reevaluated_at = "reevaluated", _utcnow()

    def alerts(
        self, context: AuthContext, *, limit: int, cursor: str | None, unread_only: bool = False
    ) -> dict[str, Any]:
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            query = select(RiskAlert).where(RiskAlert.patient_id == patient_id)
            if unread_only:
                query = query.where(RiskAlert.status == "unread")
            if cursor:
                cursor_time, cursor_id = _cursor_decode(cursor)
                query = query.where(
                    (RiskAlert.triggered_at < cursor_time)
                    | ((RiskAlert.triggered_at == cursor_time) & (RiskAlert.id < cursor_id))
                )
            rows = session.scalars(
                query.order_by(RiskAlert.triggered_at.desc(), RiskAlert.id.desc()).limit(limit + 1)
            ).all()
            more = len(rows) > limit
            rows = rows[:limit]
            return {
                "items": [self._alert_dto(x) for x in rows],
                "next_cursor": _cursor_encode(rows[-1].triggered_at, rows[-1].id)
                if more and rows
                else None,
            }

    @staticmethod
    def _alert_dto(x: RiskAlert) -> dict[str, Any]:
        return {
            "id": str(x.id),
            "environment": x.evidence_summary.get("rule_environment", "production"),
            "severity": x.severity,
            "message": x.message,
            "recommended_action": x.recommended_action,
            "status": x.status,
            "triggered_at": x.triggered_at.isoformat(),
            "read_at": x.read_at.isoformat() if x.read_at else None,
            "reevaluated_at": x.reevaluated_at.isoformat() if x.reevaluated_at else None,
            "evidence": x.evidence_summary,
        }

    def get_alert(
        self, context: AuthContext, alert_id: UUID, mark_read: bool = False
    ) -> dict[str, Any]:
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            alert = session.scalar(
                select(RiskAlert)
                .where(RiskAlert.id == alert_id, RiskAlert.patient_id == patient_id)
                .with_for_update()
            )
            if alert is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if mark_read and alert.status == "unread":
                alert.status, alert.read_at = "read", _utcnow()
            return self._alert_dto(alert)

    def reevaluate_alert(self, context: AuthContext, alert_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as session:
            patient_id = self._patient_id(session, context)
            self._scope(session, patient_id)
            alert = session.scalar(
                select(RiskAlert)
                .where(RiskAlert.id == alert_id, RiskAlert.patient_id == patient_id)
                .with_for_update()
            )
            if alert is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            alert.status, alert.reevaluated_at = "reevaluated", _utcnow()
            return self._alert_dto(alert)

"""Patient-scoped F08 task lifecycle and frozen input creation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session, sessionmaker

from gutcare.analysis.models import (
    AnalysisTask,
    AnalysisTaskCallback,
    AnalysisTaskIdempotency,
    TaskInputSnapshot,
)
from gutcare.auth.models import PatientConsent, PatientProfile, UserAccount
from gutcare.auth.service import AuthContext
from gutcare.files.models import (
    ConfirmedMedicalFact,
    FileObject,
    MedicalDocument,
    MedicalFactConflict,
    MedicalFactConflictMember,
    MedicalFieldCandidate,
    MedicalParseRequest,
)
from gutcare.medication.models import (
    MedicationCheckin,
    MedicationPlan,
    MedicationSchedule,
    MedicationSourceRef,
)
from gutcare.records.models import (
    DietItem,
    DietRecord,
    RiskAlert,
    StoolRecord,
    SymptomItem,
    SymptomRecord,
)
from gutcare.shared.errors import Problem


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


class AnalysisService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _profile(db: Session, context: AuthContext) -> PatientProfile:
        db.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(context.user_id)},
        )
        profile = db.scalar(select(PatientProfile).where(PatientProfile.user_id == context.user_id))
        if profile is None or profile.deleted_at is not None:
            raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
        account = db.scalar(select(UserAccount).where(UserAccount.id == context.user_id))
        if account is None or account.status != "active" or account.deleted_at is not None:
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
        db.execute(
            text("SELECT set_config('app.patient_id', :patient_id, true)"),
            {"patient_id": str(profile.id)},
        )
        return profile

    @staticmethod
    def _authorized(db: Session, patient_id: UUID) -> None:
        for kind in ("health_data_processing", "third_party_ai"):
            latest = db.scalar(
                select(PatientConsent)
                .where(
                    PatientConsent.patient_id == patient_id,
                    PatientConsent.consent_type == kind,
                )
                .order_by(desc(PatientConsent.decided_at), desc(PatientConsent.id))
                .limit(1)
            )
            if latest is None or not latest.granted:
                raise Problem(409, "CONSENT_REQUIRED", "Analysis consent is required")

    @staticmethod
    def _snapshot(
        db: Session, patient_id: UUID, start: datetime | None, end: datetime | None
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        record_specs: tuple[tuple[Any, str, set[str]], ...] = (
            (DietRecord, "diet_record", {"meal_type"}),
            (StoolRecord, "stool_record", {"bristol_type", "color_code", "blood_reported"}),
        )
        for model, kind, fields in record_specs:
            query = select(model).where(
                model.patient_id == patient_id,
                model.deleted_at.is_(None),
                model.confirmation_status == "confirmed",
            )
            if start is not None:
                query = query.where(model.occurred_at >= start)
            if end is not None:
                query = query.where(model.occurred_at < end)
            raw_rows: Any = db.scalars(query)
            for current_row in raw_rows:
                payload = {
                    name: getattr(current_row, name)
                    for name in fields
                    if getattr(current_row, name, None) is not None
                }
                payload.update(
                    {
                        k: v
                        for k, v in (current_row.payload or {}).items()
                        if k in {"items", "symptoms"} and isinstance(v, list)
                    }
                )
                if kind == "diet_record":
                    payload["items"] = [
                        {"name": item.name, "category_code": item.category_code}
                        for item in db.scalars(
                            select(DietItem).where(
                                DietItem.diet_record_id == current_row.id,
                                DietItem.patient_id == patient_id,
                                DietItem.confirmed_by_patient.is_(True),
                            )
                        )
                    ]
                rows.append(
                    {
                        "record_type": kind,
                        "record_id": str(current_row.id),
                        "record_version": current_row.record_version,
                        "occurred_at": current_row.occurred_at.isoformat(),
                        "confirmation_status": "confirmed",
                        "locator": f"{kind}:{current_row.id}",
                        "payload": payload,
                    }
                )
        symptom_query = select(SymptomRecord).where(
            SymptomRecord.patient_id == patient_id, SymptomRecord.deleted_at.is_(None)
        )
        if start is not None:
            symptom_query = symptom_query.where(SymptomRecord.occurred_at >= start)
        if end is not None:
            symptom_query = symptom_query.where(SymptomRecord.occurred_at < end)
        symptom_rows: Any = db.scalars(symptom_query)
        for symptom_row in symptom_rows:
            payload = {
                k: v
                for k, v in (symptom_row.payload or {}).items()
                if k in {"symptoms"} and isinstance(v, list)
            }
            payload["symptom_status"] = symptom_row.symptom_status
            if symptom_row.duration_minutes is not None:
                payload["duration_minutes"] = symptom_row.duration_minutes
            payload["symptoms"] = [
                {"symptom_code": item.symptom_code, "severity": item.severity}
                for item in db.scalars(
                    select(SymptomItem).where(
                        SymptomItem.symptom_record_id == symptom_row.id,
                        SymptomItem.patient_id == patient_id,
                        SymptomItem.patient_confirmed.is_(True),
                    )
                )
            ]
            rows.append(
                {
                    "record_type": "symptom_record",
                    "record_id": str(symptom_row.id),
                    "record_version": symptom_row.record_version,
                    "occurred_at": symptom_row.occurred_at.isoformat(),
                    "confirmation_status": "confirmed",
                    "locator": f"symptom_record:{symptom_row.id}",
                    "payload": payload,
                }
            )
        fact_query = (
            select(ConfirmedMedicalFact, MedicalFieldCandidate.record_version)
            .join(
                MedicalFieldCandidate, MedicalFieldCandidate.id == ConfirmedMedicalFact.candidate_id
            )
            .where(
                ConfirmedMedicalFact.patient_id == patient_id,
                ConfirmedMedicalFact.fact_status == "active",
                MedicalFieldCandidate.review_status.in_(["accepted", "corrected"]),
            )
        )
        open_conflicts = list(
            db.scalars(
                select(MedicalFactConflict).where(
                    MedicalFactConflict.patient_id == patient_id,
                    MedicalFactConflict.status == "open",
                )
            )
        )
        open_members = (
            list(
                db.scalars(
                    select(MedicalFactConflictMember).where(
                        MedicalFactConflictMember.patient_id == patient_id,
                        MedicalFactConflictMember.conflict_id.in_(
                            [item.id for item in open_conflicts]
                        ),
                    )
                )
            )
            if open_conflicts
            else []
        )
        open_fact_ids = {item.fact_id for item in open_members}
        reviewed_members = list(
            db.scalars(
                select(MedicalFactConflictMember)
                .join(
                    MedicalFactConflict,
                    MedicalFactConflict.id == MedicalFactConflictMember.conflict_id,
                )
                .where(
                    MedicalFactConflictMember.patient_id == patient_id,
                    MedicalFactConflict.status == "resolved",
                )
            )
        )
        reviewed_by_fact: dict[UUID, list[str]] = {}
        for member in reviewed_members:
            reviewed_by_fact.setdefault(member.fact_id, []).append(str(member.conflict_id))
        for fact, fact_version in db.execute(fact_query):
            if fact.id in open_fact_ids:
                continue
            rows.append(
                {
                    "record_type": "confirmed_medical_fact",
                    "record_id": str(fact.id),
                    "record_version": fact_version,
                    "occurred_at": fact.confirmed_at.isoformat(),
                    "confirmation_status": "confirmed",
                    "locator": f"confirmed_medical_fact:{fact.id}",
                    "payload": {
                        "field_code": fact.field_code,
                        "value_type": fact.value_type,
                        "value": fact.value,
                        "unit": fact.unit,
                        **(
                            {"reviewed_conflict_ids": reviewed_by_fact[fact.id]}
                            if fact.id in reviewed_by_fact
                            else {}
                        ),
                    },
                }
            )
        for conflict in open_conflicts:
            conflict_members = [item for item in open_members if item.conflict_id == conflict.id]
            member_payload = []
            for member in conflict_members:
                member_fact = db.get(ConfirmedMedicalFact, member.fact_id)
                if member_fact is None:
                    continue
                candidate = db.get(MedicalFieldCandidate, member_fact.candidate_id)
                member_payload.append(
                    {
                        "fact_id": str(member_fact.id),
                        "fact_version": member.fact_version,
                        "source_document_id": str(member.document_id),
                        "source_document_version": member.document_version,
                        "field_code": member_fact.field_code,
                        "value": member_fact.value,
                        "unit": member_fact.unit,
                        "sampled_on": member.sampled_on.isoformat(),
                        "locator": f"confirmed_medical_fact:{member_fact.id}",
                        "review_status": candidate.review_status if candidate else "confirmed",
                    }
                )
            rows.append(
                {
                    "record_type": "medical_fact_conflict",
                    "record_id": str(conflict.id),
                    "record_version": conflict.record_version,
                    "occurred_at": conflict.created_at.isoformat(),
                    "confirmation_status": "unresolved",
                    "locator": f"medical_fact_conflict:{conflict.id}",
                    "payload": {
                        "conflict_status": "open",
                        "review_required": True,
                        "guidance_code": "PATIENT_REVIEW_REQUIRED",
                        "members": member_payload,
                    },
                }
            )
        plan_query = select(MedicationPlan).where(
            MedicationPlan.patient_id == patient_id,
            MedicationPlan.deleted_at.is_(None),
            MedicationPlan.confirmation_status == "confirmed",
            MedicationPlan.plan_status == "active",
        )
        for plan in db.scalars(plan_query):
            rows.append(
                {
                    "record_type": "medication_plan",
                    "record_id": str(plan.id),
                    "record_version": plan.record_version,
                    "occurred_at": plan.created_at.isoformat(),
                    "confirmation_status": "confirmed",
                    "locator": f"medication_plan:{plan.id}",
                    "payload": {
                        "medication_name": plan.medication_name,
                        "route_code": plan.route_code,
                        "start_date": plan.start_date.isoformat() if plan.start_date else None,
                        "end_date": plan.end_date.isoformat() if plan.end_date else None,
                    },
                }
            )
        checkin_query = select(MedicationCheckin).where(MedicationCheckin.patient_id == patient_id)
        if start is not None:
            checkin_query = checkin_query.where(MedicationCheckin.scheduled_for >= start)
        if end is not None:
            checkin_query = checkin_query.where(MedicationCheckin.scheduled_for < end)
        for checkin in db.scalars(checkin_query):
            if checkin.status not in {"taken", "not_taken", "skipped"}:
                continue
            rows.append(
                {
                    "record_type": "medication_checkin",
                    "record_id": str(checkin.id),
                    "record_version": checkin.record_version,
                    "occurred_at": checkin.scheduled_for.isoformat(),
                    "confirmation_status": "confirmed",
                    "locator": f"medication_checkin:{checkin.id}",
                    "payload": {
                        "status": checkin.status,
                        "taken_at": checkin.taken_at.isoformat() if checkin.taken_at else None,
                    },
                }
            )
        alert_query = select(RiskAlert).where(RiskAlert.patient_id == patient_id)
        if start is not None:
            alert_query = alert_query.where(RiskAlert.triggered_at >= start)
        if end is not None:
            alert_query = alert_query.where(RiskAlert.triggered_at < end)
        for alert in db.scalars(alert_query):
            rows.append(
                {
                    "record_type": "risk_alert",
                    "record_id": str(alert.id),
                    "record_version": alert.source_record_version,
                    "occurred_at": alert.triggered_at.isoformat(),
                    "confirmation_status": "confirmed",
                    "locator": f"risk_alert:{alert.id}",
                    "payload": {"severity": alert.severity, "status": alert.status},
                }
            )
        rows.sort(key=lambda item: (item["occurred_at"], item["record_type"], item["record_id"]))
        return {
            "records": rows,
            "time_range": {
                "from": start.isoformat() if start else None,
                "to": end.isoformat() if end else None,
            },
        }

    @staticmethod
    def _source_is_live(db: Session, patient_id: UUID, evidence: dict[str, Any]) -> bool:
        source_type = evidence.get("source_type")
        try:
            source_id = UUID(str(evidence.get("source_id")))
        except (TypeError, ValueError):
            return False
        direct_sources: dict[str, Any] = {
            "diet_record": DietRecord,
            "stool_record": StoolRecord,
            "symptom_record": SymptomRecord,
        }
        if source_type in direct_sources:
            model = direct_sources[source_type]
            return (
                db.scalar(
                    select(model.id).where(
                        model.id == source_id,
                        model.patient_id == patient_id,
                        model.deleted_at.is_(None),
                    )
                )
                is not None
            )
        if source_type == "medication_plan":
            plan = db.scalar(
                select(MedicationPlan).where(
                    MedicationPlan.id == source_id,
                    MedicationPlan.patient_id == patient_id,
                    MedicationPlan.deleted_at.is_(None),
                )
            )
            return plan is not None and AnalysisService._plan_source_is_live(db, patient_id, plan)
        if source_type == "confirmed_medical_fact":
            fact = db.scalar(
                select(ConfirmedMedicalFact.id)
                .join(
                    MedicalFieldCandidate,
                    MedicalFieldCandidate.id == ConfirmedMedicalFact.candidate_id,
                )
                .join(
                    MedicalParseRequest, MedicalParseRequest.id == MedicalFieldCandidate.request_id
                )
                .join(MedicalDocument, MedicalDocument.id == MedicalParseRequest.document_id)
                .join(FileObject, FileObject.id == MedicalDocument.file_object_id)
                .where(
                    ConfirmedMedicalFact.id == source_id,
                    ConfirmedMedicalFact.patient_id == patient_id,
                    ConfirmedMedicalFact.fact_status == "active",
                    MedicalFieldCandidate.review_status.in_(["accepted", "corrected"]),
                    MedicalDocument.deleted_at.is_(None),
                    FileObject.deleted_at.is_(None),
                    FileObject.storage_status == "available",
                )
            )
            return fact is not None
        if source_type == "medication_checkin":
            checkin = db.execute(
                select(MedicationCheckin.id, MedicationPlan)
                .join(
                    MedicationSchedule,
                    (MedicationSchedule.id == MedicationCheckin.schedule_id)
                    & (MedicationSchedule.patient_id == MedicationCheckin.patient_id),
                )
                .join(
                    MedicationPlan,
                    (MedicationPlan.id == MedicationSchedule.plan_id)
                    & (MedicationPlan.patient_id == MedicationSchedule.patient_id),
                )
                .where(
                    MedicationCheckin.id == source_id,
                    MedicationCheckin.patient_id == patient_id,
                    MedicationPlan.deleted_at.is_(None),
                    MedicationSchedule.deleted_at.is_(None),
                )
            ).first()
            return checkin is not None and AnalysisService._plan_source_is_live(
                db, patient_id, checkin[1]
            )
        if source_type == "risk_alert":
            alert = db.scalar(
                select(RiskAlert).where(
                    RiskAlert.id == source_id, RiskAlert.patient_id == patient_id
                )
            )
            if alert is None:
                return False
            for model in (DietRecord, StoolRecord, SymptomRecord):
                if (
                    db.scalar(
                        select(model.id).where(
                            model.id == alert.source_record_id,
                            model.patient_id == patient_id,
                            model.deleted_at.is_(None),
                        )
                    )
                    is not None
                ):
                    return True
            return False
        return False

    @staticmethod
    def _plan_source_is_live(db: Session, patient_id: UUID, plan: MedicationPlan) -> bool:
        if plan.source_ref_id is None:
            return plan.source_type == "manual"
        source_ref = db.scalar(
            select(MedicationSourceRef).where(
                MedicationSourceRef.id == plan.source_ref_id,
                MedicationSourceRef.patient_id == patient_id,
                MedicationSourceRef.source_deleted_at.is_(None),
                MedicationSourceRef.live_document_id.is_not(None),
            )
        )
        if source_ref is None:
            return False
        return (
            db.scalar(
                select(MedicalDocument.id).where(
                    MedicalDocument.id == source_ref.live_document_id,
                    MedicalDocument.patient_id == patient_id,
                    MedicalDocument.deleted_at.is_(None),
                )
            )
            is not None
        )

    @classmethod
    def _project_result(
        cls, db: Session, patient_id: UUID, result: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if result is None:
            return None
        projected = dict(result)
        projected_evidence: list[dict[str, Any]] = []
        for item in result.get("evidence", []):
            evidence = dict(item)
            live = cls._source_is_live(db, patient_id, evidence)
            evidence["source_deleted"] = not live
            if not live:
                evidence["locator"] = None
            projected_evidence.append(evidence)
        projected["evidence"] = projected_evidence
        return projected

    @staticmethod
    def _dto(task: AnalysisTask, *, result: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "id": str(task.id),
            "analysis_type": task.analysis_type,
            "status": task.status,
            "attempt": task.attempt,
            "retry_of": str(task.retry_of) if task.retry_of else None,
            "result": task.result_payload if result is None else result,
            "error_code": task.error_code,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }

    def create(
        self, context: AuthContext, payload: dict[str, Any], key: str
    ) -> tuple[dict[str, Any], bool]:
        route = "POST:/api/v1/analysis-tasks"
        request_hash = _hash(payload)
        with self._sessions.begin() as db:
            profile = self._profile(db, context)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended("
                    "'gutcare.patient-consent-fence:' || :patient_id, 0))"
                ),
                {"patient_id": str(profile.id)},
            )
            profile = self._profile(db, context)
            self._authorized(db, profile.id)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended("
                    "'gutcare.analysis-task.idempotency:v1:' || :patient_id || "
                    "':' || :route || ':' || :key, 0))"
                ),
                {"patient_id": str(profile.id), "route": route, "key": key},
            )
            existing = db.scalar(
                select(AnalysisTaskIdempotency).where(
                    AnalysisTaskIdempotency.patient_id == profile.id,
                    AnalysisTaskIdempotency.route == route,
                    AnalysisTaskIdempotency.idempotency_key == key,
                )
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise Problem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key was used with a different request",
                    )
                return existing.response_snapshot, True
            start, end = payload.get("requested_from"), payload.get("requested_to")
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            snapshot = self._snapshot(db, profile.id, start, end)
            if not snapshot["records"]:
                raise Problem(
                    422, "ANALYSIS_INPUT_REQUIRED", "No confirmed analyzable data is available"
                )
            task = AnalysisTask(
                patient_id=profile.id,
                analysis_type=payload["analysis_type"],
                status="pending",
                requested_from=start,
                requested_to=end,
            )
            db.add(task)
            db.flush()
            digest = _hash(snapshot)
            db.add(
                TaskInputSnapshot(
                    task_id=task.id,
                    patient_id=profile.id,
                    snapshot_payload=snapshot,
                    content_hash=digest,
                )
            )
            response = self._dto(task)
            db.add(
                AnalysisTaskIdempotency(
                    patient_id=profile.id,
                    route=route,
                    idempotency_key=key,
                    request_hash=request_hash,
                    task_id=task.id,
                    response_snapshot=response,
                )
            )
            db.flush()
            return response, False

    def get(self, context: AuthContext, task_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as db:
            profile = self._profile(db, context)
            task = db.scalar(
                select(AnalysisTask).where(
                    AnalysisTask.patient_id == profile.id, AnalysisTask.id == task_id
                )
            )
            if task is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            return self._dto(
                task,
                result=self._project_result(db, profile.id, task.result_payload),
            )

    def list(self, context: AuthContext, limit: int = 20) -> list[dict[str, Any]]:
        with self._sessions.begin() as db:
            profile = self._profile(db, context)
            tasks = db.scalars(
                select(AnalysisTask)
                .where(AnalysisTask.patient_id == profile.id)
                .order_by(desc(AnalysisTask.created_at))
                .limit(limit)
            )
            return [
                self._dto(
                    task,
                    result=self._project_result(db, profile.id, task.result_payload),
                )
                for task in tasks
            ]

    def cancel(self, context: AuthContext, task_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as db:
            profile = self._profile(db, context)
            task = db.scalar(
                select(AnalysisTask)
                .where(AnalysisTask.patient_id == profile.id, AnalysisTask.id == task_id)
                .with_for_update()
            )
            if task is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if task.status not in {"pending", "processing"}:
                raise Problem(
                    409, "TASK_STATE_CONFLICT", "Task cannot be cancelled in its current state"
                )
            task.status = "cancelled"
            task.lease_expires_at = None
            task.updated_at = datetime.now(UTC)
            db.flush()
            return self._dto(task)

    def retry(self, context: AuthContext, task_id: UUID, key: str) -> tuple[dict[str, Any], bool]:
        route = f"POST:/api/v1/analysis-tasks/{task_id}/retry"
        with self._sessions.begin() as db:
            profile = self._profile(db, context)
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended("
                    "'gutcare.patient-consent-fence:' || :patient_id, 0))"
                ),
                {"patient_id": str(profile.id)},
            )
            profile = self._profile(db, context)
            self._authorized(db, profile.id)
            old = db.scalar(
                select(AnalysisTask)
                .where(AnalysisTask.patient_id == profile.id, AnalysisTask.id == task_id)
                .with_for_update()
            )
            if old is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Resource not found")
            if old.status != "failed":
                raise Problem(409, "TASK_STATE_CONFLICT", "Only failed tasks can be retried")
            snapshot = db.get(TaskInputSnapshot, task_id)
            if snapshot is None:
                raise Problem(409, "TASK_STATE_CONFLICT", "Task snapshot is unavailable")
            request_hash = _hash({"retry_of": str(task_id)})
            existing = db.scalar(
                select(AnalysisTaskIdempotency).where(
                    AnalysisTaskIdempotency.patient_id == profile.id,
                    AnalysisTaskIdempotency.route == route,
                    AnalysisTaskIdempotency.idempotency_key == key,
                )
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise Problem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key was used with a different request",
                    )
                return existing.response_snapshot, True
            already_retried = db.scalar(
                select(AnalysisTask.id).where(
                    AnalysisTask.patient_id == profile.id,
                    AnalysisTask.retry_of == old.id,
                )
            )
            if already_retried is not None:
                raise Problem(409, "TASK_STATE_CONFLICT", "This failed task was already retried")
            task = AnalysisTask(
                patient_id=profile.id,
                analysis_type=old.analysis_type,
                status="pending",
                requested_from=old.requested_from,
                requested_to=old.requested_to,
                attempt=old.attempt + 1,
                retry_of=old.id,
            )
            db.add(task)
            db.flush()
            db.add(
                TaskInputSnapshot(
                    task_id=task.id,
                    patient_id=profile.id,
                    snapshot_payload=snapshot.snapshot_payload,
                    content_hash=snapshot.content_hash,
                )
            )
            dto = self._dto(task)
            db.add(
                AnalysisTaskIdempotency(
                    patient_id=profile.id,
                    route=route,
                    idempotency_key=key,
                    request_hash=request_hash,
                    task_id=task.id,
                    response_snapshot=dto,
                )
            )
            return dto, False

    def claim(self) -> dict[str, Any] | None:
        with self._sessions.begin() as db:
            task = db.scalar(
                select(AnalysisTask)
                .where(
                    (AnalysisTask.status == "pending")
                    | (
                        (AnalysisTask.status == "processing")
                        & (AnalysisTask.lease_expires_at < datetime.now(UTC))
                    )
                )
                .order_by(AnalysisTask.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if task is None:
                return None
            db.execute(
                text("SELECT set_config('app.patient_id', :patient_id, true)"),
                {"patient_id": str(task.patient_id)},
            )
            try:
                self._authorized(db, task.patient_id)
            except Problem:
                task.status = "cancelled"
                task.lease_expires_at = None
                task.updated_at = datetime.now(UTC)
                return None
            task.status = "processing"
            task.lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
            task.updated_at = datetime.now(UTC)
            return {
                "task_id": str(task.id),
                "analysis_type": task.analysis_type,
                "attempt": task.attempt,
            }

    def inputs(self, task_id: UUID) -> dict[str, Any]:
        with self._sessions.begin() as db:
            task = db.scalar(
                select(AnalysisTask).where(
                    AnalysisTask.id == task_id, AnalysisTask.status == "processing"
                )
            )
            if task is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Task input not available")
            db.execute(
                text("SELECT set_config('app.patient_id', :patient_id, true)"),
                {"patient_id": str(task.patient_id)},
            )
            self._authorized(db, task.patient_id)
            snap = db.get(TaskInputSnapshot, task_id)
            if snap is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Task input not available")
            return {
                "task_id": str(task.id),
                "patient_id": str(task.patient_id),
                "analysis_type": task.analysis_type,
                "consent_scope": ["health_data_processing", "third_party_ai"],
                "records": snap.snapshot_payload["records"],
                "missing_data": [],
                "time_range": snap.snapshot_payload["time_range"],
                "schema_version": "1.0",
                "snapshot_hash": snap.content_hash,
            }

    def result(self, task_id: UUID, callback_id: UUID, payload: dict[str, Any]) -> None:
        with self._sessions.begin() as db:
            task = db.scalar(
                select(AnalysisTask).where(AnalysisTask.id == task_id).with_for_update()
            )
            if task is None:
                raise Problem(409, "TASK_STATE_CONFLICT", "Task is no longer accepting results")
            request_hash = _hash(payload)
            existing = db.scalar(
                select(AnalysisTaskCallback).where(
                    AnalysisTaskCallback.task_id == task_id,
                    AnalysisTaskCallback.callback_id == callback_id,
                )
            )
            if existing is not None:
                if existing.callback_type == "result" and existing.request_hash == request_hash:
                    return
                raise Problem(
                    409, "CALLBACK_ID_CONFLICT", "Callback id was used with different content"
                )
            if task.status != "processing":
                raise Problem(409, "TASK_STATE_CONFLICT", "Task is no longer accepting results")
            db.execute(
                text("SELECT set_config('app.patient_id', :patient_id, true)"),
                {"patient_id": str(task.patient_id)},
            )
            self._authorized(db, task.patient_id)
            snap = db.get(TaskInputSnapshot, task_id)
            if snap is None:
                raise Problem(404, "RESOURCE_NOT_FOUND", "Task input not available")
            refs = {
                (r["record_type"], r["record_id"], r["record_version"], r["locator"])
                for r in snap.snapshot_payload["records"]
            }
            for evidence in payload["evidence"]:
                ref = (
                    evidence.get("source_type"),
                    str(evidence.get("source_id")),
                    evidence.get("source_version"),
                    evidence.get("locator"),
                )
                if ref not in refs:
                    raise Problem(
                        422, "INVALID_EVIDENCE", "Evidence must reference this task snapshot"
                    )
            task.status = payload["status"]
            task.result_payload = {k: v for k, v in payload.items() if k != "status"}
            task.lease_expires_at = None
            task.updated_at = datetime.now(UTC)
            db.add(
                AnalysisTaskCallback(
                    task_id=task.id,
                    patient_id=task.patient_id,
                    callback_id=callback_id,
                    callback_type="result",
                    request_hash=request_hash,
                )
            )
            db.flush()

    def fail(self, task_id: UUID, callback_id: UUID, error_code: str) -> None:
        with self._sessions.begin() as db:
            task = db.scalar(
                select(AnalysisTask).where(AnalysisTask.id == task_id).with_for_update()
            )
            if task is None:
                raise Problem(409, "TASK_STATE_CONFLICT", "Task is no longer accepting callbacks")
            request_hash = _hash({"error_code": error_code})
            existing = db.scalar(
                select(AnalysisTaskCallback).where(
                    AnalysisTaskCallback.task_id == task_id,
                    AnalysisTaskCallback.callback_id == callback_id,
                )
            )
            if existing is not None:
                if existing.callback_type == "fail" and existing.request_hash == request_hash:
                    return
                raise Problem(
                    409, "CALLBACK_ID_CONFLICT", "Callback id was used with different content"
                )
            if task.status != "processing":
                raise Problem(409, "TASK_STATE_CONFLICT", "Task is no longer accepting callbacks")
            db.execute(
                text("SELECT set_config('app.patient_id', :patient_id, true)"),
                {"patient_id": str(task.patient_id)},
            )
            task.status = "failed"
            task.error_code = error_code
            task.lease_expires_at = None
            task.updated_at = datetime.now(UTC)
            db.add(
                AnalysisTaskCallback(
                    task_id=task.id,
                    patient_id=task.patient_id,
                    callback_id=callback_id,
                    callback_type="fail",
                    request_hash=request_hash,
                )
            )
            db.flush()

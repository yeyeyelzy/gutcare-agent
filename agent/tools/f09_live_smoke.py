"""One-call live smoke for F09 advice generation and callback mapping.

Run from ``agent`` with ``GCA_API_KEY`` set in the environment:
    python tools/f09_live_smoke.py

The script uses synthetic records only, disables retries and replay persistence,
and emits only aggregate status fields. It never submits a business callback.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gutcare_agents.agents.advice import AdviceAgent  # noqa: E402
from gutcare_agents.config import load_settings  # noqa: E402
from gutcare_agents.contract import (  # noqa: E402
    AgentName,
    AgentResult,
    ObsKind,
    Observation,
    PatientProfile,
    Status,
    TaskStatus,
)
from gutcare_agents.f08_adapter import adapt_inputs  # noqa: E402
from gutcare_agents.f09_adapter import map_f09_advice  # noqa: E402
from gutcare_agents.llm import LLMClient  # noqa: E402


class _SingleCallNoReplayClient(LLMClient):
    """Enforce one provider request and keep replay files free of raw output."""

    def __init__(self, settings):
        super().__init__(settings)
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("single-call limit exceeded")
        return super().complete(**kwargs)

    def _write_replay(self, *_args, **_kwargs):
        return None


def _synthetic_frozen_input(task_id: str, patient_id: str) -> dict:
    records = []
    days = ("2026-10-17", "2026-10-18", "2026-10-19")
    for day_index, day in enumerate(days):
        diet_id = str(uuid.uuid5(uuid.UUID(task_id), f"diet-{day_index}"))
        symptom_id = str(uuid.uuid5(uuid.UUID(task_id), f"symptom-{day_index}"))
        records.extend(
            [
                {
                    "record_type": "diet_record",
                    "record_id": diet_id,
                    "record_version": 1,
                    "confirmation_status": "confirmed",
                    "locator": f"diet_record:{diet_id}",
                    "occurred_at": f"{day}T12:00:00+08:00",
                    "payload": {"meal_type": "lunch", "description": "米饭和蔬菜"},
                },
                {
                    "record_type": "symptom_record",
                    "record_id": symptom_id,
                    "record_version": 1,
                    "confirmation_status": "confirmed",
                    "locator": f"symptom_record:{symptom_id}",
                    "occurred_at": f"{day}T14:00:00+08:00",
                    "payload": {
                        "name": "腹部不适",
                        "severity": 2,
                        "event_relation": "after_meal",
                    },
                },
            ]
        )
    return {
        "task_id": task_id,
        "patient_id": patient_id,
        "analysis_type": "comprehensive_health_analysis",
        "schema_version": "1.0",
        "snapshot_hash": "a" * 64,
        "time_range": {"from": "2026-10-17T00:00:00+08:00", "to": "2026-10-19T23:59:59+08:00"},
        "consent_scope": ["health_data_processing", "third_party_ai"],
        "consent_scope_snapshot": {
            "health_data_processing": True,
            "mood_data_processing": False,
            "mood_ai_sharing": False,
            "third_party_ai": True,
        },
        "records": records,
        "mood_records": [],
        "missing_data": [],
    }


def _validate_backend_shape(payload: dict) -> None:
    source = os.environ.get("GCA_BACKEND_SOURCE")
    backend_src = Path(source).expanduser() / "backend" / "src" if source else ROOT.parent / "backend" / "src"
    if not backend_src.is_dir():
        return
    sys.path.insert(0, str(backend_src))
    try:
        from gutcare.analysis.advice import AdviceCallbackBody
    except (ImportError, ModuleNotFoundError):
        return
    AdviceCallbackBody.model_validate(payload)


def main() -> int:
    started = time.monotonic()
    status = "failed"
    advice_count = 0
    mapped_count = 0
    model_used = ""
    try:
        settings = load_settings(mode="live", max_retries=0)
        if not settings.api_key:
            raise RuntimeError("live API key is not configured")
        client = _SingleCallNoReplayClient(settings)

        task_id, patient_id = str(uuid.uuid4()), str(uuid.uuid4())
        frozen = _synthetic_frozen_input(task_id, patient_id)
        request, provenance = adapt_inputs(frozen, task_id, frozen["analysis_type"])
        request.profile = PatientProfile(
            patient_id=patient_id,
            diagnosis_status="confirmed",
            diagnosis="肠易激综合征",
            profile_version=1,
        )

        trend_ids = list(provenance)
        trend = AgentResult(task_id=task_id, agent=AgentName.TREND, patient_id=patient_id)
        trend.observations = [
            Observation(
                obs_id="synthetic_confirmed_trend",
                kind=ObsKind.DERIVED_STAT,
                statement="合成记录中连续三天均有餐食记录，且各有一条随后出现的轻度腹部不适记录；仅表示时间邻近。",
                source_record_ids=trend_ids,
                confidence="high",
                value={"deterministic": True},
            )
        ]

        advice_result = AdviceAgent(settings, client).run_with_context(request, trend_result=trend)
        model_used = advice_result.model_id if client.calls else settings.text_model
        if client.calls != 1 or advice_result.status != Status.OK:
            raise RuntimeError("advice generation did not complete successfully")

        items = advice_result.data.get("advice_items") or []
        advice_count = len(items)
        run = SimpleNamespace(
            task_id=task_id,
            patient_id=patient_id,
            report={
                "observations": [item.to_dict() for item in trend.observations],
                "advice": items,
            },
        )
        mapped = map_f09_advice(run, frozen, f08_status=TaskStatus.PARTIAL)
        mapped_count = len(mapped.payload["advice"])
        if not mapped.ready or mapped_count != advice_count:
            raise RuntimeError("F09 mapper rejected one or more generated advice items")
        _validate_backend_shape(mapped.payload)
        status = "passed"
    except Exception:
        # Error details can contain provider or validation text; keep the evidence aggregate-only.
        status = "failed"
    result = {
        "status": status,
        "advice_count": advice_count,
        "mapped_count": mapped_count,
        "model_used": model_used,
        "duration": round(time.monotonic() - started, 3),
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

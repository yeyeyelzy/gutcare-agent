"""F09 mapping tests; optionally validate against a checked-out backend model."""
from __future__ import annotations

import os
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gutcare_agents.f08_adapter import F08ContractError, adapt_inputs  # noqa: E402
from gutcare_agents.f09_adapter import map_f09_advice  # noqa: E402
from gutcare_agents.agents.advice import AdviceAgent  # noqa: E402
from gutcare_agents.config import load_settings  # noqa: E402
from gutcare_agents.contract import AgentName, AgentResult, ObsKind, Observation, PatientProfile, Status  # noqa: E402
from gutcare_agents.knowledge_base import KnowledgeBase  # noqa: E402


class _FakeResponse:
    model = "unit-test"
    cached = False

    @staticmethod
    def usage():
        return {"model": "unit-test", "prompt_tokens": 0, "completion_tokens": 0}


class _RecordAdviceClient:
    def __init__(self):
        self.user_prompt = ""

    def complete_json(self, **kwargs):
        self.user_prompt = kwargs["user"]
        return ({"advice_items": [{
            "advice_id": "record_only",
            "category": "record_management",
            "title": "继续记录餐食与不适情况",
            "body": "可继续记录餐食内容和不适出现时间，便于后续回顾。记录只用于整理个人情况，不代表疾病结论。",
            "applicability": "适用于本次已确认记录",
            "uncertainty": "仅为一般记录管理建议",
            "evidence_obs_ids": ["synthetic_confirmed_trend"],
            "knowledge_ids": [],
        }], "degraded_reason": ""}, _FakeResponse())


def fixture():
    task_id, patient_id, source_id = (str(uuid.uuid4()) for _ in range(3))
    frozen = {
        "task_id": task_id, "patient_id": patient_id,
        "analysis_type": "comprehensive_health_analysis", "schema_version": "1.0",
        "snapshot_hash": "b" * 64, "time_range": None,
        "consent_scope": ["health_data_processing", "third_party_ai"],
        "consent_scope_snapshot": {
            "health_data_processing": True, "mood_data_processing": False,
            "mood_ai_sharing": False, "third_party_ai": True,
        },
        "records": [{"record_type": "stool_record", "record_id": source_id,
                     "record_version": 2, "confirmation_status": "confirmed",
                     "locator": f"stool_record:{source_id}", "payload": {"bristol_type": 4}}],
        "mood_records": [], "missing_data": [],
    }
    item = {"advice_id": "advice_001", "category": "record_management",
            "title": "继续记录", "body": "继续记录排便形态以便核对变化。",
            "uncertainty": "记录较少", "applicability": "仅用于本次记录",
            "evidence_obs_ids": ["obs_001"], "knowledge_ids": []}
    run = SimpleNamespace(task_id=task_id, patient_id=patient_id,
                          report={"observations": [{"obs_id": "obs_001",
                                                    "source_record_ids": [source_id],
                                                    "needs_confirmation": False}],
                                  "advice": [item]})
    return run, frozen


class F09MappingTests(unittest.TestCase):
    def test_general_advice_without_diagnosis_is_accepted_and_maps(self):
        from tools.f09_live_smoke import _synthetic_frozen_input

        task_id, patient_id = str(uuid.uuid4()), str(uuid.uuid4())
        frozen = _synthetic_frozen_input(task_id, patient_id)
        request, provenance = adapt_inputs(frozen, task_id, frozen["analysis_type"])
        request.profile = PatientProfile(patient_id=patient_id)
        trend = AgentResult(task_id=task_id, agent=AgentName.TREND, patient_id=patient_id)
        trend.observations = [Observation(
            obs_id="synthetic_confirmed_trend",
            kind=ObsKind.DERIVED_STAT,
            statement="合成记录中有餐食与不适时间信息，可继续记录以便回顾。",
            source_record_ids=list(provenance),
            confidence="high",
            value={"deterministic": True},
        )]
        settings = load_settings(mode="mock", prompts_dir=ROOT / "prompts", knowledge_dir=ROOT / "knowledge")
        client = _RecordAdviceClient()
        result = AdviceAgent(settings, client, knowledge=KnowledgeBase.load(ROOT / "knowledge")).run_with_context(
            request, trend_result=trend
        )

        self.assertEqual(result.status, Status.OK)
        self.assertIn("只能提供一般性建议", client.user_prompt)
        self.assertNotIn("KB-", client.user_prompt)
        self.assertEqual(result.data["advice_items"][0]["knowledge_ids"], [])
        mapped = map_f09_advice(
            SimpleNamespace(task_id=task_id, patient_id=patient_id, report={
                "observations": [item.to_dict() for item in trend.observations],
                "advice": result.data["advice_items"],
            }),
            frozen,
            f08_status="partial",
        )
        self.assertTrue(mapped.ready)
        self.assertEqual(mapped.payload["advice"][0]["evidence"][0]["evidence_type"], "patient")

    def test_patient_evidence_exactly_matches_frozen_source(self):
        run, frozen = fixture()
        mapped = map_f09_advice(run, frozen, f08_status="partial")
        self.assertTrue(mapped.ready)
        self.assertEqual(mapped.dropped, [])
        advice = mapped.payload["advice"][0]
        self.assertEqual(advice["category"], "record_management")
        self.assertEqual(advice["applicability"]["scope"], "general")
        self.assertEqual(advice["uncertainty"]["level"], "high")
        self.assertEqual(advice["evidence"], [{
            "evidence_type": "patient", "source_type": "stool_record",
            "source_id": frozen["records"][0]["record_id"], "source_version": 2,
            "locator": frozen["records"][0]["locator"],
        }])
        self.assertEqual(mapped.payload, map_f09_advice(run, frozen, f08_status="partial").payload)

    def test_unmapped_or_unconfirmed_observation_drops_entire_advice(self):
        run, frozen = fixture()
        run.report["observations"][0]["source_record_ids"] = [str(uuid.uuid4())]
        result = map_f09_advice(run, frozen, f08_status="partial")
        self.assertFalse(result.ready)
        self.assertEqual(result.dropped[0]["reason"], "unmapped_patient_evidence")
        run.report["observations"][0]["source_record_ids"] = [frozen["records"][0]["record_id"]]
        run.report["observations"][0]["needs_confirmation"] = True
        self.assertFalse(map_f09_advice(run, frozen, f08_status="partial").ready)

    def test_demo_knowledge_is_not_presented_as_approved(self):
        run, frozen = fixture()
        run.report["advice"][0]["knowledge_ids"] = ["KB-DEMO"]
        demo = {"KB-DEMO": {"review_status": "unverified_demo", "version": "demo-1",
                            "title": "演示条目", "publisher": "GutCare demo"}}
        result = map_f09_advice(run, frozen, f08_status="partial", approved_knowledge=demo)
        self.assertFalse(result.ready)
        self.assertEqual(result.dropped[0]["reason"], "knowledge_not_approved_or_incomplete")
        demo["KB-DEMO"]["review_status"] = "approved"
        result = map_f09_advice(run, frozen, f08_status="partial", approved_knowledge=demo)
        self.assertTrue(result.ready)
        self.assertEqual(result.payload["advice"][0]["evidence"][1]["knowledge_version"], "demo-1")

    def test_ineligible_f08_status_rejected(self):
        run, frozen = fixture()
        with self.assertRaises(F08ContractError):
            map_f09_advice(run, frozen, f08_status="needs_input")

    def test_empty_mock_advice_gets_safe_test_only_fixture_only_when_enabled(self):
        run, frozen = fixture()
        run.report["advice"] = []
        self.assertFalse(map_f09_advice(run, frozen, f08_status="partial").ready)
        result = map_f09_advice(run, frozen, f08_status="partial", test_only_mock_advice=True)
        self.assertTrue(result.ready)
        advice = result.payload["advice"][0]
        self.assertEqual(advice["category"], "record_management")
        self.assertEqual(len(advice["evidence"]), 1)
        self.assertEqual(advice["evidence"][0]["source_id"], frozen["records"][0]["record_id"])
        self.assertIn("mock 合成演示", advice["body"])
        self.assertNotIn("diagnos", advice["body"].lower())

    def test_mock_fixture_never_replaces_nonempty_unsafe_output(self):
        run, frozen = fixture()
        run.report["advice"][0]["body"] = "请增加剂量"
        result = map_f09_advice(run, frozen, f08_status="partial", test_only_mock_advice=True)
        self.assertFalse(result.ready)
        self.assertEqual(result.dropped[0]["reason"], "invalid_or_unsafe_text")

    def test_latest_backend_callback_model(self):
        source = os.environ.get("GCA_BACKEND_SOURCE")
        if not source:
            self.skipTest("set GCA_BACKEND_SOURCE to check the actual backend Pydantic model")
        sys.path.insert(0, str(Path(source) / "backend" / "src"))
        from gutcare.analysis.advice import AdviceCallbackBody

        run, frozen = fixture()
        mapped = map_f09_advice(run, frozen, f08_status="partial")
        AdviceCallbackBody.model_validate(mapped.payload)


if __name__ == "__main__":
    unittest.main()

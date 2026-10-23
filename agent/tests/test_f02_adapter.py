"""Targeted F02 adapter contract and retry tests."""
import base64
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

from gutcare_agents.contract import Status
from gutcare_agents.errors import ErrorCode
from gutcare_agents.f02_adapter import (
    F02ContractError, F02Journal, map_medical_result, process_medical_task, validate_input,
)


class F02AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.request_id, self.document_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.dispatch = {"request_id": self.request_id, "schema_version": "1.0"}
        self.raw = {"request_id": self.request_id, "document_id": self.document_id,
                    "document_version": 1, "document_type": "lab_report", "document_date": None,
                    "content_type": "application/pdf", "file_name": "report.pdf",
                    "content_base64": base64.b64encode(b"%PDF-1.4 synthetic").decode()}

    def test_input_validation_and_mapping(self):
        validate_input(self.raw, self.request_id)
        with self.assertRaises(F02ContractError):
            validate_input({**self.raw, "content_base64": base64.b64encode(b"bad").decode()}, self.request_id)
        result = SimpleNamespace(status=Status.OK, data={"exam_items": [
            {"name": "项目", "value": "5", "unit": "mg/L", "raw_text": "项目 5 mg/L"},
            {"name": "粪便钙卫蛋白", "value": "86", "unit": "ug/g", "raw_text": "粪便钙卫蛋白 86 ug/g"},
        ]})
        mapped = map_medical_result(self.request_id, result)
        self.assertEqual(mapped["parse_outcome"], "extracted")
        self.assertEqual([x["field_code"] for x in mapped["candidates"]],
                         ["test_item", "test_result", "test_item", "test_result"])

    def test_callback_is_replayed_without_rereading_or_reanalysis(self):
        journal = F02Journal(Path(self.tmp.name) / "agent.sqlite")
        class Client:
            reads = 0
            fail = True
            def request(inner, method, path, payload=None):
                if method == "GET":
                    inner.reads += 1
                    return self.raw
                if inner.fail:
                    raise URLError("transport")
                return {}
        client = Client()
        result = SimpleNamespace(status=Status.OK, error=None, data={"exam_items": [{"name": "项目",
            "value": "5", "raw_text": "项目 5"}]})
        with patch("gutcare_agents.f02_adapter._run_medical", return_value=result) as run:
            with self.assertRaises(URLError):
                process_medical_task(client, None, self.dispatch, journal=journal, retry_delay=0)
            client.fail = False
            process_medical_task(client, None, self.dispatch, journal=F02Journal(journal.db_path), retry_delay=0)
            self.assertEqual(run.call_count, 1)
        self.assertEqual(client.reads, 1)
        row = journal.get(self.request_id)
        self.assertEqual(row["state"], "completed")
        self.assertNotIn("content_base64", str(row))

    def test_model_failure_is_logged_with_a_stable_code_without_document_content(self):
        journal = F02Journal(Path(self.tmp.name) / "agent.sqlite")

        class Client:
            def request(_inner, method, _path, payload=None):
                if method == "GET":
                    return self.raw
                self.assertEqual(payload["error_code"], "agent_unavailable")
                return {}

        failed = SimpleNamespace(
            status=Status.FAILED,
            error={"code": ErrorCode.MODEL_TIMEOUT, "message": "private provider response"},
            data={},
        )
        with patch("gutcare_agents.f02_adapter._run_medical", return_value=failed), \
             self.assertLogs("gutcare.f02", level="ERROR") as captured:
            process_medical_task(Client(), None, self.dispatch, journal=journal, retry_delay=0)
        self.assertIn("error_code=model_timeout", "\n".join(captured.output))
        self.assertNotIn("private provider response", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()

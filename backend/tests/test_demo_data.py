"""Tests for the offline synthetic demo bundle builder."""

import importlib.util
import json
import tempfile
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "demo_data", Path(__file__).parents[2] / "scripts" / "demo_data.py"
)
assert SPEC and SPEC.loader
demo_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo_data)


def source_record(**overrides):
    record = {
        "synthetic": True,
        "for_testing_only": True,
        "clinical_use_allowed": False,
        "cohort": "cohort_a",
        "record_type": "diet-records",
        "occurred_day": 3,
        "payload": {
            "meal_type": "lunch",
            "items": [{"name": "Synthetic rice", "category_code": "grain"}],
        },
    }
    record.update(overrides)
    return record


def test_build_emits_new_ids_fixed_dates_and_accepted_bundle():
    with tempfile.TemporaryDirectory() as tmp:
        source, output = Path(tmp) / "source.json", Path(tmp) / "bundle.json"
        source.write_text(
            json.dumps({"schema_version": "1.0", "records": [source_record()]}), encoding="utf-8"
        )
        demo_data.build_bundle(source, output)
        bundle = json.loads(output.read_text(encoding="utf-8"))
    assert bundle["demo_only"] is True and bundle["synthetic_only"] is True
    row = bundle["records"][0]
    assert row["occurred_at"].startswith("2026-01-04T00:00:00")
    assert demo_data.validate_bundle(bundle)
    assert "synthetic" not in row and "for_testing_only" not in row
    diet_item = row["payload"]["items"][0]
    assert diet_item == {"name": "Demo food 1", "category_code": None, "amount_text": None}


def test_rejects_unmarked_records_without_echoing_source_content():
    with tempfile.TemporaryDirectory() as tmp:
        source, output = Path(tmp) / "source.json", Path(tmp) / "bundle.json"
        source.write_text(
            json.dumps({"schema_version": "1.0", "records": [source_record(synthetic=False)]}),
            encoding="utf-8",
        )
        try:
            demo_data.build_bundle(source, output)
        except demo_data.DemoError as exc:
            assert "synthetic" not in str(exc)
        else:
            raise AssertionError("unmarked data accepted")


def test_rejects_forbidden_fields_and_payload_text():
    for changes in (
        {"participant_id": "private-value"},
        {"payload": {"bristol_type": 4, "notes": "private-value"}},
    ):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "source.json", Path(tmp) / "bundle.json"
            source.write_text(
                json.dumps({"schema_version": "1.0", "records": [source_record(**changes)]}),
                encoding="utf-8",
            )
            try:
                demo_data.build_bundle(source, output)
            except demo_data.DemoError as exc:
                assert "private-value" not in str(exc)
            else:
                raise AssertionError("forbidden data accepted")


def test_build_does_not_retain_diet_source_text_or_categories():
    with tempfile.TemporaryDirectory() as tmp:
        source, output = Path(tmp) / "source.json", Path(tmp) / "bundle.json"
        private_values = ("Untrusted source label", "untrusted-category", "untrusted amount")
        record = source_record(
            payload={
                "meal_type": "lunch",
                "items": [
                    {
                        "name": private_values[0],
                        "category_code": private_values[1],
                        "amount_text": private_values[2],
                    }
                ],
            }
        )
        source.write_text(
            json.dumps({"schema_version": "1.0", "records": [record]}), encoding="utf-8"
        )
        demo_data.build_bundle(source, output)
        content = output.read_text(encoding="utf-8")
        assert all(value not in content for value in private_values)
        assert "Demo food 1" in content


def test_bundle_rejects_tampering_or_extra_keys():
    bundle = {
        "schema_version": "1.0",
        "demo_only": True,
        "synthetic_only": True,
        "created_at": "2026-10-18T00:00:00+00:00",
        "records": [],
    }
    assert not demo_data.validate_bundle(bundle)
    bundle["records"] = [
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "cohort": "cohort_a",
            "record_type": "stool-records",
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "payload": {"bristol_type": 4, "notes": "x"},
        }
    ]
    assert not demo_data.validate_bundle(bundle)


class FakeHttp:
    def __init__(self, ready=True, register_status=202, openapi=None, record_status=201):
        self.ready = ready
        self.register_status = register_status
        self.openapi = openapi or demo_openapi()
        self.record_status = record_status
        self.calls = []
        self.registered = set()
        self.created_records = {}

    def request(self, method, path, payload=None, headers=None):
        self.calls.append((method, path, payload, headers or {}))
        if path == "/health/ready":
            return (200, {"status": "ready"}) if self.ready else (503, None)
        if path == "/openapi.json":
            return 200, self.openapi
        if path == "/api/v1/auth/register":
            if self.register_status == 202 and payload:
                self.registered.add(payload["email"])
            return self.register_status, None
        if path == "/api/v1/auth/email/verify":
            return 204, None
        if path == "/api/v1/auth/login":
            if payload["email"] in self.registered:
                return 200, {"access_token": "opaque-access-token-value"}
            return 401, None
        if path == "/api/v1/patients/me":
            return 200, {"id": "opaque-profile-id"}
        if path == "/api/v1/patients/me/consents":
            return 200, [
                {"consent_type": "privacy_policy", "granted": True},
                {"consent_type": "health_data_processing", "granted": True},
            ]
        if path.startswith("/api/v1/"):
            if path.rsplit("/", 1)[-1] in {"diet-records", "stool-records", "symptom-records"}:
                key = (
                    payload["record_type"] if "record_type" in payload else path,
                    (headers or {}).get("Idempotency-Key"),
                )
                if self.record_status != 201:
                    return self.record_status, {"detail": "opaque response that must not be shown"}
                if key not in self.created_records:
                    self.created_records[key] = {
                        "id": f"opaque-record-{len(self.created_records) + 1}"
                    }
                return 201, self.created_records[key]
            return 201, {"id": "opaque-record-id"}
        return 404, None


def demo_openapi():
    return {
        "info": {"version": "1.0.0"},
        "paths": {
            "/api/v1/auth/register": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/RegisterRequest"}
                            }
                        },
                    },
                    "responses": {"202": {}},
                }
            },
            "/api/v1/auth/email/verify": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/VerifyEmailRequest"}
                            }
                        },
                    },
                    "responses": {"204": {}},
                }
            },
            "/api/v1/auth/login": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/LoginRequest"}
                            }
                        },
                    },
                    "responses": {"200": {}},
                }
            },
            "/api/v1/patients/me": {"get": {}},
            "/api/v1/patients/me/consents": {"get": {}},
            "/api/v1/{record_type}": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/RecordWrite"}
                            }
                        },
                    },
                    "parameters": [
                        {
                            "name": "Idempotency-Key",
                            "in": "header",
                            "required": True,
                            "schema": {"type": "string", "minLength": 8, "maxLength": 128},
                        }
                    ],
                    "responses": {"201": {}},
                }
            },
        },
        "components": {
            "schemas": {
                "RegisterRequest": {
                    "type": "object",
                    "required": [
                        "email",
                        "password",
                        "birth_year",
                        "privacy_policy_version",
                        "health_data_processing_consent",
                        "health_data_processing_policy_version",
                    ],
                    "properties": {
                        key: {}
                        for key in [
                            "email",
                            "password",
                            "birth_year",
                            "privacy_policy_version",
                            "health_data_processing_consent",
                            "health_data_processing_policy_version",
                        ]
                    },
                },
                "VerifyEmailRequest": {
                    "type": "object",
                    "required": ["token"],
                    "properties": {"token": {"type": "string", "minLength": 20}},
                },
                "LoginRequest": {
                    "type": "object",
                    "required": ["email", "password"],
                    "properties": {"email": {}, "password": {}},
                },
                "RecordWrite": {
                    "type": "object",
                    "required": ["occurred_at", "payload"],
                    "properties": {
                        "occurred_at": {"type": "string"},
                        "payload": {
                            "oneOf": [
                                {"$ref": "#/components/schemas/DietPayload"},
                                {"$ref": "#/components/schemas/StoolPayload"},
                                {"$ref": "#/components/schemas/SymptomPayload"},
                            ]
                        },
                    },
                },
                "DietPayload": {
                    "type": "object",
                    "properties": {
                        "meal_type": {"type": "string"},
                        "items": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/DietItem"},
                        },
                    },
                },
                "DietItem": {"type": "object", "properties": {"name": {"type": "string"}}},
                "StoolPayload": {
                    "type": "object",
                    "properties": {"bristol_type": {"type": "integer"}},
                },
                "SymptomPayload": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/SymptomItem"},
                        }
                    },
                },
                "SymptomItem": {
                    "type": "object",
                    "properties": {"symptom_code": {"type": "string"}},
                },
            }
        },
    }


def demo_bundle():
    return {
        "schema_version": "1.0",
        "demo_only": True,
        "synthetic_only": True,
        "created_at": datetime.now(UTC).isoformat(),
        "records": [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "cohort": "cohort_a",
                "record_type": "diet-records",
                "occurred_at": "2026-01-01T00:00:00+00:00",
                "payload": {
                    "meal_type": "lunch",
                    "items": [{"name": "Demo food 1", "category_code": None, "amount_text": None}],
                },
            },
            {
                "id": "00000000-0000-4000-8000-000000000002",
                "cohort": "cohort_b",
                "record_type": "stool-records",
                "occurred_at": "2026-01-02T00:00:00+00:00",
                "payload": {"bristol_type": 4},
            },
            {
                "id": "00000000-0000-4000-8000-000000000003",
                "cohort": "cohort_b",
                "record_type": "symptom-records",
                "occurred_at": "2026-01-03T00:00:00+00:00",
                "payload": {"items": [{"symptom_code": "bloating", "severity": 2}]},
            },
        ],
    }


def registration_notice_file(path):
    import hashlib

    entries = []
    config = {}
    for kind, version, version_key, hash_key in (
        (
            "privacy_policy",
            "demo-privacy-v1",
            "PRIVACY_POLICY_VERSION",
            "PRIVACY_POLICY_SUMMARY_HASH",
        ),
        (
            "health_data_processing",
            "demo-health-v1",
            "HEALTH_DATA_PROCESSING_POLICY_VERSION",
            "HEALTH_DATA_PROCESSING_SUMMARY_HASH",
        ),
    ):
        summary = f"Synthetic test notice for {kind}."
        digest = hashlib.sha256(summary.encode()).hexdigest()
        entries.append(
            {
                "consent_type": kind,
                "policy_version": version,
                "summary": summary,
                "summary_sha256": digest,
            }
        )
        config[version_key] = version
        config[hash_key] = digest
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "artifact_classification": "development_test_only",
                "legal_approval_status": "not_approved_for_production",
                "notices": entries,
                "backend_config": config,
            }
        ),
        encoding="utf-8",
    )


def test_initialize_registers_verifies_logs_in_and_posts_idempotent_records(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_A", "synthetic-password-a")
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_B", "synthetic-password-b")
        monkeypatch.setattr(
            demo_data.getpass, "getpass", lambda _: "opaque-verification-token-value"
        )
        fake = FakeHttp()
        for _ in range(2):
            demo_data.initialize_bundle(
                bundle_path,
                notice_path,
                "https://demo.invalid",
                "gutcare-demo",
                "example.invalid",
                demo_mode=True,
                target_env="test",
                client=fake,
            )
        registrations = [call for call in fake.calls if call[1] == "/api/v1/auth/register"]
        assert len(registrations) == 2
        assert {item[2]["email"] for item in registrations} == {
            "gutcare-demo+cohort_a@example.invalid",
            "gutcare-demo+cohort_b@example.invalid",
        }
        assert all(item[2]["privacy_policy_version"] == "demo-privacy-v1" for item in registrations)
        record_calls = [
            call
            for call in fake.calls
            if call[1].startswith("/api/v1/")
            and call[1].split("/")[-1] in {"diet-records", "stool-records", "symptom-records"}
        ]
        assert len(record_calls) == 6
        assert len(fake.created_records) == 3
        keys_by_path = {}
        for call in record_calls:
            keys_by_path.setdefault(call[1], []).append(call[3]["Idempotency-Key"])
        assert len(keys_by_path) == 3
        assert all(len(keys) == 2 and keys[0] == keys[1] for keys in keys_by_path.values())
        paths = [call[1] for call in fake.calls]
        assert paths.index("/health/ready") < paths.index("/api/v1/auth/register")
        assert paths.index("/api/v1/auth/login") < paths.index("/api/v1/auth/register")
        register_index = paths.index("/api/v1/auth/register")
        verify_index = paths.index("/api/v1/auth/email/verify")
        assert register_index < verify_index < paths.index("/api/v1/auth/login", verify_index)
        assert paths.count("/api/v1/auth/email/verify") == 2


def test_existing_active_accounts_skip_registration_and_verification(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_A", "synthetic-password-a")
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_B", "synthetic-password-b")
        fake = FakeHttp()
        fake.registered.update(
            {
                "gutcare-demo+cohort_a@example.invalid",
                "gutcare-demo+cohort_b@example.invalid",
            }
        )
        demo_data.initialize_bundle(
            bundle_path,
            notice_path,
            "https://demo.invalid",
            "gutcare-demo",
            "example.invalid",
            demo_mode=True,
            target_env="test",
            client=fake,
        )
        paths = [call[1] for call in fake.calls]
        assert paths.count("/api/v1/auth/login") == 2
        assert "/api/v1/auth/register" not in paths
        assert "/api/v1/auth/email/verify" not in paths


def test_record_idempotent_replay_accepts_contract_201_only_and_hides_unexpected_body(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_A", "synthetic-password-a")
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_B", "synthetic-password-b")
        fake = FakeHttp(record_status=200)
        fake.registered.update(
            {
                "gutcare-demo+cohort_a@example.invalid",
                "gutcare-demo+cohort_b@example.invalid",
            }
        )
        try:
            demo_data.initialize_bundle(
                bundle_path,
                notice_path,
                "https://demo.invalid",
                "gutcare-demo",
                "example.invalid",
                demo_mode=True,
                target_env="test",
                client=fake,
            )
        except demo_data.DemoError as exc:
            assert "opaque response" not in str(exc)
            assert "200" not in str(exc)
        else:
            raise AssertionError("unexpected HTTP 200 record response accepted")


def test_redirect_handler_never_follows_redirects():
    handler = demo_data._NoRedirectHandler()
    request = urllib.request.Request("https://demo.invalid/api/v1/auth/login")
    assert (
        handler.redirect_request(request, None, 302, "Found", {}, "https://other.invalid/") is None
    )


def test_initialize_fails_before_registration_when_not_demo_opted_in(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        fake = FakeHttp()
        try:
            demo_data.initialize_bundle(
                bundle_path,
                notice_path,
                "https://demo.invalid",
                "gutcare-demo",
                "example.invalid",
                demo_mode=False,
                target_env="test",
                client=fake,
            )
        except demo_data.DemoError:
            pass
        else:
            raise AssertionError("missing demo opt-in accepted")
        assert fake.calls == []


def test_initializer_http_exception_requires_local_target_and_two_opt_ins():
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        for options in (
            {"allow_local_http": True, "test_opt_in": False, "target_env": "test"},
            {"allow_local_http": True, "test_opt_in": True, "target_env": "demo"},
        ):
            fake = FakeHttp()
            try:
                demo_data.initialize_bundle(
                    bundle_path,
                    notice_path,
                    "http://127.0.0.1:8080",
                    "gutcare-demo",
                    "example.invalid",
                    demo_mode=True,
                    client=fake,
                    **options,
                )
            except demo_data.DemoError:
                pass
            else:
                raise AssertionError("HTTP exception accepted without valid opt-ins")
            assert fake.calls == []


def test_initializer_requires_explicit_valid_notice_artifact():
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        artifact = json.loads(notice_path.read_text(encoding="utf-8"))
        artifact["artifact_classification"] = "production_approved"
        notice_path.write_text(json.dumps(artifact), encoding="utf-8")
        for supplied_notice in (None, notice_path):
            fake = FakeHttp()
            try:
                demo_data.initialize_bundle(
                    bundle_path,
                    supplied_notice,
                    "https://demo.invalid",
                    "gutcare-demo",
                    "example.invalid",
                    demo_mode=True,
                    target_env="test",
                    client=fake,
                )
            except demo_data.DemoError:
                pass
            else:
                raise AssertionError("missing or disallowed notice artifact accepted")
            assert fake.calls == []


def test_openapi_preflight_rejects_missing_dto_body_key_or_payload_before_auth(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_A", "synthetic-password-a")
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_B", "synthetic-password-b")
        cases = []

        missing_body = demo_openapi()
        del missing_body["paths"]["/api/v1/auth/register"]["post"]["requestBody"]
        cases.append(missing_body)

        missing_key = demo_openapi()
        missing_key["paths"]["/api/v1/{record_type}"]["post"]["parameters"] = []
        cases.append(missing_key)

        missing_payload_dto = demo_openapi()
        del missing_payload_dto["components"]["schemas"]["SymptomPayload"]
        cases.append(missing_payload_dto)

        too_short_key = demo_openapi()
        too_short_key["paths"]["/api/v1/{record_type}"]["post"]["parameters"][0]["schema"][
            "minLength"
        ] = 1
        cases.append(too_short_key)

        for schema in cases:
            fake = FakeHttp(openapi=schema)
            try:
                demo_data.initialize_bundle(
                    bundle_path,
                    notice_path,
                    "https://demo.invalid",
                    "gutcare-demo",
                    "example.invalid",
                    demo_mode=True,
                    target_env="test",
                    client=fake,
                )
            except demo_data.DemoError:
                pass
            else:
                raise AssertionError("invalid remote OpenAPI was accepted")
            assert not any(
                call[1].endswith("/auth/login") or call[1].endswith("/auth/register")
                for call in fake.calls
            )


def test_initialize_fails_closed_on_readiness_and_registration_errors(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_A", "synthetic-password-a")
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_B", "synthetic-password-b")
        for fake in (FakeHttp(ready=False), FakeHttp(register_status=422)):
            try:
                demo_data.initialize_bundle(
                    bundle_path,
                    notice_path,
                    "https://demo.invalid",
                    "gutcare-demo",
                    "example.invalid",
                    demo_mode=True,
                    target_env="test",
                    client=fake,
                )
            except demo_data.DemoError as exc:
                assert "422" not in str(exc)
            else:
                raise AssertionError("unexpected response accepted")
            assert not any(call[1] == "/api/v1/auth/email/verify" for call in fake.calls)


def test_mailpit_requires_loopback_test_opt_in_and_extracts_only_recipient_token(monkeypatch):
    class FakeMailpit:
        def __init__(self):
            self.calls = []

        def request(self, method, path, payload=None, headers=None):
            self.calls.append(path)
            if path.startswith("/api/v1/search?"):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
                self.recipient = query["query"][0].removeprefix("to:")
                return 200, {"messages": [{"ID": "synthetic-message-id"}]}
            return 200, {
                "To": [{"Address": self.recipient}],
                "Text": "https://demo.invalid/verify?token=opaque-verification-token-value",
            }

    with tempfile.TemporaryDirectory() as tmp:
        bundle_path = Path(tmp) / "bundle.json"
        notice_path = Path(tmp) / "notice.json"
        bundle_path.write_text(json.dumps(demo_bundle()), encoding="utf-8")
        registration_notice_file(notice_path)
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_A", "synthetic-password-a")
        monkeypatch.setenv("GUTCARE_DEMO_PASSWORD_B", "synthetic-password-b")
        api = FakeHttp()
        try:
            demo_data.initialize_bundle(
                bundle_path,
                notice_path,
                "https://demo.invalid",
                "gutcare-demo",
                "example.invalid",
                demo_mode=True,
                target_env="test",
                mailpit_url="http://mailpit.invalid",
                test_opt_in=True,
                client=api,
                mailpit_client=FakeMailpit(),
            )
        except demo_data.DemoError:
            pass
        else:
            raise AssertionError("non-loopback Mailpit was accepted")
        assert api.calls == []

        mailpit = FakeMailpit()
        demo_data.initialize_bundle(
            bundle_path,
            notice_path,
            "https://demo.invalid",
            "gutcare-demo",
            "example.invalid",
            demo_mode=True,
            target_env="test",
            mailpit_url="http://127.0.0.1:8025",
            test_opt_in=True,
            client=FakeHttp(),
            mailpit_client=mailpit,
        )
        assert len(mailpit.calls) == 4

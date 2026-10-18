"""Build strictly synthetic GutCare demo bundles offline."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

SCHEMA_VERSION = "1.0"
RECORD_TYPES = {"diet-records", "stool-records", "symptom-records"}


class DemoError(Exception):
    """Safe-to-display failure without source or credential values."""


def _fail() -> NoReturn:
    raise DemoError("输入或环境校验失败；未输出源数据或远端响应内容。")


def _only(obj: Any, keys: set[str]) -> bool:
    return isinstance(obj, dict) and set(obj) <= keys


def _safe_structured_text(value: Any, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and not re.search(r"https?://|[/\\]|\b(?:www\.|[\w.-]+\.[a-z]{2,}/)", value, re.IGNORECASE)
    )


def _valid_source_record(record: Any) -> bool:
    if not isinstance(record, dict) or record.get("synthetic") is not True:
        return False
    if (
        record.get("for_testing_only") is not True
        or record.get("clinical_use_allowed") is not False
    ):
        return False
    if set(record) - {
        "synthetic",
        "for_testing_only",
        "clinical_use_allowed",
        "cohort",
        "record_type",
        "occurred_day",
        "payload",
    }:
        return False
    if (
        record.get("cohort") not in {"cohort_a", "cohort_b"}
        or record.get("record_type") not in RECORD_TYPES
    ):
        return False
    if type(record.get("occurred_day")) is not int or not 0 <= record["occurred_day"] <= 29:
        return False
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return False
    kind = record["record_type"]
    if kind == "diet-records":
        return (
            _only(payload, {"meal_type", "items"})
            and payload.get("meal_type") in {"breakfast", "lunch", "dinner", "snack", "other"}
            and isinstance(payload.get("items"), list)
            and 1 <= len(payload["items"]) <= 10
            and all(
                _only(x, {"name", "category_code", "amount_text"})
                and _safe_structured_text(x.get("name"), 80)
                and all(
                    v is None
                    or isinstance(v, str)
                    and len(v) <= 40
                    and not re.search(r"https?://|[/\\]", v, re.IGNORECASE)
                    for k, v in x.items()
                    if k != "name"
                )
                for x in payload["items"]
            )
        )
    if kind == "stool-records":
        return (
            _only(payload, {"bristol_type"})
            and type(payload.get("bristol_type")) is int
            and 1 <= payload["bristol_type"] <= 7
        )
    return (
        _only(payload, {"items", "symptom_status"})
        and payload.get("symptom_status", "ongoing") in {"ongoing", "relieved"}
        and isinstance(payload.get("items"), list)
        and 1 <= len(payload["items"]) <= 5
        and all(
            _only(x, {"symptom_code", "severity"})
            and x.get("symptom_code")
            in {
                "abdominal_pain",
                "bloating",
                "diarrhea",
                "constipation",
                "nausea",
                "vomiting",
                "acid_reflux",
                "appetite_change",
                "blood_in_stool_concern",
            }
            and ("severity" not in x or type(x["severity"]) is int and 0 <= x["severity"] <= 10)
            for x in payload["items"]
        )
    )


def build_bundle(source_path: Path, output_path: Path) -> None:
    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        if (
            not _only(source, {"schema_version", "records"})
            or source.get("schema_version") != SCHEMA_VERSION
            or not isinstance(source.get("records"), list)
            or not source["records"]
        ):
            _fail()
        records = source["records"]
        if len(records) > 500 or any(not _valid_source_record(row) for row in records):
            _fail()
        cohorts = {row["cohort"] for row in records}
        if len(cohorts) > 2:
            _fail()
        origin = date(2026, 1, 1)
        normalized = []
        for row in records:
            payload = row["payload"]
            if row["record_type"] == "diet-records":
                payload = {
                    "meal_type": payload["meal_type"],
                    "items": [
                        {"name": f"Demo food {index}", "category_code": None, "amount_text": None}
                        for index, _ in enumerate(payload["items"], start=1)
                    ],
                }
            normalized.append(
                {
                    "id": str(uuid.uuid4()),
                    "cohort": row["cohort"],
                    "record_type": row["record_type"],
                    "occurred_at": datetime.combine(
                        origin + timedelta(days=row["occurred_day"]), datetime.min.time(), UTC
                    ).isoformat(),
                    "payload": payload,
                }
            )
        bundle = {
            "schema_version": SCHEMA_VERSION,
            "demo_only": True,
            "synthetic_only": True,
            "created_at": datetime.now(UTC).isoformat(),
            "records": normalized,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except DemoError:
        raise
    except Exception as exc:
        raise DemoError("构建失败；未输出源数据或文件内容。") from exc


def validate_bundle(bundle: Any) -> bool:
    if not _only(
        bundle, {"schema_version", "demo_only", "synthetic_only", "created_at", "records"}
    ):
        return False
    if (
        bundle.get("schema_version") != SCHEMA_VERSION
        or bundle.get("demo_only") is not True
        or bundle.get("synthetic_only") is not True
    ):
        return False
    rows = bundle.get("records")
    if not isinstance(rows, list) or not rows or len(rows) > 500:
        return False
    try:
        created_at = datetime.fromisoformat(bundle["created_at"])
        if created_at.tzinfo is None:
            return False
    except (ValueError, TypeError):
        return False
    cohort_ids = set()
    record_ids = set()
    for row in rows:
        if (
            not _only(row, {"id", "cohort", "record_type", "occurred_at", "payload"})
            or row.get("cohort") not in {"cohort_a", "cohort_b"}
            or row.get("record_type") not in RECORD_TYPES
        ):
            return False
        try:
            parsed_id = uuid.UUID(row["id"])
            occurred_at = datetime.fromisoformat(row["occurred_at"])
        except (ValueError, TypeError, KeyError):
            return False
        if parsed_id in record_ids or occurred_at.tzinfo is None:
            return False
        if occurred_at.date() < date(2026, 1, 1) or occurred_at.date() > date(2026, 1, 30):
            return False
        if (
            occurred_at.time().hour
            or occurred_at.time().minute
            or occurred_at.time().second
            or occurred_at.time().microsecond
        ):
            return False
        record_ids.add(parsed_id)
        cohort_ids.add(row["cohort"])
        # Reuse exact payload allowlists, with bundle-only fixed authorization metadata.
        src = {
            "synthetic": True,
            "for_testing_only": True,
            "clinical_use_allowed": False,
            "cohort": row["cohort"],
            "record_type": row["record_type"],
            "occurred_day": 0,
            "payload": row["payload"],
        }
        if not _valid_source_record(src):
            return False
        if row["record_type"] == "diet-records" and any(
            item.get("name") != f"Demo food {index}"
            or item.get("category_code") is not None
            or item.get("amount_text") is not None
            for index, item in enumerate(row["payload"]["items"], start=1)
        ):
            return False
    return len(cohort_ids) <= 2


class HttpClient:
    """Small strict JSON client; responses and request bodies are never logged."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        request_headers = {"Accept": "application/json", "Content-Type": "application/json"}
        request_headers.update(headers or {})
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            self.base_url + path, data=body, headers=request_headers, method=method
        )
        try:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), _NoRedirectHandler()
            )
            with opener.open(request, timeout=15) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            return exc.code, None
        except Exception as exc:
            raise DemoError("网络请求失败；远端响应和请求内容已隐藏。") from exc


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, new_url: str
    ) -> Any:
        return None


def _load_registration_notice(path: Path) -> dict[str, str]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(artifact, dict)
            or not _only(
                artifact,
                {
                    "schema_version",
                    "artifact_classification",
                    "legal_approval_status",
                    "locale",
                    "canonicalization",
                    "notices",
                    "backend_config",
                },
            )
            or artifact.get("schema_version") != "1.0"
            or artifact.get("artifact_classification") != "development_test_only"
            or artifact.get("legal_approval_status") != "not_approved_for_production"
        ):
            _fail()
        notices = artifact.get("notices")
        config = artifact.get("backend_config")
        if not isinstance(notices, list) or not isinstance(config, dict):
            _fail()
        versions: dict[str, str] = {}
        for kind, key, hash_key in (
            ("privacy_policy", "PRIVACY_POLICY_VERSION", "PRIVACY_POLICY_SUMMARY_HASH"),
            (
                "health_data_processing",
                "HEALTH_DATA_PROCESSING_POLICY_VERSION",
                "HEALTH_DATA_PROCESSING_SUMMARY_HASH",
            ),
        ):
            matches = [n for n in notices if isinstance(n, dict) and n.get("consent_type") == kind]
            if len(matches) != 1:
                _fail()
            notice = matches[0]
            if not _only(notice, {"consent_type", "policy_version", "summary", "summary_sha256"}):
                _fail()
            version, summary, supplied_hash = (
                notice.get("policy_version"),
                notice.get("summary"),
                notice.get("summary_sha256"),
            )
            if not isinstance(version, str) or not 1 <= len(version) <= 32:
                _fail()
            if not isinstance(summary, str) or not isinstance(supplied_hash, str):
                _fail()
            canonical = summary.replace("\r\n", "\n").replace("\r", "\n")
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if (
                supplied_hash.lower() != digest
                or config.get(key) != version
                or str(config.get(hash_key, "")).lower() != digest
            ):
                _fail()
            versions[kind] = version
        return versions
    except DemoError:
        raise
    except Exception as exc:
        raise DemoError("告知制品无效或不可读取；未回显文件内容。") from exc


def _validate_base_url(base_url: str, allow_local_http: bool) -> None:
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    ):
        return
    if (
        allow_local_http
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    ):
        return
    _fail()


def _password(cohort: str) -> str:
    env_name = f"GUTCARE_DEMO_PASSWORD_{cohort[-1].upper()}"
    value = os.environ.get(env_name) or getpass.getpass(f"Password for {cohort}: ")
    if not 12 <= len(value) <= 128:
        _fail()
    return value


def _verification_token(
    email: str, mailpit_url: str | None, mailpit_client: HttpClient | None = None
) -> str:
    if mailpit_url is None:
        token = getpass.getpass("Email verification token: ")
        if len(token) < 20:
            _fail()
        return token
    parsed = urllib.parse.urlsplit(mailpit_url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        _fail()
    query = urllib.parse.urlencode({"query": f"to:{email}", "limit": "10"})
    mailpit = mailpit_client or HttpClient(mailpit_url)
    status_code, result = mailpit.request("GET", f"/api/v1/search?{query}")
    if (
        status_code != 200
        or not isinstance(result, dict)
        or not isinstance(result.get("messages"), list)
    ):
        _fail()
    for item in result["messages"]:
        if not isinstance(item, dict) or not isinstance(item.get("ID"), str):
            continue
        code, message = mailpit.request("GET", f"/api/v1/message/{item['ID']}")
        if code != 200 or not isinstance(message, dict):
            continue
        # Match recipient before inspecting message text; never print or persist it.
        recipients = message.get("To", [])
        addresses = (
            [r.get("Address", "").lower() for r in recipients if isinstance(r, dict)]
            if isinstance(recipients, list)
            else []
        )
        if email.lower() not in addresses:
            continue
        content = "\n".join(str(message.get(field, "")) for field in ("Text", "HTML"))
        tokens = set(re.findall(r"[?&]token=([A-Za-z0-9_-]{20,})", content))
        if len(tokens) == 1:
            token = next(iter(tokens))
            if isinstance(token, str):
                return token
        _fail()
    _fail()


def _resolve_schema(
    schema: Any, components: Any, visited: set[str] | None = None
) -> dict[str, Any] | None:
    if not isinstance(schema, dict):
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        name = ref.rsplit("/", 1)[-1]
        seen = visited or set()
        if name in seen or not isinstance(components, dict):
            return None
        target = components.get(name)
        if not isinstance(target, dict):
            return None
        return _resolve_schema(target, components, seen | {name})
    return schema


def _body_schema(operation: Any, components: Any) -> dict[str, Any] | None:
    if not isinstance(operation, dict):
        return None
    body = operation.get("requestBody")
    if not isinstance(body, dict) or body.get("required") is not True:
        return None
    content = body.get("content")
    media = content.get("application/json") if isinstance(content, dict) else None
    return _resolve_schema(media.get("schema"), components) if isinstance(media, dict) else None


def _object_has_required(schema: Any, required: set[str], components: Any) -> bool:
    resolved = _resolve_schema(schema, components)
    if resolved is None or not isinstance(resolved.get("properties"), dict):
        return False
    actual_required = resolved.get("required", [])
    return required <= set(actual_required) and required <= set(resolved["properties"])


def _schema_tree(
    schema: Any, components: Any, visited: set[int] | None = None
) -> list[dict[str, Any]]:
    resolved = _resolve_schema(schema, components)
    if resolved is None:
        return []
    seen = visited or set()
    identity = id(resolved)
    if identity in seen:
        return []
    seen.add(identity)
    result = [resolved]
    for key in ("properties", "items"):
        child = resolved.get(key)
        if isinstance(child, dict):
            result.extend(_schema_tree(child, components, seen))
    for key in ("anyOf", "oneOf", "allOf"):
        children = resolved.get(key)
        if isinstance(children, list):
            for child in children:
                result.extend(_schema_tree(child, components, seen))
    return result


def _validate_openapi(openapi: Any) -> bool:
    if not isinstance(openapi, dict):
        return False
    info = openapi.get("info")
    paths = openapi.get("paths")
    components = (
        openapi.get("components", {}).get("schemas")
        if isinstance(openapi.get("components"), dict)
        else None
    )
    if (
        not isinstance(info, dict)
        or not str(info.get("version", "")).startswith("1.")
        or not isinstance(paths, dict)
        or not isinstance(components, dict)
    ):
        return False

    def operation(path: str, method: str) -> dict[str, Any] | None:
        item = paths.get(path)
        candidate = item.get(method) if isinstance(item, dict) else None
        return candidate if isinstance(candidate, dict) else None

    required_bodies = {
        ("/api/v1/auth/register", "post"): {
            "email",
            "password",
            "birth_year",
            "privacy_policy_version",
            "health_data_processing_consent",
            "health_data_processing_policy_version",
        },
        ("/api/v1/auth/email/verify", "post"): {"token"},
        ("/api/v1/auth/login", "post"): {"email", "password"},
        ("/api/v1/{record_type}", "post"): {"occurred_at", "payload"},
    }
    operations: dict[tuple[str, str], dict[str, Any]] = {}
    success_codes = {
        ("/api/v1/auth/register", "post"): "202",
        ("/api/v1/auth/email/verify", "post"): "204",
        ("/api/v1/auth/login", "post"): "200",
        ("/api/v1/{record_type}", "post"): "201",
    }
    for (path, method), fields in required_bodies.items():
        candidate = operation(path, method)
        body_schema = _body_schema(candidate, components)
        if (
            candidate is None
            or body_schema is None
            or not _object_has_required(body_schema, fields, components)
        ):
            return False
        responses = candidate.get("responses")
        if not isinstance(responses, dict) or success_codes[(path, method)] not in responses:
            return False
        operations[(path, method)] = candidate
    for path in ("/api/v1/patients/me", "/api/v1/patients/me/consents"):
        if operation(path, "get") is None:
            return False

    verify_schema = _body_schema(operations[("/api/v1/auth/email/verify", "post")], components)
    if verify_schema is None:
        return False
    token_schema = _resolve_schema(verify_schema["properties"]["token"], components)
    if (
        token_schema is None
        or token_schema.get("type") != "string"
        or token_schema.get("minLength", 0) < 20
    ):
        return False

    record_operation = operations[("/api/v1/{record_type}", "post")]
    record_params = list(record_operation.get("parameters", []))
    path_item = paths["/api/v1/{record_type}"]
    if isinstance(path_item, dict) and isinstance(path_item.get("parameters"), list):
        record_params.extend(path_item["parameters"])
    idempotency = next(
        (
            p
            for p in record_params
            if isinstance(p, dict)
            and p.get("name") == "Idempotency-Key"
            and p.get("in") == "header"
        ),
        None,
    )
    key_schema = (
        _resolve_schema(idempotency.get("schema"), components)
        if isinstance(idempotency, dict)
        else None
    )
    minimum = key_schema.get("minLength") if key_schema else None
    maximum = key_schema.get("maxLength") if key_schema else None
    if (
        not isinstance(idempotency, dict)
        or idempotency.get("required") is not True
        or key_schema is None
        or key_schema.get("type") != "string"
        or not isinstance(minimum, int)
        or minimum < 8
        or not isinstance(maximum, int)
        or maximum > 128
    ):
        return False

    record_schema = _body_schema(record_operation, components)
    payload_schema = record_schema.get("properties", {}).get("payload") if record_schema else None
    tree = _schema_tree(payload_schema, components)
    has_diet = any({"meal_type", "items"} <= set(node.get("properties", {})) for node in tree)
    has_stool = any("bristol_type" in node.get("properties", {}) for node in tree)
    has_symptom = any(
        "symptom_code" in item.get("properties", {})
        for node in tree
        for item in _schema_tree(node.get("properties", {}).get("items"), components)
    )
    return has_diet and has_stool and has_symptom


def initialize_bundle(
    bundle_path: Path,
    notice_path: Path | None,
    api_base: str,
    email_prefix: str,
    email_domain: str,
    *,
    demo_mode: bool,
    target_env: str,
    allow_local_http: bool = False,
    mailpit_url: str | None = None,
    test_opt_in: bool = False,
    client: HttpClient | None = None,
    mailpit_client: HttpClient | None = None,
) -> None:
    """Register two demo identities and create records using only existing APIs."""
    if (
        not demo_mode
        or target_env not in {"local", "test", "demo"}
        or notice_path is None
        or not api_base
    ):
        _fail()
    local_test_allowed = allow_local_http and test_opt_in and target_env in {"local", "test"}
    _validate_base_url(api_base, local_test_allowed)
    if mailpit_url is not None and (not test_opt_in or target_env not in {"local", "test"}):
        _fail()
    if mailpit_url is not None:
        mailpit_parsed = urllib.parse.urlsplit(mailpit_url)
        if (
            mailpit_parsed.scheme != "http"
            or mailpit_parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or mailpit_parsed.username is not None
            or mailpit_parsed.password is not None
            or mailpit_parsed.query
            or mailpit_parsed.fragment
        ):
            _fail()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not validate_bundle(bundle) or {r["cohort"] for r in bundle["records"]} != {
        "cohort_a",
        "cohort_b",
    }:
        _fail()
    notice_versions = _load_registration_notice(notice_path)
    prefix = email_prefix.strip()
    domain = email_domain.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9._+-]{1,40}", prefix) or not re.fullmatch(
        r"[A-Za-z0-9.-]{1,190}", domain
    ):
        _fail()
    http = client or HttpClient(api_base)
    ready_code, ready = http.request("GET", "/health/ready")
    if ready_code != 200 or not isinstance(ready, dict) or ready.get("status") != "ready":
        _fail()
    openapi_code, openapi = http.request("GET", "/openapi.json")
    if openapi_code != 200 or not _validate_openapi(openapi):
        _fail()
    for cohort in ("cohort_a", "cohort_b"):
        email = f"{prefix}+{cohort}@{domain}"
        password = _password(cohort)
        login_code, tokens = http.request(
            "POST", "/api/v1/auth/login", {"email": email, "password": password}
        )
        if login_code == 401:
            register_code, _ = http.request(
                "POST",
                "/api/v1/auth/register",
                {
                    "email": email,
                    "password": password,
                    "birth_year": 1990 if cohort == "cohort_a" else 1985,
                    "privacy_policy_version": notice_versions["privacy_policy"],
                    "health_data_processing_consent": True,
                    "health_data_processing_policy_version": notice_versions[
                        "health_data_processing"
                    ],
                },
            )
            if register_code != 202:
                _fail()
            verify_token = _verification_token(email, mailpit_url, mailpit_client)
            if http.request("POST", "/api/v1/auth/email/verify", {"token": verify_token})[0] != 204:
                _fail()
            login_code, tokens = http.request(
                "POST", "/api/v1/auth/login", {"email": email, "password": password}
            )
        if (
            login_code != 200
            or not isinstance(tokens, dict)
            or not isinstance(tokens.get("access_token"), str)
        ):
            _fail()
        access_token = tokens["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        profile_code, profile = http.request("GET", "/api/v1/patients/me", headers=auth_headers)
        if profile_code != 200 or not isinstance(profile, dict):
            _fail()
        consent_code, consents = http.request(
            "GET", "/api/v1/patients/me/consents", headers=auth_headers
        )
        if consent_code != 200 or not isinstance(consents, list):
            _fail()
        granted = {
            c.get("consent_type")
            for c in consents
            if isinstance(c, dict) and c.get("granted") is True
        }
        if not {"privacy_policy", "health_data_processing"} <= granted:
            _fail()
        for row in (r for r in bundle["records"] if r["cohort"] == cohort):
            body = {"occurred_at": row["occurred_at"], "payload": row["payload"]}
            key = f"demo-{row['id']}"
            code, _ = http.request(
                "POST",
                f"/api/v1/{row['record_type']}",
                body,
                {**auth_headers, "Idempotency-Key": key},
            )
            if code != 201:
                _fail()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("source", type=Path)
    build.add_argument("output", type=Path)
    init = sub.add_parser("initialize")
    init.add_argument("bundle", type=Path)
    init.add_argument("--demo-mode", action="store_true")
    init.add_argument("--target-env", choices=("local", "test", "demo"), required=True)
    init.add_argument("--test-opt-in", action="store_true")
    init.add_argument("--allow-local-http", action="store_true")
    init.add_argument("--registration-notice", type=Path)
    init.add_argument("--api-base", default=os.getenv("GUTCARE_DEMO_API_BASE", ""))
    init.add_argument("--email-prefix", default=os.getenv("GUTCARE_DEMO_EMAIL_PREFIX", ""))
    init.add_argument("--email-domain", default=os.getenv("GUTCARE_DEMO_EMAIL_DOMAIN", ""))
    init.add_argument("--mailpit-url")
    args = parser.parse_args()
    try:
        if args.command == "build":
            build_bundle(args.source, args.output)
            print("Synthetic demo bundle created.")
        else:
            initialize_bundle(
                args.bundle,
                args.registration_notice,
                args.api_base,
                args.email_prefix,
                args.email_domain,
                demo_mode=args.demo_mode,
                target_env=args.target_env,
                allow_local_http=args.allow_local_http,
                mailpit_url=args.mailpit_url,
                test_opt_in=args.test_opt_in,
            )
            print("Synthetic demo initialization completed.")
        return 0
    except DemoError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("操作失败；未输出远端响应、bundle 内容或账号信息。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

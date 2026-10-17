"""Single fail-closed resolver for the server-owned current consent notices."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from gutcare.config import Settings

SUPPORTED_NOTICE_TYPES = frozenset(
    {"health_data_processing", "mood_data_processing", "mood_ai_sharing", "third_party_ai"}
)


@dataclass(frozen=True, slots=True)
class CurrentConsentNotice:
    consent_type: str
    policy_version: str
    summary: str
    purpose: str
    data_scope: str
    recipient: str
    withdrawal_effect: str
    summary_sha256: str


_CONFIG_SUFFIXES = {
    "health_data_processing": "HEALTH_DATA_PROCESSING",
    "mood_data_processing": "MOOD_DATA_PROCESSING",
    "mood_ai_sharing": "MOOD_AI_SHARING",
    "third_party_ai": "THIRD_PARTY_AI",
}


def resolve_current_consent_notice(
    settings: Settings, consent_type: str
) -> CurrentConsentNotice | None:
    """Return a notice only if artifact, environment, and runtime config agree exactly."""
    if consent_type not in SUPPORTED_NOTICE_TYPES:
        return None

    artifact_path: Path | None
    if settings.env in {"local", "test"}:
        artifact_path = settings.consent_notices_path or (
            Path(__file__).resolve().parents[4] / "contracts" / "consent" / "consent-notices.json"
        )
    elif settings.env in {"staging", "production"}:
        artifact_path = settings.consent_notices_path
    else:
        return None
    if artifact_path is None:
        return None

    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(artifact, dict):
        return None

    if settings.env in {"local", "test"}:
        artifact_allowed = (
            artifact.get("artifact_classification") == "development_test_only"
            and artifact.get("legal_approval_status") == "not_approved_for_production"
        )
    else:
        artifact_allowed = (
            artifact.get("artifact_classification") == "production_approved"
            and artifact.get("legal_approval_status") == "approved"
        )
    if not artifact_allowed:
        return None

    notices = artifact.get("notices")
    if not isinstance(notices, list):
        return None
    matches = [
        item
        for item in notices
        if isinstance(item, dict) and item.get("consent_type") == consent_type
    ]
    if len(matches) != 1:
        return None
    notice = matches[0]
    required_text_fields = (
        "policy_version",
        "summary",
        "purpose",
        "data_scope",
        "recipient",
        "withdrawal_effect",
    )
    if notice.get("enabled") is not True or any(
        not isinstance(notice.get(field), str) or not notice[field].strip()
        for field in required_text_fields
    ):
        return None

    summary = notice["summary"]
    canonical_summary = summary.replace("\r\n", "\n").replace("\r", "\n")
    summary_hash = hashlib.sha256(canonical_summary.encode("utf-8")).hexdigest()
    artifact_hash = notice.get("summary_sha256")
    if not isinstance(artifact_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", artifact_hash):
        return None
    if artifact_hash.lower() != summary_hash:
        return None

    suffix = _CONFIG_SUFFIXES[consent_type]
    configured_version = getattr(settings, f"{consent_type}_policy_version", None)
    configured_hash = getattr(settings, f"{consent_type}_summary_hash", None)
    backend_config = artifact.get("backend_config")
    if not isinstance(backend_config, dict):
        return None
    if (
        backend_config.get(f"{suffix}_POLICY_VERSION") != notice["policy_version"]
        or str(backend_config.get(f"{suffix}_SUMMARY_HASH", "")).lower() != summary_hash
        or configured_version != notice["policy_version"]
        or not isinstance(configured_hash, str)
        or configured_hash.lower() != summary_hash
    ):
        return None

    return CurrentConsentNotice(
        consent_type=consent_type,
        policy_version=notice["policy_version"],
        summary=summary,
        purpose=notice["purpose"],
        data_scope=notice["data_scope"],
        recipient=notice["recipient"],
        withdrawal_effect=notice["withdrawal_effect"],
        summary_sha256=summary_hash,
    )

"""Idempotent nonclinical risk-rule fixture for isolated phone-demo only."""

import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text

RULE_CODE = "PHONE_DEMO_SYNTHETIC_OTHER_SYMPTOM"
CONDITION = {
    "all": [
        {"field": "record_type", "op": "eq", "value": "symptom-records"},
        {"field": "symptom_codes", "op": "in", "value": ["other"]},
    ]
}


def main() -> None:
    if (
        os.environ.get("APP_ENV") != "local"
        or os.environ.get("RISK_TEST_ONLY_RULES_ENABLED") != "true"
    ):
        raise SystemExit("phone-demo fixture requires explicit local test-only opt-in")
    url = os.environ.get("MIGRATOR_DATABASE_URL")
    if not url:
        raise SystemExit("phone-demo migrator connection is required")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO safety.risk_rule (
                        rule_code, version, severity, condition_json, message,
                        recommended_action, review_status, environment, reviewed_by,
                        reviewed_at, source_refs, effective_from, expires_at
                    ) VALUES (
                        :code, 1, 'attention', CAST(:condition AS jsonb), :message,
                        :action, 'approved', 'test_only', 'phone-demo synthetic fixture',
                        :reviewed_at, CAST(:source_refs AS jsonb), :effective_from, :expires_at
                    ) ON CONFLICT (rule_code, version) DO NOTHING
                    """
                ),
                {
                    "code": RULE_CODE,
                    "condition": json.dumps(CONDITION, separators=(",", ":")),
                    "message": "演示测试提示：已触发非临床测试规则，不代表医疗判断。",
                    "action": "此提示仅用于验证演示流程；请以专业医疗意见为准。",
                    "reviewed_at": datetime.now(UTC),
                    "source_refs": json.dumps(["synthetic:phone-demo-nonclinical"]),
                    "effective_from": datetime.now(UTC),
                    "expires_at": datetime.now(UTC) + timedelta(days=3650),
                },
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

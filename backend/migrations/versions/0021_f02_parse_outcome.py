"""Persist controlled F02 parse outcomes without changing lifecycle states."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_f02_parse_outcome"
down_revision: str | None = "0020_operations_metrics_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OUTCOMES = "'extracted', 'no_supported_facts', 'insufficient_quality'"
_REASONS = (
    "'no_supported_fields', 'unsupported_content', 'low_quality_scan', "
    "'illegible_content', 'incomplete_document'"
)


def upgrade() -> None:
    for table in ("medical_document", "medical_parse_request"):
        op.add_column(
            table, sa.Column("parse_outcome", sa.String(32), nullable=True), schema="health"
        )
        op.add_column(
            table, sa.Column("parse_reason_code", sa.String(32), nullable=True), schema="health"
        )
        op.create_check_constraint(
            "ck_medical_document_parse_outcome"
            if table == "medical_document"
            else "ck_medical_parse_request_outcome",
            table,
            f"parse_outcome IS NULL OR parse_outcome IN ({_OUTCOMES})",
            schema="health",
        )
        outcome_reason_pair = (
            "(parse_outcome IS NULL AND parse_reason_code IS NULL) OR "
            "(parse_outcome = 'extracted' AND parse_reason_code IS NULL) OR "
            "(parse_outcome = 'no_supported_facts' AND parse_reason_code IN "
            "('no_supported_fields', 'unsupported_content')) OR "
            "(parse_outcome = 'insufficient_quality' AND parse_reason_code IN "
            "('low_quality_scan', 'illegible_content', 'incomplete_document'))"
        )
        if table == "medical_parse_request":
            outcome_reason_pair = (
                "(parse_outcome IS NULL AND parse_reason_code IS NULL) OR "
                "(parse_outcome = 'extracted' AND parse_reason_code IS NULL "
                "AND status IN ('needs_confirmation', 'succeeded', 'invalidated')) OR "
                "(parse_outcome = 'no_supported_facts' AND parse_reason_code IN "
                "('no_supported_fields', 'unsupported_content') "
                "AND status IN ('succeeded', 'invalidated')) OR "
                "(parse_outcome = 'insufficient_quality' AND parse_reason_code IN "
                "('low_quality_scan', 'illegible_content', 'incomplete_document') "
                "AND status IN ('succeeded', 'invalidated'))"
            )
        op.create_check_constraint(
            "ck_medical_document_parse_outcome_reason_pair"
            if table == "medical_document"
            else "ck_medical_parse_request_outcome_reason_pair",
            table,
            outcome_reason_pair,
            schema="health",
        )
        op.create_check_constraint(
            "ck_medical_document_parse_reason_code"
            if table == "medical_document"
            else "ck_medical_parse_request_reason_code",
            table,
            f"parse_reason_code IS NULL OR parse_reason_code IN ({_REASONS})",
            schema="health",
        )


def downgrade() -> None:
    for table in ("medical_parse_request", "medical_document"):
        op.drop_constraint(
            "ck_medical_document_parse_outcome_reason_pair"
            if table == "medical_document"
            else "ck_medical_parse_request_outcome_reason_pair",
            table,
            schema="health",
        )
        op.drop_constraint(
            "ck_medical_document_parse_reason_code"
            if table == "medical_document"
            else "ck_medical_parse_request_reason_code",
            table,
            schema="health",
        )
        op.drop_constraint(
            "ck_medical_document_parse_outcome"
            if table == "medical_document"
            else "ck_medical_parse_request_outcome",
            table,
            schema="health",
        )
        op.drop_column(table, "parse_reason_code", schema="health")
        op.drop_column(table, "parse_outcome", schema="health")

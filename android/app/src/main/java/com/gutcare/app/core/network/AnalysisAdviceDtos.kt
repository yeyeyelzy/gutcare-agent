package com.gutcare.app.core.network

import com.squareup.moshi.Json

data class AnalysisTaskRequestDto(
    @Json(name = "analysis_type") val analysisType: String,
    @Json(name = "requested_from") val requestedFrom: String? = null,
    @Json(name = "requested_to") val requestedTo: String? = null,
)
data class AnalysisTaskPageDto(val items: List<AnalysisTaskDto>, @Json(name = "next_cursor") val nextCursor: String?)
data class AnalysisTaskPreviewDto(
    @Json(name = "analysis_type") val analysisType: String,
    @Json(name = "requested_from") val requestedFrom: String?,
    @Json(name = "requested_to") val requestedTo: String?,
    val timezone: String,
    @Json(name = "mood_record_count_in_range") val moodRecordCountInRange: Int,
    @Json(name = "mood_record_count_eligible") val moodRecordCountEligible: Int,
    @Json(name = "mood_record_count_excluded_by_consent") val moodRecordCountExcludedByConsent: Int,
    @Json(name = "mood_exclusion_reasons") val moodExclusionReasons: List<String>,
)
data class AnalysisTaskDto(
    val id: String,
    @Json(name = "analysis_type") val analysisType: String,
    val status: String,
    @Json(name = "input_summary") val inputSummary: AnalysisInputSummaryDto,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String,
    val attempt: Int,
    @Json(name = "retry_of") val retryOf: String?,
    val result: AnalysisResultDto?,
    @Json(name = "error_code") val errorCode: String?,
)
data class AnalysisInputSummaryDto(@Json(name = "included_mood_record_count") val includedMoodRecordCount: Int)
data class AnalysisResultDto(
    @Json(name = "schema_version") val schemaVersion: String,
    val summary: String,
    val observations: List<String>,
    val evidence: List<AnalysisSourceEvidenceDto>,
    val uncertainties: List<String>,
    @Json(name = "missing_data") val missingData: List<String>,
)
data class AnalysisSourceEvidenceDto(
    @Json(name = "source_type") val sourceType: String,
    @Json(name = "source_id") val sourceId: String,
    @Json(name = "source_version") val sourceVersion: Int,
    val locator: String?,
    @Json(name = "source_deleted") val sourceDeleted: Boolean,
)
data class AdvicePageDto(val items: List<AdviceDto>, @Json(name = "next_cursor") val nextCursor: String?)
data class AdviceDto(
    val id: String,
    @Json(name = "task_id") val taskId: String,
    val category: String,
    val priority: String,
    val title: String,
    val body: String,
    val uncertainty: AdviceUncertaintyDto,
    val applicability: AdviceApplicabilityDto,
    @Json(name = "safety_boundary") val safetyBoundary: AdviceSafetyBoundaryDto,
    val version: String,
    val status: String,
    @Json(name = "basis_updated") val basisUpdated: Boolean,
    @Json(name = "basis_updated_at") val basisUpdatedAt: String?,
    @Json(name = "basis_update_reason") val basisUpdateReason: String?,
    @Json(name = "risk_priority_context") val riskPriorityContext: AdviceRiskContextDto?,
    val evidence: List<AdviceEvidenceDto>,
    val feedback: AdviceFeedbackDto?,
    @Json(name = "feedback_history") val feedbackHistory: List<AdviceFeedbackHistoryDto>,
    @Json(name = "created_at") val createdAt: String,
)
data class AdviceUncertaintyDto(val level: String, val reasons: List<String>)
data class AdviceApplicabilityDto(val scope: String, val limitations: List<String>)
data class AdviceSafetyBoundaryDto(@Json(name = "not_diagnosis") val notDiagnosis: Boolean, @Json(name = "not_prescription") val notPrescription: Boolean, @Json(name = "risk_alert_priority") val riskAlertPriority: Boolean)
data class AdviceRiskContextDto(@Json(name = "alert_id") val alertId: String, val severity: String, val status: String, @Json(name = "triggered_at") val triggeredAt: String)
/** Unified optional representation for the two OpenAPI evidence variants; no URL is opened automatically. */
data class AdviceEvidenceDto(
    @Json(name = "evidence_type") val evidenceType: String,
    @Json(name = "source_type") val sourceType: String? = null,
    @Json(name = "source_id") val sourceId: String? = null,
    @Json(name = "source_version") val sourceVersion: Int? = null,
    val locator: String? = null,
    @Json(name = "source_deleted") val sourceDeleted: Boolean? = null,
    val target: AdviceEvidenceTargetDto? = null,
    @Json(name = "knowledge_ref") val knowledgeRef: String? = null,
    @Json(name = "knowledge_version") val knowledgeVersion: String? = null,
    val title: String? = null,
    val publisher: String? = null,
    @Json(name = "citation_url") val citationUrl: String? = null,
)
data class AdviceEvidenceTargetDto(val type: String, val id: String)
data class AdviceFeedbackDto(@Json(name = "advice_id") val adviceId: String, @Json(name = "feedback_type") val feedbackType: String, val version: Int)
data class AdviceFeedbackHistoryDto(@Json(name = "feedback_type") val feedbackType: String, val version: Int, @Json(name = "created_at") val createdAt: String)
data class AdviceFeedbackRequestDto(@Json(name = "feedback_type") val feedbackType: String, @Json(name = "expected_version") val expectedVersion: Int)

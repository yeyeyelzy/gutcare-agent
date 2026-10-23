package com.gutcare.app.core.network

import com.squareup.moshi.Json

data class RiskAlertDto(
    val id: String,
    val environment: String,
    val severity: String,
    val message: String,
    @Json(name = "recommended_action") val recommendedAction: String,
    val status: String,
    @Json(name = "triggered_at") val triggeredAt: String,
    @Json(name = "read_at") val readAt: String? = null,
    @Json(name = "reevaluated_at") val reevaluatedAt: String? = null,
    val evidence: Map<String, Any?> = emptyMap(),
)
data class RiskAlertPageDto(val items: List<RiskAlertDto>, @Json(name = "next_cursor") val nextCursor: String?)

data class TrendSeriesDto(@Json(name = "has_data") val hasData: Boolean, val items: List<TrendSeriesItemDto>)
data class TrendSeriesItemDto(
    val bucket: String,
    val count: Int? = null,
    val category: String? = null,
    val status: String? = null,
    @Json(name = "duration_minutes") val durationMinutes: Int? = null,
    @Json(name = "bristol_confirmed_count") val bristolConfirmedCount: Int? = null,
    @Json(name = "bristol_unknown_count") val bristolUnknownCount: Int? = null,
    @Json(name = "mean_severity") val meanSeverity: Double? = null,
)
data class MoodTrendDto(
    val availability: String,
    val buckets: List<MoodTrendBucketDto> = emptyList(),
    @Json(name = "reason_code") val reasonCode: String? = null,
    @Json(name = "missing_consents") val missingConsents: List<String> = emptyList(),
)
data class MoodTrendBucketDto(
    @Json(name = "period_start") val periodStart: String,
    @Json(name = "period_end") val periodEnd: String,
    @Json(name = "has_data") val hasData: Boolean,
    @Json(name = "record_count") val recordCount: Int,
    @Json(name = "mood_level_counts") val moodLevelCounts: Map<String, Int>,
)
data class TrendResponseDto(
    val timezone: String,
    @Json(name = "from") val from: String,
    @Json(name = "to") val to: String,
    val bucket: String,
    val activity: TrendSeriesDto,
    val stool: TrendSeriesDto,
    val symptom: TrendSeriesDto,
    @Json(name = "diet_confirmed_categories") val dietConfirmedCategories: TrendSeriesDto,
    @Json(name = "medication_checkins") val medicationCheckins: TrendSeriesDto,
    val mood: MoodTrendDto,
)

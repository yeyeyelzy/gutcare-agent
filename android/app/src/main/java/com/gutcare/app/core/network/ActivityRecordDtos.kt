package com.gutcare.app.core.network

import com.squareup.moshi.Json

/** Strict F07 wire DTOs mirror ActivityWrite/ActivityPatch in the frozen OpenAPI contract. */
data class ActivityWriteDto(
    @Json(name = "activity_type") val activityType: String,
    val description: String?,
    val intensity: String,
    @Json(name = "subjective_feeling") val subjectiveFeeling: String,
    @Json(name = "duration_minutes") val durationMinutes: Int,
    @Json(name = "occurred_at") val occurredAt: String,
)

data class ActivityPatchDto(
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "activity_type") val activityType: String? = null,
    val description: String? = null,
    val intensity: String? = null,
    @Json(name = "subjective_feeling") val subjectiveFeeling: String? = null,
    @Json(name = "duration_minutes") val durationMinutes: Int? = null,
    @Json(name = "occurred_at") val occurredAt: String? = null,
)

data class ActivityRecordDto(
    val id: String,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "activity_type") val activityType: String,
    val description: String?,
    val intensity: String,
    @Json(name = "subjective_feeling") val subjectiveFeeling: String,
    @Json(name = "duration_minutes") val durationMinutes: Int,
    @Json(name = "occurred_at") val occurredAt: String,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String,
)

data class ActivityPageDto(val items: List<ActivityRecordDto>, @Json(name = "next_cursor") val nextCursor: String?)

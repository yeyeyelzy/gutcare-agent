package com.gutcare.app.core.network

import com.squareup.moshi.Json

/** F06 wire DTOs mirror the frozen OpenAPI contract. Patient identity is always derived by the server. */
data class MedicationPlanCreateDto(
    @Json(name = "medication_name") val medicationName: String,
    @Json(name = "dosage_text") val dosageText: String? = null,
    @Json(name = "route_code") val routeCode: String? = null,
    @Json(name = "start_date") val startDate: String? = null,
    @Json(name = "end_date") val endDate: String? = null,
    @Json(name = "source_type") val sourceType: String,
    @Json(name = "source_document_id") val sourceDocumentId: String? = null,
)

data class MedicationPlanDto(
    val id: String,
    @Json(name = "patient_id") val patientId: String,
    @Json(name = "medication_name") val medicationName: String,
    @Json(name = "dosage_text") val dosageText: String? = null,
    @Json(name = "route_code") val routeCode: String? = null,
    @Json(name = "start_date") val startDate: String? = null,
    @Json(name = "end_date") val endDate: String? = null,
    @Json(name = "source_type") val sourceType: String,
    @Json(name = "source_document_id") val sourceDocumentId: String? = null,
    @Json(name = "source_deleted") val sourceDeleted: Boolean,
    @Json(name = "confirmation_status") val confirmationStatus: String,
    @Json(name = "plan_status") val planStatus: String,
    @Json(name = "record_version") val recordVersion: Int,
)

/** Null wrappers distinguish an omitted PATCH property from an explicit JSON null. */
data class MedicationNullablePatch(val value: String?)
data class MedicationPlanPatchDto(
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "medication_name") val medicationName: String? = null,
    @Json(name = "dosage_text") val dosageText: MedicationNullablePatch? = null,
    @Json(name = "route_code") val routeCode: MedicationNullablePatch? = null,
    @Json(name = "start_date") val startDate: MedicationNullablePatch? = null,
    @Json(name = "end_date") val endDate: MedicationNullablePatch? = null,
    @Json(name = "confirmation_status") val confirmationStatus: String? = null,
)

data class MedicationPlanTransitionDto(
    @Json(name = "record_version") val recordVersion: Int,
    val action: String,
)

data class MedicationScheduleWriteDto(
    @Json(name = "local_time") val localTime: String,
    val timezone: String,
    val rrule: String? = null,
    @Json(name = "valid_from") val validFrom: String,
    @Json(name = "valid_to") val validTo: String? = null,
    val enabled: Boolean = true,
    @Json(name = "record_version") val recordVersion: Int? = null,
)

data class MedicationScheduleDto(
    val id: String,
    @Json(name = "plan_id") val planId: String,
    @Json(name = "local_time") val localTime: String,
    val timezone: String,
    val rrule: String? = null,
    @Json(name = "valid_from") val validFrom: String,
    @Json(name = "valid_to") val validTo: String? = null,
    val enabled: Boolean,
    @Json(name = "record_version") val recordVersion: Int,
)

data class MedicationCheckinUpdateDto(
    @Json(name = "record_version") val recordVersion: Int,
    val status: String,
    @Json(name = "taken_at") val takenAt: String? = null,
    val note: String? = null,
)

data class MedicationCheckinDto(
    val id: String,
    @Json(name = "schedule_id") val scheduleId: String,
    @Json(name = "local_date") val localDate: String,
    @Json(name = "scheduled_for") val scheduledFor: String,
    val status: String,
    @Json(name = "taken_at") val takenAt: String? = null,
    val note: String? = null,
    @Json(name = "record_version") val recordVersion: Int,
)

package com.gutcare.app.core.network

import com.squareup.moshi.Json

/** F02 DTOs deliberately expose metadata and patient-review candidates only, never file capabilities. */
data class MedicalDocumentDto(
    val id: String,
    @Json(name = "file_object_id") val fileObjectId: String,
    @Json(name = "document_type") val documentType: String,
    @Json(name = "hospital_name") val hospitalName: String? = null,
    @Json(name = "document_date") val documentDate: String? = null,
    val notes: String? = null,
    @Json(name = "processing_mode") val processingMode: String,
    @Json(name = "parse_status") val parseStatus: String,
    @Json(name = "parse_outcome") val parseOutcome: String? = null,
    @Json(name = "parse_reason_code") val parseReasonCode: String? = null,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String,
    @Json(name = "file_status") val fileStatus: String,
    @Json(name = "original_name") val originalName: String,
)

data class MedicalDocumentPageDto(val items: List<MedicalDocumentDto>, @Json(name = "next_cursor") val nextCursor: String?)

data class MedicalFieldCandidateDto(
    val id: String,
    @Json(name = "field_code") val fieldCode: String,
    @Json(name = "value_type") val valueType: String,
    val value: Any?,
    val unit: String? = null,
    val confidence: Double? = null,
    val uncertainty: String? = null,
    @Json(name = "source_locator") val sourceLocator: Any? = null,
    val excerpt: String? = null,
    @Json(name = "review_status") val reviewStatus: String,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "chosen_value") val chosenValue: Any? = null,
)

data class MedicalCandidateDecisionDto(
    val decision: String,
    @Json(name = "record_version") val recordVersion: Int,
    val value: Any? = null,
)

data class UploadCreateDto(
    val purpose: String = "medical_document",
    @Json(name = "file_name") val fileName: String,
    @Json(name = "content_type") val contentType: String,
    @Json(name = "size_bytes") val sizeBytes: Long,
)

data class UploadSessionDto(
    @Json(name = "upload_id") val uploadId: String,
    @Json(name = "upload_url") val uploadUrl: String,
    @Json(name = "expires_at") val expiresAt: String,
)

data class FileObjectDto(
    val id: String,
    @Json(name = "storage_status") val storageStatus: String,
    @Json(name = "content_type") val contentType: String,
    @Json(name = "size_bytes") val sizeBytes: Long,
)

data class MedicalDocumentCreateDto(
    @Json(name = "file_object_id") val fileObjectId: String,
    @Json(name = "document_type") val documentType: String,
    @Json(name = "hospital_name") val hospitalName: String? = null,
    @Json(name = "document_date") val documentDate: String? = null,
    val notes: String? = null,
    @Json(name = "processing_mode") val processingMode: String,
)

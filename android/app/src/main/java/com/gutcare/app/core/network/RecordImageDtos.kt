package com.gutcare.app.core.network

import com.squareup.moshi.Json

data class RecordImageAttachmentDto(
    val id: String,
    @Json(name = "record_id") val recordId: String,
    val position: Int,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "image_set_version") val imageSetVersion: Int,
    @Json(name = "file_status") val fileStatus: String,
    @Json(name = "created_at") val createdAt: String,
)

data class RecordImageAttachDto(
    @Json(name = "file_object_id") val fileObjectId: String,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "image_set_version") val imageSetVersion: Int,
)

data class FileDownloadGrantDto(
    @Json(name = "download_url") val downloadUrl: String,
    @Json(name = "expires_at") val expiresAt: String,
)

data class RecordImageDisclosureDto(
    val purpose: String,
    val enabled: Boolean,
    @Json(name = "policy_version") val policyVersion: String?,
    val summary: String?,
    @Json(name = "purpose_text") val purposeText: String?,
    @Json(name = "data_scope") val dataScope: String?,
    val recipient: String?,
    val retention: String?,
    @Json(name = "withdrawal_effect") val withdrawalEffect: String?,
)

data class RecordImageDisclosureTokenDto(
    @Json(name = "disclosure_token") val disclosureToken: String,
    @Json(name = "expires_at") val expiresAt: String,
)

data class RecordImageRecognitionCandidateDto(
    val id: String,
    @Json(name = "candidate_version") val candidateVersion: Int,
    @Json(name = "attachment_id") val attachmentId: String,
    @Json(name = "candidate_group_key") val candidateGroupKey: String? = null,
    @Json(name = "candidate_type") val candidateType: String,
    val value: Any?,
    @Json(name = "confidence_band") val confidenceBand: String,
    @Json(name = "uncertainty_code") val uncertaintyCode: String,
    @Json(name = "image_region") val imageRegion: List<Double>? = null,
    val status: String,
)

data class RecordImageRecognitionRequestDto(
    val id: String,
    @Json(name = "recognition_type") val recognitionType: String,
    val status: String,
    @Json(name = "reason_code") val reasonCode: String? = null,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "image_set_version") val imageSetVersion: Int,
    @Json(name = "decision_record_version") val decisionRecordVersion: Int,
    val attempt: Int,
    @Json(name = "retry_of_request_id") val retryOfRequestId: String? = null,
    val candidates: List<RecordImageRecognitionCandidateDto> = emptyList(),
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "updated_at") val updatedAt: String,
)

data class RecordImageRecognitionCreateDto(
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "image_set_version") val imageSetVersion: Int,
    @Json(name = "disclosure_token") val disclosureToken: String,
)

data class RecordImageDisclosureAcknowledgeDto(
    @Json(name = "record_id") val recordId: String,
    val purpose: String,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "image_set_version") val imageSetVersion: Int,
    @Json(name = "policy_version") val policyVersion: String,
    val acknowledged: Boolean = true,
)

data class RecordImageCandidateDecisionDto(
    val action: String,
    @Json(name = "candidate_version") val candidateVersion: Int,
    @Json(name = "record_version") val recordVersion: Int,
    @Json(name = "image_set_version") val imageSetVersion: Int,
    @Json(name = "corrected_value") val correctedValue: Any? = null,
)

/** The API response intentionally omits file_object_id; it is not sufficient to request an image preview. */
object RecordImageRules {
    const val MAX_DIET_IMAGES = 10
    const val MAX_STOOL_IMAGES = 1
    const val MAX_IMAGE_BYTES = 10L * 1024 * 1024

    fun nextPosition(type: PatientRecordType, attachments: List<RecordImageAttachmentDto>): Int? {
        val maximum = if (type == PatientRecordType.DIET) MAX_DIET_IMAGES else if (type == PatientRecordType.STOOL) MAX_STOOL_IMAGES else return null
        if (attachments.size >= maximum) return null
        if (type == PatientRecordType.STOOL) return 0
        // The frozen request schema leaves position server-owned; the backend appends at the
        // active attachment count while holding the record transaction lock.
        return attachments.size
    }
}

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

package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RecordImageDtosTest {
    @Test fun dietPositionIsActiveCountAndBackendOwnsAppendSlot() {
        val images = (0..8).map { attachment(it, it + 1, it + 1) }
        assertEquals(9, RecordImageRules.nextPosition(PatientRecordType.DIET, images))
        assertNull(RecordImageRules.nextPosition(PatientRecordType.DIET, images + attachment(9, 10, 10)))
        assertEquals(2, RecordImageRules.nextPosition(PatientRecordType.DIET, listOf(attachment(0, 1, 1), attachment(2, 1, 1))))
    }

    @Test fun stoolAllowsOneAttachmentAndNoUnsupportedRecordType() {
        assertEquals(0, RecordImageRules.nextPosition(PatientRecordType.STOOL, emptyList()))
        assertNull(RecordImageRules.nextPosition(PatientRecordType.STOOL, listOf(attachment(0, 2, 1))))
        assertNull(RecordImageRules.nextPosition(PatientRecordType.SYMPTOM, emptyList()))
    }

    @Test fun attachmentDtoDoesNotInventFileObjectIdOrDownloadCapability() {
        val dto = Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(RecordImageAttachmentDto::class.java)
            .fromJson("""{"id":"image-id","record_id":"record-id","position":0,"record_version":3,"image_set_version":1,"file_status":"available","created_at":"2026-10-20T10:00:00Z"}""")!!
        assertEquals("image-id", dto.id)
        assertEquals("available", dto.fileStatus)
        assertTrue(!Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(RecordImageAttachmentDto::class.java).toJson(dto).contains("file_object_id"))
    }

    private fun attachment(position: Int, recordVersion: Int, imageSetVersion: Int) = RecordImageAttachmentDto(
        "id-$position", "record-id", position, recordVersion, imageSetVersion, "available", "2026-10-20T10:00:00Z",
    )
}

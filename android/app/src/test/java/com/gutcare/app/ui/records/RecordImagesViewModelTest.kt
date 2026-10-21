package com.gutcare.app.ui.records

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.PatientRecordType
import com.gutcare.app.core.network.RecordImageAttachmentDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RecordImagesViewModelTest {
    @get:Rule val instantTaskExecutorRule = InstantTaskExecutorRule()

    @Test fun uploadCarriesCurrentVersionsAndUpdatesAttachmentState() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeRecordImagesGateway()
            val model = RecordImagesViewModel(gateway)
            model.load(PatientRecordType.DIET, "record-1", 3, 0)
            advanceUntilIdle()
            model.upload("food.jpg", "image/jpeg", byteArrayOf(1, 2, 3))
            advanceUntilIdle()
            assertEquals(3, gateway.recordVersion)
            assertEquals(0, gateway.imageSetVersion)
            assertEquals("diet_image", gateway.purpose)
            assertEquals(4, model.uiState.value.recordVersion)
            assertEquals(1, model.uiState.value.imageSetVersion)
            assertEquals(1, model.uiState.value.images.size)
            assertTrue(model.uiState.value.message.orEmpty().contains("安全校验"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun unsupportedContentAndTooManyAttachmentsNeverReachGateway() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeRecordImagesGateway()
            val model = RecordImagesViewModel(gateway)
            model.load(PatientRecordType.STOOL, "record-2", 1, 0)
            advanceUntilIdle()
            model.upload("bad.svg", "image/svg+xml", byteArrayOf(1))
            advanceUntilIdle()
            assertEquals(0, gateway.uploadCount)
            assertTrue(model.uiState.value.isError)
            gateway.images = listOf(RecordImageAttachmentDto("image-1", "record-2", 0, 2, 1, "available", "t"))
            model.load(PatientRecordType.STOOL, "record-2", 2, 1)
            advanceUntilIdle()
            model.upload("stool.jpg", "image/jpeg", byteArrayOf(1))
            advanceUntilIdle()
            assertEquals(0, gateway.uploadCount)
            assertFalse(model.uiState.value.canAdd)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun previewRequestsByAttachmentIdAndKeepsImageBytesOnlyInUiMemory() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeRecordImagesGateway()
            gateway.images = listOf(RecordImageAttachmentDto("image-1", "record-1", 0, 3, 1, "available", "t"))
            val model = RecordImagesViewModel(gateway)
            model.load(PatientRecordType.DIET, "record-1", 3, 1)
            advanceUntilIdle()
            model.preview(model.uiState.value.images.single())
            advanceUntilIdle()
            assertEquals("image-1", gateway.previewAttachmentId)
            assertEquals("image-1", model.uiState.value.previewImageId)
            assertTrue(model.uiState.value.previewBytes!!.contentEquals(byteArrayOf(4, 5, 6)))
            model.clearPreview()
            assertEquals(null, model.uiState.value.previewBytes)
        } finally { Dispatchers.resetMain() }
    }

    private class FakeRecordImagesGateway : RecordImagesGateway {
        var images = emptyList<RecordImageAttachmentDto>()
        var recordVersion = 0
        var imageSetVersion = 0
        var purpose: String? = null
        var uploadCount = 0
        var previewAttachmentId: String? = null
        override suspend fun list(type: PatientRecordType, recordId: String) = ApiResult.Success(images)
        override suspend fun uploadAndAttach(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int,
            idempotencyKey: String, fileName: String, contentType: String, bytes: ByteArray): ApiResult<RecordImageAttachmentDto> {
            uploadCount++
            this.recordVersion = recordVersion
            this.imageSetVersion = imageSetVersion
            purpose = if (type == PatientRecordType.DIET) "diet_image" else "stool_image"
            return ApiResult.Success(RecordImageAttachmentDto("image-new", recordId, 0, recordVersion + 1, imageSetVersion + 1, "available", "t"))
        }
        override suspend fun delete(imageId: String, recordVersion: Int, imageSetVersion: Int) = ApiResult.Success(Unit)
        override suspend fun preview(attachmentId: String): ApiResult<ByteArray> {
            previewAttachmentId = attachmentId
            return ApiResult.Success(byteArrayOf(4, 5, 6))
        }
    }
}

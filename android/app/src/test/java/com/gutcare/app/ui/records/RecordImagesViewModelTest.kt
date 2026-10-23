package com.gutcare.app.ui.records

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.PatientRecordType
import com.gutcare.app.core.network.RecordImageAttachmentDto
import com.gutcare.app.core.network.RecordImageCandidateDecisionDto
import com.gutcare.app.core.network.RecordImageDisclosureAcknowledgeDto
import com.gutcare.app.core.network.RecordImageDisclosureDto
import com.gutcare.app.core.network.RecordImageRecognitionCandidateDto
import com.gutcare.app.core.network.RecordImageRecognitionCreateDto
import com.gutcare.app.core.network.RecordImageRecognitionRequestDto
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

    @Test fun missingRequiredConsentExposesSettingsActionState() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeRecordImagesGateway().apply {
                uploadFailure = ApiResult.Failure(409, "CONSENT_REQUIRED")
            }
            val model = RecordImagesViewModel(gateway)
            model.load(PatientRecordType.STOOL, "record-consent", 1, 0)
            advanceUntilIdle()
            model.upload("stool.jpg", "image/jpeg", byteArrayOf(1, 2, 3))
            advanceUntilIdle()
            assertTrue(model.uiState.value.needsConsentSettings)
            assertTrue(model.uiState.value.message.orEmpty().contains("健康数据处理和敏感图片处理"))
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

    @Test fun recognitionRequiresDisplayedPurposeNoticeAndKeepsDietCandidatesUnconfirmedUntilDecision() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeRecordImagesGateway().apply {
                images = listOf(RecordImageAttachmentDto("image-1", "record-1", 0, 3, 1, "available", "t"))
                notice = RecordImageDisclosureDto("diet_image_recognition", true, "test-v1", "summary", "purpose", "scope", "recipient", "retention", "withdraw")
                recognitionResponse = request("candidates_ready", 3, listOf(candidate("food_name", "Rice")))
            }
            val model = RecordImagesViewModel(gateway)
            model.load(PatientRecordType.DIET, "record-1", 3, 1); advanceUntilIdle()
            model.requestRecognition(); advanceUntilIdle()
            assertEquals("diet_image_recognition", gateway.requestedPurpose)
            assertEquals(null, model.uiState.value.recognition)
            assertTrue(model.uiState.value.recognitionDisclosure?.enabled == true)
            model.acknowledgeAndStartRecognition(); advanceUntilIdle()
            assertEquals("test-v1", gateway.acknowledgment?.policyVersion)
            assertEquals(3, gateway.createdBody?.recordVersion)
            assertEquals(1, gateway.createdBody?.imageSetVersion)
            assertTrue(gateway.createdBody?.disclosureToken == "one-time-token")
            assertEquals("candidates_ready", model.uiState.value.recognition?.status)
            assertEquals("Rice", model.uiState.value.recognition?.candidates?.single()?.value)
            assertEquals(0, gateway.decisions.size)
            model.decideCandidate(model.uiState.value.recognition!!.candidates.single(), "accept")
            advanceUntilIdle()
            assertEquals("accept", gateway.decisions.single().action)
            assertEquals(3, gateway.decisions.single().recordVersion)
            assertEquals("accepted", model.uiState.value.recognition?.candidates?.single()?.status)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun stoolRecognitionExposesDirectBristolResultAndNeverCallsDecision() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeRecordImagesGateway().apply {
                images = listOf(RecordImageAttachmentDto("image-2", "record-2", 0, 2, 1, "available", "t"))
                notice = RecordImageDisclosureDto("stool_image_recognition", true, "stool-v1", null, null, null, null, null, null)
                recognitionResponse = request("candidates_ready", 2, listOf(candidate("bristol_type", 4, requiresConfirmation = false)), "stool_image_recognition")
            }
            val model = RecordImagesViewModel(gateway)
            model.load(PatientRecordType.STOOL, "record-2", 2, 1); advanceUntilIdle()
            model.requestRecognition(); advanceUntilIdle(); model.acknowledgeAndStartRecognition(); advanceUntilIdle()
            val candidate = model.uiState.value.recognition!!.candidates.single()
            model.decideCandidate(candidate, "accept"); advanceUntilIdle()
            assertTrue(gateway.decisions.isEmpty())
            assertTrue(model.uiState.value.message.orEmpty().contains("不是已确认的患者事实"))
            assertEquals(0, gateway.decisions.size)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun retryRequiresFreshDisclosureAndUsesCurrentRecordImageVersions() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeRecordImagesGateway().apply {
                images = listOf(RecordImageAttachmentDto("image-1", "record-1", 0, 5, 2, "available", "t"))
                notice = RecordImageDisclosureDto("diet_image_recognition", true, "diet-v2", null, null, null, null, null, null)
                recognitionResponse = request("failed", 5, emptyList())
            }
            val model = RecordImagesViewModel(gateway)
            model.load(PatientRecordType.DIET, "record-1", 5, 2); advanceUntilIdle()
            model.requestRecognition("previous-request"); advanceUntilIdle()
            assertEquals("previous-request", model.uiState.value.retryRequestId)
            assertEquals(0, gateway.retryCount)
            model.acknowledgeAndStartRecognition(); advanceUntilIdle()
            assertEquals(1, gateway.retryCount)
            assertEquals("previous-request", gateway.retryParentId)
            assertEquals(5, gateway.createdBody?.recordVersion)
            assertEquals(2, gateway.createdBody?.imageSetVersion)
        } finally { Dispatchers.resetMain() }
    }

    private fun candidate(type: String, value: Any?, requiresConfirmation: Boolean = true) = RecordImageRecognitionCandidateDto(
        id = "candidate-1", candidateVersion = 1, attachmentId = "image-1", candidateGroupKey = if (type == "bristol_type") null else "group-1",
        candidateType = type, value = value, requiresPatientConfirmation = requiresConfirmation,
        confidenceBand = "medium", uncertaintyCode = "other", status = "pending",
    )

    private fun request(status: String, version: Int, candidates: List<RecordImageRecognitionCandidateDto>, recognitionType: String = "diet_image_recognition") = RecordImageRecognitionRequestDto(
        id = "request-1", recognitionType = recognitionType, status = status, recordVersion = version,
        imageSetVersion = 1, decisionRecordVersion = version, attempt = 1, candidates = candidates, createdAt = "now", updatedAt = "now",
    )

    private class FakeRecordImagesGateway : RecordImagesGateway {
        var uploadFailure: ApiResult.Failure? = null
        var images = emptyList<RecordImageAttachmentDto>()
        var recordVersion = 0
        var imageSetVersion = 0
        var purpose: String? = null
        var uploadCount = 0
        var previewAttachmentId: String? = null
        var notice: RecordImageDisclosureDto? = null
        var requestedPurpose: String? = null
        var acknowledgment: RecordImageDisclosureAcknowledgeDto? = null
        var createdBody: RecordImageRecognitionCreateDto? = null
        var recognitionResponse: RecordImageRecognitionRequestDto? = null
        val decisions = mutableListOf<RecordImageCandidateDecisionDto>()
        var retryCount = 0
        var retryParentId: String? = null
        override suspend fun list(type: PatientRecordType, recordId: String) = ApiResult.Success(images)
        override suspend fun latestStoolRecognition(recordId: String): ApiResult<RecordImageRecognitionRequestDto> =
            ApiResult.Failure(404, "RESOURCE_NOT_FOUND")
        override suspend fun uploadAndAttach(type: PatientRecordType, recordId: String, recordVersion: Int, imageSetVersion: Int,
            idempotencyKey: String, fileName: String, contentType: String, bytes: ByteArray): ApiResult<RecordImageAttachmentDto> {
            uploadCount++
            uploadFailure?.let { return it }
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
        override suspend fun disclosure(purpose: String): ApiResult<RecordImageDisclosureDto> {
            requestedPurpose = purpose
            return ApiResult.Success(notice ?: error("notice missing"))
        }
        override suspend fun acknowledgeDisclosure(body: RecordImageDisclosureAcknowledgeDto): ApiResult<String> {
            acknowledgment = body
            return ApiResult.Success("one-time-token")
        }
        override suspend fun createRecognition(type: PatientRecordType, recordId: String, key: String, body: RecordImageRecognitionCreateDto): ApiResult<RecordImageRecognitionRequestDto> {
            createdBody = body
            return ApiResult.Success(recognitionResponse ?: error("request missing"))
        }
        override suspend fun recognitionRequest(requestId: String): ApiResult<RecordImageRecognitionRequestDto> = ApiResult.Success(recognitionResponse ?: error("request missing"))
        override suspend fun retryRecognition(requestId: String, key: String, body: RecordImageRecognitionCreateDto): ApiResult<RecordImageRecognitionRequestDto> {
            retryCount++
            retryParentId = requestId
            createdBody = body
            return ApiResult.Success(recognitionResponse ?: error("request missing"))
        }
        override suspend fun decideCandidate(candidateId: String, key: String, body: RecordImageCandidateDecisionDto): ApiResult<Unit> {
            decisions += body
            val current = recognitionResponse ?: error("request missing")
            recognitionResponse = current.copy(decisionRecordVersion = current.decisionRecordVersion + 1,
                candidates = current.candidates.map { if (it.id == candidateId) it.copy(status = if (body.action == "accept") "accepted" else if (body.action == "edit") "edited" else "rejected", value = null) else it })
            return ApiResult.Success(Unit)
        }
    }
}

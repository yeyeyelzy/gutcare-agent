package com.gutcare.app.ui.records

import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.FileObjectDto
import com.gutcare.app.core.network.MedicalCandidateDecisionDto
import com.gutcare.app.core.network.MedicalDocumentCreateDto
import com.gutcare.app.core.network.MedicalDocumentDto
import com.gutcare.app.core.network.MedicalDocumentPageDto
import com.gutcare.app.core.network.MedicalFieldCandidateDto
import com.gutcare.app.core.network.UploadCreateDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.RequestBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MedicalDocumentsViewModelTest {
    @Test fun listShowsEmptyAndNetworkErrorWithoutStaticReports() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway()
            val model = MedicalDocumentsViewModel(gateway)
            model.load(); advanceUntilIdle()
            assertTrue(model.uiState.value.documents.isEmpty())
            gateway.listResult = ApiResult.Failure(null, "NETWORK_ERROR")
            model.load(); advanceUntilIdle()
            assertTrue(model.uiState.value.error?.contains("网络") == true)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun candidateConflictRefreshesButNeverReplaysDecision() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val candidate = MedicalFieldCandidateDto("candidate", "test_item", "string", "CRP", recordVersion = 2, reviewStatus = "pending")
            val gateway = FakeGateway().apply {
                detailResult = ApiResult.Success(document())
                candidateResult = ApiResult.Success(listOf(candidate))
                decisionResult = ApiResult.Failure(409, "RECORD_VERSION_CONFLICT")
            }
            val model = MedicalDocumentsViewModel(gateway)
            model.open("document"); advanceUntilIdle()
            model.decide(candidate, "accept"); advanceUntilIdle()
            assertEquals(1, gateway.decisions)
            assertTrue(model.uiState.value.conflict)
            assertTrue(model.uiState.value.operationMessage?.contains("刷新") == true)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun correctionSubmitsOnlyAnExplicitPatientValue() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val candidate = MedicalFieldCandidateDto("candidate", "test_item", "string", "CRP", recordVersion = 2, reviewStatus = "pending")
            val gateway = FakeGateway()
            val model = MedicalDocumentsViewModel(gateway)
            model.decide(candidate, "correct", "hs-CRP"); advanceUntilIdle()
            assertEquals("correct", gateway.lastDecision?.decision)
            assertEquals("hs-CRP", gateway.lastDecision?.value)
            model.decide(candidate, "correct", ""); advanceUntilIdle()
            assertEquals(1, gateway.decisions)
            assertTrue(model.uiState.value.operationMessage?.contains("填写") == true)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun uploadCreatesDocumentOnlyAfterGatewayAndCompletionSucceed() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply { uploadResult = ApiResult.Success(FileObjectDto("file", "available", "application/pdf", 12)) }
            val model = MedicalDocumentsViewModel(gateway)
            model.upload("report.pdf", "application/pdf", 12, RequestBody.create(null, byteArrayOf(1)), analyze = false)
            advanceUntilIdle()
            assertEquals("store_only", gateway.created?.processingMode)
            assertEquals("报告已安全上传。", model.uiState.value.operationMessage)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun analyzeFailsClosedBeforeAnySensitiveUploadUntilConsentLookupExists() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply { uploadResult = ApiResult.Success(FileObjectDto("file", "available", "application/pdf", 12)) }
            val model = MedicalDocumentsViewModel(gateway)
            model.upload("report.pdf", "application/pdf", 12, RequestBody.create(null, byteArrayOf(1)), analyze = true)
            advanceUntilIdle()
            assertEquals(null, gateway.created)
            assertEquals(0, gateway.uploadCalls)
            assertTrue(model.uiState.value.operationMessage?.contains("授权核验") == true)
        } finally { Dispatchers.resetMain() }
    }

    private class FakeGateway : MedicalDocumentsGateway {
        var listResult: ApiResult<MedicalDocumentPageDto> = ApiResult.Success(MedicalDocumentPageDto(emptyList(), null))
        var detailResult: ApiResult<MedicalDocumentDto> = ApiResult.Failure(404, "NOT_FOUND")
        var candidateResult: ApiResult<List<MedicalFieldCandidateDto>> = ApiResult.Success(emptyList())
        var decisionResult: ApiResult<Unit> = ApiResult.Success(Unit)
        var uploadResult: ApiResult<FileObjectDto> = ApiResult.Failure(null, "NETWORK_ERROR")
        var decisions = 0
        var uploadCalls = 0
        var lastDecision: MedicalCandidateDecisionDto? = null
        var created: MedicalDocumentCreateDto? = null
        override suspend fun list(cursor: String?) = listResult
        override suspend fun detail(id: String) = detailResult
        override suspend fun candidates(documentId: String) = candidateResult
        override suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto): ApiResult<Unit> { decisions++; lastDecision = body; return decisionResult }
        override suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody): ApiResult<FileObjectDto> { uploadCalls++; return uploadResult }
        override suspend fun create(body: MedicalDocumentCreateDto): ApiResult<MedicalDocumentDto> { created = body; return ApiResult.Success(document()) }
    }
}

private fun document() = MedicalDocumentDto("document", "file", "lab_report", documentDate = "2026-10-20", processingMode = "analyze", parseStatus = "needs_confirmation", recordVersion = 1, createdAt = "", updatedAt = "", fileStatus = "available", originalName = "report.pdf")

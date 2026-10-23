package com.gutcare.app.ui.records

import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.FileObjectDto
import com.gutcare.app.core.network.MedicalCandidateDecisionDto
import com.gutcare.app.core.network.MedicalDocumentCreateDto
import com.gutcare.app.core.network.MedicalDocumentDto
import com.gutcare.app.core.network.MedicalDocumentPageDto
import com.gutcare.app.core.network.MedicalFieldCandidateDto
import com.gutcare.app.core.network.UploadCreateDto
import com.gutcare.app.core.network.ConsentNoticeDto
import com.gutcare.app.core.network.ConsentStatusDto
import com.gutcare.app.core.network.ConfirmedMedicalFactDto
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

    @Test fun openingDocumentReadsPatientConfirmedFactsFromDedicatedEndpoint() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply {
                detailResult = ApiResult.Success(document())
                confirmedFactResult = ApiResult.Success(listOf(ConfirmedMedicalFactDto("document", "test_item", "string", "CRP", confirmedAt = "2026-10-20T00:00:00Z")))
            }
            val model = MedicalDocumentsViewModel(gateway)
            model.open("document"); advanceUntilIdle()
            assertEquals("CRP", model.uiState.value.confirmedFacts.single().value)
            assertEquals(1, gateway.confirmedFactReads)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun openingDocumentExposesStringAndObjectCandidateValues() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val testItem = MedicalFieldCandidateDto("item-candidate", "test_item", "string", "fecal calprotectin", recordVersion = 1, reviewStatus = "pending")
            val resultValue = mapOf("result" to "125", "unit" to "ug/g", "reference_range" to "0-50")
            val testResult = MedicalFieldCandidateDto("result-candidate", "test_result", "object", resultValue, recordVersion = 1, reviewStatus = "pending")
            val gateway = FakeGateway().apply {
                detailResult = ApiResult.Success(document())
                candidateResult = ApiResult.Success(listOf(testItem, testResult))
            }
            val model = MedicalDocumentsViewModel(gateway)

            model.open("document"); advanceUntilIdle()

            val candidates = model.uiState.value.candidates
            assertEquals(listOf("test_item", "test_result"), candidates.map { it.fieldCode })
            assertEquals("fecal calprotectin", candidates[0].value)
            assertEquals("object", candidates[1].valueType)
            assertEquals(resultValue, candidates[1].value)
            assertEquals("ug/g", (candidates[1].value as Map<*, *>)["unit"])
        } finally { Dispatchers.resetMain() }
    }

    @Test fun uploadCreatesDocumentOnlyAfterGatewayAndCompletionSucceed() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply {
                uploadResult = ApiResult.Success(FileObjectDto("file", "available", "application/pdf", 12))
                consents += ConsentStatusDto("health_data_processing", "v1", true, "2026-10-20T00:00:00Z", null)
            }
            val model = MedicalDocumentsViewModel(gateway)
            model.upload("report.pdf", "application/pdf", 12, RequestBody.create(null, byteArrayOf(1)), analyze = false)
            advanceUntilIdle()
            assertEquals("store_only", gateway.created?.processingMode)
            assertEquals("报告已安全上传。", model.uiState.value.operationMessage)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun uploadPreservesPatientSelectedDocumentType() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply {
                uploadResult = ApiResult.Success(FileObjectDto("file", "available", "application/pdf", 12))
                consents += ConsentStatusDto("health_data_processing", "v1", true, "2026-10-20T00:00:00Z", null)
            }
            val model = MedicalDocumentsViewModel(gateway)
            model.upload("report.pdf", "application/pdf", 12, RequestBody.create(null, byteArrayOf(1)), analyze = false, documentType = "lab_report")
            advanceUntilIdle()
            assertEquals("lab_report", gateway.created?.documentType)
            assertEquals("store_only", gateway.created?.processingMode)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun analyzeShowsSeparatePurposeNoticesAndUploadsOnlyAfterBothGrants() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply { uploadResult = ApiResult.Success(FileObjectDto("file", "available", "application/pdf", 12)) }
            val model = MedicalDocumentsViewModel(gateway)
            model.upload("report.pdf", "application/pdf", 12, RequestBody.create(null, byteArrayOf(1)), analyze = true)
            advanceUntilIdle()
            assertEquals(0, gateway.uploadCalls)
            assertEquals("health_data_processing", model.uiState.value.pendingConsentNotice?.consentType)
            model.confirmConsentNotice(); advanceUntilIdle()
            assertEquals("third_party_ai", model.uiState.value.pendingConsentNotice?.consentType)
            assertEquals(0, gateway.uploadCalls)
            model.confirmConsentNotice(); advanceUntilIdle()
            assertEquals(1, gateway.uploadCalls)
            assertEquals("analyze", gateway.created?.processingMode)
            assertEquals(listOf("health_data_processing", "third_party_ai"), gateway.noticeTypes)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun storeOnlyRequiresHealthDataConsentBeforeUploading() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply { uploadResult = ApiResult.Success(FileObjectDto("file", "available", "application/pdf", 12)) }
            val model = MedicalDocumentsViewModel(gateway)
            model.upload("report.pdf", "application/pdf", 12, RequestBody.create(null, byteArrayOf(1)), analyze = false)
            advanceUntilIdle()
            assertEquals(0, gateway.uploadCalls)
            assertEquals("health_data_processing", model.uiState.value.pendingConsentNotice?.consentType)
            model.confirmConsentNotice(); advanceUntilIdle()
            assertEquals(1, gateway.uploadCalls)
            assertEquals("store_only", gateway.created?.processingMode)
            assertEquals(listOf("health_data_processing"), gateway.noticeTypes)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun analyzeFailsClosedWhenNoticeIsDisabled() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val gateway = FakeGateway().apply { enabledNotice = false }
            val model = MedicalDocumentsViewModel(gateway)
            model.upload("report.pdf", "application/pdf", 12, RequestBody.create(null, byteArrayOf(1)), analyze = true)
            advanceUntilIdle()
            assertEquals(0, gateway.uploadCalls)
            assertTrue(model.uiState.value.operationMessage?.contains("告知") == true)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun revokingEitherAnalyzeConsentUpdatesDisplayedServerStatus() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val active = ConsentStatusDto("third_party_ai", "v1", true, "2026-10-20T00:00:00Z", null)
            val gateway = FakeGateway().apply { consents += active }
            val model = MedicalDocumentsViewModel(gateway)
            model.loadConsents(); advanceUntilIdle()
            model.revokeConsent("third_party_ai"); advanceUntilIdle()
            assertEquals(false, model.uiState.value.consentStatus["third_party_ai"]?.granted)
        } finally { Dispatchers.resetMain() }
    }

    private class FakeGateway : MedicalDocumentsGateway {
        var listResult: ApiResult<MedicalDocumentPageDto> = ApiResult.Success(MedicalDocumentPageDto(emptyList(), null))
        var detailResult: ApiResult<MedicalDocumentDto> = ApiResult.Failure(404, "NOT_FOUND")
        var candidateResult: ApiResult<List<MedicalFieldCandidateDto>> = ApiResult.Success(emptyList())
        var confirmedFactResult: ApiResult<List<ConfirmedMedicalFactDto>> = ApiResult.Success(emptyList())
        var confirmedFactReads = 0
        var decisionResult: ApiResult<Unit> = ApiResult.Success(Unit)
        var uploadResult: ApiResult<FileObjectDto> = ApiResult.Failure(null, "NETWORK_ERROR")
        var decisions = 0
        var uploadCalls = 0
        var lastDecision: MedicalCandidateDecisionDto? = null
        var created: MedicalDocumentCreateDto? = null
        var consents = mutableListOf<ConsentStatusDto>()
        var noticeTypes = mutableListOf<String>()
        var enabledNotice = true
        override suspend fun consents(): ApiResult<List<ConsentStatusDto>> = ApiResult.Success(consents.toList())
        override suspend fun notice(type: String): ApiResult<ConsentNoticeDto> {
            noticeTypes += type
            return ApiResult.Success(ConsentNoticeDto(type, enabledNotice, "v1", "测试告知摘要", "解析", "医疗文档", "智能体服务", "可撤回"))
        }
        override suspend fun grantConsent(type: String, policyVersion: String): ApiResult<ConsentStatusDto> {
            val status = ConsentStatusDto(type, policyVersion, true, "2026-10-20T00:00:00Z", null)
            consents.removeAll { it.consentType == type }
            consents += status
            return ApiResult.Success(status)
        }
        override suspend fun revokeConsent(type: String, policyVersion: String): ApiResult<ConsentStatusDto> {
            val status = ConsentStatusDto(type, policyVersion, false, "2026-10-20T00:00:00Z", "2026-10-20T00:00:00Z")
            consents.removeAll { it.consentType == type }
            consents += status
            return ApiResult.Success(status)
        }
        override suspend fun list(cursor: String?) = listResult
        override suspend fun detail(id: String) = detailResult
        override suspend fun candidates(documentId: String) = candidateResult
        override suspend fun confirmedFacts(): ApiResult<List<ConfirmedMedicalFactDto>> { confirmedFactReads++; return confirmedFactResult }
        override suspend fun decide(candidateId: String, key: String, body: MedicalCandidateDecisionDto): ApiResult<Unit> { decisions++; lastDecision = body; return decisionResult }
        override suspend fun upload(key: String, metadata: UploadCreateDto, content: RequestBody): ApiResult<FileObjectDto> { uploadCalls++; return uploadResult }
        override suspend fun create(body: MedicalDocumentCreateDto): ApiResult<MedicalDocumentDto> { created = body; return ApiResult.Success(document()) }
    }
}

private fun document() = MedicalDocumentDto("document", "file", "lab_report", documentDate = "2026-10-20", processingMode = "analyze", parseStatus = "needs_confirmation", recordVersion = 1, createdAt = "", updatedAt = "", fileStatus = "available", originalName = "report.pdf")

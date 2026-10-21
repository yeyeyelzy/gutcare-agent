package com.gutcare.app.ui.privacy

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.ConsentNoticeDto
import com.gutcare.app.core.network.ConsentStatusDto
import com.gutcare.app.core.network.PrivacyDeletionAcceptedDto
import com.gutcare.app.core.network.PrivacyDeletionStatusDto
import com.gutcare.app.core.network.PrivacyExportDetailDto
import com.gutcare.app.core.network.PrivacyExportPreviewDto
import com.gutcare.app.core.network.PrivacyExportSummaryDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PrivacyViewModelTest {
    @get:Rule val instantTaskExecutorRule = InstantTaskExecutorRule()

    @Test fun consentGrantRequiresEnabledServerNoticeAndWithdrawalUsesActiveVersion() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway()
            val model = PrivacyViewModel(gateway)
            model.load(); advanceUntilIdle()
            model.requestGrantNotice("mood_ai_sharing"); advanceUntilIdle()
            assertEquals("mood-ai-v1", model.uiState.value.pendingNotice?.policyVersion)
            model.confirmGrant(); advanceUntilIdle()
            assertEquals(ConsentDecision("mood_ai_sharing", "mood-ai-v1", true), gateway.lastDecision)
            model.revoke("mood_ai_sharing"); advanceUntilIdle()
            assertEquals(ConsentDecision("mood_ai_sharing", "mood-ai-v1", false), gateway.lastDecision)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun exportRequiresPreviewThenConfirmationAndCapabilityIsClearedAfterSingleDownload() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway()
            val model = PrivacyViewModel(gateway)
            model.createPreview(); advanceUntilIdle()
            assertEquals("preview-id", model.uiState.value.preview?.exportId)
            assertEquals(0, gateway.confirmed.size)
            model.confirmPreview(); advanceUntilIdle()
            assertEquals(listOf("preview-id"), gateway.confirmed)
            model.refreshExport("export-id"); advanceUntilIdle()
            assertEquals("ephemeral-capability", model.uiState.value.activeExport?.downloadCapability)
            model.downloadReadyExport(); advanceUntilIdle()
            assertEquals("ephemeral-capability", gateway.usedCapability)
            assertNull(model.uiState.value.activeExport?.downloadCapability)
            assertEquals(4, model.uiState.value.exportBytes?.size)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun deletionReceiptRemainsOnlyInMemoryForStatusQuery() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway()
            val model = PrivacyViewModel(gateway)
            model.requestDeletion(); advanceUntilIdle()
            assertEquals("operation-id", gateway.statusOperationId)
            assertEquals("one-time-receipt-not-for-storage-1234567890", gateway.statusReceipt)
            assertEquals("one-time-receipt-not-for-storage-1234567890", model.uiState.value.deletionReceiptTransient)
            assertEquals("processing", model.uiState.value.deletionOperation?.status)
            assertTrue(model.uiState.value.message.orEmpty().contains("一次性"))
            model.clearSensitiveTransient()
            assertNull(model.uiState.value.deletionReceiptTransient)
        } finally { Dispatchers.resetMain() }
    }

    private data class ConsentDecision(val type: String, val version: String, val granted: Boolean)

    private class FakeGateway : PrivacyGateway {
        private var activeConsent = ConsentStatusDto("mood_ai_sharing", "mood-ai-v1", false, null, null)
        var lastDecision: ConsentDecision? = null
        val confirmed = mutableListOf<String>()
        var usedCapability: String? = null
        var statusOperationId: String? = null
        var statusReceipt: String? = null

        override suspend fun consents() = ApiResult.Success(listOf(activeConsent))
        override suspend fun notice(type: String) = ApiResult.Success(ConsentNoticeDto(type, true, "mood-ai-v1", "说明", "个性化分析", "受控等级与标签", "披露的智能体", "后续分析不再纳入心情"))
        override suspend fun decide(type: String, version: String, granted: Boolean): ApiResult<ConsentStatusDto> {
            lastDecision = ConsentDecision(type, version, granted)
            activeConsent = activeConsent.copy(policyVersion = version, granted = granted, decidedAt = "2026-10-20T00:00:00Z", revokedAt = if (granted) null else "2026-10-20T00:00:00Z")
            return ApiResult.Success(activeConsent)
        }
        override suspend fun deleteAccount() = ApiResult.Success(PrivacyDeletionAcceptedDto("operation-id", "one-time-receipt-not-for-storage-1234567890", "accepted"))
        override suspend fun deletionStatus(id: String, receipt: String): ApiResult<PrivacyDeletionStatusDto> {
            statusOperationId = id; statusReceipt = receipt
            return ApiResult.Success(PrivacyDeletionStatusDto(id, "processing", "2026-10-20T00:00:00Z", "2026-11-19T00:00:00Z", null))
        }
        override suspend fun createExport(categories: List<String>) = ApiResult.Success(PrivacyExportPreviewDto("preview-id", "preview", categories))
        override suspend fun exports() = ApiResult.Success(emptyList<PrivacyExportSummaryDto>())
        override suspend fun export(id: String) = ApiResult.Success(PrivacyExportDetailDto(id, "ready", listOf("profile"), "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z", "ephemeral-capability"))
        override suspend fun confirmExport(id: String): ApiResult<Unit> { confirmed += id; return ApiResult.Success(Unit) }
        override suspend fun cancelExport(id: String) = ApiResult.Success(Unit)
        override suspend fun download(capability: String): ApiResult<ByteArray> { usedCapability = capability; return ApiResult.Success(byteArrayOf(1, 2, 3, 4)) }
    }
}

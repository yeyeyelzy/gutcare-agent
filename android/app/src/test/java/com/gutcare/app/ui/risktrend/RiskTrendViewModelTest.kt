package com.gutcare.app.ui.risktrend

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.HistoryItemDto
import com.gutcare.app.core.network.HistoryPageDto
import com.gutcare.app.core.network.HistoryTargetDto
import com.gutcare.app.core.network.MoodTrendDto
import com.gutcare.app.core.network.RiskAlertDto
import com.gutcare.app.core.network.RiskAlertPageDto
import com.gutcare.app.core.network.TrendResponseDto
import com.gutcare.app.core.network.TrendSeriesDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RiskTrendViewModelTest {
    @get:Rule val instant = InstantTaskExecutorRule()

    @Test fun riskReadAndReevaluationUseServerReturnedState() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val model = RiskTrendViewModel(gateway)
            model.openRisk("r1"); advanceUntilIdle()
            model.markRead(); advanceUntilIdle()
            assertEquals("read", model.uiState.value.detail?.status)
            assertEquals("test_only", model.uiState.value.detail?.environment)
            model.reevaluate(); advanceUntilIdle()
            assertEquals("reevaluated", model.uiState.value.detail?.status)
            assertEquals("r1", gateway.lastRiskId)
        }
    }

    @Test fun trendConsentIsDistinctFromEmptyAndError() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val model = RiskTrendViewModel(gateway)
            gateway.trendResult = ApiResult.Success(sampleTrend(mood = MoodTrendDto("consent_required", reasonCode = "CONSENT_REQUIRED", missingConsents = listOf("mood_data_processing"))))
            model.loadTrends("from", "to"); advanceUntilIdle()
            assertTrue(model.uiState.value.trends is TrendState.ConsentRequired)
            gateway.trendResult = ApiResult.Success(sampleTrend())
            model.loadTrends("from", "to"); advanceUntilIdle()
            assertEquals(TrendState.Empty, model.uiState.value.trends)
            gateway.trendResult = ApiResult.Failure(null, "NETWORK_ERROR")
            model.loadTrends("from", "to"); advanceUntilIdle()
            assertTrue(model.uiState.value.trends is TrendState.Error)
        }
    }

    @Test fun historyUsesOpaqueCursorAndRetainsFirstPageWhenNextRequestFails() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val first = HistoryItemDto("id1", "mood", "2026-10-20T00:00:00Z", HistoryTargetDto("mood_record", "id1"))
            gateway.historyResults += ApiResult.Success(HistoryPageDto(listOf(first), "opaque-next"))
            gateway.historyResults += ApiResult.Failure(400, "INVALID_CURSOR")
            val model = RiskTrendViewModel(gateway)
            model.loadHistory(); advanceUntilIdle()
            model.loadMoreHistory(); advanceUntilIdle()
            val ready = model.uiState.value.history as HistoryState.Ready
            assertEquals("opaque-next", gateway.lastHistoryCursor)
            assertEquals(listOf(first), ready.items)
            assertEquals("历史位置已失效，请重新加载。", model.uiState.value.historyMoreError)
        }
    }

    private suspend fun withMainDispatcher(scheduler: TestCoroutineScheduler, block: suspend () -> Unit) {
        Dispatchers.setMain(StandardTestDispatcher(scheduler))
        try { block() } finally { Dispatchers.resetMain() }
    }

    private class FakeGateway : RiskTrendGateway {
        var lastRiskId: String? = null
        var lastHistoryCursor: String? = null
        var trendResult: ApiResult<TrendResponseDto> = ApiResult.Success(sampleTrend())
        val historyResults = ArrayDeque<ApiResult<HistoryPageDto>>()
        private var risk = RiskAlertDto("r1", "test_only", "attention", "提醒内容", "建议行动", "unread", "2026-10-20T00:00:00Z")
        override suspend fun risks(cursor: String?) = ApiResult.Success(RiskAlertPageDto(emptyList(), null))
        override suspend fun risk(id: String): ApiResult<RiskAlertDto> { lastRiskId = id; return ApiResult.Success(risk) }
        override suspend fun readRisk(id: String): ApiResult<RiskAlertDto> { lastRiskId = id; risk = risk.copy(status = "read", readAt = "now"); return ApiResult.Success(risk) }
        override suspend fun reevaluateRisk(id: String): ApiResult<RiskAlertDto> { lastRiskId = id; risk = risk.copy(status = "reevaluated", reevaluatedAt = "now"); return ApiResult.Success(risk) }
        override suspend fun trends(from: String, to: String, bucket: String) = trendResult
        override suspend fun history(cursor: String?): ApiResult<HistoryPageDto> { lastHistoryCursor = cursor; return historyResults.removeFirst() }
    }
}

private fun sampleTrend(mood: MoodTrendDto = MoodTrendDto("available", buckets = emptyList())) =
    TrendResponseDto("Asia/Shanghai", "from", "to", "day", TrendSeriesDto(false, emptyList()), TrendSeriesDto(false, emptyList()), TrendSeriesDto(false, emptyList()), TrendSeriesDto(false, emptyList()), TrendSeriesDto(false, emptyList()), mood)

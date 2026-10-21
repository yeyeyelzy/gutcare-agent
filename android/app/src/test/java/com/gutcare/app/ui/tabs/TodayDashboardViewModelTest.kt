package com.gutcare.app.ui.tabs

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.AdvicePageDto
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.HistoryItemDto
import com.gutcare.app.core.network.HistoryPageDto
import com.gutcare.app.core.network.MedicationCheckinDto
import com.gutcare.app.core.network.NotificationUnreadCountDto
import com.gutcare.app.core.network.RiskAlertPageDto
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class TodayDashboardViewModelTest {
    @get:Rule val instantTaskExecutorRule = InstantTaskExecutorRule()

    @Test fun logoutInvalidatesDelayedDashboardResponses() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeTodayGateway().apply { delayedRisks = CompletableDeferred() }
            val model = TodayDashboardViewModel(gateway)
            model.refresh("Asia/Shanghai")
            runCurrent()
            model.clearForLogout()
            gateway.delayedRisks!!.complete(ApiResult.Success(RiskAlertPageDto(emptyList(), null)))
            advanceUntilIdle()

            assertFalse(model.state.value.loading)
            assertNull(model.state.value.recentRecord.value)
            assertNull(model.state.value.unreadCount)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun recentHealthCardSkipsAdviceAndQueryCategorySetIsHealthOnly() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeTodayGateway().apply {
                history = HistoryPageDto(
                    items = listOf(item("advice"), item("mood")),
                    nextCursor = null,
                )
            }
            val model = TodayDashboardViewModel(gateway)
            model.refresh("Asia/Shanghai")
            advanceUntilIdle()

            assertEquals("最近记录：心情", model.state.value.recentRecord.value)
            assertEquals(listOf("diet", "stool", "symptom", "mood", "medication_checkin", "activity"), RECENT_HEALTH_HISTORY_CATEGORIES)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun independentFailureDoesNotBlankOtherDashboardCards() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeTodayGateway().apply { medicationResult = ApiResult.Failure(null, "NETWORK_ERROR") }
            val model = TodayDashboardViewModel(gateway)
            model.refresh("Asia/Shanghai")
            advanceUntilIdle()

            assertEquals(3, model.state.value.unreadCount)
            assertEquals("最近记录：饮食", model.state.value.recentRecord.value)
            assertNull(model.state.value.latestAdvice.value)
            assertEquals(true, model.state.value.medication.failed)
            assertFalse(model.state.value.loading)
        } finally { Dispatchers.resetMain() }
    }
}

private class FakeTodayGateway : TodayDashboardGateway {
    var delayedRisks: CompletableDeferred<ApiResult<RiskAlertPageDto>>? = null
    var medicationResult: ApiResult<List<MedicationCheckinDto>> = ApiResult.Success(emptyList())
    var history: HistoryPageDto = HistoryPageDto(listOf(item("diet")), null)
    override suspend fun risks() = delayedRisks?.await() ?: ApiResult.Success(RiskAlertPageDto(emptyList(), null))
    override suspend fun medication() = medicationResult
    override suspend fun recentHealthHistory() = ApiResult.Success(history)
    override suspend fun latestAdvice() = ApiResult.Success(AdvicePageDto(emptyList(), null))
    override suspend fun unreadCount() = ApiResult.Success(NotificationUnreadCountDto(3))
}

private fun item(type: String) = HistoryItemDto("id-$type", type, "2026-10-20T10:00:00Z", com.gutcare.app.core.network.HistoryTargetDto(type, "id-$type"))

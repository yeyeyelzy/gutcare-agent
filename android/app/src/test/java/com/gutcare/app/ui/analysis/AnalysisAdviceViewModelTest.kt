package com.gutcare.app.ui.analysis

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AnalysisAdviceViewModelTest {
    @get:Rule val instant = InstantTaskExecutorRule()

    @Test fun createRequiresARealServerPreviewAndDisplaysOnlyReturnedTask() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val model = AnalysisAdviceViewModel(gateway)
            model.create(); advanceUntilIdle()
            assertEquals(0, gateway.createCalls)
            model.preview(); advanceUntilIdle()
            assertNotNull(model.state.value.preview)
            model.create(); advanceUntilIdle()
            assertEquals(1, gateway.createCalls)
            assertEquals("pending", model.state.value.selectedTask?.status)
            assertNull(model.state.value.selectedTask?.result)
        }
    }

    @Test fun emptyAdviceAndNoAgentResultRemainExplicitEmptyStates() = runTest {
        withMainDispatcher(testScheduler) {
            val model = AnalysisAdviceViewModel(FakeGateway())
            model.load(); advanceUntilIdle()
            assertEquals(emptyList<AdviceDto>(), model.state.value.advice)
            model.openTask("task"); advanceUntilIdle()
            assertNull(model.state.value.selectedTask?.result)
        }
    }

    @Test fun dateRangeUsesPatientZoneAndExclusiveNextDayBoundary() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val model = AnalysisAdviceViewModel(gateway)
            model.setTimeZone("Asia/Shanghai")
            model.setRange("2026-10-22", "2026-10-23")
            model.preview(); advanceUntilIdle()
            assertEquals("2026-10-21T16:00:00Z", gateway.previewFrom)
            assertEquals("2026-10-23T16:00:00Z", gateway.previewTo)
        }
    }

    @Test fun comprehensiveAnalysisAllowsBothDateEndpointsToBeOmitted() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val model = AnalysisAdviceViewModel(gateway)
            model.preview(); advanceUntilIdle()
            assertEquals(1, gateway.previewCalls)
            assertNull(gateway.previewFrom)
            assertNull(gateway.previewTo)
        }
    }

    @Test fun historyIsNewestFirstAndTaskDetailReturnsToHistory() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val older = gateway.pendingTask.copy(id = "older", createdAt = "2026-10-20T08:00:00Z")
            val newer = gateway.pendingTask.copy(id = "newer", createdAt = "2026-10-22T08:00:00Z", status = "partial",
                result = AnalysisResultDto("1.0", "已有结果", emptyList(), emptyList(), emptyList(), emptyList()))
            gateway.taskItems = listOf(older, newer)
            gateway.detailItems["newer"] = newer
            val model = AnalysisAdviceViewModel(gateway)

            model.showHistory(); advanceUntilIdle()
            assertEquals(listOf("newer", "older"), model.state.value.tasks.map { it.id })
            model.openTask("newer"); advanceUntilIdle()
            assertEquals("已有结果", model.state.value.selectedTask?.result?.summary)
            model.backToList()
            assertEquals(true, model.state.value.showHistory)
            assertNull(model.state.value.selectedTask)
        }
    }

    @Test fun adviceHistoryUsesItsOwnWorkspaceState() = runTest {
        withMainDispatcher(testScheduler) {
            val model = AnalysisAdviceViewModel(FakeGateway())

            model.showAdviceHistory(); advanceUntilIdle()
            assertEquals(true, model.state.value.showAdviceHistory)
            assertEquals(false, model.state.value.showHistory)

            model.hideAdviceHistory()
            assertEquals(false, model.state.value.showAdviceHistory)
        }
    }

    @Test fun returningWhileTaskDetailRequestIsInFlightDoesNotReopenDetail() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val response = CompletableDeferred<ApiResult<AnalysisTaskDto>>()
            gateway.pendingDetailResponse = response
            val model = AnalysisAdviceViewModel(gateway)
            model.showHistory(); advanceUntilIdle()

            model.openTask("task")
            runCurrent()
            assertEquals(true, model.state.value.busy)

            model.backToList()
            assertNull(model.state.value.selectedTask)
            assertEquals(true, model.state.value.showHistory)

            response.complete(ApiResult.Success(gateway.pendingTask))
            advanceUntilIdle()
            assertNull(model.state.value.selectedTask)
            assertEquals(true, model.state.value.showHistory)
            assertEquals(false, model.state.value.busy)
        }
    }

    @Test fun taskDetailPollsUntilTerminalAndKeepsOnlyServerReturnedStructuredResult() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            gateway.polledTask = gateway.pendingTask.copy(
                status = "partial",
                result = AnalysisResultDto(
                    "1.0", "服务端摘要", listOf("记录数量有限"),
                    listOf(AnalysisSourceEvidenceDto("mood_record", "source-id", 1, null, false)),
                    listOf("样本有限"), listOf("缺少近期记录"),
                ),
            )
            val model = AnalysisAdviceViewModel(gateway)

            model.openTask("task")
            runCurrent()
            assertEquals("pending", model.state.value.selectedTask?.status)
            assertEquals(true, model.state.value.taskPolling)

            advanceTimeBy(2_000)
            runCurrent()
            assertEquals(2, gateway.taskCalls)
            assertEquals("partial", model.state.value.selectedTask?.status)
            assertEquals("服务端摘要", model.state.value.selectedTask?.result?.summary)
            assertEquals(false, model.state.value.taskPolling)
            assertEquals(false, model.state.value.taskPollingTimedOut)
        }
    }

    @Test fun pollingStopsAtBoundAndManualRefreshCanRestartIt() = runTest {
        withMainDispatcher(testScheduler) {
            val gateway = FakeGateway()
            val model = AnalysisAdviceViewModel(gateway)
            model.openTask("task")
            runCurrent()
            advanceTimeBy(30_001)
            runCurrent()
            assertEquals(16, gateway.taskCalls)
            assertEquals(false, model.state.value.taskPolling)
            assertEquals(true, model.state.value.taskPollingTimedOut)

            model.refreshTask("task")
            runCurrent()
            assertEquals(true, model.state.value.taskPolling)
            model.backToList()
            assertEquals(false, model.state.value.taskPolling)
        }
    }

    private suspend fun withMainDispatcher(scheduler: TestCoroutineScheduler, block: suspend () -> Unit) {
        Dispatchers.setMain(StandardTestDispatcher(scheduler))
        try { block() } finally { Dispatchers.resetMain() }
    }

    private class FakeGateway : AnalysisAdviceGateway {
        var createCalls = 0
        var taskCalls = 0
        var previewCalls = 0
        var previewFrom: String? = null
        var previewTo: String? = null
        var taskItems = listOf<AnalysisTaskDto>()
        val detailItems = mutableMapOf<String, AnalysisTaskDto>()
        var polledTask: AnalysisTaskDto? = null
        var pendingDetailResponse: CompletableDeferred<ApiResult<AnalysisTaskDto>>? = null
        val pendingTask = AnalysisTaskDto("task", "comprehensive_health_analysis", "pending", AnalysisInputSummaryDto(0), "now", "now", 1, null, null, null)
        private val task get() = pendingTask
        override suspend fun tasks(cursor: String?) = ApiResult.Success(AnalysisTaskPageDto(taskItems.ifEmpty { listOf(task) }, null))
        override suspend fun preview(type: String, from: String?, to: String?): ApiResult<AnalysisTaskPreviewDto> {
            previewCalls++; previewFrom = from; previewTo = to
            return ApiResult.Success(AnalysisTaskPreviewDto(type, from, to, "Asia/Shanghai", 0, 0, 0, emptyList()))
        }
        override suspend fun create(type: String, from: String?, to: String?): ApiResult<AnalysisTaskDto> { createCalls++; return ApiResult.Success(task) }
        override suspend fun task(id: String): ApiResult<AnalysisTaskDto> {
            taskCalls++
            pendingDetailResponse?.let { return withContext(NonCancellable) { it.await() } }
            return ApiResult.Success(detailItems[id] ?: if (taskCalls == 1) task else polledTask ?: task)
        }
        override suspend fun cancel(id: String) = ApiResult.Success(task.copy(status = "cancelled"))
        override suspend fun retry(id: String) = ApiResult.Success(task.copy(attempt = 2))
        override suspend fun adviceList(cursor: String?) = ApiResult.Success(AdvicePageDto(emptyList(), null))
        override suspend fun advice(id: String): ApiResult<AdviceDto> = ApiResult.Failure(404, "NOT_FOUND")
        override suspend fun markRead(id: String): ApiResult<AdviceDto> = ApiResult.Failure(404, "NOT_FOUND")
        override suspend fun archive(id: String): ApiResult<AdviceDto> = ApiResult.Failure(404, "NOT_FOUND")
        override suspend fun feedback(id: String, value: String, version: Int): ApiResult<AdviceFeedbackDto> = ApiResult.Failure(404, "NOT_FOUND")
    }
}

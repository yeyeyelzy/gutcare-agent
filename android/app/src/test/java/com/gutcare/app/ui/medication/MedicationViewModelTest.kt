package com.gutcare.app.ui.medication

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.MedicationCheckinDto
import com.gutcare.app.core.network.MedicationCheckinUpdateDto
import com.gutcare.app.core.network.MedicationPlanCreateDto
import com.gutcare.app.core.network.MedicationPlanDto
import com.gutcare.app.core.network.MedicationPlanTransitionDto
import com.gutcare.app.core.network.MedicationScheduleDto
import com.gutcare.app.core.network.MedicationScheduleWriteDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MedicationViewModelTest {
    @get:Rule val instantTaskExecutorRule = InstantTaskExecutorRule()

    @Test fun loadUsesRemotePlansAndTodayAndKeepsEmptyStateDistinct() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway().apply {
                plansResult = ApiResult.Success(emptyList())
                todayResult = ApiResult.Success(emptyList())
            }
            val model = MedicationViewModel(gateway)
            model.load(MedicationSection.TODAY)
            advanceUntilIdle()
            assertTrue(model.uiState.value.plans.isEmpty())
            assertTrue(model.uiState.value.today.isEmpty())
            assertEquals(1, gateway.todayCalls)
            gateway.plansResult = ApiResult.Failure(null, "NETWORK_ERROR")
            model.load()
            advanceUntilIdle()
            assertTrue(model.uiState.value.error.orEmpty().contains("网络"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun populatedLoadRetainsRemotePlansAndScheduledDoses() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway()
            val model = MedicationViewModel(gateway)
            model.load(MedicationSection.TODAY)
            advanceUntilIdle()
            assertEquals(listOf("plan-1"), model.uiState.value.plans.map { it.id })
            assertEquals(listOf("checkin-1"), model.uiState.value.today.map { it.id })
            assertEquals(listOf("schedule-1"), model.uiState.value.schedules["plan-1"]?.map { it.id })
        } finally { Dispatchers.resetMain() }
    }

    @Test fun createSendsManualPlanAndUniqueIdempotencyKey() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway()
            val model = MedicationViewModel(gateway)
            model.createPlan("  益生菌  ", "每日一粒", "oral", "2026-10-20", "")
            advanceUntilIdle()
            assertEquals("益生菌", gateway.createdPlan?.medicationName)
            assertEquals("manual", gateway.createdPlan?.sourceType)
            assertTrue(gateway.createPlanKey.orEmpty().length >= 8)
            assertTrue(model.uiState.value.operationMessage.orEmpty().contains("待确认"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun planTransitionsUseCurrentVersionAnd409IsExplicit() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway().apply { transitionResult = ApiResult.Failure(409, "RECORD_VERSION_CONFLICT") }
            val model = MedicationViewModel(gateway)
            model.transition(plan, "confirm")
            advanceUntilIdle()
            assertEquals(9, gateway.transition?.recordVersion)
            assertTrue(model.uiState.value.conflict)
            assertTrue(model.uiState.value.operationMessage.orEmpty().contains("版本"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun pendingCheckinCanBeExplicitlyConfirmedAsTakenWithoutChangingOtherFields() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway()
            val model = MedicationViewModel(gateway)
            model.updateCheckin(checkin, "taken")
            advanceUntilIdle()
            assertEquals("taken", gateway.checkinUpdate?.status)
            assertEquals(4, gateway.checkinUpdate?.recordVersion)
            assertTrue(gateway.checkinUpdate?.takenAt.orEmpty().contains("T"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun scheduleToggleUsesOptimisticVersionAndHistoryQueryUsesChosenDates() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeGateway()
            val model = MedicationViewModel(gateway)
            model.toggleSchedule(schedule)
            advanceUntilIdle()
            assertEquals(false, gateway.scheduleUpdate?.enabled)
            assertEquals(3, gateway.scheduleUpdate?.recordVersion)
            model.setHistoryRange("2026-10-01", "2026-10-20")
            advanceUntilIdle()
            assertEquals("2026-10-01" to "2026-10-20", gateway.historyRange)
        } finally { Dispatchers.resetMain() }
    }

    private class FakeGateway : MedicationFeatureGateway {
        var plansResult: ApiResult<List<MedicationPlanDto>> = ApiResult.Success(listOf(plan))
        var todayResult: ApiResult<List<MedicationCheckinDto>> = ApiResult.Success(listOf(checkin))
        var transitionResult: ApiResult<MedicationPlanDto> = ApiResult.Success(plan)
        var createPlanKey: String? = null
        var createdPlan: MedicationPlanCreateDto? = null
        var transition: MedicationPlanTransitionDto? = null
        var checkinUpdate: MedicationCheckinUpdateDto? = null
        var scheduleUpdate: MedicationScheduleWriteDto? = null
        var historyRange: Pair<String, String>? = null
        var todayCalls = 0
        override suspend fun plans() = plansResult
        override suspend fun createPlan(key: String, body: MedicationPlanCreateDto): ApiResult<MedicationPlanDto> {
            createPlanKey = key; createdPlan = body; return ApiResult.Success(plan)
        }
        override suspend fun transitionPlan(id: String, key: String, body: MedicationPlanTransitionDto): ApiResult<MedicationPlanDto> {
            transition = body; return transitionResult
        }
        override suspend fun schedules(planId: String) = ApiResult.Success(listOf(schedule))
        override suspend fun createSchedule(planId: String, key: String, body: MedicationScheduleWriteDto) = ApiResult.Success(schedule)
        override suspend fun updateSchedule(id: String, body: MedicationScheduleWriteDto): ApiResult<MedicationScheduleDto> {
            scheduleUpdate = body; return ApiResult.Success(schedule.copy(enabled = body.enabled))
        }
        override suspend fun deleteSchedule(id: String, version: Int) = ApiResult.Success(Unit)
        override suspend fun today(): ApiResult<List<MedicationCheckinDto>> { todayCalls++; return todayResult }
        override suspend fun history(start: String, end: String): ApiResult<List<MedicationCheckinDto>> {
            historyRange = start to end; return ApiResult.Success(emptyList())
        }
        override suspend fun updateCheckin(id: String, body: MedicationCheckinUpdateDto): ApiResult<MedicationCheckinDto> {
            checkinUpdate = body; return ApiResult.Success(checkin.copy(status = body.status))
        }
    }

    companion object {
        private val plan = MedicationPlanDto("plan-1", "patient-1", "药品A", "每次一粒", "oral", null, null, "manual", null, false, "pending", "active", 9)
        private val schedule = MedicationScheduleDto("schedule-1", "plan-1", "08:00:00", "Asia/Shanghai", "FREQ=DAILY", "2026-10-01", null, true, 3)
        private val checkin = MedicationCheckinDto("checkin-1", "schedule-1", "2026-10-20", "2026-10-20T08:00:00+08:00", "pending", null, null, 4)
    }
}

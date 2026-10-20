package com.gutcare.app.ui.records

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.MoodDetailDto
import com.gutcare.app.core.network.MoodPatchDto
import com.gutcare.app.core.network.MoodPageDto
import com.gutcare.app.core.network.MoodWriteDto
import com.gutcare.app.core.network.RecordDto
import com.gutcare.app.core.network.RecordPageDto
import com.gutcare.app.core.network.RecordPatchDto
import com.gutcare.app.core.network.RecordPayloadDto
import com.gutcare.app.core.network.RecordWriteDto
import com.gutcare.app.core.network.SymptomStatusHistoryDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RecordsViewModelTest {
    @get:Rule val instantTaskExecutorRule = InstantTaskExecutorRule()

    @Test fun listUsesRepositoryResultAndExposesEmptyAndErrorStates() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway().apply { listResult = ApiResult.Success(RecordPageDto(emptyList(), null)) }
            val model = RecordsViewModel(gateway)
            model.load(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            assertEquals(RecordsLoadState.Empty, model.uiState.value.loadState)
            gateway.listResult = ApiResult.Failure(null, "NETWORK_ERROR")
            model.load(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            assertTrue(model.uiState.value.loadState is RecordsLoadState.Error)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun savePostsARealPayloadAndReportsAcceptance() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway()
            val model = RecordsViewModel(gateway)
            model.setTimeZone("Asia/Shanghai")
            model.updateDraft { it.copy(description = "燕麦粥", mealType = "breakfast") }
            model.save(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            assertEquals("燕麦粥", gateway.lastRecordWrite?.payload?.textDescription)
            assertEquals("breakfast", gateway.lastRecordWrite?.payload?.mealType)
            assertTrue(gateway.idempotencyKey?.isNotBlank() == true)
            assertEquals("记录已保存。", model.uiState.value.operation.feedback)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun saveWaitsForProfileTimeZoneAndAcceptsTheDisplayedSlashDateFormat() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway()
            val model = RecordsViewModel(gateway)
            model.updateDraft { it.copy(date = "2026/10/19", time = "08:30", description = "粥") }
            model.save(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            assertEquals(null, gateway.lastRecordWrite)
            assertTrue(model.uiState.value.operation.feedback?.contains("时区") == true)

            model.setTimeZone("Asia/Shanghai")
            model.updateDraft { it.copy(date = "2026/10/19", time = "08:30", description = "粥") }
            model.save(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            assertEquals("2026-10-19T08:30+08:00", gateway.lastRecordWrite?.occurredAt)

            model.updateDraft { it.copy(description = "敏感草稿") }
            model.clearForLogout()
            assertEquals("", model.uiState.value.draft.description)
            model.updateDraft { it.copy(description = "再次尝试") }
            model.save(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            assertEquals("2026-10-19T08:30+08:00", gateway.lastRecordWrite?.occurredAt)
            assertTrue(model.uiState.value.operation.feedback?.contains("时区") == true)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun staleDeleteVersionSurfacesConflictAndKeepsUserInformed() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway().apply { deleteResult = ApiResult.Failure(409, "RECORD_VERSION_CONFLICT") }
            val model = RecordsViewModel(gateway)
            model.delete(WorkspaceRecordType.DIET, RecordRow("record-1", 3, "本人记录", "2026-10-19T09:00:00Z"))
            advanceUntilIdle()
            assertTrue(model.uiState.value.operation.conflict)
            assertTrue(model.uiState.value.operation.feedback?.contains("版本冲突") == true)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun otherSymptomRequiresDescriptionAndSubmitsIt() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway()
            val model = RecordsViewModel(gateway)
            model.setTimeZone("Asia/Shanghai")
            model.updateDraft { it.copy(symptomCode = "other", date = "2026-10-19", time = "08:30") }
            model.save(WorkspaceRecordType.SYMPTOM)
            assertTrue(model.uiState.value.operation.feedback.orEmpty().contains("描述"))
            assertEquals(null, gateway.lastRecordWrite)
            model.updateDraft { it.copy(otherDescription = "胃部不适") }
            model.save(WorkspaceRecordType.SYMPTOM)
            advanceUntilIdle()
            assertEquals("胃部不适", gateway.lastRecordWrite?.payload?.items?.first()?.otherDescription)

            model.updateDraft { it.copy(otherDescription = "症状".repeat(81)) }
            model.save(WorkspaceRecordType.SYMPTOM)
            assertTrue(model.uiState.value.operation.feedback.orEmpty().contains("160"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun editUsesLoadedVersionAndUpdate409IsExplicit() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway().apply {
                detailResult = ApiResult.Success(RecordDetailModel("r1", 7, "2026-10-19T08:30:00+08:00", RecordPayloadDto(textDescription = "旧描述")))
                updateResult = ApiResult.Failure(409, "RECORD_VERSION_CONFLICT")
            }
            val model = RecordsViewModel(gateway)
            model.setTimeZone("Asia/Shanghai")
            model.loadDetail(WorkspaceRecordType.DIET, "r1")
            advanceUntilIdle()
            model.beginEdit(WorkspaceRecordType.DIET)
            model.updateDraft { it.copy(description = "新描述") }
            model.save(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            assertEquals(7, gateway.lastPatch?.recordVersion)
            assertTrue(model.uiState.value.operation.conflict)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun moodNoteLoadsIntoEditAndExplicitlyClearsWithoutLeakingAfterLeaving() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway().apply {
                detailResult = ApiResult.Success(RecordDetailModel(
                    "mood-1", 6, "2026-10-19T08:30:00+08:00", RecordPayloadDto(),
                    moodLevel = 4, note = "只属于本人的备注",
                ))
            }
            val model = RecordsViewModel(gateway)
            model.setTimeZone("Asia/Shanghai")
            model.loadDetail(WorkspaceRecordType.MOOD, "mood-1")
            advanceUntilIdle()
            model.beginEdit(WorkspaceRecordType.MOOD)
            assertEquals("只属于本人的备注", model.uiState.value.draft.moodNote)
            model.updateDraft { it.copy(moodNote = "") }
            model.save(WorkspaceRecordType.MOOD)
            advanceUntilIdle()
            assertEquals(6, gateway.lastMoodPatch?.recordVersion)
            assertEquals(null, gateway.lastMoodPatch?.note?.value)
            model.clearDraft()
            model.clearDetail()
            assertEquals("", model.uiState.value.draft.moodNote)
            assertEquals(RecordDetailLoadState.Idle, model.uiState.value.detailState)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun loadMoreAppendsAndLogoutClearsSensitiveListAndDetail() = runTest {
        val dispatcher = StandardTestDispatcher(testScheduler)
        Dispatchers.setMain(dispatcher)
        try {
            val gateway = FakeGateway().apply {
                listPages[null] = ApiResult.Success(RecordPageDto(listOf(RecordDto("1", 1, "2026-10-19T08:00:00Z", RecordPayloadDto(textDescription = "一"), "", "", 0)), "next"))
                listPages["next"] = ApiResult.Success(RecordPageDto(listOf(RecordDto("2", 1, "2026-10-19T09:00:00Z", RecordPayloadDto(textDescription = "二"), "", "", 0)), null))
            }
            val model = RecordsViewModel(gateway)
            model.load(WorkspaceRecordType.DIET)
            advanceUntilIdle()
            model.loadMore()
            advanceUntilIdle()
            assertEquals(2, (model.uiState.value.loadState as RecordsLoadState.Loaded).records.size)
            model.clearForLogout()
            assertEquals(RecordsLoadState.Idle, model.uiState.value.loadState)
            assertEquals(RecordDetailLoadState.Idle, model.uiState.value.detailState)
        } finally { Dispatchers.resetMain() }
    }

    private class FakeGateway : RecordsGateway {
        var listResult: ApiResult<RecordPageDto> = ApiResult.Success(RecordPageDto(emptyList(), null))
        val listPages = mutableMapOf<String?, ApiResult<RecordPageDto>>()
        var deleteResult: ApiResult<Unit> = ApiResult.Success(Unit)
        var updateResult: ApiResult<RecordDetailModel> = ApiResult.Failure(409, "RECORD_VERSION_CONFLICT")
        var detailResult: ApiResult<RecordDetailModel> = ApiResult.Failure(404, "NOT_FOUND")
        var lastRecordWrite: RecordWriteDto? = null
        var lastPatch: RecordPatchDto? = null
        var lastMoodPatch: MoodPatchDto? = null
        var idempotencyKey: String? = null
        override suspend fun list(type: WorkspaceRecordType, cursor: String?) = listPages[cursor] ?: listResult
        override suspend fun detail(type: WorkspaceRecordType, id: String) = detailResult
        override suspend fun create(type: WorkspaceRecordType, idempotencyKey: String, body: RecordWriteDto): ApiResult<RecordDetailModel> {
            this.idempotencyKey = idempotencyKey
            lastRecordWrite = body
            return ApiResult.Success(RecordDetailModel("record-1", 1, body.occurredAt, body.payload))
        }
        override suspend fun update(type: WorkspaceRecordType, id: String, body: RecordPatchDto): ApiResult<RecordDetailModel> { lastPatch = body; return updateResult }
        override suspend fun delete(type: WorkspaceRecordType, id: String, version: Int) = deleteResult
        override suspend fun symptomStatusHistory(id: String) = ApiResult.Success(SymptomStatusHistoryDto(id, "ongoing", emptyList()))
        override suspend fun listMood(cursor: String?) = ApiResult.Success(MoodPageDto(emptyList(), null))
        override suspend fun detailMood(id: String) = ApiResult.Failure(404, "NOT_FOUND")
        override suspend fun createMood(idempotencyKey: String, body: MoodWriteDto) = ApiResult.Success(MoodDetailDto("mood-1", body.occurredAt, body.moodLevel, body.emotionTags, 1, body.occurredAt, body.occurredAt, body.note))
        override suspend fun updateMood(id: String, body: MoodPatchDto): ApiResult<MoodDetailDto> {
            lastMoodPatch = body
            return ApiResult.Failure(409, "RECORD_VERSION_CONFLICT")
        }
        override suspend fun deleteMood(id: String, version: Int) = deleteResult
    }
}

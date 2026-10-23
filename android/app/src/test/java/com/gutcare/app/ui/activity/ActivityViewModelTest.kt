package com.gutcare.app.ui.activity

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ActivityPageDto
import com.gutcare.app.core.network.ActivityPatchDto
import com.gutcare.app.core.network.ActivityRecordDto
import com.gutcare.app.core.network.ActivityWriteDto
import com.gutcare.app.core.network.ApiResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
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
class ActivityViewModelTest {
    @get:Rule val instantTaskExecutorRule = InstantTaskExecutorRule()

    @Test fun loadDistinguishesEmptyAndUnauthorized() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeActivityGateway().apply { listResult = ApiResult.Success(ActivityPageDto(emptyList(), null)) }
            val model = ActivityViewModel(gateway)
            model.load(); advanceUntilIdle()
            assertTrue(model.uiState.value.items.isEmpty())
            assertFalse(model.uiState.value.loading)
            gateway.listResult = ApiResult.Failure(401, "UNAUTHORIZED")
            model.load(); advanceUntilIdle()
            assertTrue(model.uiState.value.sessionExpired)
            assertTrue(model.uiState.value.error.orEmpty().contains("登录"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun cursorFailureKeepsFirstPageAndRetryCursor() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeActivityGateway().apply { listResult = ApiResult.Success(ActivityPageDto(listOf(record), "opaque")) }
            val model = ActivityViewModel(gateway)
            model.load(); advanceUntilIdle()
            gateway.nextPageResult = ApiResult.Failure(null, "NETWORK_ERROR")
            model.loadMore(); advanceUntilIdle()
            assertEquals(listOf(record.id), model.uiState.value.items.map { it.id })
            assertEquals("opaque", model.uiState.value.nextCursor)
            assertTrue(model.uiState.value.error.orEmpty().contains("网络"))
        } finally { Dispatchers.resetMain() }
    }

    @Test fun invalidDraftDoesNotSubmitAndCreateSendsTimezoneAndNoExtraFields() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeActivityGateway()
            val model = ActivityViewModel(gateway)
            model.beginCreate()
            model.updateDraft(ActivityDraft(activityType = "other", occurredAt = "2026-10-20T18:30:00"))
            model.save(); advanceUntilIdle()
            assertEquals(0, gateway.createCalls)
            model.updateDraft(ActivityDraft(activityType = "other", description = "瑜伽", occurredAt = "2026-10-20T18:30:00+08:00"))
            model.save(); advanceUntilIdle()
            assertEquals(1, gateway.createCalls)
            assertEquals("瑜伽", gateway.created?.description)
            assertEquals("2026-10-20T18:30:00+08:00", gateway.created?.occurredAt)
            assertFalse(model.uiState.value.formOpen)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun conflictRetainsDraftUntilExplicitResolutionAndSaveIsNeverAutomatic() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeActivityGateway()
            val model = ActivityViewModel(gateway)
            model.beginEdit(record)
            model.updateDraft(model.uiState.value.draft.copy(duration = "45"))
            gateway.updateResult = ApiResult.Failure(409, "RECORD_VERSION_CONFLICT")
            model.save(); advanceUntilIdle()
            assertEquals("45", model.uiState.value.draft.duration)
            assertEquals(2, model.uiState.value.conflictLatest?.recordVersion)
            model.keepDraftWithLatestVersion()
            assertEquals("45", model.uiState.value.draft.duration)
            assertEquals(2, model.uiState.value.editingVersion)
            assertEquals(1, gateway.updateCalls)
            assertTrue(model.uiState.value.formOpen)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun successfulDeleteImmediatelyRemovesRecordButConflictRefreshesIt() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeActivityGateway().apply { listResult = ApiResult.Success(ActivityPageDto(listOf(record), null)) }
            val model = ActivityViewModel(gateway)
            model.load(); advanceUntilIdle()
            gateway.deleteResult = ApiResult.Success(Unit)
            model.delete(record); advanceUntilIdle()
            assertTrue(model.uiState.value.items.isEmpty())
            assertEquals(1, gateway.deletedVersion)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun detailLoadsFreshRecordAndCanBeClosed() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val fresh = record.copy(recordVersion = 3, durationMinutes = 55)
            val gateway = FakeActivityGateway().apply { detailResult = ApiResult.Success(fresh) }
            val model = ActivityViewModel(gateway)
            model.openDetail("a-1"); advanceUntilIdle()
            assertEquals("a-1", gateway.lastDetailId)
            assertEquals(fresh, model.uiState.value.detail)
            assertFalse(model.uiState.value.detailLoading)
            model.closeDetail()
            assertEquals(null, model.uiState.value.detailRequestedId)
            assertEquals(null, model.uiState.value.detail)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun detailFailureIsRetryableAndUnauthorizedExpiresSession() = runTest {
        Dispatchers.setMain(Dispatchers.Unconfined)
        try {
            val gateway = FakeActivityGateway().apply { detailResult = ApiResult.Failure(503, "UNAVAILABLE") }
            val model = ActivityViewModel(gateway)
            model.openDetail("a-1"); advanceUntilIdle()
            assertEquals("a-1", model.uiState.value.detailRequestedId)
            assertFalse(model.uiState.value.detailLoading)
            assertTrue(model.uiState.value.detailError != null)
            gateway.detailResult = ApiResult.Failure(401, "UNAUTHORIZED")
            model.retryDetail(); advanceUntilIdle()
            assertTrue(model.uiState.value.sessionExpired)
            assertTrue(model.uiState.value.detailError.orEmpty().contains("登录"))
        } finally { Dispatchers.resetMain() }
    }
}

private val record = ActivityRecordDto("a-1", 1, "walking", null, "moderate", "same", 30, "2026-10-20T18:30:00+08:00", "2026-10-20T10:30:00Z", "2026-10-20T10:30:00Z")

private class FakeActivityGateway : ActivityFeatureGateway {
    var listResult: ApiResult<ActivityPageDto> = ApiResult.Success(ActivityPageDto(emptyList(), null))
    var nextPageResult: ApiResult<ActivityPageDto> = ApiResult.Success(ActivityPageDto(emptyList(), null))
    var createResult: ApiResult<ActivityRecordDto> = ApiResult.Success(record)
    var updateResult: ApiResult<ActivityRecordDto> = ApiResult.Success(record)
    var deleteResult: ApiResult<Unit> = ApiResult.Success(Unit)
    var detailResult: ApiResult<ActivityRecordDto> = ApiResult.Success(record.copy(recordVersion = 2, durationMinutes = 40))
    var created: ActivityWriteDto? = null
    var createCalls = 0
    var updateCalls = 0
    var deletedVersion = 0
    var lastDetailId: String? = null
    override suspend fun list(cursor: String?, limit: Int) = if (cursor == null) listResult else nextPageResult
    override suspend fun create(body: ActivityWriteDto): ApiResult<ActivityRecordDto> { created = body; createCalls++; return createResult }
    override suspend fun detail(id: String): ApiResult<ActivityRecordDto> { lastDetailId = id; return detailResult }
    override suspend fun update(id: String, body: ActivityPatchDto): ApiResult<ActivityRecordDto> { updateCalls++; return updateResult }
    override suspend fun delete(id: String, version: Int): ApiResult<Unit> { deletedVersion = version; return deleteResult }
}

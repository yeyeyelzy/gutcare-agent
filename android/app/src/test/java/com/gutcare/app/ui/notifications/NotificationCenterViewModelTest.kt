package com.gutcare.app.ui.notifications

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.gutcare.app.core.network.ApiResult
import com.gutcare.app.core.network.NotificationApi
import com.gutcare.app.core.network.NotificationPageDto
import com.gutcare.app.core.network.NotificationPreferenceDto
import com.gutcare.app.core.network.NotificationReadBatchRequestDto
import com.gutcare.app.core.network.NotificationReadBatchResponseDto
import com.gutcare.app.core.network.NotificationRepository
import com.gutcare.app.core.network.NotificationTargetDto
import com.gutcare.app.core.network.NotificationUnreadCountDto
import com.gutcare.app.core.network.PatientNotificationDto
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
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import retrofit2.Response

@OptIn(ExperimentalCoroutinesApi::class)
class NotificationCenterViewModelTest {
    @get:Rule val instantTaskExecutorRule = InstantTaskExecutorRule()

    @Test fun changingDetailImmediatelyClearsPreviousNotificationAndRejectsMismatchedResponse() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val api = FakeNotificationApi().apply { detailResponses[firstId] = Response.success(notification(firstId)) }
            val model = NotificationCenterViewModel(NotificationRepository(api))
            model.openDetail(firstId)
            advanceUntilIdle()
            assertEquals(firstId, model.state.value.detail?.id)

            val delayed = CompletableDeferred<Response<PatientNotificationDto>>()
            api.delayedDetail = delayed
            model.openDetail(secondId)
            runCurrent()
            assertNull(model.state.value.detail)
            delayed.complete(Response.success(notification(firstId)))
            advanceUntilIdle()

            assertNull(model.state.value.detail)
            assertTrue(model.state.value.error)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun logoutInvalidatesPendingListAndClearsNotificationState() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val api = FakeNotificationApi()
            val deferred = CompletableDeferred<Response<NotificationPageDto>>()
            api.delayedList = deferred
            val model = NotificationCenterViewModel(NotificationRepository(api))
            model.load()
            runCurrent()
            model.clearForLogout()
            deferred.complete(Response.success(NotificationPageDto(listOf(notification(firstId)), null)))
            advanceUntilIdle()

            assertTrue(model.state.value.items.isEmpty())
            assertNull(model.state.value.unreadCount)
            assertNull(model.state.value.detail)
            assertNull(model.state.value.preferences)
        } finally { Dispatchers.resetMain() }
    }

    @Test fun cursorPaginationAndBatchReadUseReturnedServerState() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val api = FakeNotificationApi().apply {
                pages += Response.success(NotificationPageDto(listOf(notification(firstId)), "opaque-cursor"))
                pages += Response.success(NotificationPageDto(listOf(notification(secondId)), null))
                unread = Response.success(NotificationUnreadCountDto(1))
                batch = Response.success(NotificationReadBatchResponseDto(listOf(notification(firstId).copy(readAt = "2026-10-20T10:00:00Z"))))
            }
            val model = NotificationCenterViewModel(NotificationRepository(api))
            model.load(); advanceUntilIdle()
            model.load(reset = false); advanceUntilIdle()
            assertEquals(listOf(firstId, secondId), model.state.value.items.map { it.id })
            assertEquals("opaque-cursor", api.requestedCursors[1])
            model.toggleSelection(firstId)
            model.markSelectedRead(); advanceUntilIdle()
            assertEquals("2026-10-20T10:00:00Z", model.state.value.items.first().readAt)
            assertTrue(model.state.value.selectedIds.isEmpty())
        } finally { Dispatchers.resetMain() }
    }

    @Test fun invalidQuietHoursAreRejectedBeforeNetworkWrite() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        try {
            val api = FakeNotificationApi()
            val model = NotificationCenterViewModel(NotificationRepository(api))
            model.editPreferences(start = "22:00", end = "")
            model.savePreferences(); advanceUntilIdle()
            assertTrue(model.state.value.error)
            assertEquals(0, api.preferenceWrites)
        } finally { Dispatchers.resetMain() }
    }
}

private const val firstId = "00000000-0000-4000-8000-000000000001"
private const val secondId = "00000000-0000-4000-8000-000000000002"

private fun notification(id: String) = PatientNotificationDto(
    id = id, eventType = "risk_alert_created", category = "risk", priority = "risk",
    occurredAt = "2026-10-20T09:00:00Z", createdAt = "2026-10-20T09:00:00Z", readAt = null,
    target = NotificationTargetDto("risk_alert", id), targetUnavailable = false,
)

private class FakeNotificationApi : NotificationApi {
    val pages = ArrayDeque<Response<NotificationPageDto>>()
    val requestedCursors = mutableListOf<String?>()
    val detailResponses = mutableMapOf<String, Response<PatientNotificationDto>>()
    var delayedList: CompletableDeferred<Response<NotificationPageDto>>? = null
    var delayedDetail: CompletableDeferred<Response<PatientNotificationDto>>? = null
    var unread: Response<NotificationUnreadCountDto> = Response.success(NotificationUnreadCountDto(0))
    var batch: Response<NotificationReadBatchResponseDto> = Response.success(NotificationReadBatchResponseDto(emptyList()))
    var preferencesValue = NotificationPreferenceDto(true, null, null, "Asia/Shanghai")
    var preferenceWrites = 0

    override suspend fun list(cursor: String?, limit: Int, category: String?, unreadOnly: Boolean): Response<NotificationPageDto> {
        requestedCursors += cursor
        return delayedList?.await() ?: pages.removeFirstOrNull() ?: Response.success(NotificationPageDto(emptyList(), null))
    }
    override suspend fun unreadCount() = unread
    override suspend fun detail(id: String) = delayedDetail?.await() ?: detailResponses[id] ?: Response.error(404, okhttp3.ResponseBody.create(null, "{}"))
    override suspend fun markRead(id: String) = Response.success(notification(id).copy(readAt = "2026-10-20T10:00:00Z"))
    override suspend fun markReadBatch(body: NotificationReadBatchRequestDto) = batch
    override suspend fun preferences() = Response.success(preferencesValue)
    override suspend fun updatePreferences(body: NotificationPreferenceDto): Response<NotificationPreferenceDto> {
        preferenceWrites++
        preferencesValue = body
        return Response.success(body)
    }
}

package com.gutcare.app.ui.notifications

import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import com.gutcare.app.core.network.NotificationApi
import com.gutcare.app.core.network.NotificationPageDto
import com.gutcare.app.core.network.NotificationPreferenceDto
import com.gutcare.app.core.network.NotificationReadBatchRequestDto
import com.gutcare.app.core.network.NotificationReadBatchResponseDto
import com.gutcare.app.core.network.NotificationRepository
import com.gutcare.app.core.network.NotificationUnreadCountDto
import com.gutcare.app.core.network.PatientNotificationDto
import org.junit.Rule
import org.junit.Test
import retrofit2.Response

class NotificationScreensTest {
    @get:Rule val composeRule = createComposeRule()

    @Test fun emptyCenterShowsUnreadStateFiltersAndEmptyCopy() {
        val model = NotificationCenterViewModel(NotificationRepository(ScreenNotificationApi))
        composeRule.setContent {
            MaterialTheme {
                NotificationCenterScreen(
                    state = NotificationCenterState(unreadCount = 0), model = model,
                    onBack = {}, onPreferences = {}, onOpenDetail = {}, onOpenTarget = {},
                )
            }
        }
        composeRule.onAllNodesWithTag("notification_center").assertCountEquals(1)
        composeRule.onAllNodesWithTag("notifications_empty").assertCountEquals(1)
        composeRule.onAllNodesWithTag("notifications_filter_risk").assertCountEquals(1)
        composeRule.onAllNodesWithTag("notifications_unread_count").assertCountEquals(1)
    }

    @Test fun unavailableTargetNeverRendersOpenAction() {
        val model = NotificationCenterViewModel(NotificationRepository(ScreenNotificationApi))
        val item = PatientNotificationDto(
            id = "00000000-0000-4000-8000-000000000001", eventType = "risk_alert_created", category = "risk", priority = "risk",
            occurredAt = "2026-10-20T09:00:00Z", createdAt = "2026-10-20T09:00:00Z", readAt = null,
            target = null, targetUnavailable = true,
        )
        composeRule.setContent {
            MaterialTheme {
                NotificationDetailScreen(
                    state = NotificationCenterState(detail = item), model = model,
                    onBack = {}, onOpenTarget = {},
                )
            }
        }
        composeRule.onAllNodesWithText("关联内容已不可用。").assertCountEquals(1)
        composeRule.onAllNodesWithTag("notification_open_target").assertCountEquals(0)
    }
}

private object ScreenNotificationApi : NotificationApi {
    override suspend fun list(cursor: String?, limit: Int, category: String?, unreadOnly: Boolean) = Response.success(NotificationPageDto(emptyList(), null))
    override suspend fun unreadCount() = Response.success(NotificationUnreadCountDto(0))
    override suspend fun detail(id: String): Response<PatientNotificationDto> = Response.error(404, okhttp3.ResponseBody.create(null, "{}"))
    override suspend fun markRead(id: String) = Response.error<PatientNotificationDto>(404, okhttp3.ResponseBody.create(null, "{}"))
    override suspend fun markReadBatch(body: NotificationReadBatchRequestDto) = Response.success(NotificationReadBatchResponseDto(emptyList()))
    override suspend fun preferences() = Response.success(NotificationPreferenceDto(true, null, null, "UTC"))
    override suspend fun updatePreferences(body: NotificationPreferenceDto) = Response.success(body)
}

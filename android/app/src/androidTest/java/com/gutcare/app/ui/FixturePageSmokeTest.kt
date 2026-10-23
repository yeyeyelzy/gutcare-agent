package com.gutcare.app.ui

import android.graphics.Bitmap
import android.content.ContentValues
import android.provider.MediaStore
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.platform.app.InstrumentationRegistry
import com.gutcare.app.core.network.ActivityRecordDto
import com.gutcare.app.core.network.NotificationApi
import com.gutcare.app.core.network.NotificationPageDto
import com.gutcare.app.core.network.NotificationPreferenceDto
import com.gutcare.app.core.network.NotificationReadBatchRequestDto
import com.gutcare.app.core.network.NotificationReadBatchResponseDto
import com.gutcare.app.core.network.NotificationRepository
import com.gutcare.app.core.network.NotificationUnreadCountDto
import com.gutcare.app.core.network.PatientNotificationDto
import com.gutcare.app.ui.activity.ActivityScreen
import com.gutcare.app.ui.activity.ActivityUiState
import com.gutcare.app.ui.notifications.NotificationCenterScreen
import com.gutcare.app.ui.notifications.NotificationCenterState
import com.gutcare.app.ui.notifications.NotificationCenterViewModel
import com.gutcare.app.ui.records.TodayCallbacks
import com.gutcare.app.ui.records.TodayScreen
import com.gutcare.app.ui.records.TodayUiState
import com.gutcare.app.ui.theme.GutCareTheme
import okhttp3.ResponseBody
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4
import retrofit2.Response

/** Synthetic, non-network page fixtures. Screenshots contain no patient data. */
@RunWith(AndroidJUnit4::class)
class FixturePageSmokeTest {
    @get:Rule val compose = createComposeRule()

    @Test fun todayFixtureRendersAndCaptures() {
        compose.setContent {
            GutCareTheme { TodayScreen(TodayUiState(dateLabel = "演示日期", displayName = "演示用户"), TodayCallbacks()) }
        }
        compose.waitForIdle()
        compose.onNodeWithTag("today_notifications").assertIsDisplayed()
        saveScreenshot("today.png")
    }

    @Test fun notificationFixtureRendersAndCaptures() {
        val model = NotificationCenterViewModel(NotificationRepository(FixtureNotificationApi))
        compose.setContent {
            GutCareTheme {
                NotificationCenterScreen(
                    state = NotificationCenterState(unreadCount = 1), model = model,
                    onBack = {}, onPreferences = {}, onOpenDetail = {}, onOpenTarget = {},
                )
            }
        }
        compose.waitForIdle()
        compose.onNodeWithTag("notification_center").assertIsDisplayed()
        compose.onNodeWithTag("notifications_unread_count").assertIsDisplayed()
        saveScreenshot("f12-notifications.png")
    }

    @Test fun activityFixtureRendersAndCaptures() {
        val record = ActivityRecordDto(
            "fixture-activity", 1, "walking", null, "moderate", "same", 25,
            "2026-10-20T18:30:00+08:00", "2026-10-20T10:30:00Z", "2026-10-20T10:30:00Z",
        )
        compose.setContent {
            GutCareTheme {
                ActivityScreen(
                    state = ActivityUiState(items = listOf(record)), onBack = {}, onRefresh = {}, onLoadMore = {},
                    onCreate = {}, onEdit = {}, onCloseForm = {}, onDraft = {}, onSave = {}, onDelete = {},
                    onKeepDraft = {}, onDiscardDraft = {}, onOpenDetail = {}, onRetryDetail = {}, onCloseDetail = {},
                )
            }
        }
        compose.waitForIdle()
        compose.onNodeWithTag("activity_back").assertIsDisplayed()
        compose.onAllNodesWithTag("activity_new").assertCountEquals(1)
        saveScreenshot("f07-activity.png")
    }

    private fun saveScreenshot(name: String) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val bitmap = instrumentation.uiAutomation.takeScreenshot()
        val context = instrumentation.targetContext
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/GutCareSmoke")
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val imageUri = context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
            ?: error("Could not create synthetic screenshot media row: $name")
        context.contentResolver.openOutputStream(imageUri, "w").use { output ->
            checkNotNull(output) { "Could not open synthetic screenshot output: $name" }
            check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)) { "Could not encode screenshot" }
        }
        val published = ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }
        check(context.contentResolver.update(imageUri, published, null, null) == 1) {
            "Could not publish synthetic screenshot: $name"
        }
        bitmap.recycle()
    }
}

private object FixtureNotificationApi : NotificationApi {
    override suspend fun list(cursor: String?, limit: Int, category: String?, unreadOnly: Boolean) =
        Response.success(NotificationPageDto(emptyList(), null))
    override suspend fun unreadCount() = Response.success(NotificationUnreadCountDto(1))
    override suspend fun detail(id: String): Response<PatientNotificationDto> = Response.error(404, ResponseBody.create(null, "{}"))
    override suspend fun markRead(id: String): Response<PatientNotificationDto> = Response.error(404, ResponseBody.create(null, "{}"))
    override suspend fun markReadBatch(body: NotificationReadBatchRequestDto) = Response.success(NotificationReadBatchResponseDto(emptyList()))
    override suspend fun preferences() = Response.success(NotificationPreferenceDto(true, null, null, "Asia/Shanghai"))
    override suspend fun updatePreferences(body: NotificationPreferenceDto) = Response.success(body)
}

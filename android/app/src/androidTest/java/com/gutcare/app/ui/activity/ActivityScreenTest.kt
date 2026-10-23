package com.gutcare.app.ui.activity

import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.gutcare.app.core.network.ActivityRecordDto
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class ActivityScreenTest {
    @get:Rule val composeRule = createComposeRule()

    @Test fun emptyStateAndNewRecordActionAreVisible() {
        composeRule.setContent {
            MaterialTheme { ActivityScreen(state = ActivityUiState(), onBack = {}, onRefresh = {}, onLoadMore = {}, onCreate = {}, onEdit = {}, onCloseForm = {}, onDraft = {}, onSave = {}, onDelete = {}, onKeepDraft = {}, onDiscardDraft = {}, onOpenDetail = {}, onRetryDetail = {}, onCloseDetail = {}) }
        }
        composeRule.onAllNodesWithTag("activity_empty").assertCountEquals(1)
        composeRule.onAllNodesWithTag("activity_new").assertCountEquals(1)
        composeRule.onAllNodesWithTag("activity_save").assertCountEquals(1)
    }

    @Test fun remoteActivityIsRenderedWithEditAndDeleteActions() {
        val record = ActivityRecordDto("record-1", 1, "walking", null, "moderate", "same", 30, "2026-10-20T18:30:00+08:00", "2026-10-20T10:30:00Z", "2026-10-20T10:30:00Z")
        var openedId: String? = null
        composeRule.setContent {
            MaterialTheme { ActivityScreen(state = ActivityUiState(items = listOf(record)), onBack = {}, onRefresh = {}, onLoadMore = {}, onCreate = {}, onEdit = {}, onCloseForm = {}, onDraft = {}, onSave = {}, onDelete = {}, onKeepDraft = {}, onDiscardDraft = {}, onOpenDetail = { openedId = it }, onRetryDetail = {}, onCloseDetail = {}) }
        }
        // The activity editor precedes the history list in the scrollable page. Bring the
        // off-screen action into view before injecting a tap, as a user would by scrolling.
        composeRule.onNodeWithTag("activity_detail_record-1").performScrollTo().performClick()
        assertEquals("record-1", openedId)
        composeRule.onAllNodesWithTag("activity_edit_record-1").assertCountEquals(1)
        composeRule.onAllNodesWithTag("activity_delete_record-1").assertCountEquals(1)
    }

    @Test fun serviceErrorIsNotPresentedAsEmpty() {
        composeRule.setContent {
            MaterialTheme { ActivityScreen(state = ActivityUiState(error = "网络暂不可用"), onBack = {}, onRefresh = {}, onLoadMore = {}, onCreate = {}, onEdit = {}, onCloseForm = {}, onDraft = {}, onSave = {}, onDelete = {}, onKeepDraft = {}, onDiscardDraft = {}, onOpenDetail = {}, onRetryDetail = {}, onCloseDetail = {}) }
        }
        composeRule.onAllNodesWithTag("activity_list_error").assertCountEquals(1)
        composeRule.onAllNodesWithTag("activity_empty").assertCountEquals(0)
    }

    @Test fun detailShowsFreshRecordAndActions() {
        val record = ActivityRecordDto("record-1", 4, "cycling", null, "high", "better", 48, "2026-10-20T18:30:00+08:00", "2026-10-20T10:30:00Z", "2026-10-20T10:30:00Z")
        var closed = false
        composeRule.setContent {
            MaterialTheme {
                ActivityScreen(state = ActivityUiState(detailRequestedId = record.id, detail = record), onBack = {}, onRefresh = {}, onLoadMore = {}, onCreate = {}, onEdit = {}, onCloseForm = {}, onDraft = {}, onSave = {}, onDelete = {}, onKeepDraft = {}, onDiscardDraft = {}, onOpenDetail = {}, onRetryDetail = {}, onCloseDetail = { closed = true })
            }
        }
        composeRule.onAllNodesWithTag("activity_detail_loaded").assertCountEquals(1)
        composeRule.onAllNodesWithTag("activity_detail_edit").assertCountEquals(1)
        composeRule.onAllNodesWithTag("activity_detail_delete").assertCountEquals(1)
        composeRule.onNodeWithTag("activity_detail_back").performClick()
        assertEquals(true, closed)
    }

    @Test fun detailErrorIsDistinctFromEmptyAndOffersRetry() {
        var retried = false
        composeRule.setContent {
            MaterialTheme {
                ActivityScreen(state = ActivityUiState(detailRequestedId = "record-1", detailError = "网络暂不可用"), onBack = {}, onRefresh = {}, onLoadMore = {}, onCreate = {}, onEdit = {}, onCloseForm = {}, onDraft = {}, onSave = {}, onDelete = {}, onKeepDraft = {}, onDiscardDraft = {}, onOpenDetail = {}, onRetryDetail = { retried = true }, onCloseDetail = {})
            }
        }
        composeRule.onNodeWithTag("activity_detail_error").assertTextContains("网络暂不可用")
        composeRule.onNodeWithTag("activity_detail_retry").performClick()
        assertEquals(true, retried)
        composeRule.onAllNodesWithTag("activity_empty").assertCountEquals(0)
    }
}

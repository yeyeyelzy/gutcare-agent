package com.gutcare.app.ui.records

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.gutcare.app.core.network.MedicalDocumentDto
import com.gutcare.app.core.network.MedicalFieldCandidateDto
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4

@RunWith(AndroidJUnit4::class)
class MedicalArchiveScreensTest {
    @get:Rule val composeRule = createComposeRule()

    @Test fun archiveRefreshAndReportNavigationAreConnected() {
        var refreshed = false
        var opened = false
        val report = report()
        composeRule.setContent {
            GutCareTheme {
                MedicalArchiveScreen(
                    state = MedicalArchiveUiState(documents = listOf(report)),
                    onBack = {}, onRetry = { refreshed = true }, onOpen = { opened = it.id == report.id }, onUpload = {},
                )
            }
        }
        composeRule.onNodeWithTag("medical_archive_refresh").performClick()
        composeRule.onNodeWithTag("medical_archive_document_0").performClick()
        composeRule.runOnIdle { check(refreshed && opened) }
    }

    @Test fun candidateExcerptIsHiddenUntilExpandedAndTruncatedAtDisplayLimit() {
        var decision: String? = null
        val longExcerpt = "CRP: " + "x".repeat(260)
        val candidate = MedicalFieldCandidateDto(
            id = "candidate", fieldCode = "test_result", valueType = "object",
            value = mapOf("result" to "4.2"), unit = "mg/L", confidence = 0.91,
            excerpt = longExcerpt, reviewStatus = "pending", recordVersion = 1,
        )
        composeRule.setContent {
            GutCareTheme {
                MedicalDocumentDetailScreen(
                    state = MedicalArchiveUiState(detail = report().copy(parseStatus = "needs_confirmation"), candidates = listOf(candidate)),
                    onBack = {}, onRetry = {}, onDecision = { _, action, _ -> decision = action },
                )
            }
        }
        composeRule.onNodeWithTag("medical_candidate_0").assertIsDisplayed()
        composeRule.onAllNodesWithTag("medical_candidate_excerpt_0").assertCountEquals(0)
        composeRule.onNodeWithTag("medical_candidate_excerpt_toggle_0").performScrollTo().performClick()
        composeRule.onNodeWithTag("medical_candidate_excerpt_0").performScrollTo().assertTextEquals(
            "报告原文：${longExcerpt.take(160)}…",
        )
        composeRule.onNodeWithTag("medical_candidate_correct_value_0").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithTag("medical_candidate_accept_0").performScrollTo().performClick()
        composeRule.runOnIdle { check(decision == "accept") }
    }

    @Test fun initialArchiveLoadingAndNetworkErrorHaveExplicitRetryState() {
        var retried = false
        composeRule.setContent {
            GutCareTheme {
                MedicalArchiveScreen(
                    state = MedicalArchiveUiState(error = "网络不可用"),
                    onBack = {}, onRetry = { retried = true }, onOpen = {}, onUpload = {},
                )
            }
        }
        composeRule.onNodeWithTag("medical_archive_error").assertIsDisplayed()
        composeRule.onNodeWithTag("medical_archive_retry").performClick()
        composeRule.runOnIdle { check(retried) }
    }
}

private fun report() = MedicalDocumentDto(
    id = "document", fileObjectId = "file", documentType = "lab_report", documentDate = "2026-10-20",
    processingMode = "analyze", parseStatus = "needs_confirmation", recordVersion = 1,
    createdAt = "", updatedAt = "", fileStatus = "available", originalName = "report.pdf",
)

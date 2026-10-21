package com.gutcare.app.ui.features

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class FeatureDirectoryScreenTest {
    @get:Rule val composeRule = createComposeRule()

    @Test fun directoryExposesP1EntriesAndDispatchesSelection() {
        var selected = ""
        composeRule.setContent {
            GutCareTheme {
                FeatureDirectoryScreen(
                    onBack = {}, onMedication = { selected = "medication" },
                    onRisks = { selected = "risks" }, onTrends = { selected = "trends" },
                    onHistory = { selected = "history" }, onPrivacy = { selected = "privacy" },
                    onNotifications = {}, onActivity = {},
                )
            }
        }
        composeRule.onNodeWithTag("features_medication").assertIsDisplayed().performClick()
        composeRule.runOnIdle { assertEquals("medication", selected) }
        composeRule.onNodeWithTag("features_risks").assertIsDisplayed()
        composeRule.onNodeWithTag("features_trends").assertIsDisplayed()
        composeRule.onNodeWithTag("features_history").assertIsDisplayed()
        composeRule.onNodeWithTag("features_privacy").assertIsDisplayed()
    }
}

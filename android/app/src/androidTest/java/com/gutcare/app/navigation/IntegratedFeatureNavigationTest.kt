package com.gutcare.app.navigation

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.navigation.compose.rememberNavController
import com.gutcare.app.core.network.PatientProfileDto
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test

class IntegratedFeatureNavigationTest {
    @get:Rule val composeRule = createComposeRule()

    @Test fun myTabReachesFeatureDirectoryAndProtectedFeatureRoute() {
        composeRule.setContent {
            GutCareTheme {
                GutCareNavHost(
                    navController = rememberNavController(),
                    sessionState = AppSessionState.Authenticated,
                    patientProfile = PatientProfileDto("patient-1", "演示用户", 1998, "Asia/Shanghai", 1),
                )
            }
        }

        composeRule.onNodeWithTag("tab_me").performClick()
        composeRule.onNodeWithTag("profile_open_features").assertIsDisplayed().performClick()
        composeRule.onNodeWithTag("feature_directory").assertIsDisplayed()
        composeRule.onNodeWithTag("features_medication").performClick()
        composeRule.onNodeWithTag("feature_unavailable").assertIsDisplayed()
    }
}

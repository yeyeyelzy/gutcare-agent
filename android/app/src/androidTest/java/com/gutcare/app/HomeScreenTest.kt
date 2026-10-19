package com.gutcare.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.gutcare.app.ui.home.HomeScreen
import com.gutcare.app.ui.home.HomeUiState
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class HomeScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun displaysNativeHomePlaceholder() {
        composeRule.setContent {
            GutCareTheme { HomeScreen(uiState = HomeUiState()) }
        }

        composeRule.onNodeWithText("GutCare").assertIsDisplayed()
        composeRule.onNodeWithText("原生 Android 工程已就绪").assertIsDisplayed()
    }
}

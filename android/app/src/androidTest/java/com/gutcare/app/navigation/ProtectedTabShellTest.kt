package com.gutcare.app.navigation

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.gutcare.app.ui.tabs.ProtectedTabShell
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test

class ProtectedTabShellTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun selectingTabChangesOnlyTheProtectedRoot() {
        composeRule.setContent {
            var selected by remember { mutableStateOf(RootTab.Today) }
            GutCareTheme {
                ProtectedTabShell(
                    selectedTab = selected,
                    onSelectTab = { selected = it },
                )
            }
        }

        composeRule.onNodeWithTag("protected_tab_content_title")
            .assertIsDisplayed()
            .assertTextEquals("今日")
        composeRule.onNodeWithContentDescription("切换到记录").performClick()
        composeRule.onNodeWithTag("protected_tab_content_title").assertTextEquals("记录")
    }
}


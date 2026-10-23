package com.gutcare.app.ui.risktrend

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performScrollTo
import com.gutcare.app.core.network.RiskAlertDto
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4

@RunWith(AndroidJUnit4::class)
class RiskAlertEnvironmentScreenTest {
    @get:Rule val compose = createComposeRule()

    @Test fun testOnlyRuleIsProminentlyDisclosed() {
        compose.setContent {
            GutCareTheme {
                RiskAlertListScreen(
                    state = RiskTrendUiState(risks = RiskListState.Ready(listOf(alert("test_only")))),
                    onLoad = {}, onLoadMore = {}, onOpen = {},
                )
            }
        }
        compose.onNodeWithTag("risk_environment_disclosure", useUnmergedTree = true).assertIsDisplayed()
        compose.onNodeWithText("演示测试规则（非临床）").performScrollTo().assertIsDisplayed()
    }

    @Test fun productionHasNoTestOnlyWarning() {
        compose.setContent {
            GutCareTheme {
                RiskAlertListScreen(
                    state = RiskTrendUiState(risks = RiskListState.Ready(listOf(alert("production")))),
                    onLoad = {}, onLoadMore = {}, onOpen = {},
                )
            }
        }
        compose.onAllNodesWithTag("risk_environment_disclosure").assertCountEquals(0)
    }

    @Test fun unknownEnvironmentIsExplicitlyUntrusted() {
        compose.setContent {
            GutCareTheme {
                RiskAlertListScreen(
                    state = RiskTrendUiState(risks = RiskListState.Ready(listOf(alert("unexpected")))),
                    onLoad = {}, onLoadMore = {}, onOpen = {},
                )
            }
        }
        compose.onNodeWithText("规则环境未知，请勿据此判断健康风险").performScrollTo().assertIsDisplayed()
    }

    private fun alert(environment: String) = RiskAlertDto(
        id = "risk-1", environment = environment, severity = "attention", message = "提醒内容",
        recommendedAction = "建议行动", status = "unread", triggeredAt = "2026-10-20T10:00:00+08:00",
    )
}

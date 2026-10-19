package com.gutcare.app.ui.auth

import android.content.Context
import android.view.inputmethod.InputMethodManager
import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.navigation.compose.rememberNavController
import com.gutcare.app.navigation.GutCareNavHost
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test
import org.junit.Assert.assertEquals

class AuthScreensTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun registrationUsesEmailAndNeverShowsPhoneOrSmsCopy() {
        composeRule.setContent {
            var draft by remember { mutableStateOf(RegistrationDraft()) }
            GutCareTheme {
                RegisterCredentialsScreen(
                    draft = draft,
                    operation = AuthOperationState.Idle,
                    onDraftChange = { draft = it },
                    onContinue = {},
                    onBack = {},
                    onLogin = {},
                )
            }
        }

        composeRule.onNodeWithContentDescription(AuthCopy.emailLabel).assertIsDisplayed()
        composeRule.onAllNodesWithText("手机号").assertCountEquals(0)
        composeRule.onAllNodesWithText("短信").assertCountEquals(0)
        composeRule.onNodeWithTag("register_continue").assertIsNotEnabled()
    }

    @Test
    fun consentGateKeepsBirthYearOutOfCompositionUntilHealthConsent() {
        val draft = RegistrationDraft(
            email = "person@example.test",
            password = "a-secure-pass",
            confirmPassword = "a-secure-pass",
            privacyPolicyAccepted = true,
        )
        composeRule.setContent {
            var currentDraft by remember { mutableStateOf(draft) }
            GutCareTheme {
                ProfileBootstrapScreen(
                    draft = currentDraft,
                    operation = AuthOperationState.Idle,
                    onDraftChange = { currentDraft = it },
                    onSubmit = {},
                    onBack = {},
                )
            }
        }

        composeRule.onAllNodesWithContentDescription("出生年份").assertCountEquals(0)
        composeRule.onNodeWithTag("profile_submit").assertIsNotEnabled()

        composeRule.onNodeWithContentDescription(AuthCopy.healthDataConsent).performClick()
        composeRule.onNodeWithContentDescription("出生年份").assertIsDisplayed().performTextInput("1990")
        composeRule.onNodeWithTag("profile_submit").assertIsEnabled()
    }

    @Test
    fun loginControlsExposeAccessibilityLabels() {
        composeRule.setContent {
            GutCareTheme {
                LoginScreen(
                    operation = AuthOperationState.Idle,
                    onLogin = { _, _ -> },
                    onBack = {},
                    onRegister = {},
                    onForgotPassword = {},
                )
            }
        }

        composeRule.onNodeWithContentDescription("返回").assertIsDisplayed()
        composeRule.onNodeWithContentDescription(AuthCopy.emailLabel).assertIsDisplayed()
        composeRule.onNodeWithContentDescription(AuthCopy.passwordLabel).assertIsDisplayed()
        composeRule.onNodeWithContentDescription("忘记密码").assertIsDisplayed()
    }

    @Test
    fun welcomeExposesReferenceCriticalArtworkAndTerms() {
        composeRule.setContent {
            GutCareTheme {
                WelcomeScreen(onLogin = {}, onRegister = {})
            }
        }

        composeRule.onNodeWithContentDescription("日常记录插图").assertIsDisplayed()
        composeRule.onNodeWithTag("welcome_register").assertIsDisplayed()
        composeRule.onNodeWithText("›").assertIsDisplayed()
        composeRule.onNodeWithTag("welcome_terms").assertIsDisplayed()
        composeRule.onNodeWithText("继续即表示同意").assertIsDisplayed()
        composeRule.onNodeWithText("用户协议与隐私政策").assertIsDisplayed()
    }

    @Test
    fun systemBackLeavingRegistrationFlowClearsSensitiveDraft() {
        composeRule.setContent {
            GutCareTheme {
                GutCareNavHost(navController = rememberNavController())
            }
        }

        composeRule.onNodeWithTag("welcome_register").performClick()
        composeRule.onNodeWithTag("register_email").performTextInput("person@example.test")
        composeRule.onNodeWithTag("register_password").performTextInput("a-secure-pass")
        composeRule.onNodeWithTag("register_confirmation").performTextInput("a-secure-pass")
        composeRule.runOnIdle {
            val focusedView = composeRule.activity.currentFocus
            val windowToken = focusedView?.windowToken ?: composeRule.activity.window.decorView.windowToken
            focusedView?.clearFocus()
            val inputMethodManager = composeRule.activity.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            inputMethodManager.hideSoftInputFromWindow(windowToken, 0)
        }
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("privacy_policy_consent").assertIsDisplayed().assertIsOff().performClick()
        composeRule.onNodeWithTag("privacy_policy_consent").assertIsOn()
        composeRule.waitForIdle()
        composeRule.onNodeWithTag("register_continue").assertIsEnabled().performClick()
        composeRule.onNodeWithTag("profile_bootstrap_screen").assertIsDisplayed()

        composeRule.runOnIdle { composeRule.activity.onBackPressedDispatcher.onBackPressed() }
        composeRule.onNodeWithTag("register_screen").assertIsDisplayed()
        composeRule.runOnIdle { composeRule.activity.onBackPressedDispatcher.onBackPressed() }
        composeRule.onNodeWithTag("welcome_screen").assertIsDisplayed()

        composeRule.onNodeWithTag("welcome_register").performClick()
        composeRule.onNodeWithTag("register_continue").assertIsNotEnabled()
        assertEditableTextEmpty("register_email")
        assertEditableTextEmpty("register_password")
        assertEditableTextEmpty("register_confirmation")
        composeRule.onNodeWithTag("privacy_policy_consent").assertIsOff()
    }

    private fun assertEditableTextEmpty(testTag: String) {
        val editableText = composeRule.onNodeWithTag(testTag)
            .fetchSemanticsNode()
            .config[SemanticsProperties.EditableText]
            .text
        assertEquals("$testTag should be empty", "", editableText)
    }
}


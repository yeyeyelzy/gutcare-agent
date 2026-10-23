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
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performScrollTo
import androidx.navigation.compose.rememberNavController
import androidx.navigation.NavHostController
import com.gutcare.app.navigation.AppRoute
import com.gutcare.app.navigation.GutCareNavHost
import com.gutcare.app.core.network.RegistrationNoticeSummaries
import com.gutcare.app.core.network.PatientProfileDto
import com.gutcare.app.ui.auth.AuthWorkflow
import com.gutcare.app.ui.theme.GutCareTheme
import org.junit.Rule
import org.junit.Test
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue

class AuthScreensTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<ComponentActivity>()

    private val testNotices = RegistrationNoticeSummaries(
        privacy = "测试用隐私告知内容",
        healthData = "测试用健康数据告知内容",
    )

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
                    healthDataNoticeSummary = testNotices.healthData,
                    onSubmit = {},
                    onBack = {},
                )
            }
        }

        composeRule.onAllNodesWithContentDescription("出生年份").assertCountEquals(0)
        composeRule.onNodeWithTag("profile_submit").assertIsNotEnabled()

        composeRule.onNodeWithTag("health_data_consent").performClick()
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
    fun emailVerificationKeepsTokenInPageStateAndGatesSubmission() {
        composeRule.setContent {
            GutCareTheme {
                EmailVerificationScreen(
                    operation = AuthOperationState.Idle,
                    onVerify = {},
                    onGoToLogin = {},
                    onBack = {},
                )
            }
        }

        composeRule.onNodeWithTag("verify_email_submit").assertIsNotEnabled()
        composeRule.onNodeWithTag("email_verification_token")
            .performTextInput("a".repeat(20))
        composeRule.onNodeWithTag("verify_email_submit").assertIsEnabled()
        composeRule.runOnIdle {
            val focusedView = composeRule.activity.currentFocus
            val windowToken = focusedView?.windowToken ?: composeRule.activity.window.decorView.windowToken
            focusedView?.clearFocus()
            val inputMethodManager = composeRule.activity.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            inputMethodManager.hideSoftInputFromWindow(windowToken, 0)
        }
        composeRule.waitForIdle()
        composeRule.onNodeWithText("验证链接中的一次性令牌仅在本页面内存中使用，不会写入日志或持久保存。").assertIsDisplayed()
    }

    @Test
    fun profileEditorRequiresValidYearAndSendsCurrentVersion() {
        var saved: Triple<String?, Int, Int>? = null
        composeRule.setContent {
            GutCareTheme {
                MyProfileScreen(
                    profile = PatientProfileDto("patient", "旧昵称", 1990, "Asia/Shanghai", 4),
                    operation = AuthOperationState.Idle,
                    onSave = { nickname, year, version -> saved = Triple(nickname, year, version) },
                    onLogout = {},
                )
            }
        }
        composeRule.onNodeWithTag("profile_save").assertIsEnabled().performClick()
        composeRule.runOnIdle { assertEquals(Triple("旧昵称", 1990, 4), saved) }
        composeRule.onNodeWithTag("profile_birth_year").performTextInput("9")
        composeRule.onNodeWithTag("profile_save").assertIsNotEnabled()
    }

    @Test
    fun passwordResetShowsGenericRequestCopyAndOnlyContinuesAfterAcceptance() {
        composeRule.setContent {
            var operation by remember { mutableStateOf<AuthOperationState>(AuthOperationState.Idle) }
            GutCareTheme {
                PasswordResetRequestScreen(
                    operation = operation,
                    onRequest = { operation = AuthOperationState.Accepted },
                    onOpenConfirmation = {},
                    onBack = {},
                )
            }
        }

        composeRule.onNodeWithText("无论邮箱是否存在，服务端都会返回相同的受理结果。").assertIsDisplayed()
        composeRule.onNodeWithTag("reset_request_submit").assertIsNotEnabled()
        composeRule.onNodeWithTag("reset_email").performTextInput("person@example.test")
        composeRule.onNodeWithTag("reset_request_submit").assertIsEnabled().performClick()
        composeRule.onNodeWithTag("reset_open_confirmation").assertIsDisplayed()
    }

    @Test
    fun passwordResetConfirmationRequiresTokenAndMatchingStrongPassword() {
        composeRule.setContent {
            GutCareTheme {
                PasswordResetConfirmScreen(
                    operation = AuthOperationState.Idle,
                    onConfirm = { _, _ -> },
                    onBack = {},
                    onGoToLogin = {},
                )
            }
        }

        composeRule.onNodeWithTag("reset_confirm_submit").assertIsNotEnabled()
        composeRule.onNodeWithTag("reset_token").performTextInput("a".repeat(20))
        composeRule.onNodeWithTag("reset_new_password").performTextInput("a-secure-pass")
        composeRule.onNodeWithTag("reset_confirmation").performTextInput("a-secure-pass")
        composeRule.onNodeWithTag("reset_confirm_submit").assertIsEnabled()
    }

    @Test
    fun systemBackLeavingRegistrationFlowClearsSensitiveDraft() {
        composeRule.setContent {
            GutCareTheme {
                GutCareNavHost(
                    navController = rememberNavController(),
                    registrationNoticeSummaries = testNotices,
                )
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

    @Test
    fun asynchronousRegistrationAcceptedCallbackNavigatesToEmailVerificationWithoutNetwork() {
        var registerCalled = false
        lateinit var registrationCallback: (AuthOperationState) -> Unit
        lateinit var navController: NavHostController
        val workflow = object : AuthWorkflow {
            override fun login(email: String, password: String, onResult: (AuthOperationState) -> Unit) = Unit
            override fun register(draft: RegistrationDraft, onResult: (AuthOperationState) -> Unit) {
                registerCalled = true
                registrationCallback = onResult
            }
            override fun verifyEmail(token: String, onResult: (AuthOperationState) -> Unit) = Unit
            override fun requestPasswordReset(email: String, onResult: (AuthOperationState) -> Unit) = Unit
            override fun confirmPasswordReset(token: String, newPassword: String, onResult: (AuthOperationState) -> Unit) = Unit
            override fun updateProfile(nickname: String?, birthYear: Int, profileVersion: Int, onResult: (AuthOperationState) -> Unit) = Unit
        }
        composeRule.setContent {
            GutCareTheme {
                navController = rememberNavController()
                GutCareNavHost(
                    navController = navController,
                    authWorkflow = workflow,
                    registrationNoticeSummaries = testNotices,
                )
            }
        }

        composeRule.onNodeWithTag("welcome_register").performClick()
        composeRule.onNodeWithTag("register_email").performTextInput("local@example.test")
        composeRule.onNodeWithTag("register_password").performTextInput("a-secure-password")
        composeRule.onNodeWithTag("register_confirmation").performTextInput("a-secure-password")
        composeRule.onNodeWithTag("privacy_policy_consent").performScrollTo().performClick()
        composeRule.onNodeWithTag("register_continue").performScrollTo().assertIsEnabled().performClick()
        composeRule.onNodeWithTag("profile_bootstrap_screen").assertIsDisplayed()

        composeRule.onNodeWithTag("health_data_consent").performScrollTo().performClick()
        composeRule.onNodeWithTag("birth_year").performTextInput("1990")
        composeRule.onNodeWithTag("profile_submit").performScrollTo().assertIsEnabled().performClick()
        composeRule.runOnIdle { assertTrue("fake workflow must receive submission", registerCalled) }
        Thread { registrationCallback(AuthOperationState.Accepted) }.start()
        composeRule.waitUntil(5_000) {
            navController.currentDestination?.route == AppRoute.EmailVerification.value
        }
        composeRule.onAllNodesWithTag("email_verification_screen").assertCountEquals(1)

        composeRule.runOnIdle { composeRule.activity.onBackPressedDispatcher.onBackPressed() }
        composeRule.onNodeWithTag("welcome_screen").assertIsDisplayed()
        composeRule.onNodeWithTag("welcome_register").performClick()
        assertEditableTextEmpty("register_email")
        assertEditableTextEmpty("register_password")
        assertEditableTextEmpty("register_confirmation")
    }

    private fun assertEditableTextEmpty(testTag: String) {
        val editableText = composeRule.onNodeWithTag(testTag)
            .fetchSemanticsNode()
            .config[SemanticsProperties.EditableText]
            .text
        assertEquals("$testTag should be empty", "", editableText)
    }
}


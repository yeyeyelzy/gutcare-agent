package com.gutcare.app.ui.auth

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.gutcare.app.BuildConfig
import com.gutcare.app.MainActivity
import com.gutcare.app.core.network.AndroidAuthComposition
import com.gutcare.app.core.network.AuthFailureReason
import java.security.SecureRandom
import java.util.UUID
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in Compose UI flow against the isolated phone-demo backend and Mailpit. */
@RunWith(AndroidJUnit4::class)
class PhoneDemoAuthUiLiveTest {
    @get:Rule
    val composeRule = createEmptyComposeRule()

    @Test
    fun registrationVerificationLoginProfileColdLaunchAndLogoutWorkThroughUi() {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("Live UI auth is opt-in", args.getString("phoneDemoLive") == "true")
        assertEquals("http://10.0.2.2:8000/api/v1/", BuildConfig.API_BASE_URL)
        assertTrue(BuildConfig.DEBUG && BuildConfig.ALLOW_EMULATOR_HTTP)

        val email = "gc-live-ui-${UUID.randomUUID().toString().replace("-", "")}@example.com"
        val password = newSyntheticPassword()
        val changedNickname = "Demo-${UUID.randomUUID().toString().take(8)}"

        var activityScenario: ActivityScenario<MainActivity>? = ActivityScenario.launch(MainActivity::class.java)
        var stage = "welcome"
        try {
            composeRule.waitUntil(30_000) { hasTag("welcome_register") }
            composeRule.onNodeWithTag("welcome_register").performClick()
            stage = "registration_credentials"
            composeRule.onNodeWithTag("register_email").performTextInput(email)
            composeRule.onNodeWithTag("register_password").performTextInput(password)
            composeRule.onNodeWithTag("register_confirmation").performTextInput(password)
            composeRule.onNodeWithTag("privacy_policy_consent").performScrollTo().performClick()
            composeRule.onNodeWithTag("register_continue").assertIsEnabled()
            composeRule.onNodeWithTag("register_continue").performScrollTo().performClick()
            stage = "registration_profile"
            composeRule.onNodeWithTag("health_data_consent").performScrollTo().performClick()
            composeRule.onNodeWithTag("birth_year").performTextInput("1990")
            composeRule.onNodeWithTag("profile_submit").assertIsEnabled()
            composeRule.onNodeWithTag("profile_submit").performScrollTo().performClick()

            stage = "registration_submit"
            composeRule.waitUntil(45_000) {
                hasTag("email_verification_screen") || hasTag("auth_operation_error")
            }
            composeRule.onNodeWithTag("email_verification_screen").assertIsDisplayed()
            stage = "email_verification"
            val token = awaitVerificationToken(email)
            composeRule.onNodeWithTag("email_verification_token").performTextInput(token)
            composeRule.onNodeWithTag("verify_email_submit").performScrollTo().performClick()
            composeRule.waitUntil(30_000) { hasText("请求已受理") }
            composeRule.onNodeWithTag("verify_email_go_to_login").performClick()

            stage = "login"
            composeRule.onNodeWithTag("login_email").performTextInput(email)
            composeRule.onNodeWithTag("login_password").performTextInput(password)
            composeRule.onNodeWithTag("login_submit").performScrollTo().performClick()
            composeRule.waitUntil(45_000) { hasTag("tab_today") }
            composeRule.onNodeWithTag("tab_me").performClick()
            composeRule.waitUntil(20_000) { hasTag("profile_save") }
            stage = "profile_edit"
            composeRule.onNodeWithTag("my_profile_screen").assertIsDisplayed()
            composeRule.onNodeWithTag("profile_nickname").performTextInput(changedNickname)
            composeRule.onNodeWithTag("profile_save").performScrollTo().performClick()
            composeRule.waitUntil(30_000) { hasText("资料版本 2") }

            // Kill the app process, then relaunch it to exercise persisted-session startup restore.
            stage = "cold_start_restore"
            activityScenario?.close()
            activityScenario = null
            InstrumentationRegistry.getInstrumentation().uiAutomation
                .executeShellCommand("am force-stop ${BuildConfig.APPLICATION_ID}").use { }
            activityScenario = ActivityScenario.launch(MainActivity::class.java)
            composeRule.waitUntil(60_000) { hasTag("tab_today") }
            composeRule.onNodeWithTag("tab_me").performClick()
            composeRule.waitUntil(30_000) { hasTag("profile_save") && hasText(changedNickname) }

            composeRule.onNodeWithTag("logout").performScrollTo().performClick()
            composeRule.waitUntil(30_000) { hasTag("welcome_screen") }
            assertTrue("Logout should return to the public welcome screen", hasTag("welcome_register"))

            val session = runBlocking {
                AndroidAuthComposition(InstrumentationRegistry.getInstrumentation().targetContext).sessions.readRefreshToken()
            }
            assertEquals(null, session)
        } catch (failure: Throwable) {
            // Avoid JUnit/Compose semantics dumps that could include entered credentials.
            val safeReason = composeRule.onAllNodesWithTag("auth_operation_error")
                .fetchSemanticsNodes()
                .flatMap { node -> node.config[SemanticsProperties.ContentDescription] }
                .flatMap { description -> AuthFailureReason.values().filter { it.name == description }.asSequence() }
                .map { it.name }
                .distinct()
                .joinToString(",")
                .ifBlank { "none" }
            val operationState = when {
                hasTag("auth_operation_error") -> "error"
                hasTag("auth_operation_loading") -> "loading"
                hasTag("auth_operation_accepted") -> "accepted"
                else -> "none"
            }
            throw AssertionError(
                "Live UI auth failure_type=${failure.javaClass.simpleName}; " +
                    "safe checkpoint: $stage; safe error codes: none; safe validation fields: none; " +
                    "safe auth reason: $safeReason; safe operation_state: $operationState",
            )
        } finally {
            activityScenario?.close()
        }
    }

    private fun hasTag(tag: String): Boolean = runCatching {
        composeRule.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }.getOrDefault(false)

    private fun hasText(text: String): Boolean = runCatching {
        composeRule.onAllNodesWithText(text, substring = true).fetchSemanticsNodes().isNotEmpty()
    }.getOrDefault(false)

    private fun awaitVerificationToken(recipient: String): String {
        val client = OkHttpClient.Builder().callTimeout(java.time.Duration.ofSeconds(3)).build()
        val deadline = System.nanoTime() + java.time.Duration.ofSeconds(45).toNanos()
        val tokenPattern = Regex("(?m)^\\s*([A-Za-z0-9_-]{60,})\\s*$")
        while (System.nanoTime() < deadline) {
            val listing = getJson(client, "http://10.0.2.2:8025/api/v1/messages?limit=50")
            val messages = listing.optJSONArray("messages") ?: listing.optJSONArray("Messages")
            if (messages != null) {
                for (index in 0 until messages.length()) {
                    val message = messages.optJSONObject(index) ?: continue
                    if (!message.optJSONArray("To")?.toString().orEmpty().contains(recipient)) continue
                    if (message.optString("Subject") != "GutCare 邮箱验证") continue
                    val id = message.optString("ID").ifBlank { message.optString("Id") }
                    if (id.isBlank()) continue
                    val detail = getJson(client, "http://10.0.2.2:8025/api/v1/message/$id")
                    val body = detail.optString("Text").ifBlank {
                        detail.optJSONObject("Message")?.optString("Text").orEmpty()
                    }
                    tokenPattern.find(body)?.groups?.get(1)?.value?.let { return it }
                }
            }
            Thread.sleep(400)
        }
        error("Synthetic verification message was unavailable from local Mailpit")
    }

    private fun getJson(client: OkHttpClient, url: String): JSONObject {
        val request = Request.Builder().url(url).get().build()
        client.newCall(request).execute().use { response ->
            check(response.isSuccessful) { "Local Mailpit returned HTTP ${response.code}" }
            return JSONObject(response.body?.string().orEmpty())
        }
    }

    private fun newSyntheticPassword(): String {
        val bytes = ByteArray(24).also(SecureRandom()::nextBytes)
        val suffix = android.util.Base64.encodeToString(
            bytes,
            android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or android.util.Base64.NO_PADDING,
        )
        return "Aa7!$suffix"
    }
}

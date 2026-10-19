package com.gutcare.app.core.network

import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.gutcare.app.BuildConfig
import java.security.SecureRandom
import java.util.UUID
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in live contract check against the isolated local phone-demo Compose environment. */
@RunWith(AndroidJUnit4::class)
class PhoneDemoAuthLiveContractTest {
    @Test
    fun emulatorCompletesRegistrationVerificationLoginProfileRefreshAndLogout() = runBlocking {
        val arguments = InstrumentationRegistry.getArguments()
        assumeTrue("Live auth test is opt-in", arguments.getString("phoneDemoLive") == "true")
        assertEquals("http://10.0.2.2:8000/api/v1/", BuildConfig.API_BASE_URL)
        assertTrue("Live check requires a debug APK", BuildConfig.DEBUG)
        assertTrue("Cleartext must remain limited to emulator debug builds", BuildConfig.ALLOW_EMULATOR_HTTP)

        val app = InstrumentationRegistry.getInstrumentation().targetContext
        val composition = AndroidAuthComposition(app)
        val email = "gc-live-${UUID.randomUUID().toString().replace("-", "")}@example.com"
        val password = newSyntheticPassword()
        var sessionCreated = false

        try {
            val registration = composition.repository.register(email, password, password, 1990)
            assertAccepted("registration", registration)

            val verificationToken = awaitVerificationToken(email)
            val verification = composition.repository.verifyEmail(verificationToken)
            assertAccepted("verification", verification)

            val login = composition.repository.login(email, password)
            assertSuccess("login/profile", login)
            sessionCreated = true
            val profile = (login as AuthWorkflowResult.Success).profile
            assertEquals(1990, profile.birthYear)

            val restored = composition.repository.restoreSession()
            assertSuccess("refresh/profile", restored)

            val logout = composition.repository.logout()
            sessionCreated = false
            assertAccepted("logout", logout)
            assertEquals(null, composition.sessions.readRefreshToken())
        } finally {
            if (sessionCreated) runCatching { composition.repository.logout() }
            runCatching { composition.sessions.clear() }
        }
    }

    private fun assertAccepted(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Accepted) return
        failSafe(stage, result)
    }

    private fun assertSuccess(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Success) return
        failSafe(stage, result)
    }

    private fun failSafe(stage: String, result: AuthWorkflowResult): Nothing {
        val detail = when (result) {
            is AuthWorkflowResult.Failure -> buildString {
                append("status=").append(result.status ?: "none")
                append(" code=").append(result.code ?: "none")
                result.requestId?.let { append(" request_id=").append(it) }
            }
            is AuthWorkflowResult.Accepted -> "unexpected accepted result"
            is AuthWorkflowResult.Success -> "unexpected success result"
        }
        throw AssertionError("$stage failed: $detail")
    }

    private fun awaitVerificationToken(recipient: String): String {
        val client = OkHttpClient.Builder().callTimeout(java.time.Duration.ofSeconds(3)).build()
        val deadline = System.nanoTime() + java.time.Duration.ofSeconds(30).toNanos()
        val tokenPattern = Regex("(?m)^\\s*([A-Za-z0-9_-]{60,})\\s*$")
        while (System.nanoTime() < deadline) {
            val listing = getJson(client, "http://10.0.2.2:8025/api/v1/messages?limit=50")
            val messages = listing.optJSONArray("messages") ?: listing.optJSONArray("Messages")
            if (messages != null) {
                for (index in 0 until messages.length()) {
                    val message = messages.optJSONObject(index) ?: continue
                    val recipients = message.optJSONArray("To")?.toString().orEmpty()
                    if (!recipients.contains(recipient) || message.optString("Subject") != "GutCare 邮箱验证") continue
                    val id = message.optString("ID").ifBlank { message.optString("Id") }
                    if (id.isBlank()) continue
                    val detail = getJson(client, "http://10.0.2.2:8025/api/v1/message/$id")
                    val text = detail.optString("Text").ifBlank {
                        detail.optJSONObject("Message")?.optString("Text").orEmpty()
                    }
                    tokenPattern.find(text)?.groups?.get(1)?.value?.let { return it }
                }
            }
            Thread.sleep(300)
        }
        error("Synthetic verification message was not available from local Mailpit")
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
        val suffix = android.util.Base64.encodeToString(bytes, android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or android.util.Base64.NO_PADDING)
        return "Aa7!$suffix"
    }
}

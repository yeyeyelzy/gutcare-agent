package com.gutcare.app.core.network

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.gutcare.app.BuildConfig
import java.security.SecureRandom
import java.time.Duration
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in Android → business API → mock F08 Agent → F09 callback → patient-read contract. */
@RunWith(AndroidJUnit4::class)
class PhoneDemoF08F09MockLiveContractTest {
    @Test
    fun androidCreatesMockAnalysisAndReadsItsAdvice() = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("F08/F09 phone-demo test is opt-in", args.getString("phoneDemoF08F09Mock") == "true")
        assertEquals("http://10.0.2.2:8000/api/v1/", BuildConfig.API_BASE_URL)
        assertTrue("Live check requires a debug APK", BuildConfig.DEBUG)
        assertTrue("Cleartext must remain limited to emulator debug builds", BuildConfig.ALLOW_EMULATOR_HTTP)

        val timeoutSeconds = args.getString("phoneDemoF08F09TimeoutSeconds")?.toLongOrNull()?.coerceIn(30, 900) ?: 240L
        val composition = AndroidAuthComposition(InstrumentationRegistry.getInstrumentation().targetContext)
        var trackedRecordId: String? = null
        var trackedRecordVersion = 1
        try {
            val email = "gc-f08f09-${UUID.randomUUID().toString().replace("-", "")}@example.com"
            val password = newSyntheticPassword()
            requireAccepted("registration", composition.repository.register(email, password, password, 1990))
            requireAccepted("verification", composition.repository.verifyEmail(awaitVerificationToken(email)))
            requireSuccess("login", composition.repository.login(email, password))
            grantConsent(composition, "third_party_ai")
            grantConsent(composition, "mood_data_processing")
            grantConsent(composition, "mood_ai_sharing")

            val record = requireApiSuccess(
                "symptom/create",
                composition.recordsRepository.create(
                    PatientRecordType.SYMPTOM,
                    UUID.randomUUID().toString(),
                    RecordWriteDto(
                        Instant.now().toString(),
                        RecordPayloadDto(items = listOf(RecordItemDto(symptomCode = "bloating", severity = 1)), symptomStatus = "ongoing"),
                    ),
                ),
            )
            trackedRecordId = record.id
            trackedRecordVersion = record.recordVersion

            val repository = composition.analysisAdviceRepository
            val created = requireApiSuccess("analysis/create", repository.create("comprehensive_health_analysis"))
            assertEquals("comprehensive_health_analysis", created.analysisType)
            assertTrue("Created task identifier missing", created.id.isNotBlank())

            val deadline = System.nanoTime() + Duration.ofSeconds(timeoutSeconds).toNanos()
            var task = created
            while (task.status in setOf("pending", "processing") && System.nanoTime() < deadline) {
                delay(2_000)
                task = requireApiSuccess("analysis/poll", repository.task(created.id))
            }
            assertTrue("F08 task did not reach a readable-result terminal state", task.status in setOf("succeeded", "partial", "needs_input"))
            assertNotNull("F08 result was not readable by the patient", task.result)

            val adviceDeadline = System.nanoTime() + Duration.ofSeconds(timeoutSeconds).toNanos()
            var advice: AdviceDto? = null
            while (advice == null && System.nanoTime() < adviceDeadline) {
                val page = requireApiSuccess("advice/list", repository.adviceList())
                advice = page.items.firstOrNull { it.taskId == created.id }
                if (advice == null) delay(2_000)
            }
            val linkedAdvice = checkNotNull(advice) { "F09 advice callback was not visible to the patient" }
            assertTrue(linkedAdvice.id.isNotBlank())
            assertEquals(created.id, linkedAdvice.taskId)

            val readAdvice = requireApiSuccess("advice/mark-read", repository.markRead(linkedAdvice.id))
            assertEquals("read", readAdvice.status)
            if (readAdvice.feedback == null) {
                val feedback = requireApiSuccess("advice/feedback", repository.feedback(readAdvice.id, "helpful", expectedVersion = 0))
                assertEquals(readAdvice.id, feedback.adviceId)
                assertEquals("helpful", feedback.feedbackType)
            }
            println("PHONE_DEMO_F08_F09_MOCK passed task_status=${task.status} result_present=true advice_present=true advice_read=true")
        } finally {
            trackedRecordId?.let { id -> runCatching { composition.recordsRepository.delete(PatientRecordType.SYMPTOM, id, trackedRecordVersion) } }
            runCatching { composition.repository.logout() }
            composition.sessions.clear()
        }
    }

    private suspend fun grantConsent(composition: AndroidAuthComposition, consentType: String) {
        val accessToken = checkNotNull(composition.sessions.readAccessToken()) { "Consent setup failed: session missing" }
        val client = OkHttpClient.Builder().callTimeout(Duration.ofSeconds(8)).build()
        val noticeRequest = Request.Builder()
            .url("http://10.0.2.2:8000/api/v1/consent-notices?consent_type=$consentType")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()
        val policyVersion = client.newCall(noticeRequest).execute().use { response ->
            check(response.isSuccessful) { "Consent notice failed: type=$consentType status=${response.code}" }
            val notice = JSONObject(response.body?.string().orEmpty())
            check(notice.optBoolean("enabled")) { "Consent notice is disabled: type=$consentType" }
            notice.optString("policy_version").also { check(it.isNotBlank()) { "Consent notice version missing: type=$consentType" } }
        }
        val body = JSONObject()
            .put("consent_type", consentType)
            .put("policy_version", policyVersion)
            .put("granted", true)
            .toString()
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("http://10.0.2.2:8000/api/v1/patients/me/consents")
            .header("Authorization", "Bearer $accessToken")
            .post(body)
            .build()
        client.newCall(request).execute().use { response ->
            check(response.code == 201) { "Consent grant failed: type=$consentType status=${response.code}" }
        }
    }

    private fun awaitVerificationToken(recipient: String): String {
        val client = OkHttpClient.Builder().callTimeout(Duration.ofSeconds(4)).build()
        val deadline = System.nanoTime() + Duration.ofSeconds(45).toNanos()
        val tokenPattern = Regex("(?m)^\\s*([A-Za-z0-9_-]{60,})\\s*$")
        while (System.nanoTime() < deadline) {
            val listing = getJson(client, "http://10.0.2.2:8025/api/v1/messages?limit=50")
            val messages = listing.optJSONArray("messages") ?: listing.optJSONArray("Messages")
            if (messages != null) for (index in 0 until messages.length()) {
                val message = messages.optJSONObject(index) ?: continue
                val recipients = message.optJSONArray("To")?.toString().orEmpty()
                if (!recipients.contains(recipient) || message.optString("Subject") != "GutCare 邮箱验证") continue
                val id = message.optString("ID").ifBlank { message.optString("Id") }
                if (id.isBlank()) continue
                val detail = getJson(client, "http://10.0.2.2:8025/api/v1/message/$id")
                val text = detail.optString("Text").ifBlank { detail.optJSONObject("Message")?.optString("Text").orEmpty() }
                tokenPattern.find(text)?.groups?.get(1)?.value?.let { return it }
            }
            Thread.sleep(300)
        }
        error("Synthetic verification message unavailable; contents suppressed")
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

    private fun <T> requireApiSuccess(stage: String, result: ApiResult<T>): T = when (result) {
        is ApiResult.Success -> result.value
        is ApiResult.Failure -> throw AssertionError("$stage failed: status=${result.status ?: "none"} code=${result.code ?: "none"}${result.requestId?.let { " request_id=$it" }.orEmpty()}")
    }

    private fun requireAccepted(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Accepted) return
        val failure = result as? AuthWorkflowResult.Failure
        throw AssertionError("$stage failed: status=${failure?.status ?: "none"} code=${failure?.code ?: "none"}${failure?.requestId?.let { " request_id=$it" }.orEmpty()}")
    }

    private fun requireSuccess(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Success) return
        val failure = result as? AuthWorkflowResult.Failure
        throw AssertionError("$stage failed: status=${failure?.status ?: "none"} code=${failure?.code ?: "none"}${failure?.requestId?.let { " request_id=$it" }.orEmpty()}")
    }
}

package com.gutcare.app.core.network

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.gutcare.app.BuildConfig
import java.security.SecureRandom
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Opt-in F03/F04/F05/F14 contract test against the isolated phone-demo stack.
 *
 * All account and record values are generated in memory. Failure messages retain only
 * status/code/request_id metadata; credentials and record bodies never enter test output.
 */
@RunWith(AndroidJUnit4::class)
class PhoneDemoRecordsLiveContractTest {
    @Test
    fun emulatorCompletesRecordCrudConflictPaginationAndLogoutIsolation() = runBlocking {
        val arguments = InstrumentationRegistry.getArguments()
        assumeTrue("Live records test is opt-in", arguments.getString("phoneDemoRecordsLive") == "true")
        assertEquals("http://10.0.2.2:8000/api/v1/", BuildConfig.API_BASE_URL)
        assertTrue("Live check requires a debug APK", BuildConfig.DEBUG)
        assertTrue("Cleartext must remain limited to emulator debug builds", BuildConfig.ALLOW_EMULATOR_HTTP)

        val app = InstrumentationRegistry.getInstrumentation().targetContext
        val composition = AndroidAuthComposition(app)
        val repository = composition.recordsRepository
        val email = "gc-records-${UUID.randomUUID().toString().replace("-", "")}@example.com"
        val password = newSyntheticPassword()
        val tracked = mutableListOf<TrackedRecord>()
        var trackedMood: TrackedMood? = null
        var sessionCreated = false

        try {
            requireAccepted("registration", composition.repository.register(email, password, password, 1990))
            val verificationToken = awaitVerificationToken(email)
            requireAccepted("verification", composition.repository.verifyEmail(verificationToken))
            requireSuccess("login/profile", composition.repository.login(email, password))
            sessionCreated = true

            val base = Instant.now()
            val dietOne = requireApiSuccess(
                "diet/create/one",
                repository.create(
                    PatientRecordType.DIET,
                    "diet-${UUID.randomUUID()}",
                    RecordWriteDto(base.minusSeconds(2).toString(), RecordPayloadDto(mealType = "breakfast", textDescription = "synthetic-a")),
                ),
            )
            tracked += TrackedRecord(PatientRecordType.DIET, dietOne.id, dietOne.recordVersion)
            val dietTwo = requireApiSuccess(
                "diet/create/two",
                repository.create(
                    PatientRecordType.DIET,
                    "diet-${UUID.randomUUID()}",
                    RecordWriteDto(base.minusSeconds(1).toString(), RecordPayloadDto(mealType = "lunch", textDescription = "synthetic-b")),
                ),
            )
            tracked += TrackedRecord(PatientRecordType.DIET, dietTwo.id, dietTwo.recordVersion)

            val firstPage = requireApiSuccess(
                "diet/list/page-one",
                repository.list(PatientRecordType.DIET, limit = 1, since = base.minusSeconds(10).toString(), until = base.plusSeconds(10).toString()),
            )
            assertEquals(1, firstPage.items.size)
            assertNotNull(firstPage.nextCursor)
            val secondPage = requireApiSuccess(
                "diet/list/page-two",
                repository.list(PatientRecordType.DIET, cursor = firstPage.nextCursor, limit = 1, since = base.minusSeconds(10).toString(), until = base.plusSeconds(10).toString()),
            )
            assertEquals(1, secondPage.items.size)
            assertNotEquals(firstPage.items.single().id, secondPage.items.single().id)
            assertTrue((firstPage.items + secondPage.items).map { it.id }.containsAll(listOf(dietOne.id, dietTwo.id)))

            exerciseRecordCrud(
                "diet",
                repository,
                tracked.first { it.id == dietOne.id },
                base.minusSeconds(2).toString(),
                RecordPayloadDto(mealType = "dinner", textDescription = "synthetic-updated"),
            )
            deleteTracked(repository, tracked.first { it.id == dietTwo.id })

            val stool = requireApiSuccess(
                "stool/create",
                repository.create(
                    PatientRecordType.STOOL,
                    "stool-${UUID.randomUUID()}",
                    RecordWriteDto(base.minusSeconds(3).toString(), RecordPayloadDto(bristolType = 3, urgencyLevel = 2, processSensation = listOf("normal"))),
                ),
            )
            val stoolTracked = TrackedRecord(PatientRecordType.STOOL, stool.id, stool.recordVersion).also(tracked::add)
            assertTrue(requireApiSuccess("stool/list", repository.list(PatientRecordType.STOOL, limit = 20)).items.any { it.id == stool.id })
            exerciseRecordCrud(
                "stool",
                repository,
                stoolTracked,
                base.minusSeconds(3).toString(),
                RecordPayloadDto(bristolType = 4, urgencyLevel = 3, processSensation = listOf("normal")),
            )

            val symptom = requireApiSuccess(
                "symptom/create",
                repository.create(
                    PatientRecordType.SYMPTOM,
                    "symptom-${UUID.randomUUID()}",
                    RecordWriteDto(
                        base.minusSeconds(4).toString(),
                        RecordPayloadDto(items = listOf(RecordItemDto(symptomCode = "bloating", severity = 2)), symptomStatus = "ongoing"),
                    ),
                ),
            )
            val symptomTracked = TrackedRecord(PatientRecordType.SYMPTOM, symptom.id, symptom.recordVersion).also(tracked::add)
            assertTrue(requireApiSuccess("symptom/list", repository.list(PatientRecordType.SYMPTOM, limit = 20)).items.any { it.id == symptom.id })
            exerciseRecordCrud(
                "symptom",
                repository,
                symptomTracked,
                base.minusSeconds(4).toString(),
                RecordPayloadDto(items = listOf(RecordItemDto(symptomCode = "bloating", severity = 1)), symptomStatus = "relieved"),
            ) {
                val statusHistory = requireApiSuccess("symptom/status-history", repository.symptomStatusHistory(symptom.id))
                assertEquals("relieved", statusHistory.currentStatus)
                assertTrue(statusHistory.events.size >= 2)
            }

            grantMoodProcessingConsent(composition)
            val mood = requireApiSuccess(
                "mood/create",
                repository.createMood(
                    "mood-${UUID.randomUUID()}",
                    MoodWriteDto(base.minusSeconds(5).toString(), 3, listOf("calm"), null),
                ),
            )
            val moodTracked = TrackedMood(mood.id, mood.recordVersion).also { trackedMood = it }
            assertTrue(requireApiSuccess("mood/list", repository.listMood(limit = 20)).items.any { it.id == mood.id })
            assertEquals(mood.id, requireApiSuccess("mood/detail", repository.moodDetail(mood.id)).id)
            val updatedMood = requireApiSuccess(
                "mood/update",
                repository.updateMood(mood.id, MoodPatchDto(mood.recordVersion, moodLevel = 4, emotionTags = listOf("content"))),
            )
            moodTracked.version = updatedMood.recordVersion
            requireConflict("mood/stale-update", repository.updateMood(mood.id, MoodPatchDto(mood.recordVersion, moodLevel = 2)))
            requireApiSuccess("mood/delete", repository.deleteMood(mood.id, moodTracked.version))
            moodTracked.deleted = true
            requireNotFound("mood/deleted-detail", repository.moodDetail(mood.id))
            assertTrue("Deleted mood remained visible in its list", requireApiSuccess("mood/list-after-delete", repository.listMood(limit = 100)).items.none { it.id == mood.id })

            tracked.filter { !it.deleted }.forEach { deleteTracked(repository, it) }
            val logoutResult = composition.repository.logout()
            assertTrue("logout failed: ${safeAuthResult(logoutResult)}", logoutResult is AuthWorkflowResult.Accepted)
            sessionCreated = false
            assertEquals(null, composition.sessions.readAccessToken())
            assertEquals(null, composition.sessions.readRefreshToken())

            val invalidationsBefore = composition.sessionInvalidations.value
            requireUnauthorized("deleted-helper/list", repository.list(PatientRecordType.DIET, limit = 1))
            assertTrue(composition.sessionInvalidations.value > invalidationsBefore)
            assertEquals(null, composition.sessions.readAccessToken())
            assertEquals(null, composition.sessions.readRefreshToken())
            sessionCreated = false
        } finally {
            if (sessionCreated) {
                trackedMood?.takeUnless { it.deleted }?.let {
                    runCatching { repository.deleteMood(it.id, it.version) }
                }
                tracked.filter { !it.deleted }.forEach { runCatching { deleteTracked(repository, it) } }
                runCatching { composition.repository.logout() }
            }
            runCatching { composition.sessions.clear() }
        }
    }

    private suspend fun exerciseRecordCrud(
        label: String,
        repository: RecordsRepository,
        tracked: TrackedRecord,
        occurredAt: String,
        updatedPayload: RecordPayloadDto,
        beforeDelete: suspend () -> Unit = {},
    ) {
        val detail = requireApiSuccess("$label/detail", repository.detail(tracked.type, tracked.id))
        assertEquals(tracked.id, detail.id)
        val staleVersion = detail.recordVersion
        val updated = requireApiSuccess(
            "$label/update",
            repository.update(tracked.type, tracked.id, RecordPatchDto(staleVersion, occurredAt, updatedPayload)),
        )
        assertTrue(updated.recordVersion > staleVersion)
        tracked.version = updated.recordVersion
        requireConflict(
            "$label/stale-update",
            repository.update(tracked.type, tracked.id, RecordPatchDto(staleVersion, occurredAt, updatedPayload)),
        )
        beforeDelete()
        deleteTracked(repository, tracked)
        requireNotFound("$label/deleted-detail", repository.detail(tracked.type, tracked.id))
        val remaining = requireApiSuccess("$label/list-after-delete", repository.list(tracked.type, limit = 100))
        assertTrue("Deleted record remained visible in its list", remaining.items.none { it.id == tracked.id })
    }

    private suspend fun deleteTracked(repository: RecordsRepository, tracked: TrackedRecord) {
        requireApiSuccess("${tracked.type.route}/delete", repository.delete(tracked.type, tracked.id, tracked.version))
        tracked.deleted = true
    }

    private suspend fun grantMoodProcessingConsent(composition: AndroidAuthComposition) {
        val accessToken = composition.sessions.readAccessToken() ?: error("consent setup failed: session missing")
        val client = OkHttpClient.Builder().callTimeout(java.time.Duration.ofSeconds(5)).build()
        val noticeRequest = Request.Builder()
            .url("http://10.0.2.2:8000/api/v1/consent-notices?consent_type=mood_data_processing")
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()
        val policyVersion = client.newCall(noticeRequest).execute().use { response ->
            check(response.isSuccessful) { "consent notice failed: status=${response.code}" }
            val notice = JSONObject(response.body?.string().orEmpty())
            check(notice.optBoolean("enabled")) { "consent notice failed: disabled" }
            notice.optString("policy_version").also { check(it.isNotBlank()) { "consent notice failed: version missing" } }
        }
        val body = JSONObject()
            .put("consent_type", "mood_data_processing")
            .put("policy_version", policyVersion)
            .put("granted", true)
            .toString()
            .toRequestBody("application/json".toMediaType())
        val consentRequest = Request.Builder()
            .url("http://10.0.2.2:8000/api/v1/patients/me/consents")
            .header("Authorization", "Bearer $accessToken")
            .post(body)
            .build()
        client.newCall(consentRequest).execute().use { response ->
            check(response.code == 201) { "consent grant failed: status=${response.code}" }
        }
    }

    private fun <T> requireApiSuccess(stage: String, result: ApiResult<T>): T = when (result) {
        is ApiResult.Success -> result.value
        is ApiResult.Failure -> throw AssertionError("$stage failed: status=${result.status ?: "none"} code=${result.code ?: "none"}${result.requestId?.let { " request_id=$it" }.orEmpty()}")
    }

    private fun requireConflict(stage: String, result: ApiResult<*>) {
        assertFailure(stage, result, 409)
    }

    private fun requireUnauthorized(stage: String, result: ApiResult<*>) {
        assertFailure(stage, result, 401)
    }

    private fun requireNotFound(stage: String, result: ApiResult<*>) {
        assertFailure(stage, result, 404)
    }

    private fun assertFailure(stage: String, result: ApiResult<*>, expectedStatus: Int) {
        if (result is ApiResult.Failure && result.status == expectedStatus) return
        throw AssertionError("$stage expected HTTP $expectedStatus but received ${safeResult(result)}")
    }

    private fun requireAccepted(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Accepted) return
        throw AssertionError("$stage failed: ${safeAuthResult(result)}")
    }

    private fun requireSuccess(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Success) return
        throw AssertionError("$stage failed: ${safeAuthResult(result)}")
    }

    private fun safeResult(result: ApiResult<*>): String = when (result) {
        is ApiResult.Success -> "success"
        is ApiResult.Failure -> "status=${result.status ?: "none"} code=${result.code ?: "none"}"
    }

    private fun safeAuthResult(result: AuthWorkflowResult): String = when (result) {
        is AuthWorkflowResult.Success -> "unexpected success"
        is AuthWorkflowResult.Accepted -> "unexpected accepted"
        is AuthWorkflowResult.Failure -> "status=${result.status ?: "none"} code=${result.code ?: "none"}${result.requestId?.let { " request_id=$it" }.orEmpty()}"
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
                    val text = detail.optString("Text").ifBlank { detail.optJSONObject("Message")?.optString("Text").orEmpty() }
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

    private data class TrackedRecord(
        val type: PatientRecordType,
        val id: String,
        var version: Int,
        var deleted: Boolean = false,
    )

    private data class TrackedMood(val id: String, var version: Int, var deleted: Boolean = false)
}

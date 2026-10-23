package com.gutcare.app.core.network

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.gutcare.app.BuildConfig
import java.time.Instant
import java.util.UUID
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Opt-in native-client image upload and Agent recognition chain against the isolated phone-demo API. */
@RunWith(AndroidJUnit4::class)
class PhoneDemoImageRecognitionLiveContractTest {
    @Test
    fun androidUploadsJpegRunsRecognitionAndConfirmsOnlyWhenRequired() = runBlocking {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("Live image E2E is opt-in", args.getString("phoneDemoImageLive") == "true")
        assertEquals("http://10.0.2.2:8000/api/v1/", BuildConfig.API_BASE_URL)
        assertTrue("Live check requires a debug APK", BuildConfig.DEBUG)
        assertTrue("Cleartext must remain limited to emulator debug builds", BuildConfig.ALLOW_EMULATOR_HTTP)

        val type = when (args.getString("phoneDemoImageType", "stool")) {
            "diet" -> PatientRecordType.DIET
            "stool" -> PatientRecordType.STOOL
            else -> error("phoneDemoImageType must be diet or stool")
        }
        val candidateType = if (type == PatientRecordType.DIET) "food_name" else "bristol_type"
        val purpose = if (type == PatientRecordType.DIET) "diet_image_recognition" else "stool_image_recognition"
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val composition = AndroidAuthComposition(context)
        try {
            val email = "gc-image-${UUID.randomUUID().toString().replace("-", "")}@example.com"
            val password = "Gc7!${UUID.randomUUID()}Aa"
            requireAccepted("registration", composition.repository.register(email, password, password, 1990))
            requireAccepted("verification", composition.repository.verifyEmail(awaitVerificationToken(email)))
            requireSuccess("login", composition.repository.login(email, password))
            grantImageConsents(composition)

            val record = requireApiSuccess(
                "${type.route}/create",
                composition.recordsRepository.create(
                    type,
                    UUID.randomUUID().toString(),
                    RecordWriteDto(
                        Instant.now().toString(),
                        if (type == PatientRecordType.DIET) RecordPayloadDto(textDescription = "合成图片联调记录")
                        else RecordPayloadDto(notes = "合成图片联调记录"),
                    ),
                ),
            )
            val jpeg = InstrumentationRegistry.getInstrumentation().context.assets
                .open(args.getString("phoneDemoImageAsset") ?: "record-image-live.jpg").use { it.readBytes() }
            require(jpeg.size in 1..RecordImageRules.MAX_IMAGE_BYTES.toInt())
            assertTrue("Input must be JPEG bytes", jpeg.take(3) == listOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte()))
            val attachment = requireApiSuccess(
                "${type.route}/image-upload-attach",
                composition.recordImagesRepository.uploadAndAttach(
                    type = type,
                    recordId = record.id,
                    recordVersion = record.recordVersion,
                    imageSetVersion = record.imageSetVersion,
                    idempotencyKey = UUID.randomUUID().toString(),
                    fileName = "synthetic-${type.route}.jpg",
                    contentType = "image/jpeg",
                    content = jpeg.toRequestBody("image/jpeg".toMediaType()),
                    sizeBytes = jpeg.size.toLong(),
                ),
            )
            val disclosure = requireApiSuccess("$purpose/disclosure", composition.recordImagesRepository.recognitionDisclosure(purpose))
            check(disclosure.enabled && !disclosure.policyVersion.isNullOrBlank()) { "$purpose disclosure is unavailable" }
            val acknowledgement = requireApiSuccess(
                "$purpose/acknowledgement",
                composition.recordImagesRepository.acknowledgeRecognitionDisclosure(
                    RecordImageDisclosureAcknowledgeDto(
                        recordId = record.id,
                        purpose = purpose,
                        recordVersion = attachment.recordVersion,
                        imageSetVersion = attachment.imageSetVersion,
                        policyVersion = disclosure.policyVersion!!,
                    ),
                ),
            )
            val request = requireApiSuccess(
                "$purpose/request",
                composition.recordImagesRepository.createRecognition(
                    type,
                    record.id,
                    UUID.randomUUID().toString(),
                    RecordImageRecognitionCreateDto(attachment.recordVersion, attachment.imageSetVersion, acknowledgement.disclosureToken),
                ),
            )
            assertNotNull("Agent request ID missing", request.id)

            val timeoutSeconds = args.getString("phoneDemoImageTimeoutSeconds")?.toLongOrNull()?.coerceIn(30, 900) ?: 240L
            val deadline = System.nanoTime() + java.time.Duration.ofSeconds(timeoutSeconds).toNanos()
            var latest = request
            while (latest.status !in setOf("candidates_ready", "no_candidates", "failed", "cancelled", "invalidated") && System.nanoTime() < deadline) {
                kotlinx.coroutines.delay(2_000)
                latest = requireApiSuccess("$purpose/poll", composition.recordImagesRepository.recognitionRequest(request.id))
            }
            assertEquals("Agent image recognition did not produce candidates", "candidates_ready", latest.status)
            val candidate = latest.candidates.firstOrNull { it.candidateType == candidateType && it.status == "pending" }
            assertNotNull("Expected pending $candidateType candidate", candidate)
            val confirmedCandidate = checkNotNull(candidate)
            if (type == PatientRecordType.STOOL) {
                assertEquals("Stool result must be direct", false, confirmedCandidate.requiresPatientConfirmation)
                assertTrue("Stool output must be Bristol-only", latest.candidates.all { it.candidateType == "bristol_type" })
                println("PHONE_DEMO_IMAGE_E2E passed type=stool bytes=${jpeg.size} candidate=$candidateType patient_decision=not_required")
            } else {
                assertEquals("Diet candidates remain patient-confirmed", true, confirmedCandidate.requiresPatientConfirmation)
                requireApiSuccess(
                    "$purpose/patient-confirmation",
                    composition.recordImagesRepository.decideRecognitionCandidate(
                        confirmedCandidate.id,
                        UUID.randomUUID().toString(),
                        RecordImageCandidateDecisionDto(
                            action = "accept",
                            candidateVersion = confirmedCandidate.candidateVersion,
                            recordVersion = latest.decisionRecordVersion,
                            imageSetVersion = latest.imageSetVersion,
                        ),
                    ),
                )
                println("PHONE_DEMO_IMAGE_E2E passed type=diet bytes=${jpeg.size} candidate=$candidateType patient_decision=accept")
            }
        } finally {
            composition.sessions.clear()
        }
    }

    private suspend fun grantImageConsents(composition: AndroidAuthComposition) {
        val token = checkNotNull(composition.sessions.readAccessToken()) { "Consent setup failed: session missing" }
        val client = okhttp3.OkHttpClient.Builder().callTimeout(java.time.Duration.ofSeconds(8)).build()
        for ((consentType, policyVersion) in listOf(
            "sensitive_image" to "test-only-image-v1",
            "third_party_ai" to "test-only-third-party-ai-v1",
        )) {
            val body = org.json.JSONObject()
                .put("consent_type", consentType)
                .put("policy_version", policyVersion)
                .put("granted", true)
                .toString()
                .toRequestBody("application/json".toMediaType())
            val request = okhttp3.Request.Builder()
                .url("http://10.0.2.2:8000/api/v1/patients/me/consents")
                .header("Authorization", "Bearer $token")
                .post(body)
                .build()
            client.newCall(request).execute().use { response ->
                check(response.code == 201) { "Consent grant failed: type=$consentType status=${response.code}" }
            }
        }
    }

    private fun awaitVerificationToken(recipient: String): String {
        val client = okhttp3.OkHttpClient.Builder().callTimeout(java.time.Duration.ofSeconds(4)).build()
        val deadline = System.nanoTime() + java.time.Duration.ofSeconds(45).toNanos()
        val tokenPattern = Regex("(?m)^\\s*([A-Za-z0-9_-]{60,})\\s*$")
        while (System.nanoTime() < deadline) {
            val listing = getJson(client, "http://10.0.2.2:8025/api/v1/messages?limit=50")
            val messages = listing.optJSONArray("messages") ?: listing.optJSONArray("Messages")
            if (messages != null) for (index in 0 until messages.length()) {
                val message = messages.optJSONObject(index) ?: continue
                if (!message.optJSONArray("To").toString().contains(recipient) || message.optString("Subject") != "GutCare 邮箱验证") continue
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

    private fun getJson(client: okhttp3.OkHttpClient, url: String): org.json.JSONObject {
        val request = okhttp3.Request.Builder().url(url).get().build()
        client.newCall(request).execute().use { response ->
            check(response.isSuccessful) { "Local Mailpit returned HTTP ${response.code}" }
            return org.json.JSONObject(response.body?.string().orEmpty())
        }
    }

    private fun <T> requireApiSuccess(stage: String, result: ApiResult<T>): T = when (result) {
        is ApiResult.Success -> result.value
        is ApiResult.Failure -> throw AssertionError("$stage failed: status=${result.status ?: "none"} code=${result.code ?: "none"}")
    }

    private fun requireAccepted(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Accepted) return
        val failure = result as? AuthWorkflowResult.Failure
        throw AssertionError("$stage failed: status=${failure?.status ?: "none"} code=${failure?.code ?: "none"}")
    }

    private fun requireSuccess(stage: String, result: AuthWorkflowResult) {
        if (result is AuthWorkflowResult.Success) return
        val failure = result as? AuthWorkflowResult.Failure
        throw AssertionError("$stage failed: status=${failure?.status ?: "none"} code=${failure?.code ?: "none"}")
    }
}

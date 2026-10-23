package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.OkHttpClient
import okhttp3.Dns
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.InetAddress
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class RecordImagesRepositoryTest {
    @Test fun imageRecognitionUsesPurposeDisclosureVersionedRequestsAndPatientDecisionContracts() = runBlocking {
        val server = MockWebServer()
        server.start()
        server.enqueue(MockResponse().setResponseCode(200).setBody(
            """{"purpose":"diet_image_recognition","enabled":true,"policy_version":"test-diet-v2","summary":"summary","purpose_text":"purpose","data_scope":"scope","recipient":"recipient","retention":"retention","withdrawal_effect":"withdraw"}""",
        ))
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"disclosure_token":"one-time-token-012345678901234567890123456789","expires_at":"2026-10-20T10:05:00Z"}"""))
        val requestJson = """{"id":"request-1","recognition_type":"diet_image_recognition","status":"candidates_ready","record_version":3,"image_set_version":1,"decision_record_version":3,"attempt":1,"retry_of_request_id":null,"candidates":[{"id":"candidate-1","candidate_version":1,"attachment_id":"image-1","candidate_group_key":"group-1","candidate_type":"food_name","value":"Rice","requires_patient_confirmation":true,"confidence_band":"medium","uncertainty_code":"other","status":"pending"}],"created_at":"2026-10-20T10:00:00Z","updated_at":"2026-10-20T10:00:00Z"}"""
        server.enqueue(MockResponse().setResponseCode(202).setBody(requestJson))
        server.enqueue(MockResponse().setResponseCode(200).setBody(requestJson))
        server.enqueue(MockResponse().setResponseCode(204))
        try {
            val api = Retrofit.Builder().baseUrl(server.url("api/v1/"))
                .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
                .build().create(RecordImagesApi::class.java)
            val repository = RecordImagesRepository(api)
            assertTrue(repository.recognitionDisclosure("diet_image_recognition") is ApiResult.Success)
            val disclosure = repository.acknowledgeRecognitionDisclosure(
                RecordImageDisclosureAcknowledgeDto("record-1", "diet_image_recognition", 3, 1, "test-diet-v2"),
            ) as ApiResult.Success
            val body = RecordImageRecognitionCreateDto(3, 1, disclosure.value.disclosureToken)
            val created = repository.createRecognition(PatientRecordType.DIET, "record-1", "create-key-123", body) as ApiResult.Success
            assertEquals("food_name", created.value.candidates.single().candidateType)
            assertEquals("Rice", created.value.candidates.single().value)
            assertTrue(created.value.candidates.single().requiresPatientConfirmation)
            assertTrue(repository.recognitionRequest("request-1") is ApiResult.Success)
            assertTrue(repository.decideRecognitionCandidate("candidate-1", "decision-key-123",
                RecordImageCandidateDecisionDto("accept", 1, 3, 1)) is ApiResult.Success)

            assertEquals("/api/v1/record-image-recognition-disclosures?purpose=diet_image_recognition", server.takeRequest().path)
            val acknowledgment = server.takeRequest()
            assertEquals("POST", acknowledgment.method)
            assertEquals("true", acknowledgment.body.readUtf8().let { Regex("\\\"acknowledged\\\":true").containsMatchIn(it).toString() })
            val create = server.takeRequest()
            assertEquals("/api/v1/dietary-records/record-1/image-recognition-requests", create.path)
            assertEquals("create-key-123", create.getHeader("Idempotency-Key"))
            assertTrue(create.body.readUtf8().contains("one-time-token-"))
            assertEquals("/api/v1/record-image-recognition-requests/request-1", server.takeRequest().path)
            val decision = server.takeRequest()
            assertEquals("/api/v1/record-image-candidates/candidate-1/decision", decision.path)
            assertEquals("decision-key-123", decision.getHeader("Idempotency-Key"))
            assertTrue(decision.body.readUtf8().contains("\"record_version\":3"))
        } finally { server.shutdown() }
    }

    @Test fun previewsUseFreshAttachmentGrantAndUnauthenticatedSameOriginCapabilityGet() = runBlocking {
        val server = MockWebServer()
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        val retrofitOrigin = server.url("api/v1/")
        val origin = retrofitOrigin.newBuilder().host("10.0.2.2").build()
        val emulatorClient = OkHttpClient.Builder().dns(object : Dns {
            override fun lookup(hostname: String) = listOf(InetAddress.getByName("127.0.0.1"))
        }).build()
        server.enqueue(MockResponse().setResponseCode(200).setBody(
            """{"download_url":"${server.url("uploads/short-capability")}","expires_at":"2026-10-20T10:05:00Z"}""",
        ))
        server.enqueue(MockResponse().setResponseCode(200).setHeader("Content-Type", "image/jpeg").setBody(okio.Buffer().write(byteArrayOf(1, 2, 3))))
        try {
            val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            val authenticated = Retrofit.Builder().baseUrl(retrofitOrigin).client(emulatorClient.newBuilder().addInterceptor { chain ->
                chain.proceed(chain.request().newBuilder().header("Authorization", "Bearer test-only").build())
            }.build()).addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(RecordImagesApi::class.java)
            val capabilityClient = Retrofit.Builder().baseUrl(retrofitOrigin).client(emulatorClient)
                .addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(RecordImagesApi::class.java)
            val api = SameOriginRecordImagesApi(authenticated, origin, capabilityClient, allowEmulatorLoopback = true)
            val result = RecordImagesRepository(api).downloadPreview("attachment-id")
            assertTrue("Expected preview bytes, got $result", result is ApiResult.Success)
            assertTrue((result as ApiResult.Success).value.contentEquals(byteArrayOf(1, 2, 3)))
            val grant = server.takeRequest()
            assertEquals("POST", grant.method)
            assertEquals("/api/v1/record-images/attachment-id/download-grants", grant.path)
            assertEquals("Bearer test-only", grant.getHeader("Authorization"))
            val preview = server.takeRequest()
            assertEquals("GET", preview.method)
            assertEquals("/uploads/short-capability", preview.path)
            assertEquals(null, preview.getHeader("Authorization"))
        } finally { server.shutdown() }
    }

    @Test fun refusesCrossOriginPreviewGrantBeforeAnyCapabilityRequest() = runBlocking {
        val server = MockWebServer()
        server.start()
        server.enqueue(MockResponse().setResponseCode(200).setBody(
            """{"download_url":"https://attacker.example/uploads/secret","expires_at":"2026-10-20T10:05:00Z"}""",
        ))
        try {
            val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            val origin = server.url("api/v1/")
            val api = Retrofit.Builder().baseUrl(origin).addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(RecordImagesApi::class.java)
            val result = RecordImagesRepository(SameOriginRecordImagesApi(api, origin)).downloadPreview("image-1")
            assertEquals("UNSAFE_DOWNLOAD_URL", (result as ApiResult.Failure).code)
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }

    @Test fun refusesLoopbackCapabilityOutsideExplicitEmulatorDebugMode() = runBlocking {
        val server = MockWebServer()
        server.start()
        server.enqueue(MockResponse().setResponseCode(200).setBody(
            """{"download_url":"${server.url("uploads/local-capability")}","expires_at":"2026-10-20T10:05:00Z"}""",
        ))
        try {
            val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            val origin = server.url("api/v1/").newBuilder().host("10.0.2.2").build()
            val api = Retrofit.Builder().baseUrl(server.url("api/v1/"))
                .addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(RecordImagesApi::class.java)
            val result = RecordImagesRepository(SameOriginRecordImagesApi(api, origin)).downloadPreview("image-1")
            assertEquals("UNSAFE_DOWNLOAD_URL", (result as ApiResult.Failure).code)
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }

    @Test fun uploadCompletesCleanFileThenAssociatesWithVersionedRecord() = runBlocking {
        val server = MockWebServer()
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        server.start(InetAddress.getByName("127.0.0.1"), 0)
        server.enqueue(MockResponse().setResponseCode(201).setBody(
            """{"upload_id":"upload-1","upload_url":"${server.url("uploads/opaque-capability")}","expires_at":"2026-10-20T11:00:00Z"}""",
        ))
        server.enqueue(MockResponse().setResponseCode(204))
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"id":"file-1","storage_status":"available","content_type":"image/jpeg","size_bytes":3}"""))
        server.enqueue(MockResponse().setResponseCode(201).setBody(
            """{"id":"image-1","record_id":"record-1","position":0,"record_version":4,"image_set_version":1,"file_status":"available","created_at":"2026-10-20T10:00:00Z"}""",
        ))
        try {
            val retrofitOrigin = server.url("api/v1/")
            val origin = retrofitOrigin.newBuilder().host("10.0.2.2").build()
            val emulatorClient = OkHttpClient.Builder().dns(object : Dns {
                override fun lookup(hostname: String) = listOf(InetAddress.getByName("127.0.0.1"))
            }).build()
            val api = Retrofit.Builder().baseUrl(retrofitOrigin).client(emulatorClient)
                .addConverterFactory(MoshiConverterFactory.create(moshi)).build().create(RecordImagesApi::class.java)
            val repository = RecordImagesRepository(SameOriginRecordImagesApi(api, origin, allowEmulatorLoopback = true))
            val result = repository.uploadAndAttach(PatientRecordType.DIET, "record-1", 3, 1,
                "create-key-123", "meal.jpg", "image/jpeg", byteArrayOf(1, 2, 3).toRequestBody("image/jpeg".toMediaType()), 3)
            assertTrue("Expected uploaded attachment, got $result", result is ApiResult.Success)
            val created = server.takeRequest()
            assertEquals("POST", created.method)
            assertEquals("/api/v1/files/uploads", created.path)
            assertTrue(created.body.readUtf8().contains("\"purpose\":\"diet_image\""))
            val upload = server.takeRequest()
            assertEquals("PUT", upload.method)
            assertEquals("/uploads/opaque-capability", upload.path)
            assertEquals("image/jpeg", upload.getHeader("Content-Type"))
            assertEquals("/api/v1/files/uploads/upload-1/complete", server.takeRequest().path)
            val attach = server.takeRequest()
            assertEquals("POST", attach.method)
            assertEquals("/api/v1/dietary-records/record-1/images", attach.path)
            val attachJson = attach.body.readUtf8()
            assertTrue(attachJson.contains("\"record_version\":3"))
            assertTrue(attachJson.contains("\"image_set_version\":1"))
            assertTrue(!attachJson.contains("\"position\""))
            assertEquals(4, (result as ApiResult.Success).value.recordVersion)
        } finally { server.shutdown() }
    }

    @Test fun serverConsentConflictDoesNotUploadAnyImageBytes() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(409).setHeader("Content-Type", "application/problem+json")
            .setBody("""{"type":"about:blank","title":"Request failed","status":409,"code":"CONSENT_REQUIRED","request_id":"req-1"}"""))
        server.start()
        try {
            val api = Retrofit.Builder().baseUrl(server.url("api/v1/"))
                .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
                .build().create(RecordImagesApi::class.java)
            val result = RecordImagesRepository(api).uploadAndAttach(PatientRecordType.STOOL, "record-2", 2, 1,
                "create-key-456", "stool.png", "image/png", byteArrayOf(1).toRequestBody("image/png".toMediaType()), 1)
            assertEquals("CONSENT_REQUIRED", (result as ApiResult.Failure).code)
            assertEquals(1, server.requestCount)
        } finally { server.shutdown() }
    }
}

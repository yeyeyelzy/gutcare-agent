package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.HttpUrl.Companion.toHttpUrl
import okio.Buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class MedicationRepositoryTest {
    @Test fun modelsMatchContractAndPendingRemainsPending() {
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        val plan = moshi.adapter(MedicationPlanDto::class.java).fromJson(
            """{"id":"plan-1","patient_id":"patient-1","medication_name":"Medicine","source_type":"manual","source_deleted":false,"confirmation_status":"pending","plan_status":"ended","record_version":3}""",
        )!!
        assertEquals("pending", plan.confirmationStatus)
        assertEquals("ended", plan.planStatus)
        val checkin = moshi.adapter(MedicationCheckinDto::class.java).fromJson(
            """{"id":"checkin-1","schedule_id":"schedule-1","local_date":"2026-10-20","scheduled_for":"2026-10-20T08:00:00Z","status":"pending","record_version":4}""",
        )!!
        assertEquals("pending", checkin.status)
        assertEquals(4, checkin.recordVersion)
    }

    @Test fun apiUsesFrozenRoutesIdempotencyVersionsAndIanaScheduleFields() = runBlocking {
        val server = MockWebServer()
        server.enqueue(json(201, planJson))
        server.enqueue(json(200, scheduleJson))
        server.enqueue(json(200, checkinJson))
        server.enqueue(MockResponse().setResponseCode(204))
        server.start()
        try {
            val api = api(server)
            api.createPlan("plan-key-123", MedicationPlanCreateDto("Medicine", sourceType = "manual"))
            api.createSchedule("plan-1", "schedule-key-123", MedicationScheduleWriteDto("08:30:00", "America/Los_Angeles", "FREQ=DAILY", "2026-10-20"))
            api.patchCheckin("checkin-1", MedicationCheckinUpdateDto(4, "taken", "2026-10-20T15:30:00Z"))
            api.deletePlan("plan-1", 5)

            val create = server.takeRequest()
            assertEquals("POST", create.method)
            assertEquals("/api/v1/medication-plans", create.path)
            assertEquals("plan-key-123", create.getHeader("Idempotency-Key"))
            assertFalse(create.body.readUtf8().contains("patient_id"))
            val schedule = server.takeRequest()
            assertEquals("/api/v1/medication-plans/plan-1/schedules", schedule.path)
            assertEquals("schedule-key-123", schedule.getHeader("Idempotency-Key"))
            val scheduleBody = schedule.body.readUtf8()
            assertTrue(scheduleBody.contains("\"timezone\":\"America/Los_Angeles\""))
            assertTrue(scheduleBody.contains("\"local_time\":\"08:30:00\""))
            val checkin = server.takeRequest()
            assertEquals("PATCH", checkin.method)
            assertEquals("/api/v1/medication-checkins/checkin-1", checkin.path)
            assertTrue(checkin.body.readUtf8().contains("\"record_version\":4"))
            val delete = server.takeRequest()
            assertEquals("/api/v1/medication-plans/plan-1?record_version=5", delete.path)
        } finally { server.shutdown() }
    }

    @Test fun versionConflictIsRetainedAsProblemCodeAndNeverRetriesWithStaleVersion() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(409).setHeader("Content-Type", "application/problem+json")
            .setBody("""{"type":"about:blank","title":"Conflict","status":409,"code":"RECORD_VERSION_CONFLICT","request_id":"request-f06"}"""))
        server.start()
        try {
            val result = MedicationRepository(api(server)).updateCheckin("checkin-1", MedicationCheckinUpdateDto(2, "taken"))
            assertEquals(ApiResult.Failure(409, "RECORD_VERSION_CONFLICT", "request-f06"), result)
            assertEquals(1, server.requestCount)
            assertTrue(server.takeRequest().body.readUtf8().contains("\"record_version\":2"))
        } finally { server.shutdown() }
    }

    @Test fun unauthorizedClearsSessionAndSignalsInvalidation() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(401).setHeader("Content-Type", "application/problem+json")
            .setBody("""{"type":"about:blank","title":"Unauthorized","status":401,"code":"AUTHENTICATION_REQUIRED","request_id":"request-f06"}"""))
        server.start()
        try {
            var cleared = false
            var invalidated = false
            val sessions = object : com.gutcare.app.core.security.SecureSessionStore {
                override suspend fun saveAccessToken(token: String) = Unit
                override suspend fun readAccessToken(): String? = "access"
                override suspend fun saveRefreshToken(token: String) = Unit
                override suspend fun readRefreshToken(): String? = "refresh"
                override suspend fun clear() { cleared = true }
            }
            val result = MedicationRepository(api(server), sessions) { invalidated = true }.todayCheckins()
            assertEquals(ApiResult.Failure(401, "AUTHENTICATION_REQUIRED", "request-f06"), result)
            assertTrue(cleared)
            assertTrue(invalidated)
        } finally { server.shutdown() }
    }

    @Test fun planPatchOmitsUntouchedFieldsAndCanExplicitlyClearValues() {
        val body = Buffer()
        MedicationPlanPatchDto(7, dosageText = MedicationNullablePatch(null)).toRequestBody().writeTo(body)
        val json = body.readUtf8()
        assertTrue(json.contains("\"record_version\":7"))
        assertTrue(json.contains("\"dosage_text\":null"))
        assertFalse(json.contains("medication_name"))
    }

    @Test fun invalidIdempotencyKeyDoesNotReachGateway() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val result = MedicationRepository(api(server)).createPlan("short", MedicationPlanCreateDto("Medicine", sourceType = "manual"))
            assertEquals(ApiResult.Failure(null, "IDEMPOTENCY_KEY_INVALID"), result)
            assertEquals(0, server.requestCount)
        } finally { server.shutdown() }
    }

    private fun json(code: Int, body: String) = MockResponse().setResponseCode(code).setHeader("Content-Type", "application/json").setBody(body)
    private fun api(server: MockWebServer): MedicationGateway = Retrofit.Builder()
        .baseUrl(server.url("api/v1/"))
        .client(OkHttpClient())
        .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
        .build().create(MedicationGateway::class.java)

    private val planJson = """{"id":"plan-1","patient_id":"patient-1","medication_name":"Medicine","source_type":"manual","source_deleted":false,"confirmation_status":"pending","plan_status":"ended","record_version":3}"""
    private val scheduleJson = """{"id":"schedule-1","plan_id":"plan-1","local_time":"08:30:00","timezone":"America/Los_Angeles","valid_from":"2026-10-20","enabled":true,"record_version":1}"""
    private val checkinJson = """{"id":"checkin-1","schedule_id":"schedule-1","local_date":"2026-10-20","scheduled_for":"2026-10-20T15:30:00Z","status":"taken","taken_at":"2026-10-20T15:30:00Z","record_version":5}"""
}

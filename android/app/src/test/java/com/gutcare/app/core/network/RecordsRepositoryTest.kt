package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import retrofit2.converter.moshi.MoshiConverterFactory
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.CancellationException
import java.lang.reflect.Proxy
import retrofit2.Retrofit
import com.gutcare.app.core.security.SecureSessionStore

class RecordsRepositoryTest {
    @Test fun recordResponseUsesFrozenOpenApiFieldsAndDefaultsAbsentAttachmentVersion() {
        val adapter = Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(RecordDto::class.java)
        val response = adapter.fromJson(
            """{"id":"record-1","record_version":1,"occurred_at":"2026-10-01T08:00:00Z","payload":{},"created_at":"2026-10-01T08:00:00Z","updated_at":"2026-10-01T08:00:00Z"}""",
        )
        assertEquals(0, response?.imageSetVersion)
    }

    @Test fun recordPageAcceptsOmittedNextCursor() {
        val adapter = Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(RecordPageDto::class.java)
        assertEquals(null, adapter.fromJson("""{"items":[]}""")?.nextCursor)
    }

    @Test fun cancellationIsPropagatedInsteadOfConvertedToAnApiFailure() = runBlocking {
        val api = Proxy.newProxyInstance(BusinessApi::class.java.classLoader, arrayOf(BusinessApi::class.java)) { _, _, _ ->
            throw CancellationException("cancelled by caller")
        } as BusinessApi
        val failure = runCatching { RecordsRepository(api).list(PatientRecordType.DIET) }.exceptionOrNull()
        assertTrue(failure is CancellationException)
    }

    @Test fun unauthorizedRecordResponseSignalsSessionInvalidation() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(401).setHeader("Content-Type", "application/problem+json")
            .setBody("""{"type":"about:blank","title":"Unauthorized","status":401,"code":"AUTHENTICATION_REQUIRED","request_id":"request-unauthorized"}"""))
        server.start()
        try {
            var access: String? = "synthetic-access"
            var refresh: String? = "synthetic-refresh"
            var events = 0
            val sessions = object : SecureSessionStore {
                override suspend fun saveAccessToken(token: String) { access = token }
                override suspend fun readAccessToken() = access
                override suspend fun saveRefreshToken(token: String) { refresh = token }
                override suspend fun readRefreshToken() = refresh
                override suspend fun clear() { access = null; refresh = null }
            }
            val result = RecordsRepository(testApi(server), sessions) {
                assertEquals(null, access)
                assertEquals(null, refresh)
                events++
            }.list(PatientRecordType.DIET)
            assertEquals(ApiResult.Failure(401, "AUTHENTICATION_REQUIRED", "request-unauthorized"), result)
            assertEquals(1, events)
            assertEquals(null, access)
            assertEquals(null, refresh)
        } finally { server.shutdown() }
    }

    @Test fun genericRecordRoutesAndRequestContractsAreExact() = runBlocking {
        val server = MockWebServer()
        repeat(5) { index ->
            val body = when (index) {
                0 -> """{"items":[],"next_cursor":null}"""
                1, 2, 3 -> recordJson
                else -> ""
            }
            server.enqueue(MockResponse().setResponseCode(if (index == 4) 204 else if (index == 1) 201 else 200).setBody(body))
        }
        server.start()
        try {
            val api = testApi(server)
            api.listRecords("diet-records", "cursor-token", 20, "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z")
            api.createRecord("stool-records", "idem-key-123", RecordWriteDto("2026-10-01T08:00:00+08:00", RecordPayloadDto(bristolType = 3)))
            api.getRecord("symptom-records", "record-1")
            api.updateRecord("symptom-records", "record-1", RecordPatchDto(2, "2026-10-01T08:00:00Z", RecordPayloadDto(symptomStatus = "relieved")))
            api.deleteRecord("diet-records", "record-1", 7)
            val requests = (0 until 5).map { server.takeRequest() }
            assertEquals("GET", requests[0].method)
            assertEquals("/api/v1/diet-records?cursor=cursor-token&limit=20&since=2026-10-01T00%3A00%3A00Z&until=2026-10-02T00%3A00%3A00Z", requests[0].path)
            assertEquals("POST", requests[1].method)
            assertEquals("idem-key-123", requests[1].getHeader("Idempotency-Key"))
            assertTrue(requests[1].body.readUtf8().contains("\"bristol_type\":3"))
            assertEquals("GET", requests[2].method)
            assertEquals("/api/v1/symptom-records/record-1", requests[2].path)
            assertEquals("PATCH", requests[3].method)
            assertTrue(requests[3].body.readUtf8().contains("\"record_version\":2"))
            assertEquals("DELETE", requests[4].method)
            assertEquals("/api/v1/diet-records/record-1?record_version=7", requests[4].path)
        } finally { server.shutdown() }
    }

    @Test fun moodAndHistoryUseIndependentRoutesAndRepeatCategoryQuery() = runBlocking {
        val server = MockWebServer()
        repeat(4) { index ->
            val body = when (index) {
                0 -> moodDetailJson
                1 -> """{"items":[],"next_cursor":null}"""
                2 -> """{"items":[],"next_cursor":null}"""
                else -> ""
            }
            server.enqueue(MockResponse().setResponseCode(if (index == 3) 204 else if (index == 0) 201 else 200).setBody(body))
        }
        server.start()
        try {
            val api = testApi(server)
            api.createMoodRecord("mood-key-123", MoodWriteDto("2026-10-01T08:00:00+08:00", 4, listOf("calm"), "private note"))
            api.listMoodRecords("mood-cursor", 10)
            api.historyTimeline(categories = listOf("diet", "mood"), since = "2026-10-01T00:00:00Z")
            api.deleteMoodRecord("mood-id", RecordVersionRequestDto(3))
            val requests = (0 until 4).map { server.takeRequest() }
            assertEquals("/api/v1/mood-records", requests[0].path)
            assertEquals("mood-key-123", requests[0].getHeader("Idempotency-Key"))
            assertEquals("/api/v1/mood-records?cursor=mood-cursor&limit=10", requests[1].path)
            assertEquals("/api/v1/history/timeline?category=diet&category=mood&since=2026-10-01T00%3A00%3A00Z", requests[2].path)
            assertEquals("DELETE", requests[3].method)
            assertTrue(requests[3].body.readUtf8().contains("\"record_version\":3"))
        } finally { server.shutdown() }
    }

    @Test fun repositoryPreservesConflictAndAuthorizationCodesWithoutRetainingBody() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(409).setHeader("Content-Type", "application/problem+json")
            .setBody("""{"type":"about:blank","title":"Conflict","status":409,"code":"RECORD_VERSION_CONFLICT","request_id":"request-1","detail":"sensitive free text"}"""))
        server.enqueue(MockResponse().setResponseCode(401).setHeader("Content-Type", "application/problem+json")
            .setBody("""{"type":"about:blank","title":"Auth","status":401,"code":"AUTHENTICATION_REQUIRED","request_id":"request-2"}"""))
        server.start()
        try {
            val repository = RecordsRepository(testApi(server))
            val conflict = repository.delete(PatientRecordType.DIET, "r", 1) as ApiResult.Failure
            assertEquals(409, conflict.status); assertEquals("RECORD_VERSION_CONFLICT", conflict.code); assertEquals("request-1", conflict.requestId)
            val unauthorized = repository.listMood() as ApiResult.Failure
            assertEquals(401, unauthorized.status); assertEquals("AUTHENTICATION_REQUIRED", unauthorized.code)
            assertEquals("/api/v1/diet-records/r?record_version=1", server.takeRequest().path)
        } finally { server.shutdown() }
    }

    @Test fun payloadSerializationOmitsUnselectedFieldsAndMoodListNeverCarriesNote() {
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        val record = moshi.adapter(RecordWriteDto::class.java).toJson(RecordWriteDto("t", RecordPayloadDto(bristolType = 2)))
        assertEquals("{\"occurred_at\":\"t\",\"payload\":{\"bristol_type\":2}}", record)
        val moodWrite = moshi.adapter(MoodWriteDto::class.java).toJson(MoodWriteDto("t", 2))
        assertTrue(moodWrite.contains("\"emotion_tags\":[]"))
        val moodSummary = moshi.adapter(MoodSummaryDto::class.java).toJson(MoodSummaryDto("id", "t", 2, emptyList(), 1, "c", "u"))
        assertTrue(!moodSummary.contains("note"))

        val clearNotePatch = okio.Buffer().also {
            MoodPatchDto(4, moodLevel = 2, note = ExplicitNullableString(null)).toRequestBody().writeTo(it)
        }.readUtf8()
        assertTrue(clearNotePatch, clearNotePatch.contains("\"note\":null"))
        assertTrue(!clearNotePatch.contains("\"value\""))
        val untouchedNotePatch = okio.Buffer().also {
            MoodPatchDto(4, moodLevel = 2).toRequestBody().writeTo(it)
        }.readUtf8()
        assertTrue(!untouchedNotePatch.contains("\"note\""))
    }

    @Test fun createKeyValidationMatchesGenericAndMoodContractBounds() = runBlocking {
        val server = MockWebServer()
        server.start()
        try {
            val repository = RecordsRepository(testApi(server))
            val recordBody = RecordWriteDto("t", RecordPayloadDto(bristolType = 1))
            assertEquals("IDEMPOTENCY_KEY_INVALID", (repository.create(PatientRecordType.STOOL, "short", recordBody) as ApiResult.Failure).code)
            assertEquals("IDEMPOTENCY_KEY_INVALID", (repository.createMood("", MoodWriteDto("t", 1)) as ApiResult.Failure).code)
            assertEquals(0, server.requestCount)
        } finally { server.shutdown() }
    }

    private val recordJson = """{"id":"record-1","record_version":1,"image_set_version":0,"occurred_at":"2026-10-01T08:00:00Z","payload":{},"created_at":"2026-10-01T08:00:00Z","updated_at":"2026-10-01T08:00:00Z"}"""
    private val moodDetailJson = """{"id":"mood-id","occurred_at":"2026-10-01T08:00:00Z","mood_level":4,"emotion_tags":["calm"],"record_version":1,"created_at":"2026-10-01T08:00:00Z","updated_at":"2026-10-01T08:00:00Z","note":null}"""

    private fun testApi(server: MockWebServer): BusinessApi = Retrofit.Builder()
        .baseUrl(server.url("api/v1/"))
        .client(OkHttpClient())
        .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
        .build()
        .create(BusinessApi::class.java)
}

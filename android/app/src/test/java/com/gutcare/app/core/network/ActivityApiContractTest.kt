package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class ActivityApiContractTest {
    @Test fun activityCrudMatchesOpenApiWithoutInventedCreateHeaders() = runBlocking {
        val server = MockWebServer()
        val record = """{"id":"a-1","record_version":1,"activity_type":"walking","description":null,"intensity":"moderate","subjective_feeling":"same","duration_minutes":30,"occurred_at":"2026-10-20T18:30:00+08:00","created_at":"2026-10-20T10:30:00Z","updated_at":"2026-10-20T10:30:00Z"}"""
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"items":[$record],"next_cursor":"opaque-cursor"}"""))
        server.enqueue(MockResponse().setResponseCode(201).setBody(record))
        server.enqueue(MockResponse().setResponseCode(200).setBody(record))
        server.enqueue(MockResponse().setResponseCode(200).setBody(record))
        server.enqueue(MockResponse().setResponseCode(204))
        server.start()
        try {
            val api = Retrofit.Builder().baseUrl(server.url("api/v1/")).client(OkHttpClient())
                .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
                .build().create(BusinessApi::class.java)
            assertEquals(1, api.listActivityRecords(limit = 50).body()?.items?.size)
            api.createActivityRecord(ActivityWriteDto("walking", null, "moderate", "same", 30, "2026-10-20T18:30:00+08:00"))
            api.getActivityRecord("a-1")
            api.patchActivityRecord("a-1", ActivityPatchDto(1, "walking", null, "moderate", "same", 45, "2026-10-20T18:30:00+08:00").toRequestBody())
            api.deleteActivityRecord("a-1", RecordVersionRequestDto(2))
            val requests = (0..4).map { server.takeRequest() }
            assertEquals("GET", requests[0].method)
            assertEquals("/api/v1/activity-records?limit=50", requests[0].path)
            assertEquals("POST", requests[1].method)
            assertEquals(null, requests[1].getHeader("Idempotency-Key"))
            assertTrue(requests[1].body.readUtf8().contains("\"activity_type\":\"walking\""))
            assertEquals("GET", requests[2].method)
            assertEquals("/api/v1/activity-records/a-1", requests[2].path)
            assertEquals("PATCH", requests[3].method)
            val patch = requests[3].body.readUtf8()
            assertTrue(patch.contains("\"record_version\":1"))
            assertTrue(patch.contains("\"description\":null"))
            assertFalse(patch.contains("patient_id"))
            assertEquals("DELETE", requests[4].method)
            assertEquals("/api/v1/activity-records/a-1", requests[4].path)
            assertEquals("{\"record_version\":2}", requests[4].body.readUtf8())
        } finally { server.shutdown() }
    }
}

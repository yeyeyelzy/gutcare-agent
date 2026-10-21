package com.gutcare.app.core.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class NotificationApiContractTest {
    @Test fun repositoryUsesFrozenNotificationRoutesFiltersBatchBodyAndPreferenceDto() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"items":[],"next_cursor":"next"}"""))
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"items":[]}"""))
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ordinary_in_app_enabled":false,"quiet_start":"22:00:00","quiet_end":"07:00:00","timezone":"Asia/Shanghai"}"""))
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"type":"about:blank","title":"Unauthorized","status":401,"code":"UNAUTHORIZED"}"""))
        server.start()
        try {
            val api = Retrofit.Builder().baseUrl(server.url("api/v1/"))
                .client(OkHttpClient())
                .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
                .build().create(NotificationApi::class.java)
            var invalidated = false
            val repository = NotificationRepository(api, onSessionInvalidated = { invalidated = true })

            val page = repository.list(cursor = "opaque/+", category = "analysis", unreadOnly = true)
            assertTrue(page is ApiResult.Success)
            assertEquals("next", (page as ApiResult.Success<NotificationPageDto>).value.nextCursor)
            repository.markReadBatch(listOf("00000000-0000-4000-8000-000000000001"))
            repository.updatePreferences(NotificationPreferenceDto(false, "22:00:00", "07:00:00", "Asia/Shanghai"))
            val unauthorized = repository.unreadCount()
            assertTrue(unauthorized is ApiResult.Failure && unauthorized.status == 401)
            assertTrue(invalidated)

            val list = server.takeRequest()
            assertEquals("GET", list.method)
            assertEquals("/api/v1/notifications?cursor=opaque%2F%2B&limit=20&category=analysis&unread_only=true", list.path)
            val batch = server.takeRequest()
            assertEquals("POST", batch.method)
            assertEquals("/api/v1/notifications/read-batch", batch.path)
            assertEquals("{\"notification_ids\":[\"00000000-0000-4000-8000-000000000001\"]}", batch.body.readUtf8())
            val prefs = server.takeRequest()
            assertEquals("PUT", prefs.method)
            assertEquals("/api/v1/notifications/preferences", prefs.path)
            val preferencesBody = prefs.body.readUtf8()
            assertTrue(preferencesBody.contains("\"ordinary_in_app_enabled\":false"))
            assertTrue(preferencesBody.contains("\"timezone\":\"Asia/Shanghai\""))
            assertEquals("GET", server.takeRequest().method)
        } finally { server.shutdown() }
    }
}

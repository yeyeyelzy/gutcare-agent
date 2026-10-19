package com.gutcare.app.core.network

import com.gutcare.app.core.security.SecureSessionStore
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class AuthSessionRepositoryTest {
    @Test fun registerUsesOnlyFrozenFieldsAndConfirmationStaysLocal() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(MockResponse().setResponseCode(202).setBody("""{"operation_id":"op-1","status":"accepted"}"""))
            val repository = repository(server, FakeSessions(), RegistrationNoticeProvider {
                RegistrationNoticeVersions("privacy-v2", "health-v3")
            })
            assertTrue(repository.register("a@example.test", "a long password", "a long password", 1990) is AuthWorkflowResult.Accepted)
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/api/v1/auth/register", request.path)
            val body = request.body.readUtf8()
            assertTrue(body.contains("\"birth_year\":1990"))
            assertTrue(body.contains("\"privacy_policy_version\":\"privacy-v2\""))
            assertTrue(body.contains("\"health_data_processing_consent\":true"))
            assertFalse(body.contains("confirm"))
            assertFalse(body.contains("sha256"))
            assertFalse(body.contains("notice_summary"))
        }
    }

    @Test fun loginStoresTokensThenLoadsProfileAndProfile404ClearsSessionWithRequestId() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(tokenResponse())
            server.enqueue(MockResponse().setResponseCode(404).setHeader("Content-Type", "application/problem+json")
                .setBody(problem(404, "RESOURCE_NOT_FOUND", "request-404")))
            val sessions = FakeSessions()
            val result = repository(server, sessions).login("a@example.test", "password")
            assertEquals(AuthWorkflowResult.Failure(404, "PROFILE_BOOTSTRAP_FAILED", "request-404"), result)
            assertEquals("/api/v1/auth/login", server.takeRequest().path)
            assertEquals("/api/v1/patients/me", server.takeRequest().path)
            assertNull(sessions.access)
            assertNull(sessions.refresh)
        }
    }

    @Test fun invalidLoginTokenPairIsRejectedBeforeStorageOrProfileBootstrap() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(tokenResponse("short", "refresh-token-123456789", tokenType = "bearer"))
            val sessions = FakeSessions()
            val result = repository(server, sessions).login("a@example.test", "password")
            assertEquals(AuthWorkflowResult.Failure(200, "INVALID_RESPONSE"), result)
            assertEquals("/api/v1/auth/login", server.takeRequest().path)
            assertEquals(1, server.requestCount)
            assertNull(sessions.access)
            assertNull(sessions.refresh)
        }
    }

    @Test fun loginPairWriteFailureClearsSessionAndDoesNotBootstrapProfile() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(tokenResponse())
            val sessions = FakeSessions().apply {
                access = "old-access"
                refresh = "old-refresh"
                failAccessWrite = true
            }
            val failure = runCatching { repository(server, sessions).login("a@example.test", "password") }.exceptionOrNull()
            assertNotNull(failure)
            assertEquals("/api/v1/auth/login", server.takeRequest().path)
            assertEquals(1, server.requestCount)
            assertNull(sessions.access)
            assertNull(sessions.refresh)
        }
    }

    @Test fun invalidRefreshRotationFailsClosedAndDoesNotLoadProfile() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(tokenResponse("access-token-123456789", "refresh-token-123456789", expiresIn = 0))
            val sessions = FakeSessions().apply { access = "old-access"; refresh = "old-refresh" }
            val result = repository(server, sessions).restoreSession()
            assertEquals(AuthWorkflowResult.Failure(200, "INVALID_RESPONSE"), result)
            assertEquals("/api/v1/auth/refresh", server.takeRequest().path)
            assertEquals(1, server.requestCount)
            assertNull(sessions.access)
            assertNull(sessions.refresh)
        }
    }

    @Test fun coldStartRotatesRefreshTokenBeforeProfileAndLogoutAlwaysClearsLocally() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(tokenResponse("access-2-123456789012345", "refresh-2-123456789012345"))
            server.enqueue(MockResponse().setResponseCode(200).setBody(profile()))
            val sessions = FakeSessions().apply { access = "old-access"; refresh = "old-refresh" }
            val repo = repository(server, sessions)
            assertTrue(repo.restoreSession() is AuthWorkflowResult.Success)
            val refresh = server.takeRequest()
            assertEquals("/api/v1/auth/refresh", refresh.path)
            assertEquals("""{"refresh_token":"old-refresh"}""", refresh.body.readUtf8())
            assertEquals("access-2-123456789012345", sessions.access)
            assertEquals("refresh-2-123456789012345", sessions.refresh)
            assertEquals("/api/v1/patients/me", server.takeRequest().path)
            server.enqueue(MockResponse().setResponseCode(204))
            assertTrue(repo.logout() is AuthWorkflowResult.Accepted)
            assertEquals("POST", server.takeRequest().method)
            assertNull(sessions.access)
            assertNull(sessions.refresh)
        }
    }

    private fun repository(server: MockWebServer, sessions: FakeSessions, notices: RegistrationNoticeProvider = RegistrationNoticeProvider { null }) =
        AuthSessionRepository(Retrofit.Builder().baseUrl(server.url("/api/v1/")).client(okhttp3.OkHttpClient())
            .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
            .build().create(BusinessApi::class.java), sessions, notices)

    private fun tokenResponse(
        access: String = "access-token-123456789",
        refresh: String = "refresh-token-123456789",
        tokenType: String = "Bearer",
        expiresIn: Int = 900,
    ) = MockResponse().setResponseCode(200)
        .setBody("""{"access_token":"$access","refresh_token":"$refresh","token_type":"$tokenType","expires_in":$expiresIn}""")
    private fun profile() = """{"id":"00000000-0000-4000-8000-000000000001","nickname":null,"birth_year":1990,"timezone":"Asia/Shanghai","profile_version":1}"""
    private fun problem(status: Int, code: String, requestId: String) = """{"type":"about:blank","title":"Failure","status":$status,"code":"$code","request_id":"$requestId"}"""

    private inline fun <T> MockWebServer.useServer(block: (MockWebServer) -> T): T {
        start()
        return try { block(this) } finally { shutdown() }
    }

    private class FakeSessions : SecureSessionStore {
        var access: String? = null
        var refresh: String? = null
        var failAccessWrite = false
        override suspend fun saveAccessToken(token: String) {
            if (failAccessWrite) error("simulated access-store failure")
            access = token
        }
        override suspend fun readAccessToken() = access
        override suspend fun saveRefreshToken(token: String) { refresh = token }
        override suspend fun readRefreshToken() = refresh
        override suspend fun clear() { access = null; refresh = null }
    }
}

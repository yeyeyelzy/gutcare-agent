package com.gutcare.app.core.network

import com.gutcare.app.core.security.SecureSessionStore
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import java.lang.reflect.Proxy
import retrofit2.Retrofit
import retrofit2.Response
import retrofit2.converter.moshi.MoshiConverterFactory

@OptIn(ExperimentalCoroutinesApi::class)
class AuthSessionRepositoryTest {
    @Test fun loginPublishesTheProfileReturnedByItsBootstrapWithoutRefetching() = runTest {
        val api = Proxy.newProxyInstance(BusinessApi::class.java.classLoader, arrayOf(BusinessApi::class.java)) { _, method, _ ->
            when (method.name) {
                "login" -> Response.success(TokenPairDto("access-token-123456789", "refresh-token-123456789", "Bearer", 900))
                "myProfile" -> Response.success(PatientProfileDto("patient-1", null, 1990, "Asia/Shanghai", 1))
                else -> error("Unexpected auth API call: ${method.name}")
            }
        } as BusinessApi
        val sessions = FakeSessions()
        var authenticatedProfile: PatientProfileDto? = null
        val workflow = RuntimeAuthWorkflow(AuthSessionRepository(api, sessions, RegistrationNoticeProvider { null }), this,
            { authenticatedProfile = it }, {})
        var state: com.gutcare.app.ui.auth.AuthOperationState? = null
        workflow.login("a@example.test", "password") { state = it }
        advanceUntilIdle()
        assertEquals("Asia/Shanghai", authenticatedProfile?.timezone)
        assertEquals(com.gutcare.app.ui.auth.AuthOperationState.Accepted, state)
        assertEquals("access-token-123456789", sessions.access)
    }

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

    @Test fun passwordResetRequestUsesFrozenUnauthenticatedRouteAndAcceptedResponse() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(MockResponse().setResponseCode(202).setBody("""{"operation_id":"op-reset","status":"accepted"}"""))
            server.enqueue(MockResponse().setResponseCode(202).setBody("""{"operation_id":"op-reset","status":"accepted"}"""))
            val repo = repository(server, FakeSessions())
            assertEquals(AuthWorkflowResult.Accepted("op-reset"), repo.requestPasswordReset("known@example.test"))
            assertEquals(AuthWorkflowResult.Accepted("op-reset"), repo.requestPasswordReset("unknown@example.test"))
            repeat(2) {
                val request = server.takeRequest()
                assertEquals("POST", request.method)
                assertEquals("/api/v1/auth/password/reset/request", request.path)
                assertEquals("""{"email":"${if (it == 0) "known@example.test" else "unknown@example.test"}"}""", request.body.readUtf8())
                assertNull(request.getHeader("Authorization"))
            }
        }
    }

    @Test fun passwordResetConfirmSendsTokenOnlyInBodyAndClearsLocalSessionOn204() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(MockResponse().setResponseCode(204))
            val sessions = FakeSessions().apply { access = "old-access"; refresh = "old-refresh" }
            var invalidations = 0
            val repo = AuthSessionRepository(api(server), sessions, RegistrationNoticeProvider { null }) { invalidations++ }
            assertEquals(AuthWorkflowResult.Accepted(""), repo.confirmPasswordReset("synthetic-reset-token", "synthetic-new-password"))
            val request = server.takeRequest()
            assertEquals("POST", request.method)
            assertEquals("/api/v1/auth/password/reset/confirm", request.path)
            val body = request.body.readUtf8()
            assertTrue("Reset credentials were not serialized to the contract fields",
                body.contains("\"token\":\"synthetic-reset-token\"") &&
                    body.contains("\"new_password\":\"synthetic-new-password\""),
            )
            assertNull(request.getHeader("Authorization"))
            assertNull(sessions.access)
            assertNull(sessions.refresh)
            assertEquals(1, invalidations)
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

    @Test fun rejectedRefreshInvalidatesTheProtectedSession() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(MockResponse().setResponseCode(401).setHeader("Content-Type", "application/problem+json")
                .setBody(problem(401, "AUTHENTICATION_REQUIRED", "request-401")))
            val sessions = FakeSessions().apply { access = "old-access"; refresh = "old-refresh" }
            var invalidations = 0
            val observed = AuthSessionRepository(api(server), sessions, RegistrationNoticeProvider { null }) { invalidations++ }
            assertEquals(AuthWorkflowResult.Failure(401, "AUTHENTICATION_REQUIRED", "request-401"), observed.restoreSession())
            assertNull(sessions.access)
            assertNull(sessions.refresh)
            assertEquals(1, invalidations)
            assertEquals("/api/v1/auth/refresh", server.takeRequest().path)
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

    @Test fun profileUpdateUsesCurrentVersionAndReturnsAuthoritativeProfile() = runBlocking {
        MockWebServer().useServer { server ->
            server.enqueue(MockResponse().setResponseCode(200).setBody(
                """{"id":"00000000-0000-4000-8000-000000000001","nickname":"小 GutCare","birth_year":1991,"timezone":"Asia/Shanghai","profile_version":2}""",
            ))
            val result = repository(server, FakeSessions()).updateMyProfile("小 GutCare", 1991, 1)
            assertEquals(AuthWorkflowResult.Success(PatientProfileDto("00000000-0000-4000-8000-000000000001", "小 GutCare", 1991, "Asia/Shanghai", 2)), result)
            val request = server.takeRequest()
            assertEquals("PATCH", request.method)
            assertEquals("/api/v1/patients/me", request.path)
            assertEquals("""{"profile_version":1,"nickname":"小 GutCare","birth_year":1991}""", request.body.readUtf8())
        }
    }

    private fun repository(server: MockWebServer, sessions: FakeSessions, notices: RegistrationNoticeProvider = RegistrationNoticeProvider { null }) =
        AuthSessionRepository(api(server), sessions, notices)

    private fun api(server: MockWebServer) = Retrofit.Builder().baseUrl(server.url("/api/v1/")).client(okhttp3.OkHttpClient())
            .addConverterFactory(MoshiConverterFactory.create(Moshi.Builder().add(KotlinJsonAdapterFactory()).build()))
            .build().create(BusinessApi::class.java)

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

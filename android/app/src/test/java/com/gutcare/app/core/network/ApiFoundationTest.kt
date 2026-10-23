package com.gutcare.app.core.network

import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class ApiFoundationTest {
    @Test fun endpointRequiresHttpsExceptExplicitEmulatorDebug() {
        assertEquals("https://api.example.test/v1/", ApiEndpoint.validate(ApiConfiguration("https://api.example.test/v1/", false, false)))
        assertEquals("http://10.0.2.2:8000/api/v1/", ApiEndpoint.validate(ApiConfiguration("http://10.0.2.2:8000/api/v1/", true, true)))
        assertThrows(IllegalArgumentException::class.java) { ApiEndpoint.validate(ApiConfiguration("http://10.0.2.2/v1/", false, true)) }
        assertThrows(IllegalArgumentException::class.java) { ApiEndpoint.validate(ApiConfiguration("http://localhost/v1/", true, true)) }
        assertThrows(IllegalArgumentException::class.java) { ApiEndpoint.validate(ApiConfiguration("http://10.0.2.2/v1/", true, false)) }
    }

    @Test fun problemDetailsParserReadsContractFieldsAndAllowsMalformedBodyToFailClosed() {
        val parsed = ProblemDetailsParser.parse("""{"type":"about:blank","title":"Request failed","status":401,"code":"AUTHENTICATION_REQUIRED","request_id":"00000000-0000-4000-8000-000000000401"}""")
        assertEquals("AUTHENTICATION_REQUIRED", parsed?.code)
        assertEquals(401, parsed?.status)
        assertNull(ProblemDetailsParser.parse("not-json"))
    }

    @Test fun bearerInterceptorPreservesExplicitAuthorizationAndInjectsOnlyWhenMissing() {
        val server = MockWebServer()
        server.enqueue(MockResponse())
        server.enqueue(MockResponse())
        server.start()
        try {
            val client = OkHttpClient.Builder().addInterceptor(BearerTokenInterceptor { "session-access" }).build()
            client.newCall(Request.Builder().url(server.url("/api/v1/items")).header("Authorization", "Basic explicit").build()).execute().close()
            assertEquals("Basic explicit", server.takeRequest().getHeader("Authorization"))
            client.newCall(Request.Builder().url(server.url("/api/v1/items")).build()).execute().close()
            assertEquals("Bearer session-access", server.takeRequest().getHeader("Authorization"))
        } finally {
            server.shutdown()
        }
    }

    @Test fun bearerInterceptorMatchesVersionedAuthRoutesAndKeepsLogoutAuthenticated() {
        val server = MockWebServer()
        repeat(8) { server.enqueue(MockResponse()) }
        server.start()
        try {
            val client = OkHttpClient.Builder().addInterceptor(BearerTokenInterceptor { "session-access" }).build()
            val routes = listOf(
                "/api/v1/auth/register",
                "/api/v1/auth/email/verify",
                "/api/v1/auth/login",
                "/api/v1/auth/refresh",
                "/api/v1/auth/password/reset/request",
                "/api/v1/auth/password/reset/confirm",
                "/api/v1/auth/logout",
                "/api/v1/patients/me",
            )
            routes.forEach { path ->
                client.newCall(Request.Builder().url(server.url(path)).build()).execute().close()
            }
            routes.forEachIndexed { index, path ->
                val request = server.takeRequest()
                assertEquals(path, request.path)
                if (index < 6) assertNull(request.getHeader("Authorization"))
                else assertEquals("Bearer session-access", request.getHeader("Authorization"))
            }
        } finally {
            server.shutdown()
        }
    }

    @Test fun concurrent401ResponsesShareOneRefresh() {
        val tokens = TestTokens()
        val refreshCount = AtomicInteger()
        val authenticator = SessionAuthenticator(tokens) {
            refreshCount.incrementAndGet()
            Thread.sleep(40)
            RefreshResult.Success(RefreshedTokens("access-new", "refresh-new"))
        }
        val start = CountDownLatch(1)
        val done = CountDownLatch(8)
        val pool = Executors.newFixedThreadPool(8)
        repeat(8) {
            pool.execute {
                start.await()
                authenticator.authenticate(null, unauthorized("access-old"))
                done.countDown()
            }
        }
        start.countDown()
        check(done.await(3, TimeUnit.SECONDS))
        pool.shutdownNow()
        assertEquals(1, refreshCount.get())
        assertEquals("access-new", tokens.currentAccessToken())
        assertEquals("refresh-new", tokens.currentRefreshToken())
    }

    @Test fun invalidRefreshCredentialsClearSession() {
        val tokens = TestTokens()
        val authenticator = SessionAuthenticator(tokens) { RefreshResult.InvalidCredentials }
        assertNull(authenticator.authenticate(null, unauthorized("access-old")))
        assertNull(tokens.currentAccessToken())
        assertNull(tokens.currentRefreshToken())
    }

    @Test fun transientRefreshFailurePreservesSessionForRetry() {
        val tokens = TestTokens()
        val authenticator = SessionAuthenticator(tokens) { RefreshResult.TransientFailure }
        assertNull(authenticator.authenticate(null, unauthorized("access-old")))
        assertEquals("access-old", tokens.currentAccessToken())
        assertEquals("refresh-old", tokens.currentRefreshToken())
    }

    @Test fun refreshIoExceptionPreservesSession() {
        val tokens = TestTokens()
        val authenticator = SessionAuthenticator(tokens) { throw java.io.IOException("network unavailable") }
        assertNull(authenticator.authenticate(null, unauthorized("access-old")))
        assertEquals("access-old", tokens.currentAccessToken())
        assertEquals("refresh-old", tokens.currentRefreshToken())
    }

    @Test fun refreshHttpFailuresClearOnlyForUnauthorized() {
        assertEquals(RefreshResult.InvalidCredentials, RefreshResult.forHttpFailure(401))
        assertEquals(RefreshResult.TransientFailure, RefreshResult.forHttpFailure(503))
        assertEquals(RefreshResult.TransientFailure, RefreshResult.forHttpFailure(429))
    }

    @Test fun authenticatorIgnoresPublicAuthAndRequestsWithoutSessionBearer() {
        val tokens = TestTokens()
        val calls = AtomicInteger()
        val authenticator = SessionAuthenticator(tokens) {
            calls.incrementAndGet()
            RefreshResult.Success(RefreshedTokens("access-new", "refresh-new"))
        }
        listOf(
            "/api/v1/auth/register", "/api/v1/auth/email/verify", "/api/v1/auth/login", "/api/v1/auth/refresh",
            "/api/v1/auth/password/reset/request", "/api/v1/auth/password/reset/confirm",
        )
            .forEach { path -> assertNull(authenticator.authenticate(null, unauthorized("access-old", path))) }
        assertNull(authenticator.authenticate(null, unauthorized(null, "/api/v1/auth/login")))
        assertNull(authenticator.authenticate(null, unauthorized(null)))
        assertNull(authenticator.authenticate(null, unauthorizedHeader("Basic explicit")))
        assertNull(authenticator.authenticate(null, unauthorized("unrecognized-token")))
        assertEquals(0, calls.get())
        assertEquals("access-old", tokens.currentAccessToken())
    }

    @Test fun expiredLogoutBearerUsesOneRefreshAndRetriesWithRotatedAccess() {
        val tokens = TestTokens()
        val refreshCount = AtomicInteger()
        val authenticator = SessionAuthenticator(tokens) {
            refreshCount.incrementAndGet()
            RefreshResult.Success(RefreshedTokens("access-new", "refresh-new"))
        }
        val retry = authenticator.authenticate(null, unauthorized("access-old", "/api/v1/auth/logout"))
        assertEquals(1, refreshCount.get())
        assertEquals("Bearer access-new", retry?.header("Authorization"))
        assertEquals("access-new", tokens.currentAccessToken())
        assertEquals("refresh-new", tokens.currentRefreshToken())
    }

    private fun unauthorized(token: String?, path: String = "/api/v1/items") = Response.Builder()
        .request(Request.Builder().url("https://api.example.test$path").apply {
            if (token != null) header("Authorization", "Bearer $token")
        }.build())
        .protocol(Protocol.HTTP_1_1).code(401).message("Unauthorized")
        .body("".toResponseBody())
        .build()

    private fun unauthorizedHeader(header: String) = Response.Builder()
        .request(Request.Builder().url("https://api.example.test/api/v1/items").header("Authorization", header).build())
        .protocol(Protocol.HTTP_1_1).code(401).message("Unauthorized")
        .body("".toResponseBody())
        .build()

    private class TestTokens : MutableAccessTokens {
        @Volatile private var access: String? = "access-old"
        @Volatile private var refresh: String? = "refresh-old"
        override val refreshLock = Any()
        override fun currentAccessToken() = access
        override fun currentRefreshToken() = refresh
        override fun isSessionAccessToken(token: String) = token == access || token == previous
        @Volatile private var previous: String? = null
        override fun replace(tokens: RefreshedTokens) { previous = access; access = tokens.accessToken; refresh = tokens.refreshToken }
        override fun clearTokens() { access = null; previous = null; refresh = null }
    }
}

package com.gutcare.app.core.network

import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route

fun interface AccessTokenProvider { fun currentAccessToken(): String? }

class BearerTokenInterceptor(private val tokens: AccessTokenProvider) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val token = tokens.currentAccessToken()
        val request = chain.request().newBuilder().apply {
            if (chain.request().header("Authorization") == null && !token.isNullOrBlank()) {
                header("Authorization", "Bearer $token")
            }
        }.build()
        return chain.proceed(request)
    }
}

data class RefreshedTokens(val accessToken: String, val refreshToken: String)

sealed interface RefreshResult {
    data class Success(val tokens: RefreshedTokens) : RefreshResult
    data object InvalidCredentials : RefreshResult
    data object TransientFailure : RefreshResult

    companion object {
        /** The refresh contract uses 401 for an invalid/revoked refresh credential. */
        fun forHttpFailure(statusCode: Int): RefreshResult =
            if (statusCode == 401) InvalidCredentials else TransientFailure
    }
}

/** Refreshes only session Bearers on business endpoints; concurrent 401s share one rotation attempt. */
class SessionAuthenticator(
    private val tokens: MutableAccessTokens,
    private val refresh: (String) -> RefreshResult,
) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        if (responseCount(response) >= 2) return null
        if ("auth" in response.request.url.pathSegments) return null
        val attempted = response.request.header("Authorization")
            ?.takeIf { it.startsWith("Bearer ") }
            ?.removePrefix("Bearer ")
            ?.takeIf { it.isNotBlank() }
            ?: return null
        if (!tokens.isSessionAccessToken(attempted)) return null

        synchronized(tokens.refreshLock) {
            val latest = tokens.currentAccessToken()
            if (!latest.isNullOrBlank() && latest != attempted) return response.request.withBearer(latest)
            val refreshToken = tokens.currentRefreshToken() ?: return null
            return when (val result = runCatching { refresh(refreshToken) }.getOrElse { RefreshResult.TransientFailure }) {
                is RefreshResult.Success -> {
                    tokens.replace(result.tokens)
                    response.request.withBearer(result.tokens.accessToken)
                }
                RefreshResult.InvalidCredentials -> {
                    tokens.clearTokens()
                    null
                }
                RefreshResult.TransientFailure -> null
            }
        }
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) { count++; prior = prior.priorResponse }
        return count
    }

    private fun Request.withBearer(token: String) = newBuilder().header("Authorization", "Bearer $token").build()
}

interface MutableAccessTokens : AccessTokenProvider {
    val refreshLock: Any
    fun currentRefreshToken(): String?
    fun isSessionAccessToken(token: String): Boolean
    fun replace(tokens: RefreshedTokens)
    fun clearTokens()
}

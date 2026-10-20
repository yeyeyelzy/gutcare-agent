package com.gutcare.app.core.network

import com.gutcare.app.core.security.SecureSessionStore
import kotlinx.coroutines.runBlocking
import retrofit2.Response

data class RegistrationNoticeVersions(val privacyPolicyVersion: String, val healthDataProcessingPolicyVersion: String)
fun interface RegistrationNoticeProvider { fun currentVersions(): RegistrationNoticeVersions? }

sealed interface AuthWorkflowResult {
    data class Success(val profile: PatientProfileDto) : AuthWorkflowResult
    data class Accepted(val operationId: String) : AuthWorkflowResult
    data class Failure(val status: Int?, val code: String?, val requestId: String? = null) : AuthWorkflowResult
}

/** Coordinates auth calls and profile bootstrap. Password confirmation is deliberately never serialized. */
class AuthSessionRepository(
    private val api: BusinessApi,
    private val sessions: SecureSessionStore,
    private val notices: RegistrationNoticeProvider,
    private val onSessionInvalidated: () -> Unit = {},
) {
    suspend fun register(email: String, password: String, confirmPassword: String, birthYear: Int): AuthWorkflowResult {
        if (password != confirmPassword) return AuthWorkflowResult.Failure(null, "PASSWORD_CONFIRMATION_MISMATCH")
        val versions = notices.currentVersions() ?: return AuthWorkflowResult.Failure(null, "REGISTRATION_NOTICE_UNAVAILABLE")
        return api.register(RegisterRequest(email, password, birthYear, versions.privacyPolicyVersion, true,
            healthDataProcessingPolicyVersion = versions.healthDataProcessingPolicyVersion)).fold { response ->
            if (response.isSuccessful) response.body()?.takeIf { it.status == "accepted" }
                ?.let { AuthWorkflowResult.Accepted(it.operationId) }
                ?: AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
            else response.failure()
        }
    }

    suspend fun verifyEmail(token: String): AuthWorkflowResult = api.verifyEmail(VerifyEmailRequest(token)).fold { response ->
        if (response.isSuccessful) AuthWorkflowResult.Accepted("") else response.failure()
    }

    suspend fun requestPasswordReset(email: String): AuthWorkflowResult = api.requestPasswordReset(PasswordResetRequest(email)).fold { response ->
        if (response.code() != 202) return@fold if (response.isSuccessful) AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE") else response.failure()
        response.body()?.takeIf { it.status == "accepted" }
            ?.let { AuthWorkflowResult.Accepted(it.operationId) }
            ?: AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
    }

    suspend fun confirmPasswordReset(token: String, newPassword: String): AuthWorkflowResult =
        api.confirmPasswordReset(PasswordResetConfirmRequest(token, newPassword)).fold { response ->
            if (response.code() == 204) {
                sessions.clear()
                onSessionInvalidated()
                AuthWorkflowResult.Accepted("")
            } else if (response.isSuccessful) {
                AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
            } else {
                response.failure()
            }
        }

    suspend fun login(email: String, password: String): AuthWorkflowResult {
        val response = api.login(LoginRequest(email, password))
        if (!response.isSuccessful) return response.failure()
        val pair = response.body() ?: return AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
        if (!pair.isValidTokenPair()) return AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
        store(pair)
        return bootstrapProfile()
    }

    /** Cold start: rotate the persisted refresh token, then require the authoritative patient profile. */
    suspend fun restoreSession(): AuthWorkflowResult {
        val refresh = sessions.readRefreshToken() ?: return AuthWorkflowResult.Failure(null, "SESSION_UNAVAILABLE")
        val response = api.refresh(RefreshRequest(refresh))
        if (!response.isSuccessful) {
            if (response.code() == 401) {
                sessions.clear()
                onSessionInvalidated()
            }
            return response.failure()
        }
        val pair = response.body() ?: return AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
        if (!pair.isValidTokenPair()) {
            sessions.clear()
            return AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
        }
        store(pair)
        return bootstrapProfile()
    }

    suspend fun logout(): AuthWorkflowResult {
        val response = runCatching { api.logout() }.getOrNull()
        sessions.clear()
        return when {
            response == null -> AuthWorkflowResult.Failure(null, "NETWORK_ERROR")
            response.isSuccessful -> AuthWorkflowResult.Accepted("")
            else -> response.failure()
        }
    }

    /** Re-reads the authenticated patient's authoritative profile for protected profile surfaces. */
    suspend fun readMyProfile(): AuthWorkflowResult = bootstrapProfile()

    private suspend fun bootstrapProfile(): AuthWorkflowResult {
        val response = api.myProfile()
        if (response.isSuccessful) return response.body()?.let(AuthWorkflowResult::Success)
            ?: AuthWorkflowResult.Failure(response.code(), "INVALID_RESPONSE")
        val failure = response.failure()
        if (response.code() == 404) {
            sessions.clear()
            return AuthWorkflowResult.Failure(404, "PROFILE_BOOTSTRAP_FAILED", failure.requestId)
        }
        return failure
    }

    private suspend fun store(pair: TokenPairDto) {
        sessions.saveTokenPair(pair.accessToken, pair.refreshToken)
    }
}

private fun TokenPairDto.isValidTokenPair(): Boolean =
    tokenType == "Bearer" && accessToken.length >= 20 && refreshToken.length >= 20 && expiresIn >= 1

private suspend fun <T> Response<T>.fold(block: suspend (Response<T>) -> AuthWorkflowResult) = block(this)

private fun Response<*>.failure(): AuthWorkflowResult.Failure {
    val details = errorBody()?.let { ProblemDetailsParser.parse(it.string()) }
    return AuthWorkflowResult.Failure(code(), details?.code, details?.requestId)
}

/** Synchronous bridge used only inside OkHttp's Authenticator callback. Auth calls are on a plain client. */
class SecureSessionAccessTokens(
    private val sessions: SecureSessionStore,
    private val onSessionInvalidated: () -> Unit = {},
) : MutableAccessTokens {
    override val refreshLock: Any = Any()
    @Volatile private var priorAccessToken: String? = null
    override fun currentAccessToken(): String? = runBlocking { sessions.readAccessToken() }
    override fun currentRefreshToken(): String? = runBlocking { sessions.readRefreshToken() }
    override fun isSessionAccessToken(token: String): Boolean = token == currentAccessToken() || token == priorAccessToken
    override fun replace(tokens: RefreshedTokens) = runBlocking {
        val previous = sessions.readAccessToken()
        try {
            sessions.saveTokenPair(tokens.accessToken, tokens.refreshToken)
            priorAccessToken = previous
        } catch (failure: Throwable) {
            priorAccessToken = null
            try {
                sessions.clear()
            } catch (clearFailure: Throwable) {
                failure.addSuppressed(clearFailure)
            }
            throw failure
        }
    }
    override fun clearTokens() = runBlocking {
        priorAccessToken = null
        sessions.clear()
        onSessionInvalidated()
    }
}

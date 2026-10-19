package com.gutcare.app.core.network

import com.gutcare.app.core.security.SecureSecretStore

/** Access token remains memory-only; the rotating refresh token is encrypted in its own namespace. */
class KeystoreAccessTokens(private val secrets: SecureSecretStore) : MutableAccessTokens {
    @Volatile private var accessToken: String? = null
    @Volatile private var previousAccessToken: String? = null
    override val refreshLock: Any = Any()

    override fun currentAccessToken(): String? = accessToken
    override fun currentRefreshToken(): String? = secrets.get(SESSION, REFRESH)
    override fun isSessionAccessToken(token: String): Boolean = token == accessToken || token == previousAccessToken
    override fun replace(tokens: RefreshedTokens) {
        secrets.put(SESSION, REFRESH, tokens.refreshToken)
        previousAccessToken = accessToken
        accessToken = tokens.accessToken
    }
    override fun clearTokens() {
        accessToken = null
        previousAccessToken = null
        secrets.remove(SESSION, REFRESH)
    }

    private companion object {
        const val SESSION = "session"
        const val REFRESH = "refresh_token"
    }
}

package com.gutcare.app.core.security

/** Secret namespaces backed by authenticated encryption. Implementations must fail closed. */
interface SecureSecretStore {
    fun put(namespace: String, name: String, value: String)
    fun get(namespace: String, name: String): String?
    fun remove(namespace: String, name: String)
    fun clearNamespace(namespace: String)
}

interface SecureSessionStore {
    suspend fun saveAccessToken(token: String)
    suspend fun readAccessToken(): String?
    suspend fun saveRefreshToken(token: String)
    suspend fun readRefreshToken(): String?
    suspend fun clear()
}

/** Access credentials are process-memory only; refresh credentials are encrypted at rest. */
class DefaultSecureSessionStore(private val secrets: SecureSecretStore) : SecureSessionStore {
    @Volatile private var accessToken: String? = null

    override suspend fun saveAccessToken(token: String) { accessToken = token }
    override suspend fun readAccessToken(): String? = accessToken
    override suspend fun saveRefreshToken(token: String) = secrets.put(SESSION_NAMESPACE, REFRESH_TOKEN, token)
    override suspend fun readRefreshToken(): String? = secrets.get(SESSION_NAMESPACE, REFRESH_TOKEN)
    override suspend fun clear() {
        accessToken = null
        secrets.clearNamespace(SESSION_NAMESPACE)
    }

    private companion object {
        const val SESSION_NAMESPACE = "session"
        const val REFRESH_TOKEN = "refresh_token"
    }
}

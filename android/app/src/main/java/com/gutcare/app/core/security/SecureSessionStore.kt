package com.gutcare.app.core.security

/**
 * Boundary for session credentials. A production implementation must use Android Keystore-backed
 * encryption before authentication is connected; credentials must never be logged or placed in
 * navigation arguments, saved state, or ordinary preferences.
 */
interface SecureSessionStore {
    suspend fun saveAccessToken(token: String)
    suspend fun readAccessToken(): String?
    suspend fun clear()
}

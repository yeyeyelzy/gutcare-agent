package com.gutcare.app.core.security

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DefaultSecureSessionStoreTest {
    @Test fun refreshTokenIsNamespacedAndClearRemovesIt() = runBlocking {
        val secrets = FakeSecrets()
        val sessions = DefaultSecureSessionStore(secrets)
        sessions.saveAccessToken("short-lived")
        sessions.saveRefreshToken("refresh-secret")
        assertEquals("short-lived", sessions.readAccessToken())
        assertEquals("refresh-secret", sessions.readRefreshToken())
        sessions.clear()
        assertNull(sessions.readAccessToken())
        assertNull(sessions.readRefreshToken())
    }

    @Test fun accessTokenIsNotPersistedBySecretStore() = runBlocking {
        val secrets = FakeSecrets()
        DefaultSecureSessionStore(secrets).saveAccessToken("memory-only")
        assertEquals(emptyMap<String, String>(), secrets.values)
    }

    private class FakeSecrets : SecureSecretStore {
        val values = mutableMapOf<String, String>()
        override fun put(namespace: String, name: String, value: String) { values["$namespace/$name"] = value }
        override fun get(namespace: String, name: String) = values["$namespace/$name"]
        override fun remove(namespace: String, name: String) { values.remove("$namespace/$name") }
        override fun clearNamespace(namespace: String) { values.keys.removeAll { it.startsWith("$namespace/") } }
    }
}

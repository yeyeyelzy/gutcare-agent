package com.gutcare.app.core.security

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test
import com.gutcare.app.core.network.RefreshedTokens
import com.gutcare.app.core.network.SecureSessionAccessTokens

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

    @Test fun refreshWriteFailureClearsOldAndNewPairBeforePublishingAccess() = runBlocking {
        val secrets = FakeSecrets()
        val sessions = DefaultSecureSessionStore(secrets)
        sessions.saveTokenPair("old-access", "old-refresh")
        secrets.failPut = true
        assertThrows(IllegalStateException::class.java) {
            runBlocking { sessions.saveTokenPair("new-access-token-long-enough", "new-refresh-token-long-enough") }
        }
        assertNull(sessions.readAccessToken())
        assertNull(sessions.readRefreshToken())
    }

    @Test fun authenticatorPairWriteFailureClearsBothCredentials() = runBlocking {
        val secrets = FakeSecrets()
        val sessions = DefaultSecureSessionStore(secrets)
        sessions.saveTokenPair("old-access", "old-refresh")
        val tokens = SecureSessionAccessTokens(sessions)
        secrets.failPut = true
        assertThrows(IllegalStateException::class.java) {
            tokens.replace(RefreshedTokens("new-access-token-long-enough", "new-refresh-token-long-enough"))
        }
        assertNull(sessions.readAccessToken())
        assertNull(sessions.readRefreshToken())
    }

    private class FakeSecrets : SecureSecretStore {
        val values = mutableMapOf<String, String>()
        var failPut = false
        override fun put(namespace: String, name: String, value: String) {
            if (failPut) error("simulated encrypted-store failure")
            values["$namespace/$name"] = value
        }
        override fun get(namespace: String, name: String) = values["$namespace/$name"]
        override fun remove(namespace: String, name: String) { values.remove("$namespace/$name") }
        override fun clearNamespace(namespace: String) { values.keys.removeAll { it.startsWith("$namespace/") } }
    }
}

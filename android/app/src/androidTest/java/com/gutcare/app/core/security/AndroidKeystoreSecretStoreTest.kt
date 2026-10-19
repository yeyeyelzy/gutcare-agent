package com.gutcare.app.core.security

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AndroidKeystoreSecretStoreTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test fun encryptsReadsAndRemovesNamespacedSecrets() {
        val store = AndroidKeystoreSecretStore(context)
        store.put("privacy", "logout_receipt", "receipt-secret")
        assertEquals("receipt-secret", store.get("privacy", "logout_receipt"))
        val persisted = context.getSharedPreferences("gutcare_encrypted_secrets", Context.MODE_PRIVATE).getString("privacy/logout_receipt", "")
        assertEquals("v1", persisted!!.substringBefore(':'))
        org.junit.Assert.assertFalse(persisted!!.contains("receipt-secret"))
        store.clearNamespace("privacy")
        assertNull(store.get("privacy", "logout_receipt"))
    }

    @Test fun corruptedCiphertextIsDeletedAndReturnsNoSecret() {
        val store = AndroidKeystoreSecretStore(context)
        val prefs = context.getSharedPreferences("gutcare_encrypted_secrets", Context.MODE_PRIVATE)
        prefs.edit().putString("session/refresh_token", "tampered-value").commit()
        assertNull(store.get("session", "refresh_token"))
        assertNull(prefs.getString("session/refresh_token", null))
    }

    @Test fun ciphertextCannotBeMovedToAnotherNamespaceKey() {
        val store = AndroidKeystoreSecretStore(context)
        val prefs = context.getSharedPreferences("gutcare_encrypted_secrets", Context.MODE_PRIVATE)
        store.put("session", "refresh_token", "refresh-secret")
        val ciphertext = prefs.getString("session/refresh_token", null)
        prefs.edit().putString("privacy/logout_receipt", ciphertext).commit()

        assertNull(store.get("privacy", "logout_receipt"))
        assertNull(prefs.getString("privacy/logout_receipt", null))
        assertEquals("refresh-secret", store.get("session", "refresh_token"))
    }

    @Test fun legacyUnversionedCiphertextIsDeletedRatherThanReadWithoutAad() {
        val store = AndroidKeystoreSecretStore(context)
        val prefs = context.getSharedPreferences("gutcare_encrypted_secrets", Context.MODE_PRIVATE)
        prefs.edit().putString("session/refresh_token", "nonce:ciphertext").commit()

        assertNull(store.get("session", "refresh_token"))
        assertNull(prefs.getString("session/refresh_token", null))
    }
}

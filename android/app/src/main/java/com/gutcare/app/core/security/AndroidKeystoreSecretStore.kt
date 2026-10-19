package com.gutcare.app.core.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.content.Context
import android.content.SharedPreferences
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Stores only AES-GCM ciphertext in private preferences; plaintext is never logged or persisted. */
// Synchronous commits are intentional: callers must know a secret write or deletion reached disk.
@Suppress("ApplySharedPref", "UseKtx")
class AndroidKeystoreSecretStore(context: Context) : SecureSecretStore {
    private val preferences: SharedPreferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    override fun put(namespace: String, name: String, value: String) {
        require(namespace.isNotBlank() && name.isNotBlank())
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        cipher.updateAAD(keyBytes(namespace, name))
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val packed = "$FORMAT_VERSION:${Base64.encodeToString(cipher.iv, Base64.NO_WRAP)}:${Base64.encodeToString(encrypted, Base64.NO_WRAP)}"
        check(preferences.edit().putString(storageKey(namespace, name), packed).commit())
    }

    override fun get(namespace: String, name: String): String? {
        val key = storageKey(namespace, name)
        val packed = preferences.getString(key, null) ?: return null
        return try {
            val parts = packed.split(':', limit = 3)
            // Pre-versioned ciphertext used no AAD, so reject and delete it instead of guessing.
            require(parts.size == 3 && parts[0] == FORMAT_VERSION)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(128, Base64.decode(parts[1], Base64.NO_WRAP)))
            cipher.updateAAD(keyBytes(namespace, name))
            String(cipher.doFinal(Base64.decode(parts[2], Base64.NO_WRAP)), Charsets.UTF_8)
        } catch (_: Exception) {
            // Unreadable or modified ciphertext is unusable. Remove it and return no secret.
            check(preferences.edit().remove(key).commit())
            null
        }
    }

    override fun remove(namespace: String, name: String) {
        check(preferences.edit().remove(storageKey(namespace, name)).commit())
    }

    override fun clearNamespace(namespace: String) {
        val prefix = "$namespace/"
        val editor = preferences.edit()
        preferences.all.keys.filter { it.startsWith(prefix) }.forEach(editor::remove)
        check(editor.commit())
    }

    private fun storageKey(namespace: String, name: String) = "$namespace/$name"
    private fun keyBytes(namespace: String, name: String) = storageKey(namespace, name).toByteArray(Charsets.UTF_8)

    private fun getOrCreateKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
        generator.init(
            KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val PREFERENCES = "gutcare_encrypted_secrets"
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val KEY_ALIAS = "gutcare_secrets_aes_gcm_v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val FORMAT_VERSION = "v1"
    }
}

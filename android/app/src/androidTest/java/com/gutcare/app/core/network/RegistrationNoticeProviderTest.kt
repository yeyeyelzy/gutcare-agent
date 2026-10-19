package com.gutcare.app.core.network

import androidx.test.core.app.ApplicationProvider
import android.content.Context
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RegistrationNoticeProviderTest {
    @Test fun generatedContractArtifactProvidesBothNoticesAndVersions() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val provider = AndroidRegistrationNoticeProvider(context)
        assertNotNull(provider.currentVersions())
        assertNotNull(provider.summaries())
        assertTrue(provider.summaries()!!.privacy.contains("test-only-privacy-v1"))
        assertTrue(provider.summaries()!!.healthData.contains("test-only-health-v1"))

        val raw = context.resources.openRawResource(
            context.resources.getIdentifier("registration_notices", "raw", context.packageName),
        ).bufferedReader(Charsets.UTF_8).use { it.readText() }
        assertTrue(RegistrationNoticeArtifactValidator.isValid(raw, debugBuild = true))
        assertTrue(!RegistrationNoticeArtifactValidator.isValid(raw.replace("e17c133d", "00000000"), debugBuild = true))
        assertTrue(!RegistrationNoticeArtifactValidator.isValid(raw, debugBuild = false))
    }
}

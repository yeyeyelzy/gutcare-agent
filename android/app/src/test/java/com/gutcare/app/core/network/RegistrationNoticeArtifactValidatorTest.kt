package com.gutcare.app.core.network

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class RegistrationNoticeArtifactValidatorTest {
    @Test fun checkedInArtifactPassesOnlyInDebugAndTamperingFailsClosed() {
        val artifactPath = System.getProperty("gutcare.registrationNoticesPath")
        val raw = artifactPath?.let(::File)?.takeIf { it.isFile }?.readText(Charsets.UTF_8)
        assertTrue("Registration notice artifact must be supplied from contracts", raw != null)
        assertTrue(RegistrationNoticeArtifactValidator.isValid(raw!!, debugBuild = true))
        assertFalse(RegistrationNoticeArtifactValidator.isValid(raw, debugBuild = false))
        assertFalse(RegistrationNoticeArtifactValidator.isValid(raw.replace("e17c133d", "00000000"), debugBuild = true))
        assertFalse(RegistrationNoticeArtifactValidator.isValid(raw.replace("\n", "\r\n"), debugBuild = true))
    }

    @Test fun missingOrMalformedArtifactFailsClosed() {
        assertFalse(RegistrationNoticeArtifactValidator.isValid("", debugBuild = true))
        assertFalse(RegistrationNoticeArtifactValidator.isValid("{}", debugBuild = true))
        assertFalse(RegistrationNoticeArtifactValidator.isValid("not-json", debugBuild = true))
    }

    @Test fun testOnlyArtifactIsRejectedOutsideDebugBuilds() {
        // The validator rejects all checked-in development/test material for non-debug variants.
        assertFalse(RegistrationNoticeArtifactValidator.isValid("{}", debugBuild = false))
    }
}

package com.gutcare.app.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class AuthFailureReasonTest {
    @Test
    fun mapsOnlyExactAllowlistedBackendDetails() {
        assertEquals(
            AuthFailureReason.HEALTH_CONSENT_REQUIRED,
            AuthFailureReason.fromBackendDetail("Health data processing consent is required"),
        )
        assertEquals(
            AuthFailureReason.UNSUPPORTED_POLICY_VERSION,
            AuthFailureReason.fromBackendDetail("Unsupported consent policy version"),
        )
        assertEquals(
            AuthFailureReason.POLICY_VERSION_MISMATCH,
            AuthFailureReason.fromBackendDetail("Consent policy version does not match"),
        )
        listOf(null, "HEALTH_CONSENT_REQUIRED", "private patient value", "").forEach {
            assertEquals(AuthFailureReason.OTHER, AuthFailureReason.fromBackendDetail(it))
        }
    }

    @Test
    fun parserRetainsOnlySafeMetadataAndReason() {
        val rawSecret = "patient@example.test and private validation input"
        val parsed = ProblemDetailsParser.parse(
            """{"type":"about:blank","title":"failed","status":422,"code":"VALIDATION_ERROR","request_id":"req-1","detail":"Consent policy version does not match","errors":[{"input":"$rawSecret","message":"$rawSecret"}]}""",
        )

        assertEquals(AuthFailureReason.POLICY_VERSION_MISMATCH, parsed?.reason)
        assertEquals(422, parsed?.status)
        assertFalse(parsed.toString().contains(rawSecret))
        assertFalse(parsed.toString().contains("\"input\":"))
        assertFalse(parsed.toString().contains("\"message\":"))
    }

    @Test
    fun unknownBackendDetailIsDiscarded() {
        val parsed = ProblemDetailsParser.parse(
            """{"status":422,"code":"VALIDATION_ERROR","request_id":"req-2","detail":"$rawDetail"}""",
        )

        assertEquals(AuthFailureReason.OTHER, parsed?.reason)
        assertFalse(parsed.toString().contains(rawDetail))
    }

    private val rawDetail = "validation failed for patient@example.test"
}

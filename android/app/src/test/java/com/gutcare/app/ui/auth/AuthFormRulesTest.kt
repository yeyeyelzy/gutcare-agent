package com.gutcare.app.ui.auth

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AuthFormRulesTest {
    @Test
    fun emailAndPasswordAreRequiredForCredentialStep() {
        val valid = RegistrationDraft(
            email = "person@example.test",
            password = "a-secure-pass",
            confirmPassword = "a-secure-pass",
            privacyPolicyAccepted = true,
        )

        assertTrue(AuthValidators.canContinueRegistration(valid))
        assertFalse(AuthValidators.canContinueRegistration(valid.copy(email = "invalid-email")))
        assertFalse(AuthValidators.canContinueRegistration(valid.copy(password = "short", confirmPassword = "short")))
        assertFalse(AuthValidators.canContinueRegistration(valid.copy(confirmPassword = "different-password")))
    }

    @Test
    fun healthConsentIsRequiredBeforeBirthYearCanBeSubmitted() {
        val credentials = RegistrationDraft(
            email = "person@example.test",
            password = "a-secure-pass",
            confirmPassword = "a-secure-pass",
            privacyPolicyAccepted = true,
            birthYear = "1990",
        )

        assertFalse(AuthValidators.canSubmitRegistration(credentials))
        assertTrue(AuthValidators.canSubmitRegistration(credentials.copy(healthDataProcessingAccepted = true)))
    }

    @Test
    fun publicAuthenticationCopyHasNoPhoneOrSmsTerminology() {
        val visibleCopy = AuthCopy.allVisibleCopy.joinToString(separator = " ")

        assertFalse(visibleCopy.contains("手机号"))
        assertFalse(visibleCopy.contains("短信"))
        assertFalse(visibleCopy.contains("SMS", ignoreCase = true))
    }

    @Test
    fun registrationDraftIsFullyClearedWhenFlowIsExited() {
        val draft = RegistrationDraft(
            email = "person@example.test",
            password = "a-secure-pass",
            confirmPassword = "a-secure-pass",
            privacyPolicyAccepted = true,
            healthDataProcessingAccepted = true,
            birthYear = "1990",
        )

        assertTrue(draft.clearForExit() == RegistrationDraft())
    }
}


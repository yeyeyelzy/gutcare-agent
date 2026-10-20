package com.gutcare.app.navigation

import com.gutcare.app.ui.auth.RegistrationDraft
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RoutePolicyTest {
    @Test
    fun publicSessionCannotEnterProtectedTabRoutes() {
        assertEquals(
            AppRoute.Welcome,
            RoutePolicy.allowedDestination(AppSessionState.Public, AppRoute.Today),
        )
        assertEquals(
            AppRoute.Analysis,
            RoutePolicy.allowedDestination(AppSessionState.Authenticated, AppRoute.Analysis),
        )
    }

    @Test
    fun registrationProfileRequiresCompletedCredentialStep() {
        val draft = RegistrationDraft(
            email = "person@example.test",
            password = "a-secure-pass",
            confirmPassword = "a-secure-pass",
            privacyPolicyAccepted = true,
        )

        assertTrue(RoutePolicy.canEnterProfile(draft))
        assertFalse(RoutePolicy.canEnterProfile(draft.copy(privacyPolicyAccepted = false)))
    }

    @Test
    fun registerSuccessTargetIsEmailVerificationNotProtectedHome() {
        assertTrue(RoutePolicy.shouldClearRegistrationDraftOnExit(AppRoute.EmailVerification))
        assertFalse(AppRoute.EmailVerification.value in AppRoute.protectedRoutes)
        assertTrue(AppRoute.Today.value in AppRoute.protectedRoutes)
    }

    @Test
    fun recordsAndHealthArchiveRoutesRemainProtected() {
        assertEquals(AppRoute.Welcome, RoutePolicy.allowedDestination(AppSessionState.Public, AppRoute.DietRecordNew))
        assertEquals(AppRoute.Welcome, RoutePolicy.allowedDestination(AppSessionState.Public, AppRoute.HealthArchive))
        assertEquals(AppRoute.MoodRecordNew, RoutePolicy.allowedDestination(AppSessionState.Authenticated, AppRoute.MoodRecordNew))
        listOf(
            AppRoute.DietRecords, AppRoute.StoolRecords, AppRoute.SymptomRecords, AppRoute.MoodRecords,
            AppRoute.DietRecordNew, AppRoute.StoolRecordNew, AppRoute.SymptomRecordNew, AppRoute.MoodRecordNew,
            AppRoute.HealthArchive,
        ).forEach { assertEquals(AppRoute.Welcome, RoutePolicy.allowedDestination(AppSessionState.Public, it)) }
    }
}

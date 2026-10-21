package com.gutcare.app.navigation

import com.gutcare.app.ui.auth.RegistrationDraft
import com.gutcare.app.ui.auth.AuthOperationState
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
    fun acceptedRegistrationDoesNotLetOldProfileGuardRaceDraftClear() {
        val clearedDraft = RegistrationDraft()

        assertTrue(RoutePolicy.shouldRedirectFromInvalidRegistrationProfile(clearedDraft, AuthOperationState.Idle))
        assertFalse(RoutePolicy.shouldRedirectFromInvalidRegistrationProfile(clearedDraft, AuthOperationState.Accepted))
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

    @Test
    fun newlyIntegratedBusinessRoutesAreProtectedAndHaveUniquePatterns() {
        val routes = listOf(
            AppRoute.FeatureDirectory, AppRoute.Medication, AppRoute.RiskAlerts,
            AppRoute.RiskAlertDetail, AppRoute.Trends, AppRoute.History,
            AppRoute.PrivacySettings, AppRoute.RecordImages,
            AppRoute.Notifications, AppRoute.NotificationDetail, AppRoute.NotificationPreferences, AppRoute.Activity,
        )
        routes.forEach { route ->
            assertTrue("${route.value} must be protected", route.value in AppRoute.protectedRoutes)
            assertEquals(AppRoute.Welcome, RoutePolicy.allowedDestination(AppSessionState.Public, route))
            assertEquals(route, RoutePolicy.allowedDestination(AppSessionState.Authenticated, route))
        }
        assertEquals("risk-alerts/abc", riskAlertDetailRoute("abc"))
        assertEquals("records/images/diet/abc", recordImagesRoute("diet", "abc"))
        assertEquals("notifications/c2e5c22e-8f26-4d12-9b68-2b71cdbd065f", notificationDetailRoute("c2e5c22e-8f26-4d12-9b68-2b71cdbd065f"))
        assertTrue(routes.map(AppRoute::value).distinct().size == routes.size)
    }
}

package com.gutcare.app.navigation

import com.gutcare.app.ui.auth.AuthValidators
import com.gutcare.app.ui.auth.AuthOperationState
import com.gutcare.app.ui.auth.RegistrationDraft

/** Typed route catalogue. Strings are exposed only at Navigation Compose's boundary. */
sealed class AppRoute(val value: String) {
    data object Welcome : AppRoute("welcome")
    data object Login : AppRoute("auth/login")
    data object RegisterCredentials : AppRoute("auth/register")
    data object RegisterProfile : AppRoute("auth/register/profile")
    data object EmailVerification : AppRoute("auth/email-verification")
    data object PasswordResetRequest : AppRoute("auth/password/reset")
    data object PasswordResetConfirm : AppRoute("auth/password/reset/confirm")
    data object Today : AppRoute("tabs/today")
    data object Records : AppRoute("tabs/records")
    data object Analysis : AppRoute("tabs/analysis")
    data object Me : AppRoute("tabs/me")
    data object DietRecords : AppRoute("records/diet")
    data object StoolRecords : AppRoute("records/stool")
    data object SymptomRecords : AppRoute("records/symptoms")
    data object MoodRecords : AppRoute("records/mood")
    data object DietRecordNew : AppRoute("records/diet/new?origin={origin}")
    data object StoolRecordNew : AppRoute("records/stool/new?origin={origin}")
    data object SymptomRecordNew : AppRoute("records/symptoms/new?origin={origin}")
    data object MoodRecordNew : AppRoute("records/mood/new?origin={origin}")
    data object RecordDetail : AppRoute("records/detail/{recordType}/{recordId}")
    data object RecordEdit : AppRoute("records/edit/{recordType}/{recordId}")
    data object HealthArchive : AppRoute("records/health-archive")
    data object MedicalDocumentDetail : AppRoute("records/medical-documents/{documentId}")
    data object FeatureDirectory : AppRoute("features")
    data object Medication : AppRoute("medication")
    data object Activity : AppRoute("activity?origin={origin}")
    data object RiskAlerts : AppRoute("risk-alerts")
    data object RiskAlertDetail : AppRoute("risk-alerts/{alertId}")
    data object Trends : AppRoute("trends")
    data object History : AppRoute("history")
    data object PrivacySettings : AppRoute("settings/privacy")
    data object Notifications : AppRoute("notifications")
    data object NotificationDetail : AppRoute("notifications/{notificationId}")
    data object NotificationPreferences : AppRoute("notifications/preferences")
    data object RecordImages : AppRoute("records/images/{recordType}/{recordId}")

    companion object {
        val publicRoutes = setOf(
            "welcome",
            "auth/login",
            "auth/register",
            "auth/register/profile",
            "auth/email-verification",
            "auth/password/reset",
            "auth/password/reset/confirm",
        )
        val protectedRoutes = setOf(
            "tabs/today", "tabs/records", "tabs/analysis", "tabs/me",
            "records/diet", "records/stool", "records/symptoms", "records/mood",
            "records/diet/new?origin={origin}", "records/stool/new?origin={origin}", "records/symptoms/new?origin={origin}", "records/mood/new?origin={origin}",
            "records/detail/{recordType}/{recordId}", "records/edit/{recordType}/{recordId}",
            "records/health-archive",
            "records/medical-documents/{documentId}",
            "features", "medication", "activity?origin={origin}", "risk-alerts", "risk-alerts/{alertId}",
            "trends", "history", "settings/privacy", "notifications", "notifications/{notificationId}", "notifications/preferences", "records/images/{recordType}/{recordId}",
        )
    }
}

private fun encodeRouteSegment(value: String) = value.replace("%", "%25").replace("/", "%2F").replace("?", "%3F")
fun recordDetailRoute(type: String, id: String): String = "records/detail/${encodeRouteSegment(type)}/${encodeRouteSegment(id)}"
fun recordEditRoute(type: String, id: String): String = "records/edit/${encodeRouteSegment(type)}/${encodeRouteSegment(id)}"
fun medicalDocumentDetailRoute(id: String): String = "records/medical-documents/${encodeRouteSegment(id)}"
fun riskAlertDetailRoute(id: String): String = "risk-alerts/${encodeRouteSegment(id)}"
fun recordImagesRoute(type: String, id: String): String = "records/images/${encodeRouteSegment(type)}/${encodeRouteSegment(id)}"
fun notificationDetailRoute(id: String): String = "notifications/${encodeRouteSegment(id)}"
fun recordFormRoute(route: AppRoute, origin: RecordEntryOrigin): String =
    "${route.value.substringBefore('?')}?origin=${origin.routeValue}"

fun activityRoute(origin: RecordEntryOrigin): String = recordFormRoute(AppRoute.Activity, origin)

enum class RecordEntryOrigin(val routeValue: String) {
    TODAY("today"),
    RECORDS("records");

    companion object {
        fun fromRouteValue(value: String?): RecordEntryOrigin =
            entries.firstOrNull { it.routeValue == value } ?: RECORDS
    }
}

enum class RootTab(
    val route: AppRoute,
    val title: String,
    val subtitle: String,
    val glyph: String,
) {
    Today(AppRoute.Today, "今日", "用于查看本人当天的业务摘要。", "·"),
    Records(AppRoute.Records, "记录", "用于进入本人记录分类。", "□"),
    Analysis(AppRoute.Analysis, "分析", "用于进入受保护的分析任务。", "⌁"),
    Me(AppRoute.Me, "我的", "用于管理本人账户与设置。", "○"),
}

sealed interface AppSessionState {
    data object Public : AppSessionState
    data object Authenticated : AppSessionState
}

object RoutePolicy {
    fun startDestination(sessionState: AppSessionState): AppRoute = when (sessionState) {
        AppSessionState.Public -> AppRoute.Welcome
        AppSessionState.Authenticated -> AppRoute.Today
    }

    fun allowedDestination(sessionState: AppSessionState, requested: AppRoute): AppRoute =
        if (requested.value in AppRoute.protectedRoutes && sessionState !is AppSessionState.Authenticated) {
            AppRoute.Welcome
        } else {
            requested
        }

    fun canEnterProfile(draft: RegistrationDraft): Boolean = AuthValidators.canContinueRegistration(draft)

    /**
     * Registration success clears the sensitive draft immediately, before Navigation Compose has
     * committed the email-verification destination. Do not let the old profile entry's guard race
     * that transition and redirect back to credentials.
     */
    fun shouldRedirectFromInvalidRegistrationProfile(
        draft: RegistrationDraft,
        registrationOperation: AuthOperationState,
    ): Boolean = !canEnterProfile(draft) && registrationOperation != AuthOperationState.Accepted

    fun shouldClearRegistrationDraftOnExit(destination: AppRoute): Boolean = destination in setOf(
        AppRoute.Welcome,
        AppRoute.Login,
        AppRoute.EmailVerification,
    )

    /** Safe destination used when a secondary route was restored or opened without an owner stack. */
    fun backFallback(currentRoute: String?, recordType: String? = null, recordId: String? = null, recordOrigin: String? = null): String? = when (currentRoute) {
        AppRoute.Login.value,
        AppRoute.RegisterCredentials.value,
        AppRoute.EmailVerification.value -> AppRoute.Welcome.value
        AppRoute.RegisterProfile.value -> AppRoute.RegisterCredentials.value
        AppRoute.PasswordResetRequest.value -> AppRoute.Login.value
        AppRoute.PasswordResetConfirm.value -> AppRoute.PasswordResetRequest.value
        AppRoute.FeatureDirectory.value,
        AppRoute.Medication.value,
        AppRoute.PrivacySettings.value -> AppRoute.Me.value
        AppRoute.Activity.value -> if (RecordEntryOrigin.fromRouteValue(recordOrigin) == RecordEntryOrigin.TODAY) {
            AppRoute.Today.value
        } else {
            AppRoute.Records.value
        }
        AppRoute.HealthArchive.value -> AppRoute.Records.value
        AppRoute.RiskAlerts.value -> AppRoute.Today.value
        AppRoute.RiskAlertDetail.value -> AppRoute.RiskAlerts.value
        AppRoute.Trends.value -> AppRoute.Analysis.value
        AppRoute.History.value -> AppRoute.Records.value
        AppRoute.Notifications.value -> AppRoute.Today.value
        AppRoute.NotificationDetail.value,
        AppRoute.NotificationPreferences.value -> AppRoute.Notifications.value
        AppRoute.RecordDetail.value -> recordType?.let(::recordCategoryRoute) ?: AppRoute.Records.value
        AppRoute.RecordEdit.value -> if (!recordType.isNullOrBlank() && !recordId.isNullOrBlank()) {
            recordDetailRoute(recordType, recordId)
        } else AppRoute.Records.value
        AppRoute.RecordImages.value -> if (!recordType.isNullOrBlank() && !recordId.isNullOrBlank()) {
            recordDetailRoute(recordType, recordId)
        } else AppRoute.Records.value
        AppRoute.MedicalDocumentDetail.value -> AppRoute.HealthArchive.value
        AppRoute.DietRecords.value,
        AppRoute.StoolRecords.value,
        AppRoute.SymptomRecords.value,
        AppRoute.MoodRecords.value -> AppRoute.Records.value
        AppRoute.DietRecordNew.value -> recordFormBackTarget(AppRoute.DietRecords, recordOrigin)
        AppRoute.StoolRecordNew.value -> recordFormBackTarget(AppRoute.StoolRecords, recordOrigin)
        AppRoute.SymptomRecordNew.value -> recordFormBackTarget(AppRoute.SymptomRecords, recordOrigin)
        AppRoute.MoodRecordNew.value -> recordFormBackTarget(AppRoute.MoodRecords, recordOrigin)
        else -> null
    }

    private fun recordCategoryRoute(recordType: String): String = when (recordType) {
        "diet" -> AppRoute.DietRecords.value
        "stool" -> AppRoute.StoolRecords.value
        "symptoms", "symptom" -> AppRoute.SymptomRecords.value
        "mood" -> AppRoute.MoodRecords.value
        else -> AppRoute.Records.value
    }

    private fun recordFormBackTarget(category: AppRoute, origin: String?): String =
        if (RecordEntryOrigin.fromRouteValue(origin) == RecordEntryOrigin.TODAY) AppRoute.Today.value else category.value
}


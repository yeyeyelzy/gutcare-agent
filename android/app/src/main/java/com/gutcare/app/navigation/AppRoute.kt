package com.gutcare.app.navigation

import com.gutcare.app.ui.auth.AuthValidators
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
    data object DietRecordNew : AppRoute("records/diet/new")
    data object StoolRecordNew : AppRoute("records/stool/new")
    data object SymptomRecordNew : AppRoute("records/symptoms/new")
    data object MoodRecordNew : AppRoute("records/mood/new")
    data object RecordDetail : AppRoute("records/detail/{recordType}/{recordId}")
    data object RecordEdit : AppRoute("records/edit/{recordType}/{recordId}")
    data object HealthArchive : AppRoute("records/health-archive")
    data object MedicalDocumentDetail : AppRoute("records/medical-documents/{documentId}")

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
            "records/diet/new", "records/stool/new", "records/symptoms/new", "records/mood/new",
            "records/detail/{recordType}/{recordId}", "records/edit/{recordType}/{recordId}",
            "records/health-archive",
            "records/medical-documents/{documentId}",
        )
    }
}

private fun encodeRouteSegment(value: String) = value.replace("%", "%25").replace("/", "%2F").replace("?", "%3F")
fun recordDetailRoute(type: String, id: String): String = "records/detail/${encodeRouteSegment(type)}/${encodeRouteSegment(id)}"
fun recordEditRoute(type: String, id: String): String = "records/edit/${encodeRouteSegment(type)}/${encodeRouteSegment(id)}"
fun medicalDocumentDetailRoute(id: String): String = "records/medical-documents/${encodeRouteSegment(id)}"

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

    fun shouldClearRegistrationDraftOnExit(destination: AppRoute): Boolean = destination in setOf(
        AppRoute.Welcome,
        AppRoute.Login,
        AppRoute.EmailVerification,
    )
}


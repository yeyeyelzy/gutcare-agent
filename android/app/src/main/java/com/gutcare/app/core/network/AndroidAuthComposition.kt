package com.gutcare.app.core.network

import android.content.Context
import com.gutcare.app.core.security.AndroidKeystoreSecretStore
import com.gutcare.app.core.security.DefaultSecureSessionStore
import com.gutcare.app.core.security.SecureSessionStore
import com.squareup.moshi.Json
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import java.security.MessageDigest
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import retrofit2.Response

/** Loads the exact consent artifact copied from contracts/consent by Gradle. */
class AndroidRegistrationNoticeProvider(context: Context) : RegistrationNoticeProvider {
    private val notices: List<RegistrationNotice> = runCatching {
        val raw = context.resources.openRawResource(
            context.resources.getIdentifier("registration_notices", "raw", context.packageName)
                .also { check(it != 0) },
        ).bufferedReader(Charsets.UTF_8).use { it.readText() }
        check(RegistrationNoticeArtifactValidator.isValid(raw, com.gutcare.app.BuildConfig.DEBUG))
        raw.let { Moshi.Builder().add(KotlinJsonAdapterFactory()).build().adapter(RegistrationNoticeArtifact::class.java).fromJson(it) }
            .also { artifact ->
                check(artifact != null)
            }?.notices ?: error("Invalid registration notice artifact")
    }.getOrElse { emptyList() }

    override fun currentVersions(): RegistrationNoticeVersions? {
        val privacy = notices.singleOrNull { it.consentType == "privacy_policy" } ?: return null
        val health = notices.singleOrNull { it.consentType == "health_data_processing" } ?: return null
        return RegistrationNoticeVersions(privacy.policyVersion, health.policyVersion)
    }

    fun summaries(): RegistrationNoticeSummaries? {
        val privacy = notices.singleOrNull { it.consentType == "privacy_policy" } ?: return null
        val health = notices.singleOrNull { it.consentType == "health_data_processing" } ?: return null
        return RegistrationNoticeSummaries("版本 ${privacy.policyVersion}\n${privacy.summary}", "版本 ${health.policyVersion}\n${health.summary}")
    }

}

internal object RegistrationNoticeArtifactValidator {
    fun isValid(raw: String, debugBuild: Boolean): Boolean = runCatching {
        check(debugBuild) // The only checked-in artifact is explicitly development/test-only.
        check(!raw.startsWith('\uFEFF') && !raw.contains("\r"))
        val artifact = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            .adapter(RegistrationNoticeArtifact::class.java).fromJson(raw) ?: error("missing artifact")
        check(artifact.schemaVersion == "1.0")
        check(artifact.artifactClassification == "development_test_only")
        check(artifact.legalApprovalStatus == "not_approved_for_production")
        check(artifact.notices.map { it.consentType }.toSet() == setOf("privacy_policy", "health_data_processing"))
        check(artifact.notices.size == 2)
        artifact.notices.forEach { notice ->
            check(notice.policyVersion.isNotBlank() && notice.summary.isNotBlank())
            check(notice.summarySha256 == sha256(notice.summary))
        }
        val privacy = artifact.notices.single { it.consentType == "privacy_policy" }
        val health = artifact.notices.single { it.consentType == "health_data_processing" }
        val configs = artifact.backendConfig
        check(configs.privacyPolicyVersion == privacy.policyVersion)
        check(configs.privacyPolicySummaryHash == privacy.summarySha256)
        check(configs.healthDataProcessingPolicyVersion == health.policyVersion)
        check(configs.healthDataProcessingSummaryHash == health.summarySha256)
        true
    }.getOrDefault(false)

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.replace("\r\n", "\n").replace('\r', '\n').toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}

data class RegistrationNoticeSummaries(val privacy: String, val healthData: String)
private data class RegistrationNoticeArtifact(
    @Json(name = "schema_version") val schemaVersion: String?,
    @Json(name = "artifact_classification") val artifactClassification: String?,
    @Json(name = "legal_approval_status") val legalApprovalStatus: String?,
    val notices: List<RegistrationNotice> = emptyList(),
    @Json(name = "backend_config") val backendConfig: NoticeBackendConfig = NoticeBackendConfig(),
)
private data class RegistrationNotice(
    @Json(name = "consent_type") val consentType: String,
    @Json(name = "policy_version") val policyVersion: String,
    val summary: String,
    @Json(name = "summary_sha256") val summarySha256: String,
)
private data class NoticeBackendConfig(
    @Json(name = "PRIVACY_POLICY_VERSION") val privacyPolicyVersion: String = "",
    @Json(name = "PRIVACY_POLICY_SUMMARY_HASH") val privacyPolicySummaryHash: String = "",
    @Json(name = "HEALTH_DATA_PROCESSING_POLICY_VERSION") val healthDataProcessingPolicyVersion: String = "",
    @Json(name = "HEALTH_DATA_PROCESSING_SUMMARY_HASH") val healthDataProcessingSummaryHash: String = "",
)

/** One encrypted session store and one token source feed both Retrofit clients. */
class AndroidAuthComposition(context: Context) {
    val sessions: SecureSessionStore = DefaultSecureSessionStore(AndroidKeystoreSecretStore(context.applicationContext))
    private val tokens = SecureSessionAccessTokens(sessions)
    private val plainApi = BusinessApiFactory.createPlainConfigured()
    private val authenticatedApi = BusinessApiFactory.createConfigured(
        accessTokens = tokens,
        authenticator = sessionAuthenticator(tokens, plainApi),
    )
    val notices = AndroidRegistrationNoticeProvider(context.applicationContext)
    val repository = AuthSessionRepository(BusinessApiRouter(plainApi, authenticatedApi), sessions, notices)
    fun workflow(scope: CoroutineScope, onAuthenticated: () -> Unit, onLoggedOut: () -> Unit) =
        RuntimeAuthWorkflow(repository, scope, onAuthenticated, onLoggedOut)

    suspend fun restore(): AuthWorkflowResult = repository.restoreSession()
    suspend fun logout(): AuthWorkflowResult = repository.logout()

    private class BusinessApiRouter(private val plain: BusinessApi, private val authenticated: BusinessApi) : BusinessApi {
        override suspend fun register(body: RegisterRequest) = plain.register(body)
        override suspend fun verifyEmail(body: VerifyEmailRequest) = plain.verifyEmail(body)
        override suspend fun login(body: LoginRequest) = plain.login(body)
        override suspend fun refresh(body: RefreshRequest) = plain.refresh(body)
        override suspend fun logout() = authenticated.logout()
        override suspend fun myProfile() = authenticated.myProfile()
    }
}

class RuntimeAuthWorkflow(
    private val repository: AuthSessionRepository,
    private val scope: CoroutineScope,
    private val onAuthenticated: () -> Unit,
    private val onLoggedOut: () -> Unit,
) : com.gutcare.app.ui.auth.AuthWorkflow {
    override fun login(email: String, password: String, onResult: (com.gutcare.app.ui.auth.AuthOperationState) -> Unit) = scope.launch {
        runCatching { repository.login(email, password) }
            .onSuccess { result ->
                if (result is AuthWorkflowResult.Success) onAuthenticated()
                onResult(result.toUiState())
            }
            .onFailure { onResult(networkError()) }
    }.let { }

    override fun register(draft: com.gutcare.app.ui.auth.RegistrationDraft, onResult: (com.gutcare.app.ui.auth.AuthOperationState) -> Unit) = scope.launch {
        if (!draft.privacyPolicyAccepted || !draft.healthDataProcessingAccepted) {
            onResult(com.gutcare.app.ui.auth.AuthOperationState.Error("REGISTRATION_CONSENT_REQUIRED"))
            return@launch
        }
        runCatching { repository.register(draft.email.trim(), draft.password, draft.confirmPassword, draft.birthYear.toInt()) }
            .onSuccess { onResult(it.toUiState()) }
            .onFailure { onResult(networkError()) }
    }.let { }

    override fun requestPasswordReset(email: String, onResult: (com.gutcare.app.ui.auth.AuthOperationState) -> Unit) =
        onResult(com.gutcare.app.ui.auth.AuthOperationState.Error("当前客户端暂未提供密码重置服务。"))

    override fun confirmPasswordReset(token: String, newPassword: String, onResult: (com.gutcare.app.ui.auth.AuthOperationState) -> Unit) =
        onResult(com.gutcare.app.ui.auth.AuthOperationState.Error("当前客户端暂未提供密码重置服务。"))

    override fun verifyEmail(token: String, onResult: (com.gutcare.app.ui.auth.AuthOperationState) -> Unit) {
        scope.launch {
            runCatching { repository.verifyEmail(token) }
                .onSuccess { onResult(it.toUiState()) }
                .onFailure { onResult(networkError()) }
        }
    }

    fun logout(onResult: (com.gutcare.app.ui.auth.AuthOperationState) -> Unit) {
        scope.launch {
            val result = runCatching { repository.logout() }
            onLoggedOut()
            result.onSuccess { onResult(it.toUiState()) }.onFailure { onResult(networkError()) }
        }
    }

    private fun AuthWorkflowResult.toUiState() = when (this) {
        is AuthWorkflowResult.Success -> com.gutcare.app.ui.auth.AuthOperationState.Accepted
        is AuthWorkflowResult.Accepted -> com.gutcare.app.ui.auth.AuthOperationState.Accepted
        is AuthWorkflowResult.Failure -> com.gutcare.app.ui.auth.AuthOperationState.Error(
            listOfNotNull(code ?: "REQUEST_FAILED", status?.let { "HTTP $it" }, requestId?.let { "request_id: $it" }).joinToString(" · "),
        )
    }

    private fun networkError() = com.gutcare.app.ui.auth.AuthOperationState.Error("NETWORK_ERROR · 请检查网络后重试。")
}

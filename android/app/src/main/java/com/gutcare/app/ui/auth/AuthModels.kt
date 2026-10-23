package com.gutcare.app.ui.auth

/**
 * These UI-only models deliberately have no dependency on Retrofit, secure storage, or a token
 * implementation.  Credentials only exist in the current composition state and are cleared when
 * a registration flow is exited.
 */
sealed interface AuthOperationState {
    data object Idle : AuthOperationState
    data object Loading : AuthOperationState
    data object Accepted : AuthOperationState
    data class Error(val message: String) : AuthOperationState
}

data class RegistrationDraft(
    val email: String = "",
    val password: String = "",
    val confirmPassword: String = "",
    val privacyPolicyAccepted: Boolean = false,
    val healthDataProcessingAccepted: Boolean = false,
    val birthYear: String = "",
) {
    fun clearForExit(): RegistrationDraft = RegistrationDraft()

    fun withoutPasswords(): RegistrationDraft = copy(password = "", confirmPassword = "")
}

object AuthValidators {
    private val emailPattern = Regex("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")

    fun isValidEmail(email: String): Boolean = email.length <= 254 && emailPattern.matches(email.trim())

    fun isValidPassword(password: String): Boolean = password.length in 12..128

    fun passwordsMatch(password: String, confirmation: String): Boolean = password == confirmation

    fun isValidBirthYear(year: String): Boolean = year.toIntOrNull()?.let { it in 1900..2100 } == true

    fun canContinueRegistration(draft: RegistrationDraft): Boolean =
        isValidEmail(draft.email) &&
            isValidPassword(draft.password) &&
            passwordsMatch(draft.password, draft.confirmPassword) &&
            draft.privacyPolicyAccepted

    fun canSubmitRegistration(draft: RegistrationDraft): Boolean =
        canContinueRegistration(draft) &&
            draft.healthDataProcessingAccepted &&
            isValidBirthYear(draft.birthYear)
}

/** Public authentication copy is centralised so the allowed identifiers are mechanically testable. */
object AuthCopy {
    const val emailLabel = "邮箱"
    const val passwordLabel = "密码"
    const val passwordConfirmationLabel = "确认密码"
    const val privacyConsent = "我已阅读并同意以上隐私告知"
    const val healthDataConsent = "我单独同意测试环境处理出生年份及健康记录"

    val allVisibleCopy: List<String> = listOf(
        emailLabel,
        passwordLabel,
        passwordConfirmationLabel,
        privacyConsent,
        healthDataConsent,
        "邮箱验证",
        "重置密码",
    )
}

/**
 * Boundary for the later core/network implementation.  It intentionally exposes outcomes, never
 * access tokens, refresh tokens, password values, or verification tokens as UI state.
 */
interface AuthWorkflow {
    fun login(email: String, password: String, onResult: (AuthOperationState) -> Unit)
    fun register(draft: RegistrationDraft, onResult: (AuthOperationState) -> Unit)
    fun verifyEmail(token: String, onResult: (AuthOperationState) -> Unit)
    fun requestPasswordReset(email: String, onResult: (AuthOperationState) -> Unit)
    fun confirmPasswordReset(token: String, newPassword: String, onResult: (AuthOperationState) -> Unit)
    fun updateProfile(nickname: String?, birthYear: Int, profileVersion: Int, onResult: (AuthOperationState) -> Unit)
}

/**
 * Safe development-only behaviour until the core API adapter is supplied. It never performs a
 * request, stores a field, or treats an attempted login as an authenticated session.
 */
object UnconnectedAuthWorkflow : AuthWorkflow {
    private const val unavailable = "认证服务尚未接入，请稍后重试。"

    override fun login(email: String, password: String, onResult: (AuthOperationState) -> Unit) {
        onResult(AuthOperationState.Error(unavailable))
    }

    override fun register(draft: RegistrationDraft, onResult: (AuthOperationState) -> Unit) {
        onResult(AuthOperationState.Error(unavailable))
    }

    override fun verifyEmail(token: String, onResult: (AuthOperationState) -> Unit) {
        onResult(AuthOperationState.Error(unavailable))
    }

    override fun requestPasswordReset(email: String, onResult: (AuthOperationState) -> Unit) {
        onResult(AuthOperationState.Error(unavailable))
    }

    override fun confirmPasswordReset(token: String, newPassword: String, onResult: (AuthOperationState) -> Unit) {
        onResult(AuthOperationState.Error(unavailable))
    }

    override fun updateProfile(nickname: String?, birthYear: Int, profileVersion: Int, onResult: (AuthOperationState) -> Unit) {
        onResult(AuthOperationState.Error(unavailable))
    }
}


package com.gutcare.app.ui.auth

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.gutcare.app.ui.design.FeatureGlyph
import com.gutcare.app.ui.design.FeatureRow
import com.gutcare.app.ui.design.GutCareBrand
import com.gutcare.app.ui.design.GutCareCard
import com.gutcare.app.ui.design.GutCareConsentRow
import com.gutcare.app.ui.design.GutCareDimensions
import com.gutcare.app.ui.design.GutCarePage
import com.gutcare.app.ui.design.GutCarePrimaryButton
import com.gutcare.app.ui.design.GutCareSecondaryButton
import com.gutcare.app.ui.design.GutCareTextField
import com.gutcare.app.ui.design.ScreenStatus
import com.gutcare.app.ui.design.WelcomeChecklistIllustration
import com.gutcare.app.ui.theme.GutCareBrandGreen
import com.gutcare.app.ui.theme.GutCareDanger
import com.gutcare.app.ui.theme.GutCareLine
import com.gutcare.app.ui.theme.GutCareMuted
import com.gutcare.app.ui.theme.GutCareOrangeSoft
import com.gutcare.app.ui.theme.GutCarePurpleSoft
import com.gutcare.app.ui.theme.GutCareSage

@Composable
fun WelcomeScreen(
    onLogin: () -> Unit,
    onRegister: () -> Unit,
    modifier: Modifier = Modifier,
) {
    GutCarePage(modifier = modifier.testTag("welcome_screen")) {
        Spacer(Modifier.height(44.dp))
        GutCareBrand(modifier = Modifier.fillMaxWidth(), center = true)
        Spacer(Modifier.height(44.dp))
        Text(
            text = "A LITTLE CARE, EVERY DAY",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.ExtraBold,
            color = GutCareBrandGreen,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            text = "日常有记录，\n随访有依据。",
            style = MaterialTheme.typography.displayLarge,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            text = "管理报告、记录生活、回顾变化",
            style = MaterialTheme.typography.bodyLarge,
            color = GutCareMuted,
        )
        WelcomeChecklistIllustration(
            modifier = Modifier
                .fillMaxWidth()
                .height(228.dp)
                .padding(top = 16.dp),
        )
        Spacer(Modifier.height(8.dp))
        FeatureRow(GutCareSage, FeatureGlyph.Archive, "档案由你确认", "重要信息，清楚可查")
        Spacer(Modifier.height(14.dp))
        FeatureRow(GutCareOrangeSoft, FeatureGlyph.Note, "记录随时补充", "饮食、排便、症状，随手记下")
        Spacer(Modifier.height(14.dp))
        FeatureRow(GutCarePurpleSoft, FeatureGlyph.Trend, "变化慢慢看见", "让每次随访，有迹可循")
        Spacer(Modifier.height(22.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            GutCarePrimaryButton(
                label = "注册",
                onClick = onRegister,
                modifier = Modifier.weight(1f),
                showTrailingArrow = true,
                testTag = "welcome_register",
            )
            GutCareSecondaryButton(
                label = "登录",
                onClick = onLogin,
                modifier = Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(16.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .testTag("welcome_terms"),
            horizontalArrangement = Arrangement.Center,
        ) {
            Text(
                text = "继续即表示同意",
                style = MaterialTheme.typography.bodyMedium,
                color = GutCareMuted,
            )
            Spacer(Modifier.width(4.dp))
            Text(
                text = "用户协议与隐私政策",
                style = MaterialTheme.typography.bodyMedium,
                color = GutCareBrandGreen,
            )
        }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
fun LoginScreen(
    operation: AuthOperationState,
    onLogin: (email: String, password: String) -> Unit,
    onBack: () -> Unit,
    onRegister: () -> Unit,
    onForgotPassword: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onBack)
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var passwordVisible by remember { mutableStateOf(false) }
    val canSubmit = AuthValidators.isValidEmail(email) && AuthValidators.isValidPassword(password)

    AuthPageHeader(
        title = "欢迎回来",
        subtitle = "登录后，档案与记录将同步到你的账户",
        onBack = onBack,
        modifier = modifier.testTag("login_screen"),
    ) {
        GutCareTextField(
            value = email,
            onValueChange = { email = it },
            label = AuthCopy.emailLabel,
            supportingText = if (email.isNotEmpty() && !AuthValidators.isValidEmail(email)) "请输入有效邮箱" else null,
            isError = email.isNotEmpty() && !AuthValidators.isValidEmail(email),
            testTag = "login_email",
        )
        Spacer(Modifier.height(14.dp))
        GutCareTextField(
            value = password,
            onValueChange = { password = it },
            label = AuthCopy.passwordLabel,
            supportingText = if (password.isNotEmpty() && !AuthValidators.isValidPassword(password)) "密码至少 12 位" else null,
            isError = password.isNotEmpty() && !AuthValidators.isValidPassword(password),
            password = true,
            passwordVisible = passwordVisible,
            onPasswordVisibilityChange = { passwordVisible = !passwordVisible },
            testTag = "login_password",
        )
        TextButton(
            onClick = onForgotPassword,
            modifier = Modifier
                .align(Alignment.End)
                .sizeIn(minWidth = GutCareDimensions.touchTarget, minHeight = GutCareDimensions.touchTarget)
                .semantics { contentDescription = "忘记密码" },
        ) {
            Text("忘记密码？", color = GutCareBrandGreen, style = MaterialTheme.typography.bodyMedium)
        }
        AuthOperationMessage(operation)
        Spacer(Modifier.height(12.dp))
        GutCarePrimaryButton(
            label = "登录",
            onClick = { onLogin(email.trim(), password) },
            enabled = canSubmit,
            loading = operation is AuthOperationState.Loading,
            testTag = "login_submit",
        )
        Spacer(Modifier.height(22.dp))
        InlineNavigationPrompt(prefix = "还没有账号？", action = "立即注册", onClick = onRegister)
    }
}

@Composable
fun RegisterCredentialsScreen(
    draft: RegistrationDraft,
    operation: AuthOperationState,
    onDraftChange: (RegistrationDraft) -> Unit,
    onContinue: () -> Unit,
    onBack: () -> Unit,
    onLogin: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onBack)
    var passwordVisible by remember { mutableStateOf(false) }
    var confirmationVisible by remember { mutableStateOf(false) }
    val emailInvalid = draft.email.isNotEmpty() && !AuthValidators.isValidEmail(draft.email)
    val passwordInvalid = draft.password.isNotEmpty() && !AuthValidators.isValidPassword(draft.password)
    val confirmationInvalid = draft.confirmPassword.isNotEmpty() && !AuthValidators.passwordsMatch(draft.password, draft.confirmPassword)

    AuthPageHeader(
        title = "创建账号",
        subtitle = "先设置登录方式，再完成健康数据处理同意",
        onBack = onBack,
        modifier = modifier.testTag("register_screen"),
    ) {
        GutCareTextField(
            value = draft.email,
            onValueChange = { onDraftChange(draft.copy(email = it)) },
            label = AuthCopy.emailLabel,
            supportingText = if (emailInvalid) "请输入有效邮箱" else null,
            isError = emailInvalid,
            testTag = "register_email",
        )
        Spacer(Modifier.height(14.dp))
        GutCareTextField(
            value = draft.password,
            onValueChange = { onDraftChange(draft.copy(password = it)) },
            label = "设置密码（至少 12 位）",
            supportingText = if (passwordInvalid) "密码长度应为 12 至 128 位" else null,
            isError = passwordInvalid,
            password = true,
            passwordVisible = passwordVisible,
            onPasswordVisibilityChange = { passwordVisible = !passwordVisible },
            testTag = "register_password",
        )
        Spacer(Modifier.height(14.dp))
        GutCareTextField(
            value = draft.confirmPassword,
            onValueChange = { onDraftChange(draft.copy(confirmPassword = it)) },
            label = AuthCopy.passwordConfirmationLabel,
            supportingText = if (confirmationInvalid) "两次输入的密码不一致" else null,
            isError = confirmationInvalid,
            password = true,
            passwordVisible = confirmationVisible,
            onPasswordVisibilityChange = { confirmationVisible = !confirmationVisible },
            testTag = "register_confirmation",
        )
        Spacer(Modifier.height(18.dp))
        GutCareCard(padding = 16.dp) {
            Text("隐私说明", style = MaterialTheme.typography.titleMedium)
            Text(
                "测试构建的告知版本会由后续认证适配器提供；正式发布须使用已审核的告知制品。",
                modifier = Modifier.padding(top = 6.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = GutCareMuted,
            )
            Spacer(Modifier.height(8.dp))
            GutCareConsentRow(
                checked = draft.privacyPolicyAccepted,
                onCheckedChange = { onDraftChange(draft.copy(privacyPolicyAccepted = it)) },
                description = AuthCopy.privacyConsent,
                testTag = "privacy_policy_consent",
            )
        }
        AuthOperationMessage(operation)
        Spacer(Modifier.height(16.dp))
        GutCarePrimaryButton(
            label = "继续",
            onClick = onContinue,
            enabled = AuthValidators.canContinueRegistration(draft),
            loading = operation is AuthOperationState.Loading,
            testTag = "register_continue",
        )
        Spacer(Modifier.height(22.dp))
        InlineNavigationPrompt(prefix = "已有账号？", action = "去登录", onClick = onLogin)
    }
}

@Composable
fun ProfileBootstrapScreen(
    draft: RegistrationDraft,
    operation: AuthOperationState,
    onDraftChange: (RegistrationDraft) -> Unit,
    onSubmit: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onBack)
    val birthYearInvalid = draft.birthYear.isNotEmpty() && !AuthValidators.isValidBirthYear(draft.birthYear)
    AuthPageHeader(
        title = "开始建档",
        subtitle = "完成必要信息后，我们会发送邮箱验证邮件",
        onBack = onBack,
        modifier = modifier.testTag("profile_bootstrap_screen"),
    ) {
        GutCareCard {
            Text("健康数据处理", style = MaterialTheme.typography.titleLarge)
            Text(
                "出生年份属于健康资料。请先阅读并单独同意，再填写这一必要信息。",
                modifier = Modifier.padding(top = 8.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = GutCareMuted,
            )
            Spacer(Modifier.height(12.dp))
            GutCareConsentRow(
                checked = draft.healthDataProcessingAccepted,
                onCheckedChange = {
                    onDraftChange(
                        if (it) draft.copy(healthDataProcessingAccepted = true) else draft.copy(
                            healthDataProcessingAccepted = false,
                            birthYear = "",
                        ),
                    )
                },
                description = AuthCopy.healthDataConsent,
                testTag = "health_data_consent",
            )
            if (draft.healthDataProcessingAccepted) {
                Spacer(Modifier.height(16.dp))
                GutCareTextField(
                    value = draft.birthYear,
                    onValueChange = { value -> onDraftChange(draft.copy(birthYear = value.filter(Char::isDigit).take(4))) },
                    label = "出生年份",
                    supportingText = if (birthYearInvalid) "请输入 1900 至 2100 的四位年份" else "仅收集年份，不收集完整出生日期",
                    isError = birthYearInvalid,
                    testTag = "birth_year",
                )
            }
        }
        Spacer(Modifier.height(18.dp))
        GutCareCard(padding = 16.dp) {
            Text("本阶段不收集", style = MaterialTheme.typography.titleMedium)
            Text(
                "真实姓名、性别、完整出生日期、检查报告和医疗图片将在认证后按需处理。",
                modifier = Modifier.padding(top = 5.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = GutCareMuted,
            )
        }
        AuthOperationMessage(operation)
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = "注册并发送验证邮件",
            onClick = onSubmit,
            enabled = AuthValidators.canSubmitRegistration(draft),
            loading = operation is AuthOperationState.Loading,
            testTag = "profile_submit",
        )
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
fun EmailVerificationScreen(
    operation: AuthOperationState,
    onGoToLogin: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onBack)
    AuthPageHeader(
        title = "验证邮箱",
        subtitle = "请在注册邮箱中打开验证链接。验证完成后，请使用邮箱和密码登录。",
        onBack = onBack,
        modifier = modifier.testTag("email_verification_screen"),
    ) {
        GutCareCard {
            Text("等待邮箱验证", style = MaterialTheme.typography.titleLarge)
            Text(
                "验证链接为一次性安全操作。本页面不会保存或展示验证令牌。",
                modifier = Modifier.padding(top = 8.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = GutCareMuted,
            )
            Spacer(Modifier.height(12.dp))
            ScreenStatus("认证服务接入后可显示发送与验证状态。")
        }
        AuthOperationMessage(operation)
        Spacer(Modifier.height(20.dp))
        GutCareSecondaryButton(
            label = "重新发送验证邮件",
            onClick = {},
            enabled = false,
        )
        Spacer(Modifier.height(12.dp))
        GutCarePrimaryButton(label = "我已完成验证，去登录", onClick = onGoToLogin)
    }
}

@Composable
fun PasswordResetRequestScreen(
    operation: AuthOperationState,
    onRequest: (String) -> Unit,
    onOpenConfirmation: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onBack)
    var email by remember { mutableStateOf("") }
    AuthPageHeader(
        title = "重置密码",
        subtitle = "输入注册邮箱，我们将发送重置说明。",
        onBack = onBack,
        modifier = modifier.testTag("password_reset_request_screen"),
    ) {
        GutCareTextField(
            value = email,
            onValueChange = { email = it },
            label = AuthCopy.emailLabel,
            supportingText = if (email.isNotEmpty() && !AuthValidators.isValidEmail(email)) "请输入有效邮箱" else null,
            isError = email.isNotEmpty() && !AuthValidators.isValidEmail(email),
            testTag = "reset_email",
        )
        Spacer(Modifier.height(12.dp))
        Text(
            "无论邮箱是否存在，服务端都会返回相同的受理结果。",
            style = MaterialTheme.typography.bodyMedium,
            color = GutCareMuted,
        )
        AuthOperationMessage(operation)
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = "发送重置说明",
            onClick = { onRequest(email.trim()) },
            enabled = AuthValidators.isValidEmail(email),
            loading = operation is AuthOperationState.Loading,
        )
        if (operation is AuthOperationState.Accepted) {
            Spacer(Modifier.height(12.dp))
            GutCareSecondaryButton(label = "我已收到重置链接", onClick = onOpenConfirmation)
        }
    }
}

@Composable
fun PasswordResetConfirmScreen(
    operation: AuthOperationState,
    onConfirm: (token: String, newPassword: String) -> Unit,
    onBack: () -> Unit,
    onGoToLogin: () -> Unit,
    modifier: Modifier = Modifier,
) {
    BackHandler(onBack = onBack)
    var token by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    val validPassword = AuthValidators.isValidPassword(password)
    val canSubmit = token.length >= 20 && validPassword && AuthValidators.passwordsMatch(password, confirmation)

    AuthPageHeader(
        title = "设置新密码",
        subtitle = "验证令牌只在当前页面内存中使用，不会被保存。",
        onBack = onBack,
        modifier = modifier.testTag("password_reset_confirm_screen"),
    ) {
        GutCareTextField(
            value = token,
            onValueChange = { token = it },
            label = "一次性验证令牌",
            supportingText = if (token.isNotEmpty() && token.length < 20) "令牌格式不完整" else null,
            isError = token.isNotEmpty() && token.length < 20,
            testTag = "reset_token",
        )
        Spacer(Modifier.height(14.dp))
        GutCareTextField(
            value = password,
            onValueChange = { password = it },
            label = "新密码（至少 12 位）",
            supportingText = if (password.isNotEmpty() && !validPassword) "密码长度应为 12 至 128 位" else null,
            isError = password.isNotEmpty() && !validPassword,
            password = true,
            testTag = "reset_new_password",
        )
        Spacer(Modifier.height(14.dp))
        GutCareTextField(
            value = confirmation,
            onValueChange = { confirmation = it },
            label = AuthCopy.passwordConfirmationLabel,
            supportingText = if (confirmation.isNotEmpty() && !AuthValidators.passwordsMatch(password, confirmation)) "两次输入的密码不一致" else null,
            isError = confirmation.isNotEmpty() && !AuthValidators.passwordsMatch(password, confirmation),
            password = true,
            testTag = "reset_confirmation",
        )
        AuthOperationMessage(operation)
        Spacer(Modifier.height(20.dp))
        GutCarePrimaryButton(
            label = "确认重置",
            onClick = { onConfirm(token, password) },
            enabled = canSubmit,
            loading = operation is AuthOperationState.Loading,
        )
        if (operation is AuthOperationState.Accepted) {
            Spacer(Modifier.height(12.dp))
            GutCareSecondaryButton(label = "返回登录", onClick = onGoToLogin)
        }
    }
}

@Composable
private fun AuthPageHeader(
    title: String,
    subtitle: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    GutCarePage(modifier = modifier) {
        Spacer(Modifier.height(28.dp))
        BackButton(onClick = onBack)
        Spacer(Modifier.height(48.dp))
        GutCareBrand(modifier = Modifier.fillMaxWidth(), center = true)
        Spacer(Modifier.height(40.dp))
        Text(
            text = title,
            modifier = Modifier.fillMaxWidth(),
            style = MaterialTheme.typography.displayLarge,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            text = subtitle,
            modifier = Modifier.fillMaxWidth(),
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            color = GutCareMuted,
        )
        Spacer(Modifier.height(36.dp))
        content()
        Spacer(Modifier.height(28.dp))
    }
}

@Composable
private fun BackButton(onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .sizeIn(minWidth = GutCareDimensions.touchTarget, minHeight = GutCareDimensions.touchTarget)
            .background(Color.White, RoundedCornerShape(15.dp))
            .border(1.dp, GutCareLine, RoundedCornerShape(15.dp))
            .semantics { contentDescription = "返回" },
        contentAlignment = Alignment.Center,
    ) {
        TextButton(
            onClick = onClick,
            modifier = Modifier.size(52.dp),
        ) {
            Text("‹", color = MaterialTheme.colorScheme.onBackground, style = MaterialTheme.typography.displayLarge)
        }
    }
}

@Composable
private fun AuthOperationMessage(operation: AuthOperationState) {
    when (operation) {
        AuthOperationState.Idle -> Unit
        AuthOperationState.Loading -> ScreenStatus("正在安全处理，请稍候。", Modifier.padding(top = 12.dp))
        AuthOperationState.Accepted -> ScreenStatus("请求已受理，请按后续提示继续。", Modifier.padding(top = 12.dp))
        is AuthOperationState.Error -> Text(
            operation.message,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 12.dp)
                .semantics { contentDescription = "操作失败：${operation.message}" },
            style = MaterialTheme.typography.bodyMedium,
            textAlign = TextAlign.Center,
            color = GutCareDanger,
        )
    }
}

@Composable
private fun InlineNavigationPrompt(prefix: String, action: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(prefix, style = MaterialTheme.typography.bodyLarge, color = GutCareMuted)
        TextButton(
            onClick = onClick,
            modifier = Modifier.heightIn(min = GutCareDimensions.touchTarget),
        ) {
            Text(action, color = GutCareBrandGreen, style = MaterialTheme.typography.bodyLarge)
        }
    }
}


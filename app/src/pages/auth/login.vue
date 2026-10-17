<template>
  <AuthScaffold test-id="auth-login" eyebrow="SECURE ACCOUNT" title="欢迎回来" subtitle="登录后，档案与记录将安全同步到你的账号。">
      <GcField id="login-email" v-model="email" label="邮箱" type="email" icon="email" autocomplete="email" placeholder="请输入注册邮箱" required test-id="login-email" />
      <GcField id="login-password" v-model="password" label="密码" type="password" icon="lock" autocomplete="current-password" placeholder="请输入密码" :maxlength="128" required revealable test-id="login-password" />
      <view v-if="auth.logoutWarning?.kind === 'secure_storage_cleanup_failed'" class="logout-warning" role="alert" data-testid="logout-storage-warning">
        <text>本机安全存储未能删除刷新凭据（{{ auth.logoutWarning.code }}）。应用内存会话已清除，请重新启动应用；若问题持续，请联系支持并提供错误代码。</text>
      </view>
      <view v-else-if="auth.logoutWarning?.kind === 'server_logout_unconfirmed'" class="logout-warning" role="alert" data-testid="logout-server-warning">
        <text>服务器未确认退出。本机刷新凭据已删除；请在网络恢复后重新登录。<text v-if="auth.logoutWarning.requestId">支持编号：{{ auth.logoutWarning.requestId }}</text></text>
      </view>
      <view class="forgot-row"><button class="text-link" data-testid="login-forgot" @click="router?.navigate('forgotPassword')">忘记密码？</button></view>
      <InlineProblem :error="error" fallback="暂时无法登录，请稍后重试。" test-id="login-error" />
      <GcButton label="登录" :busy="busy" :disabled="!canSubmit" test-id="login-submit" @click="submit" />
    <template #footer>
      <text class="footer-prompt">还没有账号？</text>
      <button class="text-link" data-testid="login-register" @click="router?.navigate('register')">创建账号</button>
      <button class="text-link deletion-link" data-testid="login-deletion-progress" @click="router?.navigate('accountDeletionProgress')">查询账号注销进度</button>
    </template>
  </AuthScaffold>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { AppError } from '../../api/errors'
import { isValidEmail } from '../../api/authFormValidation'
import { authApiKey, startupCoordinatorKey, appRouterKey } from '../../api/context'
import AuthScaffold from '../../components/AuthScaffold.vue'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'
import InlineProblem from '../../components/InlineProblem.vue'
import { useAuthStore } from '../../stores/auth'

const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref<unknown>(null)
const authApi = inject(authApiKey)
const startup = inject(startupCoordinatorKey)
const router = inject(appRouterKey)
const auth = useAuthStore()
const canSubmit = computed(() => isValidEmail(email.value) && password.value.length > 0 && !busy.value)

async function submit() {
  if (!authApi || !startup || !canSubmit.value) return
  busy.value = true
  error.value = null
  try {
    await authApi.login({ email: email.value.trim(), password: password.value })
    password.value = ''
    const state = await startup.continueAfterLogin()
    if (state === 'unavailable') error.value = auth.startupError ?? new AppError('unavailable', '暂时无法获取账户资料。')
  } catch (cause) {
    error.value = cause
  } finally {
    busy.value = false
  }
}
</script>

<style lang="scss" scoped>
.forgot-row { margin: -2px 0 16px; display: flex; justify-content: flex-end; }
.text-link { min-height: 44px; padding: 0 4px; background: transparent; color: var(--gc-color-brand); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-semibold); }
.footer-prompt { margin-right: 5px; color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); }
.logout-warning { margin: 0 0 14px; padding: 12px 14px; border: 1px solid var(--gc-color-danger-border); border-radius: var(--gc-radius-md); background: var(--gc-color-danger-pale); color: var(--gc-color-danger); font-size: 12px; line-height: 1.55; }
</style>

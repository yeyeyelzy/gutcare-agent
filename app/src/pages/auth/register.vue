<template>
  <AuthScaffold test-id="auth-register" eyebrow="CREATE ACCOUNT" title="创建账号" subtitle="先完成邮箱账户信息，下一步将单独确认健康数据处理。" :step="1" step-label="第 1 步 · 账户信息">
    <template v-if="noticeAvailable">
      <view class="register-fields">
        <GcField id="register-email" v-model="email" label="邮箱" type="email" icon="email" autocomplete="email" placeholder="请输入常用邮箱" required test-id="register-email" />
        <GcField id="register-password" v-model="password" label="设置密码" type="password" icon="lock" autocomplete="new-password" placeholder="至少 12 位" :maxlength="128" required revealable test-id="register-password" />
        <GcField id="register-password-confirm" v-model="confirmPassword" label="确认密码" type="password" icon="lock" autocomplete="new-password" placeholder="再次输入密码" :maxlength="128" required revealable test-id="register-password-confirm" />
      </view>
        <NoticeCard title="隐私政策" :description="privacySummary" :version="privacyPolicyVersion" variant="info" test-id="privacy-notice">
          <button class="consent-toggle" role="checkbox" :aria-checked="privacyAccepted" data-testid="privacy-consent" @click="privacyAccepted = !privacyAccepted">
            <view class="check-box" :class="{ 'check-box--checked': privacyAccepted }"><text v-if="privacyAccepted">✓</text></view>
            <text>我已阅读并同意隐私政策</text>
          </button>
        </NoticeCard>
        <text v-if="formMessage" class="form-message" role="alert">{{ formMessage }}</text>
        <GcButton class="continue" label="继续" :disabled="busy" :busy="busy" test-id="register-continue" @click="continueToProfile" />
    </template>
    <InlineProblem v-else :error="noticeError" fallback="注册暂不可用：当前构建未配置经批准的隐私告知制品。" test-id="register-notice-error" />
    <template #footer><text class="footer-prompt">已有账号？</text><button class="text-link" data-testid="register-login" @click="router?.reLaunch('login')">返回登录</button></template>
  </AuthScaffold>
</template>

<script setup lang="ts">
import { inject, ref } from 'vue'
import { onBackPress, onUnload } from '@dcloudio/uni-app'
import { registrationNotice } from '../../config/registrationNotices'
import { validateRegistrationCredentials } from '../../api/authFormValidation'
import { appRouterKey } from '../../api/context'
import { useRegistrationDraftStore } from '../../stores/registrationDraft'
import AuthScaffold from '../../components/AuthScaffold.vue'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'
import InlineProblem from '../../components/InlineProblem.vue'
import NoticeCard from '../../components/NoticeCard.vue'

const draft = useRegistrationDraftStore()
const router = inject(appRouterKey)
const email = ref(draft.email)
const password = ref(draft.password)
const confirmPassword = ref(draft.confirmPassword)
const privacyAccepted = ref(draft.privacyPolicyAccepted)
const formMessage = ref('')
const busy = ref(false)
const noticeError = ref<unknown>(null)
let privacyPolicyVersion = ''
let privacySummary = ''
let noticeAvailable = true
try {
  const notice = registrationNotice('privacy_policy')
  privacyPolicyVersion = notice.policyVersion
  privacySummary = notice.summary
} catch (error) {
  noticeAvailable = false
  noticeError.value = error
}

onBackPress(() => {
  draft.cancelWorkflow()
  router?.reLaunch('login')
  return true
})

onUnload(() => {
  if (draft.password || draft.confirmPassword) draft.cancelWorkflow()
})

function continueToProfile() {
  if (busy.value) return
  const validation = validateRegistrationCredentials({
    email: email.value,
    password: password.value,
    confirmPassword: confirmPassword.value,
    privacyAccepted: privacyAccepted.value,
  })
  if (validation) {
    formMessage.value = validationMessage(validation)
    return
  }
  try {
    draft.saveAccountStep({
      email: email.value,
      password: password.value,
      confirmPassword: confirmPassword.value,
      privacyPolicyAccepted: privacyAccepted.value,
      privacyPolicyVersion,
    })
    router?.navigate('registerProfile')
  } catch {
    formMessage.value = '请检查邮箱、密码和隐私政策确认。'
  }
}

function validationMessage(error: NonNullable<ReturnType<typeof validateRegistrationCredentials>>): string {
  if (error === 'email') return '请输入有效的邮箱地址。'
  if (error === 'password') return '密码至少需要 12 个字符。'
  if (error === 'password_mismatch') return '两次输入的密码不一致。'
  return '请先阅读并同意隐私政策。'
}
</script>

<style lang="scss" scoped>
.register-fields { margin-bottom: 20px; }
.consent-toggle { width: 100%; min-height: 48px; margin-top: 12px; padding: 5px 0; display: flex; align-items: center; gap: 10px; background: transparent; color: var(--gc-color-text); text-align: left; font-size: 12px; line-height: 1.5; }
.check-box { flex: 0 0 22px; width: 22px; height: 22px; border: 1.5px solid var(--gc-color-muted); border-radius: 6px; display: grid; place-items: center; background: var(--gc-color-surface); color: var(--gc-color-on-brand); font-size: 14px; font-weight: var(--gc-font-weight-bold); }
.check-box--checked { border-color: var(--gc-color-brand); background: var(--gc-color-brand); }
.form-message { display: block; margin: 12px 0; color: var(--gc-color-danger); font-size: 12px; }
.continue { margin-top: 18px; }
.footer-prompt { margin-right: 5px; color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); }
.text-link { min-height: 44px; padding: 0 4px; background: transparent; color: var(--gc-color-brand); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-semibold); }
</style>

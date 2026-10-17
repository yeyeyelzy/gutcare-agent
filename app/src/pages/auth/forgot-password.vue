<template>
  <AuthScaffold test-id="auth-forgot-password" eyebrow="ACCOUNT RECOVERY" title="找回密码" subtitle="输入注册邮箱。如果该邮箱对应有效账户，我们会发送重置说明。">
    <view class="form-card">
      <GcField id="reset-request-email" v-model="email" label="邮箱" type="email" autocomplete="email" placeholder="请输入注册邮箱" required test-id="reset-request-email" />
      <NoticeCard title="保护账户隐私" description="无论邮箱是否已注册，提交后都会显示相同确认信息。" test-id="reset-privacy-notice" />
      <InlineProblem :error="error" fallback="暂时无法提交请求，请稍后重试。" test-id="reset-request-error" />
      <view v-if="accepted" class="accepted" role="status" aria-live="polite" data-testid="reset-request-accepted">
        <text class="accepted-title">请求已提交</text>
        <text class="accepted-copy">如果该邮箱已注册且可以接收邮件，我们会发送密码重置说明。为保护账户隐私，我们不会透露账户是否存在。</text>
        <GcButton label="输入重置令牌" variant="secondary" test-id="reset-enter-token" @click="router?.navigate('resetPassword')" />
      </view>
      <GcButton v-else label="发送重置说明" :busy="busy" :disabled="busy || !isValidEmail(email)" test-id="reset-request-submit" @click="submit" />
    </view>
    <template #footer><button class="text-link" data-testid="forgot-back-login" @click="router?.reLaunch('login')">返回登录</button></template>
  </AuthScaffold>
</template>

<script setup lang="ts">
import { inject, ref } from 'vue'
import { onBackPress } from '@dcloudio/uni-app'
import { appRouterKey, passwordResetServiceKey } from '../../api/context'
import { isValidEmail } from '../../api/authFormValidation'
import AuthScaffold from '../../components/AuthScaffold.vue'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'
import InlineProblem from '../../components/InlineProblem.vue'
import NoticeCard from '../../components/NoticeCard.vue'

const router = inject(appRouterKey)
const passwordReset = inject(passwordResetServiceKey)
const email = ref('')
const busy = ref(false)
const accepted = ref(false)
const error = ref<unknown>(null)

onBackPress(() => { router?.reLaunch('login'); return true })

async function submit() {
  if (!passwordReset || busy.value || !isValidEmail(email.value)) return
  busy.value = true
  error.value = null
  try {
    await passwordReset.request(email.value)
    accepted.value = true
  } catch (cause) {
    error.value = cause
  } finally {
    busy.value = false
  }
}
</script>

<style lang="scss" scoped>
.form-card { padding: 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }
.accepted { margin: 16px 0; padding: 16px; border: 1px solid var(--gc-color-sage); border-radius: var(--gc-radius-md); background: var(--gc-color-sage-pale); }
.accepted-title { display: block; color: var(--gc-color-brand-strong); font-size: var(--gc-font-size-md); font-weight: var(--gc-font-weight-semibold); }
.accepted-copy { display: block; margin: 7px 0 14px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.65; }
.text-link { min-height: 44px; padding: 0 4px; background: transparent; color: var(--gc-color-brand); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-semibold); }
</style>

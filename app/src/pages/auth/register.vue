<template>
  <view class="screen">
    <text class="heading">创建账户</text>
    <text class="intro">使用邮箱注册 GutCare</text>
    <template v-if="noticeAvailable">
      <label class="label" for="register-email">邮箱</label>
      <input id="register-email" v-model="email" class="input" type="text" autocomplete="email" placeholder="name@example.com" />
      <label class="label" for="register-password">密码</label>
      <input id="register-password" v-model="password" class="input" password placeholder="至少 12 位" />
      <label class="label" for="register-password-confirm">确认密码</label>
      <input id="register-password-confirm" v-model="confirmPassword" class="input" password placeholder="再次输入密码" />
      <text class="notice-copy">{{ privacySummary }}</text>
      <view class="choice"><switch :checked="privacyAccepted" @change="onPrivacyChange" /><text>我已阅读隐私政策</text></view>
      <text v-if="message" class="notice" role="alert">{{ message }}</text>
      <button class="primary" :disabled="!canContinue" @click="continueToProfile">继续</button>
    </template>
    <text v-else class="notice" role="alert">注册暂不可用：当前构建未配置经批准的注册告知制品。</text>
  </view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onUnload } from '@dcloudio/uni-app'
import { registrationNotice } from '../../config/registrationNotices'
import { appRouterKey } from '../../api/context'
import { useRegistrationDraftStore } from '../../stores/registrationDraft'

const draft = useRegistrationDraftStore()
const router = inject(appRouterKey)
const email = ref(draft.email)
const password = ref(draft.password)
const confirmPassword = ref(draft.confirmPassword)
const privacyAccepted = ref(draft.privacyPolicyAccepted)
const message = ref('')
let privacyPolicyVersion = ''
let privacySummary = ''
let noticeAvailable = true
try {
  const notice = registrationNotice('privacy_policy')
  privacyPolicyVersion = notice.policyVersion
  privacySummary = notice.summary
} catch {
  noticeAvailable = false
}

const canContinue = computed(() => email.value.trim().length > 0 && password.value.length >= 12
  && password.value === confirmPassword.value && privacyAccepted.value)

onBackPress(() => {
  draft.cancelWorkflow()
  router?.reLaunch('login')
  return true
})

onUnload(() => {
  if (draft.password || draft.confirmPassword) draft.cancelWorkflow()
})

function continueToProfile() {
  if (!canContinue.value) return
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
    message.value = '请检查邮箱、密码和隐私政策确认。'
  }
}

function onPrivacyChange(event: Event) {
  const detail = (event as unknown as { detail: { value: boolean } }).detail
  privacyAccepted.value = detail.value
}
</script>

<style lang="scss" scoped>
.screen { min-height: 100vh; padding: 40px 24px 32px; display: flex; flex-direction: column; background: var(--gc-color-canvas); }
.heading { font-size: 28px; font-weight: 700; }
.intro { margin: 8px 0 24px; color: var(--gc-color-muted); }
.label { margin: 18px 0 8px; font-weight: 600; }
.input { height: 52px; padding: 0 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); }
.notice-copy { margin-top: 24px; padding: 14px; border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); line-height: 1.6; }
.choice { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.primary { margin-top: auto; border-radius: var(--gc-radius-md); background: var(--gc-color-brand); color: white; }
.notice { margin-top: 16px; color: var(--gc-color-danger); }
</style>

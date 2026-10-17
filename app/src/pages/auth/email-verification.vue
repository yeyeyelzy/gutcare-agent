<template>
  <view class="screen">
    <text class="heading">验证邮箱</text>
    <text class="intro">验证令牌将发送至 {{ emailLabel }}。请输入邮件中的一次性令牌。</text>
    <label class="label" for="verification-token">邮箱验证令牌</label>
    <input id="verification-token" v-model="token" class="input" type="text" autocomplete="one-time-code" placeholder="输入验证令牌" />
    <text v-if="message" class="notice" role="alert">{{ message }}</text>
    <button class="primary" :loading="busy" :disabled="busy || !token.trim()" @click="submit">验证邮箱</button>
  </view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onLoad, onUnload } from '@dcloudio/uni-app'
import { AppError } from '../../api/errors'
import { appRouterKey, emailVerificationServiceKey } from '../../api/context'
import { useRegistrationDraftStore } from '../../stores/registrationDraft'

const draft = useRegistrationDraftStore()
const verification = inject(emailVerificationServiceKey)
const router = inject(appRouterKey)
const token = ref('')
const message = ref('')
const busy = ref(false)
const emailLabel = computed(() => draft.email || '注册邮箱')

onLoad(() => {
  if (!draft.email || !verification) {
    draft.clear()
    router?.reLaunch('login')
  }
})

onBackPress(() => {
  draft.clear()
  router?.reLaunch('login')
  return true
})

onUnload(() => draft.clear())

async function submit() {
  if (!verification || busy.value) return
  busy.value = true
  message.value = ''
  try {
    await verification.verify(token.value)
    token.value = ''
    uni.showToast({ title: '邮箱已验证，请登录', icon: 'none' })
    router?.reLaunch('login')
  } catch (error) {
    message.value = verificationFailureMessage(error)
  } finally {
    busy.value = false
  }
}

function verificationFailureMessage(error: unknown): string {
  if (error instanceof AppError && error.kind === 'unavailable') return '验证服务暂不可用，请稍后重试。'
  if (error instanceof AppError && error.status === 422) return '验证令牌无效或已过期，请检查邮件后重试。'
  return '邮箱验证未完成，请检查令牌后重试。'
}
</script>

<style lang="scss" scoped>
.screen { min-height: 100vh; padding: 40px 24px 32px; display: flex; flex-direction: column; background: var(--gc-color-canvas); }
.heading { font-size: 28px; font-weight: 700; }
.intro { margin: 12px 0 24px; color: var(--gc-color-muted); line-height: 1.6; }
.label { margin: 18px 0 8px; font-weight: 600; }
.input { height: 52px; padding: 0 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); }
.notice { margin-top: 16px; color: var(--gc-color-danger); }
.primary { margin-top: auto; border-radius: var(--gc-radius-md); background: var(--gc-color-brand); color: white; }
</style>

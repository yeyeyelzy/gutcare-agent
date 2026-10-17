<template>
  <AuthScaffold test-id="auth-email-verification" eyebrow="VERIFY EMAIL" title="验证你的邮箱" :subtitle="`一次性验证令牌已发送至 ${emailLabel}。请在下方手动输入邮件中的令牌。`">
    <view class="mail-illustration" aria-hidden="true"><view class="mail-back" /><view class="mail-front"><view class="mail-fold" /></view><view class="mail-spark spark-a" /><view class="mail-spark spark-b" /></view>
    <view class="form-card">
      <GcField id="verification-token" v-model="token" label="邮箱验证令牌" placeholder="输入邮件中的一次性令牌" hint="令牌至少 20 个字符。" autocomplete="one-time-code" required test-id="verification-token" />
      <InlineProblem :error="error" fallback="邮箱验证暂未完成，请检查令牌后重试。" test-id="verification-error" />
      <GcButton label="验证邮箱" :busy="busy" :disabled="busy || token.trim().length < 20" test-id="verification-submit" @click="submit" />
    </view>
    <template #footer><button class="text-link" data-testid="verification-back-login" @click="returnToLogin">返回登录</button></template>
  </AuthScaffold>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onLoad, onUnload } from '@dcloudio/uni-app'
import { appRouterKey, emailVerificationServiceKey } from '../../api/context'
import { useRegistrationDraftStore } from '../../stores/registrationDraft'
import AuthScaffold from '../../components/AuthScaffold.vue'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'
import InlineProblem from '../../components/InlineProblem.vue'

const draft = useRegistrationDraftStore()
const verification = inject(emailVerificationServiceKey)
const router = inject(appRouterKey)
const token = ref('')
const error = ref<unknown>(null)
const busy = ref(false)
const emailLabel = computed(() => draft.email || '你的注册邮箱')

onLoad(() => { if (!draft.email || !verification) returnToLogin() })
onBackPress(() => { returnToLogin(); return true })
onUnload(() => { token.value = ''; draft.clear() })

function returnToLogin() {
  token.value = ''
  draft.clear()
  router?.reLaunch('login')
}

async function submit() {
  if (!verification || busy.value || !token.value.trim()) return
  busy.value = true
  error.value = null
  try {
    await verification.verify(token.value)
    token.value = ''
    uni.showToast({ title: '邮箱已验证，请登录', icon: 'none' })
    router?.reLaunch('login')
  } catch (cause) {
    error.value = cause
  } finally {
    busy.value = false
  }
}
</script>

<style lang="scss" scoped>
.mail-illustration { width: 100%; height: 116px; margin: -2px 0 18px; position: relative; display: grid; place-items: center; }
.mail-back { width: 105px; height: 73px; border-radius: 12px; background: var(--gc-color-sage-pale); transform: rotate(-5deg); }
.mail-front { position: absolute; width: 96px; height: 64px; top: 32px; border-radius: 8px; background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); overflow: hidden; }
.mail-fold { position: absolute; left: 9px; top: -34px; width: 78px; height: 78px; border-right: 2px solid var(--gc-color-brand); border-bottom: 2px solid var(--gc-color-brand); transform: rotate(45deg); background: var(--gc-color-canvas); }
.mail-spark { position: absolute; width: 7px; height: 7px; border-radius: 50%; background: var(--gc-color-orange); }.spark-a { left: 27%; top: 21px; }.spark-b { right: 27%; bottom: 17px; width: 5px; height: 5px; background: var(--gc-color-purple); }
.form-card { padding: 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }
.text-link { min-height: 44px; padding: 0 4px; background: transparent; color: var(--gc-color-brand); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-semibold); }
</style>

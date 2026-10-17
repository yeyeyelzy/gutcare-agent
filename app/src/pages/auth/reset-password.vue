<template>
  <AuthScaffold test-id="auth-reset-password" eyebrow="SET NEW PASSWORD" title="设置新密码" subtitle="输入邮件中的一次性重置令牌，并创建新的登录密码。令牌仅在当前页面内存中使用。">
    <view class="form-card">
      <GcField id="reset-token" v-model="token" label="密码重置令牌" placeholder="手动输入邮件中的一次性令牌" hint="令牌至少 20 个字符。" autocomplete="one-time-code" required test-id="reset-token" />
      <GcField id="new-password" v-model="password" label="新密码" type="password" autocomplete="new-password" placeholder="至少 12 个字符" :maxlength="128" required revealable test-id="new-password" />
      <GcField id="new-password-confirm" v-model="confirmation" label="确认新密码" type="password" autocomplete="new-password" placeholder="再次输入新密码" :maxlength="128" required revealable test-id="new-password-confirm" />
      <text v-if="validationMessage" class="validation" role="alert">{{ validationMessage }}</text>
      <InlineProblem :error="error" fallback="暂时无法重置密码，请稍后重试。" test-id="reset-confirm-error" />
      <GcButton label="更新密码" :busy="busy" :disabled="busy" test-id="reset-confirm-submit" @click="submit" />
    </view>
    <template #footer><button class="text-link" data-testid="reset-back-login" @click="leavePage">取消并返回登录</button></template>
  </AuthScaffold>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onUnload } from '@dcloudio/uni-app'
import { appRouterKey, passwordResetServiceKey } from '../../api/context'
import { passwordResetValidationError } from '../../api/authFormValidation'
import AuthScaffold from '../../components/AuthScaffold.vue'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'
import InlineProblem from '../../components/InlineProblem.vue'

const router = inject(appRouterKey)
const passwordReset = inject(passwordResetServiceKey)
const token = ref('')
const password = ref('')
const confirmation = ref('')
const busy = ref(false)
const error = ref<unknown>(null)
const validationMessage = ref('')
const validationError = computed(() => passwordResetValidationError({ token: token.value, password: password.value, confirmation: confirmation.value }))

onBackPress(() => { leavePage(); return true })
onUnload(clearSensitiveFields)

function clearSensitiveFields() { token.value = ''; password.value = ''; confirmation.value = '' }
function leavePage() { clearSensitiveFields(); router?.reLaunch('login') }

async function submit() {
  if (!passwordReset || busy.value) return
  const invalid = validationError.value
  if (invalid) {
    validationMessage.value = invalid === 'token' ? '请输入至少 20 个字符的重置令牌。' : invalid === 'password' ? '新密码需要 12 至 128 个字符。' : '两次输入的新密码不一致。'
    return
  }
  busy.value = true
  error.value = null
  validationMessage.value = ''
  try {
    await passwordReset.confirm(token.value, password.value)
    clearSensitiveFields()
    uni.showToast({ title: '密码已更新，请重新登录', icon: 'none' })
    router?.reLaunch('login')
  } catch (cause) {
    error.value = cause
  } finally {
    busy.value = false
  }
}
</script>

<style lang="scss" scoped>
.form-card { padding: 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }
.validation { display: block; margin: 12px 0; color: var(--gc-color-danger); font-size: 12px; }
.text-link { min-height: 44px; padding: 0 4px; background: transparent; color: var(--gc-color-brand); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-semibold); }
</style>

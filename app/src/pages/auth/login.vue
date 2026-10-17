<template>
  <view class="screen">
    <text class="heading">欢迎回来</text>
    <text class="intro">使用邮箱和密码登录 GutCare</text>
    <label class="label" for="email">邮箱</label>
    <input id="email" v-model="email" class="input" type="text" autocomplete="email" placeholder="name@example.com" />
    <label class="label" for="password">密码</label>
    <input id="password" v-model="password" class="input" password placeholder="请输入密码" />
    <button class="primary" :loading="busy" :disabled="busy" @click="submit">登录</button>
    <button class="secondary" @click="goToRegistration">创建账户</button>
    <text v-if="message" class="notice" role="alert">{{ message }}</text>
  </view>
</template>

<script setup lang="ts">
import { inject, ref } from 'vue'
import { AppError } from '../../api/errors'
import { authApiKey, startupCoordinatorKey, appRouterKey } from '../../api/context'

const email = ref('')
const password = ref('')
const busy = ref(false)
const message = ref('')
const authApi = inject(authApiKey)
const startup = inject(startupCoordinatorKey)
const router = inject(appRouterKey)

async function submit() {
  if (!authApi || !startup || busy.value) return
  busy.value = true
  message.value = ''
  try {
    await authApi.login({ email: email.value.trim(), password: password.value })
    const state = await startup.continueAfterLogin()
    if (state === 'unavailable') message.value = '暂时无法获取账户资料，请检查网络后重试。'
  } catch (error) {
    message.value = error instanceof AppError && error.code === 'INVALID_CREDENTIALS'
      ? '邮箱或密码不正确，或邮箱尚未验证。'
      : '暂时无法登录，请稍后重试。'
  } finally {
    busy.value = false
  }
}

function goToRegistration() {
  router?.navigate('register')
}
</script>

<style lang="scss" scoped>
.screen { min-height: 100vh; padding: 64px 24px 32px; display: flex; flex-direction: column; background: var(--gc-color-canvas); }
.heading { font-size: 28px; font-weight: 700; }
.intro { margin: 8px 0 32px; color: var(--gc-color-muted); }
.label { margin: 18px 0 8px; font-weight: 600; }
.input { height: 52px; padding: 0 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-sm); background: var(--gc-color-surface); }
.primary { margin-top: 28px; border-radius: var(--gc-radius-md); background: var(--gc-color-brand); color: white; }
.primary[disabled] { opacity: .5; }
.secondary { margin-top: 12px; background: transparent; color: var(--gc-color-brand); }
.notice { margin-top: 16px; color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); text-align: center; }
</style>

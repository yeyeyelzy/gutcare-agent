<template>
  <view class="screen">
    <text class="heading">暂时无法载入账户资料</text>
    <text class="body">账户与患者资料状态不一致。为保护账户数据，暂不继续进入应用，也不会创建本地资料。</text>
    <text v-if="requestId" class="request-id">支持编号：{{ requestId }}</text>
    <button class="primary" @click="returnToLogin">返回登录</button>
  </view>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { appRouterKey } from '../../api/context'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const router = inject(appRouterKey)
const requestId = computed(() => auth.profileErrorRequestId)

function returnToLogin() {
  router?.reLaunch('login')
}
</script>

<style lang="scss" scoped>
.screen { min-height: 100vh; padding: 48px 24px 32px; display: flex; flex-direction: column; background: var(--gc-color-canvas); }
.heading { font-size: 24px; font-weight: 700; }
.body { margin-top: 16px; line-height: 1.6; color: var(--gc-color-muted); }
.request-id { margin-top: 18px; font-size: var(--gc-font-size-sm); color: var(--gc-color-muted); }
.primary { margin-top: auto; border-radius: var(--gc-radius-md); background: var(--gc-color-brand); color: white; }
</style>

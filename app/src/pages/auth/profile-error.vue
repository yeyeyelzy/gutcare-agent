<template>
  <AuthScaffold test-id="auth-profile-error" eyebrow="ACCOUNT SAFETY" title="暂时无法载入账户资料" subtitle="为保护账户数据，我们需要确认登录账户与患者资料保持一致。">
    <view class="error-card">
      <view class="shield" aria-hidden="true">!</view>
      <text class="message">当前账户资料状态暂不可用。我们不会创建本地资料，也不会继续进入应用。</text>
      <view v-if="requestId" class="request-box" data-testid="profile-error-request-id"><text class="request-label">支持编号</text><text class="request-id">{{ requestId }}</text></view>
      <text class="support-copy">如需协助，请通过你获取 GutCare 服务时提供的官方支持渠道联系支持人员，并手动提供支持编号。此入口不会自动发送任何资料。</text>
      <button class="support-action" data-testid="profile-error-support" @click="showSupportGuidance">查看联系支持说明</button>
      <GcButton label="返回登录" test-id="profile-error-login" @click="returnToLogin" />
    </view>
  </AuthScaffold>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { appRouterKey } from '../../api/context'
import { useAuthStore } from '../../stores/auth'
import AuthScaffold from '../../components/AuthScaffold.vue'
import GcButton from '../../components/GcButton.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const requestId = computed(() => auth.profileErrorRequestId)
function returnToLogin() { router?.reLaunch('login') }
function showSupportGuidance() {
  uni.showModal({
    title: '联系支持',
    content: requestId.value
      ? `请使用你获取服务时提供的官方支持渠道，并手动提供支持编号 ${requestId.value}。此操作不会发送账户或健康资料。`
      : '请使用你获取服务时提供的官方支持渠道联系支持人员。此操作不会发送账户或健康资料。',
    showCancel: false,
    confirmText: '知道了',
  })
}
</script>

<style lang="scss" scoped>
.error-card { padding: 22px 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }
.shield { width: 52px; height: 52px; margin: 0 auto 16px; border: 2px solid var(--gc-color-orange); border-radius: 18px 18px 22px 22px; display: grid; place-items: center; color: var(--gc-color-orange); font-size: 23px; font-weight: var(--gc-font-weight-bold); }
.message { display: block; color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); line-height: 1.7; text-align: center; }
.request-box { margin: 18px 0; padding: 12px 14px; border-radius: var(--gc-radius-md); background: var(--gc-color-canvas); }
.request-label { display: block; color: var(--gc-color-muted); font-size: 11px; }.request-id { display: block; margin-top: 4px; color: var(--gc-color-text); font-size: 12px; overflow-wrap: anywhere; }
.support-copy { display: block; margin: 14px 0 5px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.65; }
.support-action { width: 100%; min-height: 44px; margin: 2px 0 10px; background: transparent; color: var(--gc-color-brand); font-size: 13px; }
</style>

<template>
  <view v-if="pageMeta" class="placeholder-page" data-testid="feature-placeholder">
    <view class="placeholder-shell">
      <view class="topbar"><button class="back-button" :aria-label="`返回${ownerLabel}`" data-testid="placeholder-back" @click="returnToOwner">‹</button><text class="topbar-title">{{ pageMeta.title }}</text><view class="topbar-spacer" /></view>
      <view class="placeholder-card">
        <view class="placeholder-mark" aria-hidden="true"><text>· · ·</text></view>
        <text class="eyebrow">GUTCARE</text>
        <text class="title">功能建设中</text>
        <text class="copy">{{ pageMeta.title }}页面尚未开放。当前不会展示模拟记录、虚构的分析结果或未载入的数据。</text>
        <GcButton :label="`返回${ownerLabel}`" variant="primary" test-id="placeholder-return" @click="returnToOwner" />
      </view>
      <text class="security-note">此页面受本人账户访问保护。</text>
    </view>
  </view>
  <view v-else class="invalid-route" role="status">正在返回安全入口…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onLoad } from '@dcloudio/uni-app'
import { appRouterKey } from '../../api/context'
import { canRenderRoute, PLACEHOLDER_META, placeholderRouteFromScreen } from '../../navigation/routes'
import type { AppTabName, PlaceholderRouteName } from '../../navigation/routes'
import { useAuthStore } from '../../stores/auth'
import GcButton from '../../components/GcButton.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const routeName = ref<PlaceholderRouteName | null>(null)
const pageMeta = computed(() => routeName.value ? PLACEHOLDER_META[routeName.value] : null)
const owner = computed<AppTabName>(() => pageMeta.value?.ownerTab ?? 'today')
const ownerLabel = computed(() => ({ today: '今日', records: '记录', analysis: '分析', me: '我的' }[owner.value]))

onLoad((options) => {
  const name = placeholderRouteFromScreen(options?.screen)
  if (!name) {
    if (!canRenderRoute('placeholder', auth.state)) router?.requireAuthentication('placeholder')
    else router?.switchTab('today')
    return
  }
  if (!canRenderRoute(name, auth.state)) {
    router?.requireAuthentication(name)
    return
  }
  routeName.value = name
})

onBackPress(() => { returnToOwner(); return true })

function returnToOwner() { router?.switchTab(owner.value) }
</script>

<style lang="scss" scoped>
.placeholder-page { min-height: 100vh; background: var(--gc-color-canvas); }.placeholder-shell { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); }.topbar { display: flex; height: 48px; align-items: center; justify-content: space-between; }.back-button { display: grid; width: 44px; height: 44px; padding: 0; place-items: center; border: 0; border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 28px; line-height: 1; }.topbar-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.topbar-spacer { width: 44px; }
.placeholder-card { display: flex; min-height: 355px; margin-top: 78px; padding: 28px 22px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); flex-direction: column; align-items: center; justify-content: center; background: var(--gc-color-surface); text-align: center; box-shadow: var(--gc-shadow-card); }.placeholder-mark { display: grid; width: 70px; height: 70px; margin-bottom: 20px; place-items: center; border-radius: 24px; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 19px; letter-spacing: 3px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1.2px; }.title { display: block; margin-top: 7px; color: var(--gc-color-text); font-size: 22px; font-weight: var(--gc-font-weight-bold); }.copy { display: block; max-width: 290px; margin: 9px 0 22px; color: var(--gc-color-muted); font-size: 13px; line-height: 1.65; }.placeholder-card :deep(.gc-button) { max-width: 280px; }.security-note { display: block; margin-top: 18px; color: var(--gc-color-muted); font-size: 11px; text-align: center; }.invalid-route { display: grid; min-height: 100vh; place-items: center; color: var(--gc-color-muted); }
</style>

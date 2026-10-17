<template>
  <view v-if="canRender()" class="screen">
    <view class="home-header"><view><text class="eyebrow">GUTCARE</text><text class="title">今日</text></view><view class="avatar" aria-hidden="true">{{ firstLetter }}</view></view>
    <view class="welcome-card"><text class="welcome-title">你好，{{ auth.profile?.nickname || 'GutCare 用户' }}</text><text class="welcome-copy">你的记录和资料仅对本人账户开放。</text></view>
    <view class="action-card"><text class="action-title">账户与资料</text><text class="action-copy">查看或更新昵称、出生年份与时区。</text><GcButton label="个人资料" variant="secondary" test-id="today-profile" @click="router?.navigate('profile')" /></view>
    <view class="action-card logout-card"><text class="action-title">结束本次使用</text><text class="action-copy">退出后将清除本机内存会话，并尝试删除安全存储中的刷新凭据。</text><GcButton label="退出登录" variant="quiet" test-id="today-logout" @click="confirmLogout" /></view>
  </view>
  <view v-else class="screen" aria-live="polite">
    <text>正在验证会话…</text>
  </view>
</template>

<script setup lang="ts">
import { useAuthStore } from '../../stores/auth'
import { canRenderRoute } from '../../navigation/routes'
import { inject, ref, computed } from 'vue'
import { appRouterKey, sessionServiceKey } from '../../api/context'
import GcButton from '../../components/GcButton.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const session = inject(sessionServiceKey)
const logoutBusy = ref(false)
const logoutPromptOpen = ref(false)
const canRender = () => canRenderRoute('today', auth.state)
const firstLetter = computed(() => (auth.profile?.nickname || 'G').slice(0, 1))

function confirmLogout() {
  if (logoutBusy.value || logoutPromptOpen.value || !session) return
  logoutPromptOpen.value = true
  uni.showModal({ title: '退出登录', content: '退出后需要重新登录才能查看本人资料和记录。', confirmText: '退出登录', cancelText: '取消', success: (result: { confirm: boolean }) => { if (result.confirm) void logout() }, complete: () => { logoutPromptOpen.value = false } })
}

async function logout() {
  if (!session || logoutBusy.value) return
  logoutBusy.value = true
  try { await session.logout() } catch { /* SessionService carries safe logout details to the login screen. */ } finally { logoutBusy.value = false }
}
</script>

<style lang="scss" scoped>
.screen { min-height: 100vh; max-width: 430px; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 22px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); background: var(--gc-color-canvas); }
.home-header { display: flex; align-items: center; justify-content: space-between; margin: 8px 2px 24px; }.eyebrow { display: block; color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1.2px; }.title { display: block; margin-top: 3px; font-size: 28px; font-weight: var(--gc-font-weight-bold); }.avatar { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); font-size: 18px; font-weight: var(--gc-font-weight-bold); }
.welcome-card { padding: 20px; border-radius: var(--gc-radius-lg); background: var(--gc-color-brand); color: var(--gc-color-on-brand); box-shadow: var(--gc-shadow-card); }.welcome-title { display: block; font-size: 19px; font-weight: var(--gc-font-weight-semibold); }.welcome-copy { display: block; margin-top: 6px; color: rgba(255,255,255,.82); font-size: 13px; line-height: 1.5; }
.action-card { margin-top: 16px; padding: 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }.action-title { display: block; font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.action-copy { display: block; margin: 5px 0 12px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.5; }.logout-card :deep(.gc-button) { justify-content: flex-start; padding-left: 0; }
</style>


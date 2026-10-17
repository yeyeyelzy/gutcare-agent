<template>
  <scroll-view class="welcome-scroll" scroll-y :show-scrollbar="false">
    <view class="welcome" data-testid="welcome-page">
      <view class="topline"><view class="brand"><view class="brand-mark"><view class="leaf leaf-a" /><view class="leaf leaf-b" /><view class="stem" /></view><text>GutCare</text></view><view class="status-pill"><view class="status-dot" />安心记录</view></view>
      <view class="hero-art" aria-hidden="true">
        <svg class="hero-illustration" viewBox="0 0 340 270" role="presentation">
          <circle cx="170" cy="132" r="112" fill="var(--gc-color-sage-glow)" />
          <circle cx="170" cy="132" r="82" fill="var(--gc-color-surface-soft)" stroke="var(--gc-color-sage-outline)" />
          <path d="M83 93c26-25 56-25 87 0v106c-31-19-61-19-87 0z" fill="#fff" stroke="var(--gc-color-brand)" stroke-width="4" stroke-linejoin="round" />
          <path d="M170 93c26-25 56-25 87 0v106c-31-19-61-19-87 0z" fill="var(--gc-color-paper)" stroke="var(--gc-color-brand)" stroke-width="4" stroke-linejoin="round" />
          <path d="M170 94v106" stroke="var(--gc-color-sage)" stroke-width="3" />
          <path d="M105 121h42M105 136h42M195 121h42M195 136h42" stroke="var(--gc-color-border)" stroke-width="4" stroke-linecap="round" />
          <path d="M112 174c8-15 17-15 26 0-9 14-18 14-26 0zm116-62c-1-19 8-28 27-27-1 19-10 28-27 27z" fill="var(--gc-color-sage-pale)" stroke="var(--gc-color-brand)" stroke-width="3" />
          <circle cx="70" cy="60" r="7" fill="var(--gc-color-orange)" /><circle cx="269" cy="195" r="6" fill="var(--gc-color-purple)" />
          <path d="M69 174c15-12 26-10 33 7-15 12-26 10-33-7zm204-96c-14-11-25-9-31 7 14 11 25 9 31-7z" fill="var(--gc-color-sage)" />
        </svg>
      </view>
      <view class="welcome-copy">
        <text class="eyebrow">YOUR HEALTH, IN YOUR HANDS</text>
        <text class="headline">更了解自己，<text class="headline-accent">从每天一点开始</text></text>
        <text class="description">记录身体的变化，让健康管理变得简单、安心。</text>
      </view>
      <view class="feature-list">
        <view class="feature-row"><view class="feature-icon">✓</view><text>记录由你掌控，隐私安全保护</text></view>
        <view class="feature-row"><view class="feature-icon">＋</view><text>轻松记录每日身体变化</text></view>
        <view class="feature-row"><view class="feature-icon">⌁</view><text>在自己的节奏里照顾健康</text></view>
      </view>
      <view v-if="startupBusy" class="restore-loading" role="status" aria-live="polite" data-testid="welcome-restore-loading"><view class="loading-dot" /><text>正在安全检查会话…</text></view>
      <InlineProblem v-if="startupState === 'unavailable'" :error="startupError" fallback="暂时无法恢复之前的会话。解锁设备或检查网络后可重试。" test-id="welcome-restore-error" />
      <view class="actions">
        <GcButton v-if="startupState === 'unavailable'" label="重试会话恢复" variant="secondary" :busy="retrying" test-id="welcome-retry" @click="retryRestore" />
        <GcButton label="创建账号" :disabled="startupBusy" test-id="welcome-register" @click="router?.navigate('register')" />
        <GcButton label="登录" variant="secondary" :disabled="startupBusy" test-id="welcome-login" @click="router?.navigate('login')" />
      </view>
      <text class="legal-note">继续即表示你将使用 GutCare 管理个人健康记录。</text>
    </view>
  </scroll-view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { AppError } from '../../api/errors'
import { appRouterKey, startupCoordinatorKey } from '../../api/context'
import { useAuthStore } from '../../stores/auth'
import GcButton from '../../components/GcButton.vue'
import InlineProblem from '../../components/InlineProblem.vue'

const startup = inject(startupCoordinatorKey)
const router = inject(appRouterKey)
const auth = useAuthStore()
const retrying = ref(false)
const startupState = computed(() => startup?.state ?? 'idle')
const startupBusy = computed(() => startupState.value === 'idle' || startupState.value === 'restoring')
const startupError = computed(() => startupState.value === 'unavailable' ? auth.startupError ?? new AppError('unavailable', '会话恢复暂不可用。') : null)

async function retryRestore() {
  if (!startup || retrying.value) return
  retrying.value = true
  try { await startup.retryRestore() } finally { retrying.value = false }
}
</script>

<style lang="scss" scoped>
.welcome-scroll { height: 100vh; }
.welcome { min-height: 100vh; max-width: 430px; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 20px) 24px calc(env(safe-area-inset-bottom, 0px) + 26px); display: flex; flex-direction: column; background: radial-gradient(circle at 78% 23%, var(--gc-color-sage-pale) 0, var(--gc-color-canvas) 35%, var(--gc-color-canvas) 100%); }
.topline { display: flex; align-items: center; justify-content: space-between; }
.brand { display: flex; align-items: center; gap: 9px; color: var(--gc-color-brand-strong); font-size: 18px; font-weight: var(--gc-font-weight-bold); }
.brand-mark { position: relative; width: 32px; height: 32px; border-radius: 50%; background: var(--gc-color-surface); }
.leaf { position: absolute; width: 10px; height: 16px; border: 2px solid var(--gc-color-brand); border-radius: 10px 1px 10px 1px; transform: rotate(35deg); }
.leaf-a { left: 8px; top: 5px; }.leaf-b { right: 6px; top: 10px; transform: rotate(215deg); }.stem { position: absolute; left: 15px; top: 13px; width: 2px; height: 13px; background: var(--gc-color-brand); transform: rotate(23deg); border-radius: 2px; }
.status-pill { min-height: 34px; padding: 0 11px; display: flex; align-items: center; gap: 6px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-pill); background: var(--gc-color-surface-glass); color: var(--gc-color-muted); font-size: 11px; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--gc-color-brand); }
.hero-art { height: min(35vh, 280px); min-height: 205px; position: relative; margin: 24px 0 10px; display: grid; place-items: center; }
.hero-illustration { width: min(100%, 340px); height: 100%; }
.halo { position: absolute; border-radius: 50%; }
.halo-outer { width: min(68vw, 250px); aspect-ratio: 1; background: var(--gc-color-sage-glow); }
.halo-inner { width: min(52vw, 190px); aspect-ratio: 1; background: var(--gc-color-surface-soft); border: 1px solid var(--gc-color-sage-outline); }
.book { width: 102px; height: 126px; z-index: 1; position: relative; border-radius: 12px 16px 16px 12px; background: var(--gc-color-brand); box-shadow: 0 18px 35px rgba(33,75,62,.22); transform: rotate(-6deg); }
.book::before { content: ''; position: absolute; inset: 8px 8px 8px 15px; border-radius: 2px 10px 10px 2px; background: var(--gc-color-paper); }
.book-page { position: absolute; z-index: 1; left: 27px; top: 28px; width: 46px; height: 46px; border-radius: 50%; background: var(--gc-color-sage-pale); }
.book-page::before, .book-page::after { content: ''; position: absolute; width: 15px; height: 23px; top: 7px; border: 2px solid var(--gc-color-brand); border-radius: 12px 1px 12px 1px; }
.book-page::before { left: 8px; transform: rotate(25deg); }.book-page::after { right: 6px; top: 14px; transform: rotate(205deg); }
.book-line { position: absolute; z-index: 1; left: 29px; width: 42px; height: 3px; border-radius: 3px; background: var(--gc-color-border); }.line-one { top: 86px; }.line-two { top: 96px; width: 30px; }
.art-leaf { z-index: 2; position: absolute; width: 34px; height: 50px; border: 3px solid var(--gc-color-brand); border-radius: 34px 2px 34px 2px; opacity: .8; }.leaf-left { left: 16%; bottom: 22%; transform: rotate(-32deg); }.leaf-right { right: 15%; top: 16%; transform: rotate(147deg); }
.art-dot { position: absolute; width: 9px; height: 9px; border-radius: 50%; background: var(--gc-color-orange); }.dot-one { left: 22%; top: 18%; }.dot-two { right: 22%; bottom: 20%; width: 7px; height: 7px; background: var(--gc-color-purple); }.dot-three { right: 31%; top: 8%; width: 5px; height: 5px; }
.welcome-copy { margin: 6px 0 18px; text-align: center; }.eyebrow { display: block; margin-bottom: 11px; color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1.5px; }.headline { display: block; font-size: 26px; line-height: 1.4; font-weight: var(--gc-font-weight-bold); letter-spacing: -.6px; }.headline-accent { color: var(--gc-color-brand); }.description { display: block; margin-top: 11px; color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); line-height: 1.6; }
.feature-list { margin: 2px auto 14px; }.feature-row { min-height: 36px; display: flex; align-items: center; gap: 9px; color: var(--gc-color-muted); font-size: 12px; }.feature-icon { width: 22px; height: 22px; display: grid; place-items: center; border-radius: 50%; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 13px; font-weight: var(--gc-font-weight-bold); }
.restore-loading { min-height: 44px; display: flex; justify-content: center; align-items: center; gap: 9px; color: var(--gc-color-muted); font-size: 12px; }.loading-dot { width: 16px; height: 16px; border: 2px solid var(--gc-color-sage); border-top-color: var(--gc-color-brand); border-radius: 50%; animation: turn .7s linear infinite; }@keyframes turn { to { transform: rotate(360deg); } }
.actions { display: flex; gap: 11px; margin-top: auto; }.actions :deep(.gc-button) { flex: 1; padding: 0 12px; }.legal-note { display: block; margin-top: 16px; color: var(--gc-color-muted); font-size: 10px; line-height: 1.5; text-align: center; }
</style>

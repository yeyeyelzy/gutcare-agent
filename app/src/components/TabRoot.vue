<template>
  <view class="tab-root" :data-testid="testId">
    <scroll-view class="tab-scroll" scroll-y :show-scrollbar="false">
      <view v-if="authorized" class="tab-content"><slot /></view>
      <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
    </scroll-view>
    <GcBottomNav v-if="authorized" :active="active" />
  </view>
</template>

<script setup lang="ts">
import type { AppTabName } from '../navigation/routes'
import GcBottomNav from './GcBottomNav.vue'

defineProps<{ active: AppTabName; authorized: boolean; testId: string }>()
</script>

<style lang="scss" scoped>
.tab-root { min-height: 100vh; background: var(--gc-color-canvas); }
.tab-scroll { height: 100vh; }
.tab-content { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 18px) 20px calc(env(safe-area-inset-bottom, 0px) + 92px); }
.auth-pending { display: grid; min-height: 100vh; place-items: center; padding: 24px; color: var(--gc-color-muted); text-align: center; }
</style>

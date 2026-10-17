<template>
  <view class="gc-bottom-nav-wrap">
    <view class="gc-bottom-nav" role="navigation" aria-label="主导航" data-testid="bottom-nav">
      <button
        v-for="item in items"
        :key="item.name"
        class="nav-item"
        :class="{ 'nav-item--active': active === item.name }"
        :aria-label="item.label"
        :aria-current="active === item.name ? 'page' : undefined"
        :data-testid="`tab-${item.name}`"
        @click="router?.switchTab(item.name)"
      >
        <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path v-if="item.name === 'today'" d="M3.5 10.5 12 3.8l8.5 6.7M5.5 9.5v10h13v-10M9.5 19.5v-6h5v6" />
          <path v-else-if="item.name === 'records'" d="M7 4.5h10a1.5 1.5 0 0 1 1.5 1.5v13a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 19v-13A1.5 1.5 0 0 1 7 4.5ZM9 9h6M9 13h6M9 17h3" />
          <path v-else-if="item.name === 'analysis'" d="M4 19.5h16M6.5 17v-5M12 17V6M17.5 17V9" />
          <path v-else d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20a7.5 7.5 0 0 1 15 0" />
        </svg>
        <text class="nav-label">{{ item.label }}</text>
      </button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { inject } from 'vue'
import type { AppTabName } from '../navigation/routes'
import { appRouterKey } from '../api/context'

defineProps<{ active: AppTabName }>()
const router = inject(appRouterKey)
const items: ReadonlyArray<{ name: AppTabName; label: string }> = [
  { name: 'today', label: '今日' },
  { name: 'records', label: '记录' },
  { name: 'analysis', label: '分析' },
  { name: 'me', label: '我的' },
]
</script>

<style lang="scss" scoped>
.gc-bottom-nav-wrap { position: fixed; z-index: var(--gc-layer-sticky); right: 0; bottom: 0; left: 0; padding-bottom: env(safe-area-inset-bottom, 0px); background: var(--gc-color-surface-glass); box-shadow: 0 -6px 22px rgba(25, 54, 52, 0.08); backdrop-filter: blur(16px); }
.gc-bottom-nav { display: flex; width: 100%; max-width: 430px; height: 64px; margin: 0 auto; align-items: center; justify-content: space-around; }
.nav-item { display: flex; min-width: 64px; min-height: 48px; padding: 4px 8px; border: 0; border-radius: var(--gc-radius-md); flex: 1; flex-direction: column; align-items: center; justify-content: center; gap: 2px; background: transparent; color: var(--gc-color-muted); }
.nav-item--active { color: var(--gc-color-brand); }
.nav-icon { width: 23px; height: 23px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.nav-label { display: block; font-size: 11px; line-height: 1.3; font-weight: var(--gc-font-weight-medium); }
</style>

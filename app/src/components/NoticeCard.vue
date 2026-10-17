<template>
  <view class="notice-card" :class="`notice-card--${variant}`" :data-testid="testId">
    <view class="notice-icon" aria-hidden="true"><text>{{ variant === 'consent' ? '✓' : 'i' }}</text></view>
    <view class="notice-body">
      <text class="notice-title">{{ title }}</text>
      <text class="notice-copy">{{ description }}</text>
      <text v-if="version" class="notice-version">版本 {{ version }}</text>
      <slot />
    </view>
  </view>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ title: string; description: string; version?: string; variant?: 'info' | 'consent'; testId: string }>(), { variant: 'info' })
</script>

<style lang="scss" scoped>
.notice-card { display: flex; gap: 12px; padding: 15px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }
.notice-card--consent { border-color: var(--gc-color-sage); background: var(--gc-color-sage-pale); }
.notice-icon { flex: 0 0 28px; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 14px; font-weight: var(--gc-font-weight-bold); }
.notice-card--consent .notice-icon { background: var(--gc-color-surface); }
.notice-body { min-width: 0; flex: 1; }
.notice-title { display: block; margin-bottom: 5px; color: var(--gc-color-text); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-semibold); }
.notice-copy { display: block; color: var(--gc-color-muted); font-size: 12px; line-height: 1.65; }
.notice-version { display: block; margin-top: 7px; color: var(--gc-color-muted); font-size: 10px; }
</style>

<template>
  <scroll-view class="scaffold-scroll" scroll-y :show-scrollbar="false">
    <view class="scaffold" :data-testid="testId">
      <view class="brand" aria-label="GutCare">
        <view class="brand-mark" aria-hidden="true"><view class="leaf leaf-a" /><view class="leaf leaf-b" /><view class="stem" /></view>
        <text class="brand-name">GutCare</text>
      </view>
      <view v-if="step" class="step-row" :aria-label="stepLabel">
        <view class="step-track"><view class="step-progress" :style="{ width: step === 1 ? '50%' : '100%' }" /></view>
        <text class="step-caption">{{ stepLabel }}</text>
      </view>
      <view class="heading-block">
        <text v-if="eyebrow" class="eyebrow">{{ eyebrow }}</text>
        <text class="title">{{ title }}</text>
        <text v-if="subtitle" class="subtitle">{{ subtitle }}</text>
      </view>
      <slot />
      <view v-if="$slots.footer" class="footer"><slot name="footer" /></view>
    </view>
  </scroll-view>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
  eyebrow?: string
  step?: 1 | 2
  stepLabel?: string
  testId: string
}>()
</script>

<style lang="scss" scoped>
.scaffold-scroll { width: 100%; height: 100vh; }
.scaffold { min-height: 100vh; width: 100%; max-width: 430px; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 24px) 24px calc(env(safe-area-inset-bottom, 0px) + 28px); display: flex; flex-direction: column; background: var(--gc-color-canvas); }
.brand { display: flex; justify-content: center; align-items: center; gap: 9px; margin-bottom: 28px; }
.brand-mark { width: 32px; height: 32px; position: relative; border-radius: 50%; background: var(--gc-color-sage-pale); }
.leaf { position: absolute; width: 10px; height: 16px; border: 2px solid var(--gc-color-brand); border-radius: 10px 1px 10px 1px; transform: rotate(35deg); }
.leaf-a { left: 8px; top: 5px; }
.leaf-b { right: 6px; top: 10px; transform: rotate(215deg); }
.stem { position: absolute; left: 15px; top: 13px; width: 2px; height: 13px; background: var(--gc-color-brand); transform: rotate(23deg); border-radius: 2px; }
.brand-name { color: var(--gc-color-brand-strong); font-size: 18px; font-weight: var(--gc-font-weight-bold); letter-spacing: .2px; }
.step-row { margin: -4px 0 22px; display: flex; align-items: center; gap: 12px; }
.step-track { flex: 1; height: 5px; border-radius: var(--gc-radius-pill); background: var(--gc-color-sage-pale); overflow: hidden; }
.step-progress { height: 100%; border-radius: inherit; background: var(--gc-color-brand); transition: width .18s ease; }
.step-caption { color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); white-space: nowrap; }
.heading-block { margin-bottom: 24px; }
.eyebrow { display: block; margin-bottom: 8px; color: var(--gc-color-brand); font-size: 12px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1.2px; }
.title { display: block; color: var(--gc-color-text); font-size: 28px; font-weight: var(--gc-font-weight-bold); letter-spacing: -.6px; line-height: 1.25; }
.subtitle { display: block; margin-top: 10px; color: var(--gc-color-muted); font-size: var(--gc-font-size-sm); line-height: 1.65; }
.footer { margin-top: auto; padding-top: 28px; text-align: center; }
</style>

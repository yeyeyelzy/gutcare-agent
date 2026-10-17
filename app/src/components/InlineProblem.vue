<template>
  <view v-if="message" class="problem" role="alert" aria-live="polite" :data-testid="testId">
    <view class="problem-mark" aria-hidden="true">!</view>
    <view class="problem-copy">
      <text class="problem-message">{{ message }}</text>
      <text v-if="requestId" class="request-id">支持编号：{{ requestId }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { presentAuthProblem } from '../api/authUiState'

const props = withDefaults(defineProps<{ error: unknown; fallback?: string; testId: string }>(), { fallback: '暂时无法完成操作，请稍后重试。' })
const presentation = computed(() => presentAuthProblem(props.error, props.fallback))
const message = computed(() => presentation.value?.message ?? '')
const requestId = computed(() => presentation.value?.requestId)
</script>

<style lang="scss" scoped>
.problem { margin: 16px 0; padding: 13px 14px; display: flex; align-items: flex-start; gap: 10px; border: 1px solid var(--gc-color-danger-border); border-radius: var(--gc-radius-md); background: var(--gc-color-danger-pale); }
.problem-mark { flex: 0 0 22px; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--gc-color-danger); color: var(--gc-color-on-brand); font-size: 13px; font-weight: var(--gc-font-weight-bold); }
.problem-copy { min-width: 0; }
.problem-message { display: block; color: var(--gc-color-danger); font-size: var(--gc-font-size-sm); line-height: 1.5; }
.request-id { display: block; margin-top: 5px; color: var(--gc-color-muted); font-size: 11px; overflow-wrap: anywhere; }
</style>

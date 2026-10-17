<template>
  <view class="data-status" :class="`data-status--${state}`" :role="state === 'error' ? 'alert' : 'status'" aria-live="polite" :aria-busy="state === 'loading'" :data-testid="testId">
    <view v-if="state === 'loading'" class="status-spinner" aria-hidden="true" />
    <view v-else class="status-mark" aria-hidden="true">{{ state === 'error' ? '!' : state === 'empty' ? '○' : '·' }}</view>
    <text class="status-copy">{{ copy }}</text>
    <button v-if="state === 'error' && retryable" class="retry" :disabled="busy" @click="$emit('retry')">{{ busy ? '正在重试…' : '重试' }}</button>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  state: 'loading' | 'empty' | 'error' | 'unavailable'
  message?: string
  retryable?: boolean
  busy?: boolean
  testId: string
}>(), { retryable: false, busy: false })
defineEmits<{ retry: [] }>()
const copy = computed(() => props.message ?? ({
  loading: '正在安全载入本人数据…',
  empty: '此范围内暂无记录。',
  error: '暂时无法载入，请稍后重试。',
  unavailable: '此功能尚未接入数据服务；当前不展示演示或推测数据。',
}[props.state]))
</script>

<style lang="scss" scoped>
.data-status { min-height: 58px; display: flex; align-items: center; gap: 10px; color: var(--gc-color-muted); }
.status-mark { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; border-radius: 50%; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 16px; }
.status-copy { min-width: 0; flex: 1; font-size: 12px; line-height: 1.55; }
.data-status--error { color: var(--gc-color-danger); }
.data-status--error .status-mark { background: var(--gc-color-danger-pale); color: var(--gc-color-danger); }
.status-spinner { width: 19px; height: 19px; flex: 0 0 19px; border: 2px solid var(--gc-color-sage); border-top-color: var(--gc-color-brand); border-radius: 50%; animation: spin .7s linear infinite; }
.retry { min-width: 56px; min-height: 44px; border: 0; background: transparent; color: var(--gc-color-brand-strong); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }
.retry[disabled] { opacity: .55; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>

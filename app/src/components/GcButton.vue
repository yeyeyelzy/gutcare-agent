<template>
  <button
    class="gc-button"
    :class="[`gc-button--${variant}`, { 'gc-button--block': block, 'gc-button--busy': busy }]"
    :disabled="isGcButtonDisabled(disabled, busy)"
    :loading="busy"
    :aria-busy="busy"
    :aria-label="ariaLabel"
    :data-testid="testId"
    @click="$emit('click')"
  >
    <view v-if="busy" class="busy-dot" aria-hidden="true" />
    <slot>{{ label }}</slot>
  </button>
</template>

<script setup lang="ts">
import { isGcButtonDisabled } from '../api/authUiState'

withDefaults(defineProps<{
  label?: string
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger'
  disabled?: boolean
  busy?: boolean
  block?: boolean
  ariaLabel?: string
  testId: string
}>(), { variant: 'primary', disabled: false, busy: false, block: true })

defineEmits<{ click: [] }>()
</script>

<style lang="scss" scoped>
.gc-button { min-height: 48px; padding: 0 20px; border: 1px solid transparent; border-radius: 16px; display: inline-flex; align-items: center; justify-content: center; gap: 9px; color: var(--gc-color-text); font-size: var(--gc-font-size-md); font-weight: var(--gc-font-weight-semibold); line-height: 1.2; transition: opacity .15s ease, transform .15s ease; }
.gc-button--block { width: 100%; }
.gc-button--primary { background: var(--gc-color-brand); color: var(--gc-color-on-brand); box-shadow: var(--gc-shadow-card); }
.gc-button--secondary { border-color: var(--gc-color-border); background: var(--gc-color-surface); color: var(--gc-color-brand-strong); }
.gc-button--quiet { background: transparent; color: var(--gc-color-brand); }
.gc-button--danger { border-color: var(--gc-color-danger); background: var(--gc-color-surface); color: var(--gc-color-danger); }
.gc-button[disabled] { opacity: .52; }
.gc-button--busy { opacity: .75; }
.busy-dot { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.45); border-top-color: currentColor; border-radius: 50%; animation: turn .7s linear infinite; }
.gc-button--secondary .busy-dot, .gc-button--quiet .busy-dot { border-color: var(--gc-color-border); border-top-color: currentColor; }
@keyframes turn { to { transform: rotate(360deg); } }
</style>

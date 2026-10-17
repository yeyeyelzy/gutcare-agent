<template>
  <view class="field" :class="{ 'field--invalid': invalid, 'field--disabled': disabled }">
    <label class="field-label" :for="id">
      <text>{{ label }}</text><text v-if="required" class="required-mark" aria-hidden="true">*</text>
    </label>
    <view class="field-control">
      <view v-if="icon" class="field-icon" aria-hidden="true">{{ iconGlyph }}</view>
      <input
        :id="id"
        class="field-input"
        :class="{ 'field-input--with-action': revealable }"
        :type="resolvedType"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :maxlength="maxlength"
        :autocomplete="autocomplete"
        :password="resolvedType === 'password'"
        :aria-label="label"
        :aria-invalid="invalid"
        :aria-describedby="descriptionId"
        :data-testid="testId"
        @input="onInput"
      />
      <button v-if="revealable" class="reveal" type="button" :aria-label="visible ? '隐藏密码' : '显示密码'" :data-testid="`${testId}-visibility`" @click="visible = !visible">
        <text aria-hidden="true">{{ visible ? '隐藏' : '显示' }}</text>
      </button>
    </view>
    <text v-if="hint" :id="descriptionId" class="field-hint">{{ hint }}</text>
    <text v-if="error" :id="descriptionId" class="field-error" role="alert">{{ error }}</text>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  id: string
  label: string
  modelValue: string
  type?: 'email' | 'text' | 'password' | 'number'
  placeholder?: string
  autocomplete?: string
  required?: boolean
  disabled?: boolean
  invalid?: boolean
  hint?: string
  error?: string
  maxlength?: number
  revealable?: boolean
  testId: string
  icon?: 'email' | 'lock' | 'key'
}>(), { type: 'text', autocomplete: 'off', required: false, disabled: false, invalid: false, maxlength: 254, revealable: false })

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const visible = ref(false)
const resolvedType = computed(() => props.type === 'email' ? 'text' : props.revealable && visible.value ? 'text' : props.type)
const descriptionId = computed(() => `${props.id}-description`)
const iconGlyph = computed(() => props.icon === 'email' ? '✉' : props.icon === 'lock' ? '⌑' : '◇')

function onInput(event: Event) {
  const detail = (event as unknown as { detail?: { value?: unknown } }).detail
  const target = event.target as HTMLInputElement | null
  const value = typeof detail?.value === 'string' ? detail.value : target?.value ?? ''
  emit('update:modelValue', value)
}
</script>

<style lang="scss" scoped>
.field { margin-bottom: 14px; }
.field-label { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; color: var(--gc-color-text); font-size: var(--gc-font-size-sm); font-weight: var(--gc-font-weight-semibold); }
.required-mark, .field-error { color: var(--gc-color-danger); }
.field-control { min-height: 54px; padding: 0 13px; display: flex; align-items: center; gap: 10px; border: 1px solid var(--gc-color-border); border-radius: 13px; background: var(--gc-color-surface); transition: border-color .15s ease, box-shadow .15s ease; }
.field-icon { flex: 0 0 20px; width: 20px; color: var(--gc-color-muted); font-size: 17px; text-align: center; }
.field-control:focus-within { border-color: var(--gc-color-brand); box-shadow: 0 0 0 3px var(--gc-color-brand-focus); }
.field--invalid .field-control { border-color: var(--gc-color-danger); }
.field-input { min-width: 0; width: 100%; height: 52px; padding: 0; border: 0; background: transparent; color: var(--gc-color-text); font-size: var(--gc-font-size-md); }
.field-input--with-action { width: calc(100% - 56px); }
.field-input::placeholder { color: var(--gc-color-placeholder); }
.field-input[disabled] { opacity: .65; }
.reveal { min-width: 48px; min-height: 44px; padding: 0 4px; background: transparent; color: var(--gc-color-brand); font-size: 12px; }
.field-hint, .field-error { display: block; margin-top: 6px; font-size: 12px; line-height: 1.5; }
.field-hint { color: var(--gc-color-muted); }
</style>

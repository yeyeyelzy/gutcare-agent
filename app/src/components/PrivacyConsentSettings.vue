<template>
  <view class="privacy-page">
    <view class="privacy-shell">
      <view class="topbar"><button class="back-button" aria-label="返回上一页" data-testid="consent-back" @click="$emit('back')">‹</button><text class="topbar-title">隐私与授权</text><view class="spacer" /></view>
      <view class="intro"><text class="eyebrow">PRIVACY CONTROL</text><text class="title">授权管理</text><text class="subtitle">每项授权独立管理。服务端没有可用的当前告知时，不会开放同意操作。</text></view>
      <view v-if="loading" class="state-card" role="status" aria-busy="true">正在读取授权状态与当前告知…</view>
      <view v-else-if="loadError" class="state-card error" role="alert"><text>{{ loadError }}</text><text v-if="requestId">请求编号：{{ requestId }}</text><GcButton label="重试" variant="secondary" :busy="busy" test-id="consent-retry" @click="load" /></view>
      <view v-else class="consent-list">
        <view v-for="item in items" :key="item.type" class="consent-card" :data-testid="`consent-${item.type}`">
          <view class="card-heading"><text class="card-title">{{ item.title }}</text><text class="status" :class="{ granted: item.status?.granted }">{{ consentStateLabel(item.status) }}</text></view>
          <text class="notice-state" role="status">{{ item.notice?.enabled ? (item.notice.policy_version?.startsWith('test-only-') ? '开发/自动化测试专用告知，未获生产法律批准。' : '服务端当前正式告知。') : item.noticeFailed ? (item.status?.granted ? '暂时无法读取当前告知；不能新同意，但可撤回已有授权。' : '暂时无法读取当前告知；当前不能提交同意。') : (item.status?.granted ? '当前告知不可用；不能新同意，但可撤回已有授权。' : '正式告知尚未配置，当前不能提交同意。') }}</text>
          <GcButton v-if="item.noticeFailed" label="重试读取告知" variant="secondary" :busy="loading" :disabled="loading" :test-id="`consent-notice-retry-${item.type}`" @click="load" />
          <template v-if="item.notice?.enabled">
            <text class="notice-copy">{{ item.notice.summary }}</text>
            <text class="notice-label">用途</text><text class="notice-copy">{{ item.notice.purpose }}</text>
            <text class="notice-label">处理范围</text><text class="notice-copy">{{ item.notice.data_scope }}</text>
            <text class="notice-label">接收方</text><text class="notice-copy">{{ item.notice.recipient }}</text>
            <text class="notice-label">撤回效果</text><text class="notice-copy">{{ item.notice.withdrawal_effect }}</text>
            <text class="policy-version">告知版本：{{ item.notice.policy_version }}</text>
          </template>
          <GcButton
            v-if="item.notice?.enabled || item.status?.granted"
            :label="item.status?.granted ? '撤回此项授权' : '单独同意此项授权'"
            :variant="item.status?.granted ? 'secondary' : 'primary'"
            :busy="busyType === item.type"
            :disabled="busy"
            :test-id="`consent-action-${item.type}`"
            @click="decide(item)"
          />
        </view>
        <view class="scope-note" data-testid="consent-scope-note">心情记录的新建与修改需要“健康数据处理”和“心情数据处理”均已同意。智能分析中的心情共享还需“心情智能共享”和“第三方智能处理”分别同意；这两项不会作为普通记录授权的替代条件。查看和删除本人心情记录不依赖这些记录写入授权。</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref } from 'vue'
import { consentApiKey } from '../api/context'
import { AppError } from '../api/errors'
import type { ConsentNotice, ConsentStatus } from '../api/openapiTypes'
import type { ManagedConsentType } from '../api/consentApi'
import GcButton from './GcButton.vue'

defineEmits<{ back: [] }>()
const api = inject(consentApiKey)
const loading = ref(true)
const busy = ref(false)
const busyType = ref<ManagedConsentType | null>(null)
const loadError = ref('')
const requestId = ref('')
const statuses = ref<ConsentStatus[]>([])
const notices = ref<Partial<Record<ManagedConsentType, ConsentNotice>>>({})
const noticeFailures = ref<Partial<Record<ManagedConsentType, boolean>>>({})
const definitions: { type: ManagedConsentType; title: string }[] = [
  { type: 'health_data_processing', title: '健康数据处理' },
  { type: 'mood_data_processing', title: '心情数据处理' },
  { type: 'mood_ai_sharing', title: '心情智能共享' },
  { type: 'third_party_ai', title: '第三方智能处理' },
]
const items = computed(() => definitions.map((definition) => ({
  ...definition,
  status: statuses.value.find((status) => status.consent_type === definition.type),
  notice: notices.value[definition.type],
  noticeFailed: noticeFailures.value[definition.type] === true,
})))

function consentStateLabel(status: ConsentStatus | undefined): string {
  if (!status?.decided_at) return '未决定'
  if (status.granted) return '已同意'
  return status.revoked_at ? '已撤回' : '未授权'
}

onMounted(() => { void load() })

async function load() {
  if (!api) { loading.value = false; loadError.value = '授权服务暂不可用。'; return }
  loading.value = true; loadError.value = ''; requestId.value = ''
  try {
    statuses.value = await api.list()
    noticeFailures.value = {}
    const results = await Promise.all(definitions.map(async ({ type }) => {
      try { return [type, await api.notice(type)] as const }
      catch { noticeFailures.value[type] = true; return [type, { consent_type: type, enabled: false } as ConsentNotice] as const }
    }))
    notices.value = Object.fromEntries(results)
  } catch (error) {
    loadError.value = error instanceof AppError && error.status === 401
      ? '登录状态已失效，请重新登录。'
      : '暂时无法读取授权状态，请检查网络后重试。'
    requestId.value = error instanceof AppError ? error.requestId ?? '' : ''
  } finally { loading.value = false }
}

async function decide(item: (typeof items.value)[number]) {
  const notice = item.notice
  const granted = item.status?.granted !== true
  const policyVersion = granted
    ? (notice?.enabled ? notice.policy_version : null)
    : (item.status?.policy_version ?? null)
  if (!api || busy.value || !policyVersion) return
  const message = granted
    ? `确认单独同意“${item.title}”？请先阅读本页完整告知。`
    : `确认撤回“${item.title}”？撤回将按既定规则停止后续依赖此授权的处理。${notice?.enabled ? ` ${notice.withdrawal_effect}` : ''}`
  uni.showModal({ title: granted ? '确认授权' : '确认撤回', content: message, confirmText: granted ? '确认同意' : '确认撤回', cancelText: '取消', success: async ({ confirm }) => {
    if (!confirm || !api) return
    busy.value = true; busyType.value = item.type
    try {
      await api.decide({ consent_type: item.type, policy_version: policyVersion, granted })
      await load()
    } catch (error) {
      loadError.value = error instanceof AppError && error.status === 422
        ? '当前告知版本已变化或不可用；已停止提交，请重新载入服务端告知。'
        : '授权操作未完成，请稍后重试。'
      requestId.value = error instanceof AppError ? error.requestId ?? '' : ''
    } finally { busy.value = false; busyType.value = null }
  } })
}
</script>

<style lang="scss" scoped>
.privacy-page { min-height: 100vh; background: var(--gc-color-canvas); }.privacy-shell { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); }.topbar { display: flex; height: 48px; align-items: center; justify-content: space-between; }.back-button { display: grid; width: 44px; height: 44px; place-items: center; border: 0; border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 27px; }.topbar-title { font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.spacer { width: 44px; }.intro { display: flex; margin: 24px 2px 18px; flex-direction: column; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.title { margin-top: 5px; font-size: 26px; font-weight: var(--gc-font-weight-bold); }.subtitle { margin-top: 7px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.6; }.consent-list { display: flex; flex-direction: column; gap: 12px; }.consent-card,.state-card,.scope-note { display: flex; padding: 17px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); flex-direction: column; gap: 9px; background: var(--gc-color-surface); }.card-heading { display: flex; justify-content: space-between; gap: 12px; }.card-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.status { color: var(--gc-color-muted); font-size: 12px; }.status.granted { color: var(--gc-color-brand-strong); }.notice-state { color: var(--gc-color-warning); font-size: 11px; line-height: 1.5; }.notice-copy { color: var(--gc-color-text); font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }.notice-label { margin-top: 2px; color: var(--gc-color-muted); font-size: 10px; }.policy-version { color: var(--gc-color-muted); font-size: 10px; }.scope-note { color: var(--gc-color-muted); font-size: 11px; line-height: 1.65; }.error { color: var(--gc-color-danger); }
</style>

<template>
  <view class="page" data-testid="deletion-progress">
    <view class="topbar"><text class="topbar-title">账号注销进度</text><view class="spacer" /></view>
    <view v-if="receiptToReveal" class="receipt-card" role="alert" data-testid="deletion-receipt-once"><text class="section-title">请立即手动记录一次性凭证</text><text class="copy">此凭证仅在本次成功响应后显示。离开页面后不会再次展示。请勿截图、复制、转发或粘贴到其他应用。</text><text class="meta">请求编号：{{ acceptedOperationId }}</text><text class="receipt">{{ receiptToReveal }}</text><text v-if="receiptStorage === 'memory_only'" class="warning">本机安全存储不可用，凭证仅保存在当前进程内。请现在手动记录；关闭应用后可能无法找回。</text><text v-if="receiptStorageErrorCode" class="warning">安全保存失败（{{ receiptStorageErrorCode }}）。请妥善手动记录一次性凭证。</text><text v-if="refreshCleanupError" class="warning">本机刷新凭据未能确认删除（{{ refreshCleanupError }}）。应用内存会话已清除；请重启应用并联系支持。</text></view>
    <view v-else-if="acceptedUnavailable" class="warning-card" role="status" data-testid="deletion-receipt-unavailable"><text>本次响应未提供可显示的凭证，本机也没有可关联的凭证。为保护安全，系统无法恢复或重新显示一次性凭证；请联系支持并说明账号注销请求已受理。</text><text class="meta">请求编号：{{ acceptedOperationId }}</text><text v-if="receiptStorageErrorCode" class="warning">读取本机安全存储失败（{{ receiptStorageErrorCode }}）。</text><text v-if="refreshCleanupError" class="warning">本机刷新凭据未能确认删除（{{ refreshCleanupError }}）。应用内存会话已清除；请重启应用并联系支持。</text></view>
    <view v-if="status" class="status-card" aria-live="polite" data-testid="deletion-status-result"><text class="section-title">当前状态：{{ statusLabel }}</text><text class="copy">{{ statusDescription }}</text><text class="meta">请求编号：{{ status.operation_id }}</text><text class="meta">受理时间：{{ status.requested_at }}</text><text class="meta">预计完成时间：{{ status.due_at }}</text><text v-if="status.status === 'completed' && status.completed_at" class="meta">完成时间：{{ status.completed_at }}</text></view>
    <view v-if="statusError" class="error" role="alert" data-testid="deletion-status-error">{{ statusErrorText }}</view>
    <view v-if="queryStorageWarning" class="warning-card" role="status" data-testid="deletion-receipt-save-warning">{{ queryStorageWarning }}</view>
    <view v-if="savedRecord" class="card"><text class="section-title">查询已保存的进度</text><text class="copy">凭证保存在本机安全存储中，仅用于查询注销状态。</text><GcButton label="查询进度" :busy="busy" :disabled="busy" test-id="deletion-query-saved" @click="querySaved" /></view>
    <view class="card"><text class="section-title">手动查询</text><text class="copy">如你已自行保存一次性凭证，可在此输入。输入内容仅用于本次查询，不会写入普通应用存储。</text><GcField id="deletion-operation-id" v-model="operationId" label="请求编号" placeholder="输入请求编号" autocomplete="off" test-id="deletion-operation-id"/><GcField id="deletion-receipt" v-model="receipt" label="一次性凭证" type="password" placeholder="输入一次性凭证" autocomplete="off" test-id="deletion-receipt"/><GcButton label="查询注销进度" :busy="busy" :disabled="busy || !canQueryManual" test-id="deletion-query-manual" @click="queryManual" /></view>
    <view v-if="status?.status === 'overdue' || status?.status === 'dead_letter'" class="support" role="note" data-testid="deletion-contact-support">该请求需要支持团队协助。请联系官方支持并提供请求编号；请勿重复提交注销请求。</view>
    <button class="login-link" data-testid="deletion-progress-login" @click="router?.reLaunch('login')">返回登录</button>
  </view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import { AppError } from '../../api/errors'
import { appRouterKey, privacyDeletionServiceKey } from '../../api/context'
import type { DeletionReceiptRecord } from '../../api/deletionReceiptStore'
import type { DeletionStatusResult } from '../../api/privacyDeletionService'
import type { PrivacyDeletionStatus } from '../../api/openapiTypes'
import GcButton from '../../components/GcButton.vue'
import GcField from '../../components/GcField.vue'

const deletion = inject(privacyDeletionServiceKey)
const router = inject(appRouterKey)
const status = ref<PrivacyDeletionStatus | null>(null)
const savedRecord = ref<DeletionReceiptRecord | null>(null)
const receiptToReveal = ref<string | null>(null)
const receiptStorage = ref<'secure' | 'memory_only' | 'unavailable'>('unavailable')
const receiptStorageErrorCode = ref<string | null>(null)
const refreshCleanupError = ref<string | null>(null)
const acceptedUnavailable = ref(false)
const acceptedOperationId = ref('')
const operationId = ref('')
const receipt = ref('')
const busy = ref(false)
const statusError = ref<unknown>(null)
const queryStorageWarning = ref('')
let pageGeneration = 0
let pageVisible = false
let clearInFlightManualSecrets: (() => void) | null = null
const canQueryManual = computed(() => /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(operationId.value.trim()) && receipt.value.length >= 40 && receipt.value.length <= 128)
const statusLabel = computed(() => ({ pending: '等待处理', processing: '处理中', overdue: '需要支持协助', dead_letter: '需要支持协助', completed: '已完成' }[status.value?.status ?? 'pending']))
const statusDescription = computed(() => ({ pending: '注销请求已受理，尚未开始后台处理。受理不代表数据已物理删除。', processing: '后台正在按既定流程处理。受理不代表数据已物理删除。', overdue: '该请求已超出预期处理时间，请联系支持团队协助。', dead_letter: '该请求需要支持团队人工协助，请勿重复提交注销。', completed: '服务端已确认注销流程完成。' }[status.value?.status ?? 'pending']))
const statusErrorText = computed(() => {
  if (statusError.value instanceof AppError && statusError.value.status === 404) return '未找到匹配的注销请求或凭证。请核对输入内容。'
  if (statusError.value instanceof AppError && statusError.value.status === 429) return '查询过于频繁，请稍后再试。'
  if (statusError.value instanceof AppError && ['offline', 'network', 'timeout'].includes(statusError.value.kind)) return '当前无法连接服务。请联网后重新查询。'
  if (statusError.value instanceof AppError && statusError.value.requestId) return `暂时无法查询。请稍后重试；如问题持续，请联系支持并提供编号 ${statusError.value.requestId}。`
  return '暂时无法查询注销进度，请稍后重试。'
})

onShow(() => {
  pageVisible = true
  const generation = ++pageGeneration
  void initialize(generation)
})
onHide(clearSensitivePageState)
onUnload(clearSensitivePageState)
function isCurrentPage(generation: number): boolean {
  return pageVisible && generation === pageGeneration
}

function clearSensitivePageState() {
  pageVisible = false
  pageGeneration += 1
  clearInFlightManualSecrets?.()
  clearInFlightManualSecrets = null
  acceptedOperationId.value = ''
  operationId.value = ''
  receipt.value = ''
  receiptToReveal.value = null
  savedRecord.value = null
  status.value = null
  statusError.value = null
  queryStorageWarning.value = ''
  receiptStorageErrorCode.value = null
  refreshCleanupError.value = null
  acceptedUnavailable.value = false
  receiptStorage.value = 'unavailable'
  busy.value = false
}

async function initialize(generation: number) {
  if (!deletion) {
    if (isCurrentPage(generation)) statusError.value = new Error('服务暂不可用')
    return
  }
  const accepted = deletion.takeAcceptedProgressContext()
  if (accepted) {
    acceptedOperationId.value = accepted.operationId
    receiptToReveal.value = accepted.receiptForOneTimeDisplay
    receiptStorage.value = accepted.receiptStorage
    receiptStorageErrorCode.value = accepted.receiptStorageErrorCode
    refreshCleanupError.value = accepted.refreshTokenCleanupErrorCode
    acceptedUnavailable.value = !accepted.receiptAvailable
  }
  const record = await deletion.loadSavedRecord()
  if (!isCurrentPage(generation)) return
  savedRecord.value = record
}

async function querySaved() {
  const record = savedRecord.value
  if (!record || !deletion || busy.value) return
  await runQuery(() => deletion.querySavedStatus(record))
}

async function queryManual() {
  if (!deletion || !canQueryManual.value || busy.value) return
  let id = operationId.value.trim()
  let token = receipt.value
  operationId.value = ''
  receipt.value = ''
  const clearSecrets = () => { id = ''; token = '' }
  clearInFlightManualSecrets = clearSecrets
  try { await runQuery(() => deletion.queryManualStatus(id, token)) }
  finally {
    id = ''
    token = ''
    if (clearInFlightManualSecrets === clearSecrets) clearInFlightManualSecrets = null
  }
}

async function runQuery(query: () => Promise<DeletionStatusResult>) {
  const generation = pageGeneration
  busy.value = true
  statusError.value = null
  queryStorageWarning.value = ''
  try {
    const result = await query()
    if (!isCurrentPage(generation)) return
    status.value = result.status
    if (!result.receiptStoredSecurely && result.status.status !== 'completed') {
      queryStorageWarning.value = '查询成功，但凭证未能保存在本机安全存储中（' + (result.receiptStorageErrorCode ?? 'SECURE_STORAGE_FAILED') + '）。凭证仅在当前进程内保留，请妥善保存你原有的一次性凭证。'
    }
    const record = result.status.status === 'completed' ? null : await deletion?.loadSavedRecord() ?? null
    if (!isCurrentPage(generation)) return
    savedRecord.value = record
  } catch (error) {
    if (isCurrentPage(generation)) statusError.value = error
  } finally {
    if (isCurrentPage(generation)) busy.value = false
  }
}
</script>

<style lang="scss" scoped>
.page { box-sizing: border-box; width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 16px) 20px calc(env(safe-area-inset-bottom, 0px) + 28px); background: var(--gc-color-canvas); }.topbar { display: flex; min-height: 48px; align-items: center; justify-content: space-between; margin-bottom: 18px; }.topbar-title { color: var(--gc-color-text); font-size: 19px; font-weight: var(--gc-font-weight-semibold); }.spacer { width: 44px; }.card,.status-card,.receipt-card,.warning-card,.support { display: flex; margin-bottom: 14px; padding: 16px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); flex-direction: column; gap: 10px; }.receipt-card,.warning-card,.support { border-color: var(--gc-color-danger-border); background: var(--gc-color-danger-pale); }.section-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.copy,.meta { color: var(--gc-color-muted); font-size: 12px; line-height: 1.6; }.meta { word-break: break-all; }.receipt { padding: 13px; border-radius: var(--gc-radius-md); background: var(--gc-color-canvas); color: var(--gc-color-text); font-family: monospace; font-size: 12px; line-height: 1.6; word-break: break-all; user-select: text; }.warning,.support { color: var(--gc-color-danger); font-size: 12px; line-height: 1.6; }.error { margin-bottom: 14px; padding: 13px; border: 1px solid var(--gc-color-danger-border); border-radius: var(--gc-radius-md); background: var(--gc-color-danger-pale); color: var(--gc-color-danger); font-size: 12px; line-height: 1.6; }.login-link { min-height: 48px; margin-top: 4px; background: transparent; color: var(--gc-color-brand); font-size: 14px; }
</style>

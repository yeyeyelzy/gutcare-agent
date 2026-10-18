<template>
  <view v-if="authorized" class="conflict-page" data-testid="medical-fact-conflict-workspace">
    <view class="shell">
      <view class="topbar"><button class="back" aria-label="返回" data-testid="medical-fact-conflict-back" @click="goBack">‹</button><text class="topbar-title">{{ isDetail ? '检验事实冲突详情' : '待核对冲突' }}</text><button class="refresh" :disabled="busy" data-testid="medical-fact-conflict-refresh" @click="refresh">刷新</button></view>
      <view class="intro"><text class="eyebrow">MEDICAL RECORD REVIEW</text><text class="title">{{ isDetail ? '检验结果有差异' : '待核对冲突' }}</text><text class="subtitle">值存在差异，APP 不判断正确性或严重性；请结合来源资料核对。</text></view>

      <template v-if="!isDetail">
        <view class="filters" role="group" aria-label="冲突状态筛选">
          <button v-for="option in filters" :key="option.value" class="filter" :class="{ selected: selectedStatus === option.value }" :aria-pressed="selectedStatus === option.value" :data-testid="`medical-fact-conflict-filter-${option.value}`" @click="changeFilter(option.value)">{{ option.label }}</button>
        </view>
        <view v-if="listLoading && items.length === 0" class="state-card" role="status" data-testid="medical-fact-conflict-list-loading">正在读取冲突…</view>
        <view v-else-if="listError && items.length === 0" class="state-card error-card" data-testid="medical-fact-conflict-list-error"><text>{{ listError }}</text><GcButton label="重试" test-id="medical-fact-conflict-list-retry" @click="loadList" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view v-else-if="items.length === 0" class="state-card" data-testid="medical-fact-conflict-empty">当前筛选下没有冲突记录。</view>
        <view v-else class="conflict-list" data-testid="medical-fact-conflict-list">
          <view v-if="listError" class="inline-error" role="alert" data-testid="medical-fact-conflict-refresh-error"><text>{{ listError }}</text><button class="text-action" data-testid="medical-fact-conflict-refresh-retry" @click="loadList">重试刷新</button><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
          <button v-for="item in items" :key="item.id" class="conflict-row" :data-testid="`medical-fact-conflict-row-${item.id}`" @click="router?.navigateMedicalFactConflictDetail(item.id)">
            <view class="row-head"><text class="row-title">检验结果存在差异</text><text class="status">{{ conflictStatusLabel(item.status) }}</text></view>
            <text class="row-meta">建立时间：{{ formatDate(item.created_at) }}</text>
            <text class="row-version">记录版本 {{ item.record_version }}</text>
            <text class="chevron" aria-hidden="true">›</text>
          </button>
        </view>
        <text class="safety-note">列表顺序遵循服务端返回；应用不按临床含义重排或推断。</text>
      </template>

      <template v-else>
        <view v-if="detailLoading && !detail" class="state-card" role="status" data-testid="medical-fact-conflict-detail-loading">正在读取冲突详情…</view>
        <view v-else-if="detailError && !detail" class="state-card error-card" data-testid="medical-fact-conflict-detail-error"><text>{{ detailError }}</text><GcButton label="重试" test-id="medical-fact-conflict-detail-retry" @click="loadDetail" /><text v-if="detailRequestId" class="request-id">请求编号：{{ detailRequestId }}</text></view>
        <view v-else-if="detail" class="detail" data-testid="medical-fact-conflict-detail">
          <view class="detail-card">
            <view class="row-head"><text class="section-title">冲突状态</text><text class="status">{{ conflictStatusLabel(detail.status) }}</text></view>
            <text class="notice">这些是来自不同报告的患者确认事实。应用不选择正确值，不判断临床严重性，也不合并或删除事实。</text>
            <text class="row-meta">记录版本 {{ detail.record_version }} · 创建于 {{ formatDate(detail.created_at) }}</text>
            <text v-if="detail.resolution === 'keep_both'" class="row-meta">处理方式：保留双方为独立事实</text>
          </view>
          <view v-if="detailError" class="inline-error" role="alert" data-testid="medical-fact-conflict-detail-refresh-error"><text>{{ detailError }}</text><text v-if="detailRequestId" class="request-id">请求编号：{{ detailRequestId }}</text></view>
          <view class="member-list" data-testid="medical-fact-conflict-members">
            <view v-for="(member, index) in detail.members || []" :key="member.fact_id" class="member-card" :data-testid="`medical-fact-conflict-member-${index}`">
              <text class="member-title">{{ conflictFieldLabel(member.field_code) }}</text>
              <text class="member-value">{{ conflictMemberValueLabel(member) }}<text v-if="conflictMemberUnitLabel(member.unit ?? null)" class="unit"> {{ conflictMemberUnitLabel(member.unit ?? null) }}</text></text>
              <text class="row-meta">采样日期：{{ conflictSampledOnLabel(member.sampled_on) }}</text>
              <text class="row-meta">事实编号：{{ safeId(member.fact_id) }}</text>
              <text class="row-meta">来源档案：{{ conflictDocumentIdLabel(member.source_document_id) }}</text>
              <button v-if="isUuid(member.source_document_id)" class="source-button" :data-testid="`medical-fact-conflict-source-${index}`" @click="router?.navigateMedicalDocumentDetail(member.source_document_id)">查看来源档案</button>
            </view>
            <view v-if="detail.members && detail.members.length === 0" class="state-card" data-testid="medical-fact-conflict-members-empty">来源事实当前不可用。</view>
          </view>
          <view v-if="detail.status === 'open'" class="keep-both-card">
            <text class="section-title">保留双方事实</text>
            <text class="row-meta">此操作保留双方为独立事实，不选择优先值、不合并、不删除。确认后冲突标记为已处理。</text>
            <GcButton label="确认保留双方" :busy="busy" :disabled="busy || !canKeepBoth(detail)" test-id="medical-fact-conflict-keep-both" @click="confirmKeepBoth" />
          </view>
          <view v-else class="readonly-note" data-testid="medical-fact-conflict-readonly">此冲突为只读状态，不能再次处理。</view>
          <view v-if="actionError" class="inline-error" role="alert" data-testid="medical-fact-conflict-action-error"><text>{{ actionError }}</text><button class="text-action" :disabled="busy" data-testid="medical-fact-conflict-action-refresh" @click="loadDetail">刷新当前状态</button><text v-if="actionRequestId" class="request-id">请求编号：{{ actionRequestId }}</text></view>
          <text v-if="conflictNotice" class="notice" role="status" data-testid="medical-fact-conflict-notice">{{ conflictNotice }}</text>
        </view>
      </template>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite" data-testid="medical-fact-conflict-auth-gate">正在验证本人会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { appRouterKey, medicalFactConflictsApiKey } from '../api/context'
import { AppError } from '../api/errors'
import type { MedicalFactConflict } from '../api/openapiTypes'
import { canKeepBoth, conflictDocumentIdLabel, conflictFieldLabel, conflictMemberUnitLabel, conflictMemberValueLabel, conflictSampledOnLabel, conflictStatusLabel } from '../api/medicalFactConflictView'
import type { MedicalFactConflictStatusFilter } from '../api/medicalFactConflictView'
import { canRenderRoute, isUuid } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import GcButton from './GcButton.vue'

const props = defineProps<{ mode: 'list' | 'detail' }>()
const api = inject(medicalFactConflictsApiKey)
const router = inject(appRouterKey)
const auth = useAuthStore()
const isDetail = computed(() => props.mode === 'detail')
const routeName = computed(() => isDetail.value ? 'medicalFactConflictDetail' : 'medicalFactConflicts')
const authorized = computed(() => canRenderRoute(routeName.value, auth.state))
const conflictId = ref('')
const selectedStatus = ref<MedicalFactConflictStatusFilter>('open')
const items = ref<MedicalFactConflict[]>([])
const detail = ref<MedicalFactConflict | null>(null)
const listLoading = ref(false)
const detailLoading = ref(false)
const busy = ref(false)
const listError = ref('')
const detailError = ref('')
const actionError = ref('')
const conflictNotice = ref('')
const requestId = ref('')
const detailRequestId = ref('')
const actionRequestId = ref('')
let generation = 0
let visible = false
let firstShow = true
let appliedStatus: MedicalFactConflictStatusFilter = 'open'
const filters: { value: MedicalFactConflictStatusFilter; label: string }[] = [
  { value: 'open', label: '待核对' }, { value: 'resolved', label: '已处理' }, { value: 'invalidated', label: '来源失效' }, { value: 'all', label: '全部' },
]
const isCurrent = (value: number) => visible && value === generation

onLoad((options) => {
  if (!authorized.value) { router?.requireAuthentication(routeName.value); return }
  visible = true
  if (isDetail.value) {
    conflictId.value = typeof options?.conflict_id === 'string' ? options.conflict_id : ''
    if (!isUuid(conflictId.value)) { detailError.value = '冲突编号无效。'; return }
    void loadDetail()
  } else {
    const status = options?.status
    if (isStatusFilter(status)) selectedStatus.value = status
    appliedStatus = selectedStatus.value
    void loadList()
  }
})
onShow(() => {
  if (!authorized.value) { router?.requireAuthentication(routeName.value); return }
  visible = true
  if (firstShow) { firstShow = false; return }
  if (isDetail.value && isUuid(conflictId.value)) void loadDetail()
  else if (!isDetail.value) void loadList()
})
onHide(() => { visible = false; generation++; listLoading.value = false; detailLoading.value = false; busy.value = false })
onUnload(() => { visible = false; generation++; listLoading.value = false; detailLoading.value = false; busy.value = false })
onBackPress(() => { goBack(); return true })

async function loadList() {
  if (!api || isDetail.value || listLoading.value || !visible) return
  const current = ++generation
  listLoading.value = true
  listError.value = ''
  requestId.value = ''
  try {
    const result = await api.list(selectedStatus.value)
    if (!isCurrent(current)) return
    // The API is deliberately non-paginated. Preserve the exact service ordering.
    items.value = result
    appliedStatus = selectedStatus.value
  } catch (error) {
    if (!isCurrent(current)) return
    listError.value = safeError(error, '冲突列表暂不可用；已保留现有内容。')
    requestId.value = requestIdOf(error)
    selectedStatus.value = appliedStatus
  } finally { if (isCurrent(current)) listLoading.value = false }
}

async function changeFilter(status: MedicalFactConflictStatusFilter) {
  if (status === selectedStatus.value || listLoading.value) return
  selectedStatus.value = status
  await loadList()
}

async function loadDetail() {
  if (!api || !isDetail.value || !isUuid(conflictId.value) || detailLoading.value || !visible) return
  const current = ++generation
  detailLoading.value = true
  detailError.value = ''
  detailRequestId.value = ''
  try {
    const result = await api.get(conflictId.value)
    if (!isCurrent(current)) return
    detail.value = result
  } catch (error) {
    if (!isCurrent(current)) return
    detailError.value = safeError(error, '冲突暂不可用，请稍后重试。')
    detailRequestId.value = requestIdOf(error)
    if (isNotFound(error)) { detail.value = null; detailError.value = '冲突或来源不存在，或当前不可用。' }
  } finally { if (isCurrent(current)) detailLoading.value = false }
}

function confirmKeepBoth() {
  if (!detail.value || !canKeepBoth(detail.value) || busy.value || !visible) return
  const current = generation
  uni.showModal({
    title: '保留双方事实？',
    content: '双方将作为独立事实保留。应用不会选择正确值、合并或删除任何一方。',
    confirmText: '确认保留双方',
    cancelText: '暂不处理',
    success: ({ confirm }) => { if (confirm && isCurrent(current)) void keepBoth(current) },
  })
}

async function keepBoth(current: number) {
  if (!api || !detail.value || !canKeepBoth(detail.value) || busy.value || !isCurrent(current)) return
  busy.value = true
  actionError.value = ''
  actionRequestId.value = ''
  conflictNotice.value = ''
  try {
    await api.keepBoth(detail.value.id, { record_version: detail.value.record_version }, createIdempotencyKey())
    if (!isCurrent(current)) return
    conflictNotice.value = '服务端已接受保留双方决定；正在读取最新冲突状态。'
    await refreshDetailAfterAction(current)
  } catch (error) {
    if (!isCurrent(current)) return
    actionRequestId.value = requestIdOf(error)
    if (error instanceof AppError && error.status === 409) {
      actionError.value = '冲突状态已变化，决定未自动重发。请查看最新状态；如仍可处理，需再次明确确认。'
      await refreshDetailAfterConflict(current)
    } else if (isNotFound(error)) {
      detail.value = null
      detailError.value = '冲突或来源不存在，或当前不可用。'
    } else actionError.value = safeError(error, '决定暂未完成；请刷新核对服务端状态后再操作。')
  } finally { if (isCurrent(current)) busy.value = false }
}

async function refreshDetailAfterConflict(current: number) {
  if (!api || !isCurrent(current)) return
  try {
    const latest = await api.get(conflictId.value)
    if (!isCurrent(current)) return
    detail.value = latest
  } catch (error) {
    if (!isCurrent(current)) return
    if (isNotFound(error)) { detail.value = null; detailError.value = '冲突或来源不存在，或当前不可用。' }
    else detailError.value = safeError(error, '暂时无法读取最新状态；当前显示内容已保留。')
    detailRequestId.value = requestIdOf(error)
  }
}

async function refreshDetailAfterAction(current: number) {
  if (!api || !isCurrent(current)) return
  try {
    const latest = await api.get(conflictId.value)
    if (!isCurrent(current)) return
    detail.value = latest
  } catch (error) {
    if (!isCurrent(current)) return
    if (isNotFound(error)) { detail.value = null; detailError.value = '冲突或来源不存在，或当前不可用。' }
    else detailError.value = safeError(error, '处理已受理，但暂时无法刷新最新状态。')
    detailRequestId.value = requestIdOf(error)
  }
}

function refresh() { if (isDetail.value) void loadDetail(); else void loadList() }
function goBack() { if (isDetail.value) router?.navigateBack(); else router?.navigate('healthArchive') }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间不可用' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date) }
function safeId(value: string) { return isUuid(value) ? value : '编号不可用' }
function requestIdOf(error: unknown) { return error instanceof AppError ? error.requestId ?? error.problem?.request_id ?? '' : '' }
function isNotFound(error: unknown) { return error instanceof AppError && error.status === 404 }
function safeError(error: unknown, fallback: string) {
  if (!(error instanceof AppError)) return fallback
  if (error.status === 401) return '登录状态已失效，请重新登录。'
  if (error.status === 404) return '冲突或来源不存在，或当前不可用。'
  if (error.status === 409) return '记录已发生变化，请刷新后重新核对。'
  if (error.status === 422) return '请求未通过服务端校验，请刷新状态后重试。'
  if (error.kind === 'offline' || error.kind === 'network' || error.kind === 'timeout') return '网络暂不可用，请检查连接后重试。'
  return fallback
}
function createIdempotencyKey() { return globalThis.crypto?.randomUUID?.() ?? `medical-conflict-${Date.now()}-${Math.random().toString(36).slice(2)}` }
function isStatusFilter(value: unknown): value is MedicalFactConflictStatusFilter { return value === 'open' || value === 'resolved' || value === 'invalidated' || value === 'all' }
</script>

<style lang="scss" scoped>
.conflict-page{min-height:100vh;background:var(--gc-color-canvas)}.shell{box-sizing:border-box;width:100%;max-width:430px;min-height:100vh;margin:0 auto;padding:calc(env(safe-area-inset-top,0px) + 10px) 20px calc(env(safe-area-inset-bottom,0px) + 24px)}.topbar{display:flex;height:48px;align-items:center;justify-content:space-between}.back,.refresh,.filter,.source-button,.text-action{min-height:44px;border:1px solid var(--gc-color-border);border-radius:12px;background:var(--gc-color-surface);color:var(--gc-color-brand-strong)}.back{width:44px;padding:0;font-size:26px}.topbar-title{font-size:14px;font-weight:var(--gc-font-weight-semibold);color:var(--gc-color-text)}.refresh{min-width:54px;padding:0 10px;font-size:11px}.intro{margin:18px 2px}.eyebrow{display:block;color:var(--gc-color-brand);font-size:10px;letter-spacing:1px}.title{display:block;margin-top:5px;color:var(--gc-color-text);font-size:25px;font-weight:var(--gc-font-weight-bold)}.subtitle{display:block;margin-top:7px;color:var(--gc-color-muted);font-size:12px;line-height:1.55}.filters{display:flex;gap:6px;margin:16px 0;flex-wrap:wrap}.filter{flex:1;min-width:68px;padding:0 9px;font-size:11px}.filter.selected{border-color:var(--gc-color-brand);background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong)}.state-card,.detail-card,.keep-both-card,.readonly-note{display:flex;margin:12px 0;padding:16px;border:1px solid var(--gc-color-border);border-radius:16px;flex-direction:column;gap:10px;background:var(--gc-color-surface);color:var(--gc-color-muted);font-size:12px;line-height:1.5}.error-card{align-items:center}.conflict-list,.member-list{display:flex;flex-direction:column;gap:10px}.conflict-row{display:flex;position:relative;min-height:88px;padding:14px 38px 14px 14px;border:1px solid var(--gc-color-border);border-radius:16px;flex-direction:column;align-items:flex-start;gap:8px;background:var(--gc-color-surface);text-align:left}.row-head{display:flex;width:100%;align-items:center;justify-content:space-between;gap:8px}.row-title,.section-title,.member-title{color:var(--gc-color-text);font-size:13px;font-weight:var(--gc-font-weight-semibold)}.status{flex:0 0 auto;padding:5px 8px;border-radius:999px;background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong);font-size:10px}.row-meta,.row-version,.request-id{color:var(--gc-color-muted);font-size:10px;line-height:1.5;overflow-wrap:anywhere}.row-version{font-variant-numeric:tabular-nums}.chevron{position:absolute;top:27px;right:15px;color:var(--gc-color-placeholder);font-size:23px}.safety-note{display:block;margin:16px 4px;color:var(--gc-color-muted);font-size:10px;line-height:1.5;text-align:center}.detail-card{margin-top:0}.notice{display:block;padding:11px;border-radius:11px;background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong);font-size:11px;line-height:1.5}.member-card{display:flex;padding:15px;border:1px solid var(--gc-color-border);border-radius:15px;flex-direction:column;gap:8px;background:var(--gc-color-surface)}.member-value{color:var(--gc-color-text);font-size:16px;font-weight:var(--gc-font-weight-semibold);overflow-wrap:anywhere}.unit{color:var(--gc-color-muted);font-size:12px;font-weight:400}.source-button,.text-action{align-self:flex-start;padding:0 12px;font-size:11px}.keep-both-card{margin-top:16px;border-color:var(--gc-color-brand-pale)}.readonly-note{background:var(--gc-color-canvas)}.inline-error{display:flex;margin:12px 0;padding:12px;border:1px solid var(--gc-color-danger-border);border-radius:12px;flex-direction:column;gap:8px;background:var(--gc-color-danger-pale);color:var(--gc-color-danger);font-size:11px;line-height:1.5}.auth-pending{min-height:100vh;display:grid;place-items:center;color:var(--gc-color-muted)}
</style>

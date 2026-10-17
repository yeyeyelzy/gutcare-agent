<template>
  <view v-if="pageReady" class="risk-page" data-testid="risk-workspace">
    <view class="shell">
      <view class="topbar">
        <button class="back" aria-label="返回" data-testid="risk-back" @click="goBack">‹</button>
        <text class="topbar-title">{{ detail ? '风险提示详情' : '风险提示' }}</text>
        <view class="spacer" />
      </view>
      <view class="intro">
        <text class="eyebrow">SAFETY INFORMATION</text>
        <text class="title">{{ detail ? '本人风险提示' : '风险提示' }}</text>
        <text class="subtitle">提示依据已记录的结构化信息，不构成诊断。紧急提示可直接查看，无需等待智能分析。</text>
      </view>

      <template v-if="detail">
        <DashboardDataStatus v-if="loadState === 'loading'" state="loading" test-id="risk-detail-loading" />
        <view v-else-if="loadState === 'error'" class="status-card">
          <DashboardDataStatus state="error" :message="loadMessage" retryable :busy="busy" test-id="risk-detail-error" @retry="loadDetail" />
          <text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
          <button class="secondary" data-testid="risk-detail-to-list" @click="showList">返回风险列表</button>
        </view>
        <view v-else-if="alert" class="alert-card" :class="`alert-card--${alert.severity}`" data-testid="risk-detail">
          <view class="severity-line" :aria-label="severityLabel(alert.severity)">
            <text class="severity-symbol" aria-hidden="true">{{ severityIcon(alert.severity) }}</text>
            <text class="severity-label">{{ severityLabel(alert.severity) }}</text>
          </view>
          <text class="alert-message">{{ alert.message }}</text>
          <view class="action-block"><text class="action-heading">建议采取的行动</text><text class="action-copy">{{ alert.recommended_action }}</text></view>
          <text class="disclaimer">已查看或已重新评估仅表示记录状态变化，不代表风险解除或确认安全。</text>
          <text class="meta">触发时间：{{ formatDate(alert.triggered_at) }} · {{ statusLabel(alert.status) }}</text>
          <view class="actions">
            <button v-if="alert.status === 'unread'" class="primary" :disabled="busy" data-testid="risk-mark-read" @click="markRead">标记已查看</button>
            <button v-if="alert.status !== 'reevaluated'" class="secondary" :disabled="busy" data-testid="risk-reevaluate" @click="reevaluate">标记已重新评估</button>
          </view>
          <text v-if="actionError" class="action-error" role="alert">{{ actionError }}</text>
          <text v-if="actionRequestId" class="request-id">请求编号：{{ actionRequestId }}</text>
        </view>
      </template>

      <template v-else>
        <view class="filters">
          <button class="filter" :class="{ selected: !unreadOnly }" data-testid="risk-filter-all" @click="setUnread(false)">全部提示</button>
          <button class="filter" :class="{ selected: unreadOnly }" data-testid="risk-filter-unread" @click="setUnread(true)">仅未查看</button>
        </view>
        <DashboardDataStatus v-if="loadState === 'loading'" state="loading" test-id="risk-list-loading" />
        <view v-else-if="loadState === 'error'" class="status-card">
          <DashboardDataStatus state="error" :message="loadMessage" retryable :busy="busy" test-id="risk-list-error" @retry="reload" />
          <text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
        </view>
        <view v-else-if="alerts.length === 0" class="empty" data-testid="risk-empty">
          <text class="empty-mark" aria-hidden="true">○</text><text class="empty-title">当前筛选下没有风险提示</text>
          <text class="subtitle">这只表示当前列表为空，不是对健康状态的判断。</text>
        </view>
        <view v-else class="list" data-testid="risk-list">
          <view v-if="refreshError" class="refresh-error" role="alert" data-testid="risk-refresh-error"><text>{{ refreshError }}</text><button class="retry" :disabled="busy" data-testid="risk-refresh-retry" @click="reload(true)">重试刷新</button><text v-if="refreshRequestId" class="request-id">请求编号：{{ refreshRequestId }}</text></view>
          <button v-for="item in alerts" :key="item.id" class="alert-card alert-item" :class="`alert-card--${item.severity}`" :data-testid="`risk-${item.id}`" @click="open(item.id)">
            <view class="severity-line"><text class="severity-symbol" aria-hidden="true">{{ severityIcon(item.severity) }}</text><text class="severity-label">{{ severityLabel(item.severity) }}</text><text class="status-label">{{ statusLabel(item.status) }}</text></view>
            <text class="alert-message">{{ item.message }}</text>
            <text class="action-copy">{{ item.recommended_action }}</text>
            <text class="meta">{{ formatDate(item.triggered_at) }} · 查看详情 ›</text>
          </button>
          <view v-if="moreError" class="more-error" role="alert"><text>{{ moreError }}</text><button class="retry" :disabled="busy" data-testid="risk-more-retry" @click="loadMore">{{ busy ? '正在重试…' : '重试载入' }}</button></view>
          <button v-else-if="cursor" class="secondary more" :disabled="busy" data-testid="risk-more" @click="loadMore">{{ busy ? '正在载入…' : '载入更多' }}</button>
        </view>
      </template>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onLoad, onShow } from '@dcloudio/uni-app'
import { riskApiKey, appRouterKey } from '../api/context'
import { AppError } from '../api/errors'
import type { RiskAlert } from '../api/openapiTypes'
import { RiskListFirstShowGate, safeRefreshRiskList } from '../api/riskListRefresh'
import type { RiskRouteName } from '../navigation/routes'
import { canRenderRoute } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import DashboardDataStatus from './DashboardDataStatus.vue'

const props = defineProps<{ routeName: RiskRouteName }>()
const auth = useAuthStore()
const api = inject(riskApiKey)
const router = inject(appRouterKey)
const detail = computed(() => props.routeName === 'riskAlertDetail')
const pageReady = ref(false)
const alertId = ref('')
const alert = ref<RiskAlert | null>(null)
const alerts = ref<RiskAlert[]>([])
const cursor = ref<string | null>(null)
const unreadOnly = ref(false)
const loadState = ref<'loading' | 'ready' | 'error'>('loading')
const busy = ref(false)
const requestId = ref('')
const actionRequestId = ref('')
const actionError = ref('')
const moreError = ref('')
const loadMessage = ref('')
const refreshError = ref('')
const refreshRequestId = ref('')
const firstShowGate = new RiskListFirstShowGate()

onLoad((options) => {
  if (!canRenderRoute(props.routeName, auth.state)) { router?.requireAuthentication(props.routeName); return }
  pageReady.value = true
  alertId.value = typeof options?.alert_id === 'string' && /^[0-9a-f-]{36}$/i.test(options.alert_id) ? options.alert_id : ''
  if (detail.value) void loadDetail()
  else void reload()
})
onShow(() => {
  if (!pageReady.value) return
  if (!canRenderRoute(props.routeName, auth.state)) { router?.requireAuthentication(props.routeName); return }
  if (!detail.value && firstShowGate.shouldFetch()) void reload(true)
})
onBackPress(() => { goBack(); return true })

async function reload(preserveExisting = false) {
  if (!api || !canRenderRoute(props.routeName, auth.state) || busy.value) return
  const keepVisibleList = preserveExisting && alerts.value.length > 0
  busy.value = true; if (!keepVisibleList) loadState.value = 'loading'; requestId.value = ''; loadMessage.value = ''; moreError.value = ''
  if (keepVisibleList) { refreshError.value = ''; refreshRequestId.value = '' }
  try {
    const loadPage = () => api.list({ limit: 20, unread_only: unreadOnly.value })
    const result = keepVisibleList ? await safeRefreshRiskList({ items: alerts.value, cursor: cursor.value }, loadPage) : { snapshot: await loadPage().then((page) => ({ items: page.items, cursor: page.next_cursor })), error: null }
    if (result.error !== null) {
      applyError(result.error); refreshError.value = '刷新失败，仍显示上次载入的风险提示；可重试。'; refreshRequestId.value = requestId.value; loadState.value = 'ready'
    } else {
      alerts.value = result.snapshot.items; cursor.value = result.snapshot.cursor; loadState.value = 'ready'; refreshError.value = ''; refreshRequestId.value = ''
    }
  }
  catch (error) { applyError(error); loadMessage.value = error instanceof AppError && error.kind === 'offline' ? '当前离线，风险提示未能载入；请重试。' : '暂时无法载入风险提示；未将失败解释为无风险。'; loadState.value = 'error' }
  finally { busy.value = false }
}
async function loadMore() {
  if (!api || !cursor.value || busy.value) return
  busy.value = true; moreError.value = ''
  try { const page = await api.list({ limit: 20, cursor: cursor.value, unread_only: unreadOnly.value }); alerts.value = [...alerts.value, ...page.items]; cursor.value = page.next_cursor }
  catch (error) { applyError(error); moreError.value = '后续提示暂时无法载入；现有提示仍保留。' }
  finally { busy.value = false }
}
async function loadDetail() {
  if (!api || !alertId.value || !canRenderRoute(props.routeName, auth.state)) { loadState.value = 'error'; loadMessage.value = '此风险提示暂不可用。'; return }
  busy.value = true; loadState.value = 'loading'; requestId.value = ''; loadMessage.value = ''
  try { alert.value = await api.get(alertId.value); loadState.value = 'ready' }
  catch (error) { applyError(error); loadMessage.value = error instanceof AppError && error.status === 404 ? '此风险提示不存在或当前不可用。' : error instanceof AppError && error.kind === 'offline' ? '当前离线，无法载入风险详情。' : '暂时无法载入风险详情，请重试。'; loadState.value = 'error' }
  finally { busy.value = false }
}
async function mutate(action: 'read' | 'reevaluate') {
  if (!api || !alert.value || busy.value) return
  busy.value = true; actionError.value = ''; actionRequestId.value = ''
  try { alert.value = action === 'read' ? await api.markRead(alert.value.id) : await api.reevaluate(alert.value.id) }
  catch (error) { applyError(error); actionError.value = error instanceof AppError && error.status === 404 ? '此风险提示已不可用。' : '操作未完成，当前状态未作推测；请重试。' }
  finally { busy.value = false }
}
function markRead() { return mutate('read') }
function reevaluate() { return mutate('reevaluate') }
function setUnread(value: boolean) { if (unreadOnly.value === value) return; unreadOnly.value = value; void reload() }
function open(id: string) { router?.navigateRiskAlertDetail(id) }
function showList() { router?.navigate('riskAlerts') }
function goBack() { if (detail.value) router?.navigateBack(); else router?.switchTab('today') }
function applyError(error: unknown) { if (error instanceof AppError) { requestId.value = error.requestId ?? ''; actionRequestId.value = error.requestId ?? '' } }
function severityLabel(value: RiskAlert['severity']) { return value === 'emergency' ? '紧急提示' : value === 'seek_care' ? '尽快就医提示' : '关注提示' }
function severityIcon(value: RiskAlert['severity']) { return value === 'emergency' ? '!' : value === 'seek_care' ? '△' : 'i' }
function statusLabel(value: RiskAlert['status']) { return value === 'unread' ? '未查看' : value === 'read' ? '已查看' : '已重新评估 · 非安全结论' }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date) }
</script>

<style lang="scss" scoped>
.risk-page { min-height: 100vh; background: var(--gc-color-canvas); }.shell { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 12px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); }.topbar { display: flex; height: 48px; align-items: center; gap: 12px; }.back { width: 44px; height: 44px; border: 0; border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 28px; }.topbar-title { color: var(--gc-color-text); font-size: 14px; font-weight: var(--gc-font-weight-semibold); }.spacer { flex: 1; }.intro { display: flex; margin: 18px 2px 18px; flex-direction: column; gap: 5px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; letter-spacing: 1px; }.title { color: var(--gc-color-text); font-size: 25px; font-weight: var(--gc-font-weight-bold); }.subtitle,.meta { color: var(--gc-color-muted); font-size: 12px; line-height: 1.55; }.filters { display: flex; gap: 8px; margin-bottom: 12px; }.filter,.secondary,.primary { min-height: 44px; padding: 0 15px; border: 1px solid var(--gc-color-border); border-radius: 14px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 13px; }.filter.selected { border-color: var(--gc-color-brand); color: var(--gc-color-brand-strong); }.list { display: flex; flex-direction: column; gap: 12px; }.alert-card { display: flex; width: 100%; padding: 16px; border: 1px solid var(--gc-color-border); border-left: 5px solid var(--gc-color-brand); border-radius: var(--gc-radius-lg); flex-direction: column; align-items: stretch; gap: 10px; background: var(--gc-color-surface); color: var(--gc-color-text); text-align: left; box-shadow: var(--gc-shadow-card); }.alert-card--seek_care { border-left-color: var(--gc-color-peach-strong, #B84E2A); }.alert-card--emergency { border: 2px solid var(--gc-color-danger); border-left-width: 8px; background: var(--gc-color-danger-pale); }.severity-line { display: flex; align-items: center; gap: 8px; }.severity-symbol { display: grid; width: 28px; height: 28px; place-items: center; border: 1px solid currentColor; border-radius: 50%; color: var(--gc-color-brand-strong); font-weight: var(--gc-font-weight-bold); }.alert-card--emergency .severity-symbol,.alert-card--emergency .severity-label { color: var(--gc-color-danger); }.severity-label { color: var(--gc-color-brand-strong); font-size: 13px; font-weight: var(--gc-font-weight-bold); }.status-label { margin-left: auto; color: var(--gc-color-muted); font-size: 11px; }.alert-message { color: var(--gc-color-text); font-size: 15px; line-height: 1.55; font-weight: var(--gc-font-weight-semibold); }.action-block { display: flex; padding: 12px; border-radius: 12px; flex-direction: column; gap: 4px; background: rgba(255,255,255,.75); }.action-heading { color: var(--gc-color-text); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }.action-copy { color: var(--gc-color-text); font-size: 13px; line-height: 1.55; }.disclaimer { color: var(--gc-color-muted); font-size: 11px; line-height: 1.5; }.meta { font-size: 11px; }.actions { display: flex; flex-wrap: wrap; gap: 8px; }.primary { border-color: var(--gc-color-brand); background: var(--gc-color-brand); color: white; }.secondary { color: var(--gc-color-brand-strong); }.action-error,.more-error,.refresh-error { color: var(--gc-color-danger); font-size: 12px; }.status-card,.empty { padding: 16px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); }.empty { display: flex; min-height: 160px; align-items: center; justify-content: center; flex-direction: column; gap: 10px; text-align: center; }.empty-mark { color: var(--gc-color-muted); font-size: 28px; }.empty-title { color: var(--gc-color-text); font-weight: var(--gc-font-weight-semibold); }.more-error { display: flex; align-items: center; justify-content: space-between; padding: 12px; border: 1px solid var(--gc-color-danger); border-radius: 12px; }.refresh-error { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; padding: 10px; border: 1px solid var(--gc-color-danger); border-radius: 12px; gap: 6px; }.retry { min-height: 44px; padding: 0 12px; border: 0; background: transparent; color: var(--gc-color-brand-strong); }.more { align-self: center; }.request-id { display: block; margin-top: 6px; color: var(--gc-color-muted); font-size: 10px; }.auth-pending { display: grid; min-height: 100vh; place-items: center; color: var(--gc-color-muted); }
</style>

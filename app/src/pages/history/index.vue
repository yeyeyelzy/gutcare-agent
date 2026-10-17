<template>
  <view v-if="pageReady" class="history-page" data-testid="history-page">
    <view class="shell">
      <view class="topbar"><button class="back" aria-label="返回" data-testid="history-back" @click="goBack">‹</button><text class="topbar-title">历史时间线</text><view class="spacer" /></view>
      <view class="intro"><text class="eyebrow">YOUR HEALTH HISTORY</text><text class="title">历史时间线</text><text class="muted">仅显示记录类别、时间与可用的受控入口。</text></view>

      <view class="filters" data-testid="history-filters">
        <text class="filter-heading">记录类别（可多选；不选表示全部）</text>
        <view class="category-row">
          <button v-for="category in categoryOptions" :key="category.value" class="chip" :class="{ selected: selectedCategories.includes(category.value) }" :aria-pressed="selectedCategories.includes(category.value)" :disabled="busy" :data-testid="`history-category-${category.value}`" @click="toggleCategory(category.value)">{{ category.label }}</button>
        </view>
        <view class="date-row"><view class="date-control"><text class="date-label">开始日期（含）</text><picker mode="date" :value="sinceDay" @change="setSince"><view class="date-picker" data-testid="history-since">{{ sinceDay || '不限' }}</view></picker></view><view class="date-control"><text class="date-label">结束日期（含）</text><picker mode="date" :value="untilDay" @change="setUntil"><view class="date-picker" data-testid="history-until">{{ untilDay || '不限' }}</view></picker></view></view>
        <text class="range-note">按设备本地日历筛选，发送带时区的 UTC 半开区间。</text>
        <text v-if="filterError" class="error" role="alert" data-testid="history-filter-error">{{ filterError }}</text>
      </view>

      <view v-if="loadState === 'loading' && items.length === 0" class="status-card"><DashboardDataStatus state="loading" test-id="history-loading" /></view>
      <view v-else-if="loadState === 'error' && items.length === 0" class="status-card"><DashboardDataStatus state="error" :message="loadError" retryable :busy="busy" test-id="history-error" @retry="reload(false)" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
      <view v-else-if="loadState === 'empty' && items.length === 0" class="empty" data-testid="history-empty"><text class="empty-mark" aria-hidden="true">⌁</text><text class="section-title">当前筛选下暂无历史项目</text><text class="muted">空列表不代表其他业务状态。</text></view>
      <view v-else class="timeline" data-testid="history-list">
        <view v-if="refreshError" class="inline-error" role="alert" data-testid="history-refresh-error"><text>{{ refreshError }}</text><button class="text-action" :disabled="busy" data-testid="history-refresh-retry" @click="reload(true)">重试刷新</button><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view v-for="event in items" :key="`${event.type}:${event.id}`" class="event-card" :data-testid="`history-event-${event.id}`">
          <view class="event-marker" aria-hidden="true">{{ iconFor(event.type) }}</view>
          <view class="event-copy"><text class="event-type">{{ labelFor(event.type) }}</text><text class="event-time">{{ formatDate(event.occurred_at) }}</text></view>
          <button v-if="mapHistoryTarget(event.target).name !== 'unavailable'" class="open-target" :aria-label="`查看${labelFor(event.type)}`" :disabled="busy" :data-testid="`history-target-${event.id}`" @click="openTarget(event)">查看 ›</button>
          <text v-else class="target-unavailable" data-testid="history-target-unavailable">入口不可用</text>
        </view>
        <view v-if="moreError" class="inline-error" role="alert" data-testid="history-more-error"><text>{{ moreError }}</text><button class="text-action" :disabled="busy" data-testid="history-more-retry" @click="loadMore">重试载入</button><text v-if="moreRequestId" class="request-id">请求编号：{{ moreRequestId }}</text></view>
        <button v-else-if="cursor" class="more" :disabled="busy" data-testid="history-more" @click="loadMore">{{ busy ? '正在载入…' : '载入更多' }}</button>
      </view>
      <text class="privacy-note">时间线不包含备注、心情标签、摘要或诊断推断。</text>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { inject, ref } from 'vue'
import { onBackPress, onHide, onLoad, onShow } from '@dcloudio/uni-app'
import { historyApiKey, appRouterKey } from '../../api/context'
import { AppError } from '../../api/errors'
import type { HistoryCategory, HistoryEvent } from '../../api/openapiTypes'
import { appendHistoryPage, failHistoryAppend, HISTORY_CATEGORIES, HistoryFirstShowGate, historyBounds, isHistoryResponseCurrent, mapHistoryTarget } from '../../api/historyTimeline'
import { canRenderRoute } from '../../navigation/routes'
import type { AppTabName } from '../../navigation/routes'
import { useAuthStore } from '../../stores/auth'
import DashboardDataStatus from '../../components/DashboardDataStatus.vue'

const auth = useAuthStore()
const api = inject(historyApiKey)
const router = inject(appRouterKey)
const pageReady = ref(false)
const busy = ref(false)
const items = ref<HistoryEvent[]>([])
const cursor = ref<string | null>(null)
const selectedCategories = ref<HistoryCategory[]>([])
const sinceDay = ref('')
const untilDay = ref('')
const loadState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
const loadError = ref('')
const refreshError = ref('')
const moreError = ref('')
const filterError = ref('')
const requestId = ref('')
const moreRequestId = ref('')
const ownerTab = ref<AppTabName>('records')
const firstShow = new HistoryFirstShowGate()
let generation = 0
const categoryOptions: ReadonlyArray<{ value: HistoryCategory; label: string }> = [
  { value: 'diet', label: '饮食' }, { value: 'stool', label: '排便' }, { value: 'symptom', label: '症状' },
  { value: 'mood', label: '心情' }, { value: 'medication_checkin', label: '用药打卡' },
  { value: 'activity', label: '活动' }, { value: 'advice', label: '建议' },
]

onLoad(() => {
  if (!canRenderRoute('history', auth.state)) { router?.requireAuthentication('history'); return }
  pageReady.value = true
  ownerTab.value = findOwnerTab()
  void reload(false)
})
onShow(() => {
  if (!pageReady.value) return
  if (!canRenderRoute('history', auth.state)) { router?.requireAuthentication('history'); return }
  if (firstShow.shouldRefresh()) void reload(true)
})
onHide(() => { generation += 1; busy.value = false })
onBackPress(() => { goBack(); return true })

async function reload(preserve: boolean) {
  if (!api || !pageReady.value || !canRenderRoute('history', auth.state) || busy.value) return
  const bounds = historyBounds(sinceDay.value, untilDay.value)
  if (bounds.error) { filterError.value = bounds.error; loadError.value = bounds.error; loadState.value = 'error'; return }
  filterError.value = ''
  const requestGeneration = ++generation
  const keep = preserve && items.value.length > 0
  busy.value = true
  if (!keep) { loadState.value = 'loading'; loadError.value = ''; requestId.value = '' }
  refreshError.value = ''; moreError.value = ''; moreRequestId.value = ''
  try {
    const page = await api.list({ limit: 20, category: selectedCategories.value, since: bounds.since, until: bounds.until })
    if (!isCurrentPage(requestGeneration)) return
    items.value = page.items
    cursor.value = page.next_cursor
    loadState.value = items.value.length ? 'ready' : 'empty'
    requestId.value = ''
  } catch (error) {
    if (!isCurrentPage(requestGeneration)) return
    capture(error)
    if (keep) { refreshError.value = friendlyError(error, '刷新失败，现有时间线仍保留；可重试。'); loadState.value = 'ready' }
    else { loadError.value = friendlyError(error, '暂时无法载入历史时间线，请重试。'); loadState.value = 'error' }
  } finally {
    if (isCurrentPage(requestGeneration)) busy.value = false
  }
}

async function loadMore() {
  if (!api || !cursor.value || busy.value || !canRenderRoute('history', auth.state)) return
  const bounds = historyBounds(sinceDay.value, untilDay.value)
  if (bounds.error) { filterError.value = bounds.error; return }
  const requestGeneration = ++generation
  const requestedCursor = cursor.value
  busy.value = true; moreError.value = ''; moreRequestId.value = ''
  try {
    const page = await api.list({ limit: 20, cursor: requestedCursor, category: selectedCategories.value, since: bounds.since, until: bounds.until })
    if (!isCurrentPage(requestGeneration)) return
    const next = appendHistoryPage({ items: items.value, cursor: cursor.value, moreError: '', requestId: '' }, page)
    items.value = next.items; cursor.value = next.cursor; moreError.value = next.moreError; moreRequestId.value = next.requestId
  } catch (error) {
    if (!isCurrentPage(requestGeneration)) return
    capture(error)
    const failed = failHistoryAppend({ items: items.value, cursor: cursor.value, moreError: '', requestId: '' }, friendlyError(error, '后续项目暂时无法载入；现有时间线和游标已保留。'), error instanceof AppError ? error.requestId ?? error.problem?.request_id ?? '' : '')
    items.value = failed.items; cursor.value = failed.cursor; moreError.value = failed.moreError; moreRequestId.value = failed.requestId
  } finally {
    if (isCurrentPage(requestGeneration)) busy.value = false
  }
}

function toggleCategory(value: HistoryCategory) {
  if (busy.value) return
  selectedCategories.value = selectedCategories.value.includes(value)
    ? selectedCategories.value.filter((item) => item !== value)
    : [...selectedCategories.value, value].sort()
  resetAndReload()
}
function setSince(event: { detail?: { value?: string } }) { if (event.detail?.value) { sinceDay.value = event.detail.value; resetAndReload() } }
function setUntil(event: { detail?: { value?: string } }) { if (event.detail?.value) { untilDay.value = event.detail.value; resetAndReload() } }
function resetAndReload() { generation += 1; busy.value = false; items.value = []; cursor.value = null; loadState.value = 'loading'; loadError.value = ''; refreshError.value = ''; moreError.value = ''; requestId.value = ''; void reload(false) }
function openTarget(event: HistoryEvent) {
  const target = mapHistoryTarget(event.target)
  if (target.name === 'unavailable') return
  if (target.name === 'medications' || target.name === 'advice') router?.navigate(target.name)
  else if ('id' in target) router?.navigateHistoryTarget(event.target.type, target.id)
}
function isCurrentPage(requestGeneration: number) { return isHistoryResponseCurrent(requestGeneration, generation, pageReady.value, canRenderRoute('history', auth.state)) }
function goBack() { if (getCurrentPages().length > 1) router?.navigateBack(); else router?.switchTab(ownerTab.value) }
function findOwnerTab(): AppTabName { const stack = getCurrentPages(); const prior = stack.length > 1 ? stack[stack.length - 2]?.route ?? '' : ''; return prior.includes('/tabs/me/') ? 'me' : prior.includes('/tabs/analysis/') ? 'analysis' : prior.includes('/tabs/today/') ? 'today' : 'records' }
function capture(error: unknown) { requestId.value = error instanceof AppError ? error.requestId ?? error.problem?.request_id ?? '' : '' }
function friendlyError(error: unknown, fallback: string) {
  if (error instanceof AppError && error.kind === 'offline') return '当前离线，历史时间线未能载入；请检查连接后重试。'
  if (error instanceof AppError && error.status === 400) return '当前游标或筛选已失效；请刷新时间线后重试。'
  if (error instanceof AppError && error.status === 422) return '时间范围或筛选参数无效；请调整后重试。'
  if (error instanceof AppError && error.status === 404) return '历史项目当前不可用。'
  return fallback
}
function labelFor(value: HistoryCategory) { return ({ diet: '饮食记录', stool: '排便记录', symptom: '症状记录', mood: '心情记录', medication_checkin: '用药打卡', activity: '活动记录', advice: '建议' } satisfies Record<HistoryCategory, string>)[value] }
function iconFor(value: HistoryCategory) { return ({ diet: '餐', stool: '记', symptom: '＋', mood: '♡', medication_checkin: '药', activity: '↗', advice: 'i' } satisfies Record<HistoryCategory, string>)[value] }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间不可用' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date) }
</script>

<style lang="scss" scoped>
.history-page{min-height:100vh;background:var(--gc-color-canvas)}.shell{width:100%;max-width:430px;min-height:100vh;margin:0 auto;padding:calc(env(safe-area-inset-top,0px) + 10px) 20px calc(env(safe-area-inset-bottom,0px) + 24px)}.topbar{display:flex;height:48px;align-items:center;gap:10px}.back{width:44px;height:44px;border:0;border-radius:50%;background:var(--gc-color-surface);color:var(--gc-color-text);font-size:28px}.topbar-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.spacer{flex:1}.intro{display:flex;margin:18px 2px 14px;flex-direction:column;gap:5px}.eyebrow{color:var(--gc-color-brand);font-size:10px;letter-spacing:1px}.title{color:var(--gc-color-text);font-size:25px;font-weight:var(--gc-font-weight-bold)}.muted,.range-note,.privacy-note{color:var(--gc-color-muted);font-size:11px;line-height:1.5}.filters,.event-card,.empty,.status-card{padding:14px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);background:var(--gc-color-surface);box-shadow:var(--gc-shadow-card)}.filters{display:flex;margin-bottom:12px;flex-direction:column;gap:10px}.filter-heading,.date-label{color:var(--gc-color-text);font-size:12px;font-weight:var(--gc-font-weight-semibold)}.category-row{display:flex;flex-wrap:wrap;gap:7px}.chip{min-width:44px;min-height:40px;padding:0 11px;border:1px solid var(--gc-color-border);border-radius:14px;background:var(--gc-color-canvas);color:var(--gc-color-text);font-size:11px}.chip.selected{border-color:var(--gc-color-brand);background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong)}.date-row{display:flex;gap:10px}.date-control{display:flex;min-width:0;flex:1;flex-direction:column;gap:5px}.date-picker{display:flex;min-height:44px;align-items:center;padding:0 10px;border:1px solid var(--gc-color-border);border-radius:12px;background:var(--gc-color-canvas);color:var(--gc-color-text);font-size:12px}.range-note{font-size:10px}.timeline{display:flex;flex-direction:column;gap:9px}.event-card{display:flex;min-height:72px;align-items:center;gap:10px;padding:10px 12px}.event-marker{display:grid;width:42px;height:42px;flex:0 0 42px;place-items:center;border-radius:14px;background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong);font-size:16px;font-weight:var(--gc-font-weight-semibold)}.event-copy{display:flex;min-width:0;flex:1;flex-direction:column;gap:5px}.event-type{color:var(--gc-color-text);font-size:13px;font-weight:var(--gc-font-weight-semibold)}.event-time{color:var(--gc-color-muted);font-size:11px}.open-target,.more,.text-action{min-height:44px;padding:0 11px;border:1px solid var(--gc-color-border);border-radius:12px;background:var(--gc-color-surface);color:var(--gc-color-brand-strong);font-size:11px}.target-unavailable{color:var(--gc-color-muted);font-size:10px}.more{align-self:center;margin-top:4px}.inline-error{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px;border:1px solid var(--gc-color-danger);border-radius:12px;color:var(--gc-color-danger);font-size:11px}.request-id{color:var(--gc-color-muted);font-size:10px}.status-card{margin-top:10px}.empty{display:flex;min-height:170px;align-items:center;justify-content:center;flex-direction:column;gap:9px;text-align:center}.empty-mark{display:grid;width:42px;height:42px;place-items:center;border-radius:50%;background:var(--gc-color-sage-pale);color:var(--gc-color-brand);font-size:23px}.section-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.error{color:var(--gc-color-danger);font-size:11px}.privacy-note{display:block;margin:13px 3px}.auth-pending{display:grid;min-height:100vh;place-items:center;color:var(--gc-color-muted)}
</style>

<template>
  <view v-if="pageReady" class="notification-page" data-testid="notification-workspace">
    <view class="shell">
      <view class="topbar"><button class="back" aria-label="返回" data-testid="notification-back" @click="goBack">‹</button><text class="topbar-title">{{ isPreferences ? '通知偏好' : isTarget ? '关联页面' : detail ? '通知详情' : '通知中心' }}</text><button v-if="!detail && !isPreferences && !isTarget" class="settings" aria-label="通知偏好设置" data-testid="notification-preferences-link" @click="router?.navigate('notificationPreferences')">偏好</button><view v-else class="spacer" /></view>

      <template v-if="isPreferences">
        <view v-if="prefsState === 'loading'" class="status-card"><DashboardDataStatus state="loading" test-id="notification-prefs-loading" /></view>
        <view v-else-if="prefsState === 'error'" class="status-card"><DashboardDataStatus state="error" :message="prefsError" retryable :busy="busy" test-id="notification-prefs-error" @retry="loadPreferences" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view v-else-if="preferences" class="preference-card" data-testid="notification-preferences">
          <text class="section-title">普通站内提醒</text>
          <view class="pref-row"><view class="pref-copy"><text class="pref-title">接收普通提醒</text><text class="muted">关闭后不接收普通提醒派发。</text></view><button class="toggle" :class="{ 'toggle--on': draft.ordinary_in_app_enabled }" :aria-pressed="draft.ordinary_in_app_enabled" :disabled="busy" data-testid="ordinary-notification-toggle" @click="draft.ordinary_in_app_enabled = !draft.ordinary_in_app_enabled">{{ draft.ordinary_in_app_enabled ? '已开启' : '已关闭' }}</button></view>
          <text class="risk-exemption" data-testid="risk-preference-exemption">风险通知不受此开关或静默时段影响；设置不会更改风险提示的已读状态。</text>
          <text class="section-title quiet-title">静默时段（可选）</text>
          <view class="time-row"><label for="quiet-start">开始</label><input id="quiet-start" v-model="draft.quiet_start" type="time" :disabled="busy" data-testid="quiet-start" /><label for="quiet-end">结束</label><input id="quiet-end" v-model="draft.quiet_end" type="time" :disabled="busy" data-testid="quiet-end" /></view>
          <view class="timezone-row"><text>时区</text><input v-model="draft.timezone" :disabled="busy" maxlength="64" placeholder="IANA 时区，例如 Asia/Shanghai" data-testid="notification-timezone" /></view>
          <text class="muted">当前设备时区：{{ deviceTimezone }}</text>
          <text v-if="prefsError" class="error" role="alert">{{ prefsError }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
          <button class="primary" :disabled="busy" data-testid="save-notification-preferences" @click="savePreferences">{{ busy ? '正在保存…' : '保存偏好' }}</button>
        </view>
      </template>

      <template v-else-if="isTarget">
        <view v-if="notificationTargetId && notificationTargetType" class="safe-target" data-testid="notification-target-placeholder"><text class="safe-mark" aria-hidden="true">i</text><text class="section-title">{{ notificationTargetType === 'analysis_task' ? '分析任务' : '建议' }}关联页面尚未开放</text><text class="muted">已安全保留并校验通知关联标识；此处不会展示未载入的报告或建议正文。</text><button class="secondary" data-testid="notification-target-return" @click="goBack">返回通知</button></view>
      </template>

      <template v-else-if="detail">
        <DashboardDataStatus v-if="loadState === 'loading'" state="loading" test-id="notification-detail-loading" />
        <view v-else-if="loadState === 'error'" class="status-card"><DashboardDataStatus state="error" :message="loadError" retryable :busy="busy" test-id="notification-detail-error" @retry="loadDetail" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text><button class="secondary" data-testid="notification-detail-list" @click="router?.navigate('notifications')">返回通知列表</button></view>
        <view v-else-if="item" class="notification-card" data-testid="notification-detail">
          <view class="notification-heading"><text class="category">{{ categoryLabel(item.category) }}</text><text class="priority" :class="{ 'priority--risk': item.priority === 'risk' }">{{ item.priority === 'risk' ? '风险通知' : '普通通知' }}</text></view>
          <text class="event-title">{{ eventLabel(item.event_type) }}</text><text class="meta">发生时间：{{ formatDate(item.occurred_at) }}</text><text class="meta">创建时间：{{ formatDate(item.created_at) }}</text><text class="meta">{{ item.read_at ? `已读：${formatDate(item.read_at)}` : '尚未阅读' }}</text>
          <text v-if="!targetAvailable(item)" class="target-unavailable" data-testid="notification-target-unavailable">关联内容当前不可用。</text>
          <button v-else class="secondary" data-testid="notification-open-target" @click="openTarget(item)">打开关联页面 ›</button>
          <text class="muted">通知不包含报告、建议或用药正文。</text>
          <text v-if="actionError" class="error" role="alert">{{ actionError }}</text><text v-if="actionRequestId" class="request-id">请求编号：{{ actionRequestId }}</text>
          <button v-if="item.read_at === null" class="primary" :disabled="busy" data-testid="notification-mark-read" @click="markRead">{{ busy ? '正在处理…' : '标记已读' }}</button>
        </view>
      </template>

      <template v-else>
        <view class="intro"><text class="eyebrow">GUTCARE · INBOX</text><text class="title">通知中心</text><text class="muted">未读 {{ unreadCount === null ? '—' : unreadCount }} 条</text></view>
        <view class="filter-row" aria-label="通知类别筛选">
          <button v-for="filter in filters" :key="filter.value || 'all'" class="filter" :class="{ selected: category === filter.value }" :aria-pressed="category === filter.value" :disabled="busy" :data-testid="`notification-filter-${filter.value || 'all'}`" @click="setCategory(filter.value)">{{ filter.label }}</button>
        </view>
        <view class="filter-row"><button class="filter" :class="{ selected: !unreadOnly }" :aria-pressed="!unreadOnly" :disabled="busy" data-testid="notification-unread-all" @click="setUnread(false)">全部</button><button class="filter" :class="{ selected: unreadOnly }" :aria-pressed="unreadOnly" :disabled="busy" data-testid="notification-unread-only" @click="setUnread(true)">仅未读</button></view>
        <view class="batch-row"><text class="muted">已选择 {{ selectedIds.length }} 条</text><button class="text-action" :disabled="busy || selectedIds.length === 0" data-testid="notification-batch-read" @click="markSelectedRead">{{ busy ? '正在处理…' : '将所选标为已读' }}</button></view>
        <view v-if="actionError" class="refresh-error" role="alert" data-testid="notification-batch-error"><text>{{ actionError }}</text><text v-if="actionRequestId" class="request-id">请求编号：{{ actionRequestId }}</text></view>
        <DashboardDataStatus v-if="loadState === 'loading' && items.length === 0" state="loading" test-id="notification-list-loading" />
        <view v-else-if="loadState === 'error' && items.length === 0" class="status-card"><DashboardDataStatus state="error" :message="loadError" retryable :busy="busy" test-id="notification-list-error" @retry="reload" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view v-else-if="loadState === 'empty' && items.length === 0" class="empty" data-testid="notification-empty"><text class="safe-mark" aria-hidden="true">○</text><text class="section-title">当前筛选下没有通知</text><text class="muted">列表为空不代表其他业务状态。</text></view>
        <view v-else class="list" data-testid="notification-list">
          <view v-if="refreshError" class="refresh-error" role="alert" data-testid="notification-refresh-error"><text>{{ refreshError }}</text><button class="text-action" :disabled="busy" data-testid="notification-refresh-retry" @click="reload(true)">重试刷新</button></view>
          <view v-for="notification in items" :key="notification.id" class="notification-card" :class="{ unread: notification.read_at === null, 'risk-card': notification.priority === 'risk' }" :data-testid="`notification-${notification.id}`">
            <button class="select-button" :aria-label="selected(notification.id) ? '取消选择' : '选择通知'" :aria-pressed="selected(notification.id)" :disabled="busy || notification.read_at !== null" :data-testid="`notification-select-${notification.id}`" @click="toggleSelected(notification.id)">{{ selected(notification.id) ? '☑' : '□' }}</button>
            <button class="item-main" :data-testid="`notification-open-${notification.id}`" @click="router?.navigateNotificationDetail(notification.id)"><view class="notification-heading"><text class="category">{{ categoryLabel(notification.category) }}</text><text class="priority" :class="{ 'priority--risk': notification.priority === 'risk' }">{{ notification.priority === 'risk' ? '风险通知' : '普通通知' }}</text><text class="read-state">{{ notification.read_at === null ? '未读' : '已读' }}</text></view><text class="event-title">{{ eventLabel(notification.event_type) }}</text><text class="meta">{{ formatDate(notification.occurred_at) }} · 查看通知 ›</text><text v-if="!targetAvailable(notification)" class="target-unavailable">关联内容当前不可用</text></button>
          </view>
          <view v-if="moreError" class="more-error" role="alert" data-testid="notification-more-error"><text>{{ moreError }}</text><button class="text-action" :disabled="busy" data-testid="notification-more-retry" @click="loadMore">重试载入</button></view>
          <button v-else-if="cursor" class="secondary more" :disabled="busy" data-testid="notification-more" @click="loadMore">{{ busy ? '正在载入…' : '载入更多' }}</button>
          <text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
        </view>
        <text class="footer-note">仅显示服务端提供的通知类型与时间，不展示正文或推断内容。</text>
      </template>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, reactive, ref } from 'vue'
import { onBackPress, onLoad, onShow } from '@dcloudio/uni-app'
import { appRouterKey, notificationApiKey } from '../api/context'
import { AppError } from '../api/errors'
import type { NotificationCategory, NotificationPreference, NotificationPreferencesWrite, PatientNotification } from '../api/openapiTypes'
import type { AppTabName, NotificationRouteName } from '../navigation/routes'
import { NotificationFirstShowGate, applyNotificationRead, unreadCountAfterUpdates } from '../api/notificationState'
import { canRenderRoute, isUuid, mapNotificationTarget } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import DashboardDataStatus from './DashboardDataStatus.vue'

const props = defineProps<{ routeName: NotificationRouteName }>()
const auth = useAuthStore()
const api = inject(notificationApiKey)
const router = inject(appRouterKey)
const detail = computed(() => props.routeName === 'notificationDetail')
const isPreferences = computed(() => props.routeName === 'notificationPreferences')
const isTarget = computed(() => props.routeName === 'notificationTarget')
const pageReady = ref(false)
const ownerTab = ref<AppTabName>('today')
const itemId = ref('')
const notificationTargetId = ref('')
const notificationTargetType = ref<'analysis_task' | 'advice' | null>(null)
const items = ref<PatientNotification[]>([])
const item = ref<PatientNotification | null>(null)
const cursor = ref<string | null>(null)
const category = ref<NotificationCategory | ''>('')
const unreadOnly = ref(false)
const selectedIds = ref<string[]>([])
const unreadCount = ref<number | null>(null)
const countLoading = ref(false)
const loadState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
const prefsState = ref<'loading' | 'ready' | 'error'>('loading')
const busy = ref(false)
const loadError = ref('')
const prefsError = ref('')
const actionError = ref('')
const moreError = ref('')
const refreshError = ref('')
const requestId = ref('')
const actionRequestId = ref('')
const firstShow = new NotificationFirstShowGate()
const preferences = ref<NotificationPreference | null>(null)
const deviceTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const draft = reactive({ ordinary_in_app_enabled: true, quiet_start: '', quiet_end: '', timezone: deviceTimezone })
const filters: ReadonlyArray<{ value: NotificationCategory | ''; label: string }> = [
  { value: '', label: '全部类别' }, { value: 'analysis', label: '分析' }, { value: 'advice', label: '建议' }, { value: 'risk', label: '风险' }, { value: 'medication_reminder', label: '用药提醒' },
]

onLoad((options) => {
  if (!canRenderRoute(props.routeName, auth.state)) { router?.requireAuthentication(props.routeName); return }
  pageReady.value = true
  ownerTab.value = findOwnerTab()
  itemId.value = isUuid(options?.notification_id) ? options.notification_id : ''
  if (detail.value) void loadDetail()
  else if (isPreferences.value) void loadPreferences()
  else if (isTarget.value) void validateTarget(options)
  else { void reload(); void loadUnreadCount() }
})
onShow(() => {
  if (!pageReady.value) return
  if (!canRenderRoute(props.routeName, auth.state)) { router?.requireAuthentication(props.routeName); return }
  if (!detail.value && !isPreferences.value && !isTarget.value && firstShow.shouldRefresh()) { void reload(true); void loadUnreadCount() }
})
onBackPress(() => { goBack(); return true })

async function reload(preserve = false) {
  if (!api || !canRenderRoute(props.routeName, auth.state) || busy.value) return
  const keep = preserve && items.value.length > 0
  busy.value = true; if (!keep) loadState.value = 'loading'; loadError.value = ''; moreError.value = ''; actionError.value = ''; requestId.value = ''
  try {
    const page = await api.list({ limit: 20, category: category.value || undefined, unread_only: unreadOnly.value })
    items.value = page.items; cursor.value = page.next_cursor; loadState.value = items.value.length ? 'ready' : 'empty'; refreshError.value = ''
    selectedIds.value = selectedIds.value.filter((id) => items.value.some((entry) => entry.id === id && entry.read_at === null))
  } catch (error) {
    capture(error)
    if (keep) { refreshError.value = '刷新失败，仍保留已载入的通知；可重试。'; loadState.value = 'ready' }
    else { loadError.value = error instanceof AppError && error.kind === 'offline' ? '当前离线，通知未能载入；请重试。' : error instanceof AppError && error.status === 404 ? '通知列表当前不可用。' : '暂时无法载入通知，请重试。'; loadState.value = 'error' }
  } finally { busy.value = false }
}
async function loadMore() {
  if (!api || !cursor.value || busy.value || !canRenderRoute(props.routeName, auth.state)) return
  busy.value = true; moreError.value = ''; requestId.value = ''
  try { const page = await api.list({ limit: 20, cursor: cursor.value, category: category.value || undefined, unread_only: unreadOnly.value }); items.value = [...items.value, ...page.items]; cursor.value = page.next_cursor }
  catch (error) { capture(error); moreError.value = '后续通知暂时无法载入；现有通知仍保留。' }
  finally { busy.value = false }
}
async function loadDetail() {
  if (!api || !itemId.value || !canRenderRoute(props.routeName, auth.state)) { loadState.value = 'error'; loadError.value = '此通知暂不可用。'; return }
  busy.value = true; loadState.value = 'loading'; requestId.value = ''; loadError.value = ''
  try { item.value = await api.get(itemId.value); loadState.value = 'ready' }
  catch (error) { capture(error); loadError.value = error instanceof AppError && error.status === 404 ? '此通知不存在或当前不可用。' : error instanceof AppError && error.kind === 'offline' ? '当前离线，无法载入通知详情。' : '暂时无法载入通知详情，请重试。'; loadState.value = 'error' }
  finally { busy.value = false }
}
async function markRead() {
  if (!api || !item.value || item.value.read_at !== null || busy.value) return
  busy.value = true; actionError.value = ''; actionRequestId.value = ''
  try { item.value = await api.markRead(item.value.id); await loadUnreadCount() }
  catch (error) { capture(error); actionError.value = error instanceof AppError && error.status === 404 ? '此通知已不可用。' : '标记未完成，当前状态未作推测；请重试。' }
  finally { busy.value = false }
}
async function markSelectedRead() {
  if (!api || selectedIds.value.length === 0 || busy.value) return
  const ids = [...selectedIds.value]
  const before = items.value.filter((entry) => ids.includes(entry.id))
  busy.value = true; actionError.value = ''; actionRequestId.value = ''; requestId.value = ''
  try {
    const result = await api.markBatchRead(ids)
    items.value = applyNotificationRead(items.value, result.items)
    selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id))
    if (unreadCount.value !== null) unreadCount.value = unreadCountAfterUpdates(unreadCount.value, before, result.items)
    await loadUnreadCount()
  } catch (error) {
    capture(error); actionError.value = error instanceof AppError && error.status === 404 ? '所选通知中有项目已不可用；选择与列表均保留，请刷新后重试。' : error instanceof AppError && error.status === 409 ? '通知状态已变化；所选项目与列表均保留，请刷新后重试。' : '批量操作未完成；选择与列表均保留，请重试。'
  } finally { busy.value = false }
}
async function loadUnreadCount() {
  if (!api || !canRenderRoute(props.routeName, auth.state) || countLoading.value) return
  countLoading.value = true
  try { unreadCount.value = (await api.unreadCount()).count } catch { /* Keep the last server count; never infer zero from a failed request. */ }
  finally { countLoading.value = false }
}
async function loadPreferences() {
  if (!api || !canRenderRoute(props.routeName, auth.state)) return
  busy.value = true; prefsState.value = 'loading'; prefsError.value = ''; requestId.value = ''
  try { const value = await api.getPreferences(); applyPreferences(value); prefsState.value = 'ready' }
  catch (error) { capture(error); prefsError.value = error instanceof AppError && error.kind === 'offline' ? '当前离线，无法载入通知偏好。' : '暂时无法载入通知偏好，请重试。'; prefsState.value = 'error' }
  finally { busy.value = false }
}
async function savePreferences() {
  if (!api || !preferences.value || busy.value) return
  if ((draft.quiet_start && !draft.quiet_end) || (!draft.quiet_start && draft.quiet_end)) { prefsError.value = '静默时段开始与结束时间需同时填写。'; return }
  try { new Intl.DateTimeFormat('en', { timeZone: draft.timezone }).format(new Date()) } catch { prefsError.value = '请输入有效的 IANA 时区。'; return }
  const payload: NotificationPreferencesWrite = { ordinary_in_app_enabled: draft.ordinary_in_app_enabled, quiet_start: draft.quiet_start || null, quiet_end: draft.quiet_end || null, timezone: draft.timezone }
  busy.value = true; prefsError.value = ''; requestId.value = ''
  try { applyPreferences(await api.updatePreferences(payload)); prefsState.value = 'ready' }
  catch (error) { capture(error); prefsError.value = error instanceof AppError && error.status === 422 ? '偏好参数不符合服务端要求，请检查时间与时区。' : '偏好未保存，已保留当前编辑内容；请重试。' }
  finally { busy.value = false }
}
function applyPreferences(value: NotificationPreference) { preferences.value = value; draft.ordinary_in_app_enabled = value.ordinary_in_app_enabled; draft.quiet_start = value.quiet_start?.slice(0, 5) ?? ''; draft.quiet_end = value.quiet_end?.slice(0, 5) ?? ''; draft.timezone = value.timezone }
function setCategory(value: NotificationCategory | '') { if (category.value === value) return; category.value = value; items.value = []; cursor.value = null; selectedIds.value = []; void reload() }
function setUnread(value: boolean) { if (unreadOnly.value === value) return; unreadOnly.value = value; items.value = []; cursor.value = null; selectedIds.value = []; void reload() }
function toggleSelected(id: string) { if (selected(id)) selectedIds.value = selectedIds.value.filter((entry) => entry !== id); else if (selectedIds.value.length < 100) selectedIds.value = [...selectedIds.value, id]; else actionError.value = '一次最多选择 100 条通知。' }
function selected(id: string) { return selectedIds.value.includes(id) }
function targetAvailable(value: PatientNotification) { return mapNotificationTarget(value.target, value.target_unavailable).kind !== 'unavailable' }
function openTarget(value: PatientNotification) {
  const target = mapNotificationTarget(value.target, value.target_unavailable)
  if (target.kind === 'risk_alert') router?.navigateRiskAlertDetail(target.id)
  else if (target.kind === 'medication_checkin') router?.navigate('medications')
  else if (target.kind === 'analysis_task') router?.navigateNotificationTarget(target.kind, target.id)
  else if (target.kind === 'advice') router?.navigateAdviceDetail(target.id, 'me', 'notification', value.id)
}
function validateTarget(options: Record<string, unknown> | undefined) {
  const type = options?.target_type
  const id = options?.target_id
  if ((type === 'analysis_task' || type === 'advice') && isUuid(id)) { notificationTargetType.value = type; notificationTargetId.value = id }
  else router?.switchTab('today')
}
function goBack() { if (detail.value || isPreferences.value || isTarget.value) { if (getCurrentPages().length > 1) router?.navigateBack(); else router?.switchTab(isPreferences.value ? 'me' : ownerTab.value) } else router?.switchTab(ownerTab.value) }
function findOwnerTab(): AppTabName { const stack = getCurrentPages(); const prior = stack.length > 1 ? stack[stack.length - 2]?.route ?? '' : ''; return prior.includes('/tabs/me/') ? 'me' : prior.includes('/tabs/records/') ? 'records' : prior.includes('/tabs/analysis/') ? 'analysis' : 'today' }
function capture(error: unknown) { if (error instanceof AppError) { requestId.value = error.requestId ?? error.problem?.request_id ?? ''; actionRequestId.value = requestId.value } }
function categoryLabel(value: NotificationCategory) { return ({ analysis: '分析', advice: '建议', risk: '风险', medication_reminder: '用药提醒' } satisfies Record<NotificationCategory, string>)[value] }
function eventLabel(value: PatientNotification['event_type']) { return ({ analysis_completed: '分析任务状态通知', advice_created: '有新的建议通知', risk_alert_created: '有新的风险提示', checkin_reminder: '用药打卡提醒' } satisfies Record<PatientNotification['event_type'], string>)[value] }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date) }
</script>

<style lang="scss" scoped>
.notification-page{min-height:100vh;background:var(--gc-color-canvas)}.shell{width:100%;max-width:430px;min-height:100vh;margin:0 auto;padding:calc(env(safe-area-inset-top,0px) + 10px) 20px calc(env(safe-area-inset-bottom,0px) + 24px)}.topbar{display:flex;height:48px;align-items:center;gap:10px}.back{width:44px;height:44px;border:0;border-radius:50%;background:var(--gc-color-surface);color:var(--gc-color-text);font-size:28px}.topbar-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.settings,.text-action{min-height:44px;margin-left:auto;padding:0 10px;border:0;background:transparent;color:var(--gc-color-brand-strong);font-size:12px;font-weight:var(--gc-font-weight-semibold)}.spacer{width:44px;margin-left:auto}.intro{display:flex;margin:18px 2px 14px;flex-direction:column;gap:4px}.eyebrow{color:var(--gc-color-brand);font-size:10px;letter-spacing:1px}.title{color:var(--gc-color-text);font-size:25px;font-weight:var(--gc-font-weight-bold)}.muted,.meta,.footer-note{color:var(--gc-color-muted);font-size:11px;line-height:1.5}.filter-row{display:flex;gap:7px;overflow-x:auto;margin:0 0 8px;padding-bottom:2px}.filter{min-height:40px;flex:0 0 auto;padding:0 12px;border:1px solid var(--gc-color-border);border-radius:14px;background:var(--gc-color-surface);color:var(--gc-color-text);font-size:11px}.filter.selected{border-color:var(--gc-color-brand);color:var(--gc-color-brand-strong);background:var(--gc-color-sage-pale)}.batch-row{display:flex;align-items:center;justify-content:space-between;margin:2px 0 10px;padding:0 3px}.list{display:flex;flex-direction:column;gap:10px}.notification-card,.preference-card,.status-card,.empty,.safe-target{position:relative;padding:15px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);background:var(--gc-color-surface);box-shadow:var(--gc-shadow-card)}.notification-card{display:flex;gap:8px}.notification-card.unread{border-left:4px solid var(--gc-color-brand)}.notification-card.risk-card{border-left:5px solid var(--gc-color-danger)}.select-button{width:44px;height:44px;flex:0 0 44px;border:0;background:transparent;color:var(--gc-color-brand-strong);font-size:20px}.item-main{display:flex;min-width:0;flex:1;padding:0;border:0;flex-direction:column;align-items:stretch;gap:6px;background:transparent;text-align:left}.notification-heading{display:flex;align-items:center;gap:8px}.category{color:var(--gc-color-brand-strong);font-size:11px;font-weight:var(--gc-font-weight-semibold)}.priority{padding:3px 7px;border-radius:10px;background:var(--gc-color-sage-pale);color:var(--gc-color-muted);font-size:9px}.priority--risk{background:var(--gc-color-danger-pale);color:var(--gc-color-danger);font-weight:var(--gc-font-weight-bold)}.read-state{margin-left:auto;color:var(--gc-color-muted);font-size:10px}.event-title{color:var(--gc-color-text);font-size:14px;line-height:1.45;font-weight:var(--gc-font-weight-semibold)}.target-unavailable{color:var(--gc-color-muted);font-size:11px}.more,.secondary,.primary{min-height:44px;padding:0 14px;border:1px solid var(--gc-color-border);border-radius:14px;background:var(--gc-color-surface);color:var(--gc-color-brand-strong);font-size:12px}.more{align-self:center}.primary{border-color:var(--gc-color-brand);background:var(--gc-color-brand);color:white}.status-card{margin-top:10px}.empty,.safe-target{display:flex;min-height:170px;margin-top:10px;align-items:center;justify-content:center;flex-direction:column;gap:10px;text-align:center}.safe-mark{display:grid;width:40px;height:40px;place-items:center;border:1px solid var(--gc-color-brand);border-radius:50%;color:var(--gc-color-brand);font-size:20px}.section-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.refresh-error,.more-error{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:10px;border:1px solid var(--gc-color-danger);border-radius:12px;color:var(--gc-color-danger);font-size:11px}.footer-note{display:block;margin:14px 3px}.notification-card .event-title,.notification-card .meta{display:block}.preference-card{display:flex;margin-top:16px;flex-direction:column;gap:14px}.pref-row{display:flex;align-items:center;justify-content:space-between;gap:12px}.pref-copy{display:flex;flex-direction:column;gap:4px}.pref-title{color:var(--gc-color-text);font-size:13px;font-weight:var(--gc-font-weight-semibold)}.toggle{min-width:72px;min-height:44px;padding:0 10px;border:1px solid var(--gc-color-border);border-radius:16px;background:var(--gc-color-canvas);color:var(--gc-color-muted);font-size:11px}.toggle--on{border-color:var(--gc-color-brand);background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong)}.risk-exemption{padding:10px;border-radius:12px;background:var(--gc-color-peach);color:var(--gc-color-text);font-size:11px;line-height:1.5}.quiet-title{margin-top:2px}.time-row,.timezone-row{display:flex;align-items:center;gap:8px;color:var(--gc-color-text);font-size:12px}.time-row input,.timezone-row input{min-width:0;height:42px;flex:1;padding:0 8px;border:1px solid var(--gc-color-border);border-radius:10px;background:var(--gc-color-canvas);color:var(--gc-color-text);font-size:12px}.error{color:var(--gc-color-danger);font-size:12px}.request-id{display:block;color:var(--gc-color-muted);font-size:10px}.auth-pending{display:grid;min-height:100vh;place-items:center;color:var(--gc-color-muted)}
</style>

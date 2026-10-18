<template>
  <TabRoot active="today" :authorized="authorized" test-id="today-tab">
    <view class="header">
      <view class="header-copy">
        <text class="eyebrow">GUTCARE · {{ dateLabel ?? '日期暂不可用' }}</text>
        <text class="title">今日</text>
      </view>
      <button class="notification-trigger" :aria-label="notificationCount === null ? '打开通知中心' : `打开通知中心，未读 ${notificationCount} 条`" data-testid="today-notifications" @click="router?.navigate('notifications')">
        <svg class="bell-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
        <text v-if="notificationCount !== null && notificationCount > 0" class="notification-badge" data-testid="today-notification-count">{{ notificationCount > 99 ? '99+' : notificationCount }}</text>
      </button>
      <button class="profile-trigger" aria-label="打开我的页面" data-testid="today-profile" @click="router?.switchTab('me')">
        <GcAvatar size="header" />
      </button>
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">站内通知</text><button class="text-link" data-testid="today-notification-link" @click="router?.navigate('notifications')">查看全部</button></view>
    <view class="panel notification-summary" data-testid="today-notification-summary"><text v-if="notificationLoading && notificationCount === null" class="notification-copy" role="status">正在载入未读数…</text><template v-else><text class="notification-count">{{ notificationCount === null ? '—' : notificationCount }}</text><text class="notification-copy">条未读通知</text></template><view v-if="notificationCountError" class="notification-error" role="alert"><text>{{ notificationCountError }}</text><button class="notification-retry" :disabled="notificationLoading" data-testid="today-notification-retry" @click="() => loadNotificationCount()">重试</button></view></view>

    <view class="welcome-card">
      <view class="welcome-copy">
        <text class="welcome-title">你好，{{ auth.profile?.nickname || 'GutCare 用户' }}</text>
        <text class="welcome-subtitle">照顾肠胃健康，从记录日常开始。</text>
      </view>
      <view class="hero-mark" aria-hidden="true"><text>+</text></view>
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">风险提示</text><button class="text-link" data-testid="today-risk-link" @click="router?.navigate('riskAlerts')">查看全部</button></view>
    <view class="panel risk-panel" data-testid="today-risk-alerts">
      <DashboardDataStatus v-if="riskState !== 'ready' || riskAlerts.length === 0" :state="riskState === 'ready' ? 'empty' : riskState" :message="riskMessage" :retryable="riskState === 'error'" :busy="riskLoading" test-id="today-risk-status" @retry="() => loadTodayRisk()" />
      <view v-else class="risk-items">
        <button v-for="item in riskAlerts" :key="item.id" class="risk-item" :class="`risk-item--${item.severity}`" :data-testid="`today-risk-${item.id}`" @click="router?.navigateRiskAlertDetail(item.id)">
          <text class="risk-symbol" aria-hidden="true">{{ riskIcon(item.severity) }}</text>
          <view class="risk-copy"><text class="risk-severity">{{ riskLabel(item.severity) }} · {{ item.status === 'unread' ? '未查看' : '已查看' }}</text><text class="risk-message">{{ item.message }}</text><text class="risk-action">{{ item.recommended_action }}</text></view>
        </button>
      </view>
      <text class="risk-disclaimer">已查看或已重新评估不表示风险解除或确认安全。</text>
      <view v-if="riskRefreshError" class="card-refresh-error" role="alert"><text>{{ riskRefreshError }}</text><button data-testid="today-risk-refresh-retry" :disabled="riskLoading" @click="() => loadTodayRisk()">重试</button></view>
    </view>

    <view class="section-heading"><text class="section-title">今日概览</text><text class="section-caption">仅显示已连接的本人数据</text></view>
    <view class="panel summary-panel" data-testid="today-summary">
      <view class="panel-top"><text class="panel-title">最近建议</text><text class="panel-kicker">ADVICE</text></view>
      <DashboardDataStatus v-if="adviceState !== 'ready'" :state="adviceState" :message="adviceError || undefined" :retryable="adviceState === 'error' || Boolean(adviceError)" :busy="adviceLoading" test-id="advice-status" @retry="() => loadLatestAdvice()" />
      <view v-if="advice" class="advice-preview" data-testid="today-latest-advice">
        <text class="advice-status">状态：{{ adviceStatusLabel(advice.status) }}</text>
        <text class="advice-title">{{ advice.title }}</text>
        <button class="advice-open" data-testid="today-advice-open" @click="router?.navigateAdviceDetail(advice.id, 'me', 'list')">查看建议</button>
      </view>
      <view v-if="adviceError && adviceLoaded" class="card-refresh-error" role="alert"><text>{{ adviceError }}</text><button data-testid="today-advice-retry" :disabled="adviceLoading" @click="() => loadLatestAdvice()">重试</button></view>
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">快捷记录</text><button class="text-link" data-testid="today-all-records" @click="router?.switchTab('records')">全部记录</button></view>
    <view class="quick-grid" data-testid="today-quick-records">
      <button v-for="item in quickActions" :key="item.route" class="quick-tile" :data-testid="`quick-${item.route}`" @click="router?.navigate(item.route)">
        <view class="quick-icon" :class="`quick-icon--${item.tint}`" aria-hidden="true"><text>{{ item.icon }}</text></view>
        <text class="quick-label">{{ item.label }}</text>
      </button>
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">用药计划</text><button class="text-link" data-testid="today-medication-link" @click="router?.navigate('medications')">查看全部</button></view>
    <view class="panel compact-panel" data-testid="today-medications">
      <view class="panel-icon panel-icon--peach" aria-hidden="true">＋</view>
      <view class="panel-content"><text class="panel-title">本人计划的今日打卡状态</text><DashboardDataStatus v-if="medicationState !== 'ready'" :state="medicationState" :message="medicationMessage || undefined" :retryable="medicationState === 'error'" :busy="medicationLoading" test-id="medication-status" @retry="() => loadTodayMedication()" /><view v-if="medicationCheckins.length" class="medication-summary" data-testid="today-medication-summary"><text v-for="item in medicationCheckins.slice(0, 3)" :key="item.id" class="medication-detail">{{ medicationStatusLabel(item.status) }}</text><text v-if="medicationCheckins.length > 3" class="medication-detail">还有 {{ medicationCheckins.length - 3 }} 项；查看完整安排</text></view><view v-if="medicationRefreshError" class="card-refresh-error" role="alert"><text>{{ medicationRefreshError }}</text><button data-testid="today-medication-refresh-retry" :disabled="medicationLoading" @click="() => loadTodayMedication()">重试</button></view></view>
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">今日趋势</text><button class="text-link" data-testid="today-trends-link" @click="router?.navigate('trends')">查看趋势</button></view>
    <view class="panel data-panel" data-testid="today-trends">
      <view class="panel-top"><text class="panel-title">本人记录统计</text><text class="panel-kicker">TODAY</text></view>
      <DashboardDataStatus v-if="trendState !== 'ready'" :state="trendState" :message="trendError || undefined" :retryable="trendState === 'error'" :busy="trendLoading" test-id="trend-status" @retry="() => loadTodayTrend()" />
      <view v-else class="trend-metrics" data-testid="today-trend-metrics">
        <view v-for="metric in trendMetrics" :key="metric.key" class="trend-metric" :data-testid="`today-trend-${metric.key}`">
          <text class="trend-title">{{ metric.title }}</text>
          <template v-if="metric.state === 'consent_required'"><text class="trend-note">心情趋势需先获得授权；当前不是空数据。</text><text v-for="consent in metric.missingConsents" :key="consent" class="trend-note">· {{ moodMissingConsentLabel(consent) }}</text><button class="trend-privacy" data-testid="today-trend-privacy" @click="router?.navigate('privacyCenter')">前往隐私中心</button></template>
          <text v-else-if="metric.state === 'empty'" class="trend-note">今日暂无已汇总记录。</text>
          <template v-else><text v-for="(line, index) in metric.lines" :key="`${metric.key}-${index}`" class="trend-line">{{ line }}</text></template>
        </view>
      </view>
      <view v-if="trendRefreshError" class="card-refresh-error" role="alert"><text>{{ trendRefreshError }}</text><button data-testid="today-trend-retry" :disabled="trendLoading" @click="() => loadTodayTrend()">重试</button></view>
    </view>
  </TabRoot>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import { adviceApiKey, appRouterKey, medicationApiKey, notificationApiKey, riskApiKey, trendApiKey } from '../../../api/context'
import type { AppRouteName } from '../../../navigation/routes'
import { canRenderRoute } from '../../../navigation/routes'
import { useAuthStore } from '../../../stores/auth'
import DashboardDataStatus from '../../../components/DashboardDataStatus.vue'
import GcAvatar from '../../../components/GcAvatar.vue'
import TabRoot from '../../../components/TabRoot.vue'
import type { MedicationCheckin } from '../../../api/openapiTypes'
import type { RiskAlert } from '../../../api/openapiTypes'
import type { Advice } from '../../../api/openapiTypes'
import { buildTodayTrendQuery, formatTodayDateLabel, todayTrendMetrics } from '../../../api/todayDashboardView'

const auth = useAuthStore()
const router = inject(appRouterKey)
const medicationApi = inject(medicationApiKey)
const riskApi = inject(riskApiKey)
const notificationApi = inject(notificationApiKey)
const adviceApi = inject(adviceApiKey)
const trendApi = inject(trendApiKey)
const authorized = computed(() => canRenderRoute('today', auth.state))
const medicationState = ref<'loading' | 'empty' | 'error' | 'unavailable' | 'ready'>(medicationApi ? 'loading' : 'unavailable')
const medicationLoading = ref(false)
const medicationMessage = ref('')
const medicationCheckins = ref<MedicationCheckin[]>([])
const medicationStatusLabel = (status: MedicationCheckin['status']) => ({ taken: '已记录服用', not_taken: '本人记录未服用', pending: '待回应', skipped: '已跳过' })[status]
const riskState = ref<'loading' | 'empty' | 'error' | 'unavailable' | 'ready'>(riskApi ? 'loading' : 'unavailable')
const riskLoading = ref(false)
const riskMessage = ref('')
const riskRefreshError = ref('')
const riskAlerts = ref<RiskAlert[]>([])
const notificationCount = ref<number | null>(null)
const notificationCountError = ref(notificationApi ? '' : '未读数服务暂不可用。')
const notificationLoading = ref(false)
const adviceState = ref<'loading' | 'empty' | 'error' | 'unavailable' | 'ready'>(adviceApi ? 'loading' : 'unavailable')
const advice = ref<Advice | null>(null)
const adviceLoading = ref(false)
const adviceError = ref('')
const adviceLoaded = ref(false)
const trendState = ref<'loading' | 'error' | 'unavailable' | 'ready'>(trendApi ? 'loading' : 'unavailable')
const trendMetrics = ref<ReturnType<typeof todayTrendMetrics>>([])
const trendLoading = ref(false)
const trendError = ref('')
const trendRefreshError = ref('')
let visible = false
let generation = 0
const medicationLoaded = ref(false)
const medicationRefreshError = ref('')
const riskLoaded = ref(false)
const trendLoaded = ref(false)
const dashboardNow = ref(new Date())
const dateLabel = computed(() => formatTodayDateLabel(auth.profile?.timezone, dashboardNow.value))
const quickActions: ReadonlyArray<{ route: AppRouteName; label: string; icon: string; tint: string }> = [
  { route: 'recordDiet', label: '饮食', icon: '餐', tint: 'peach' },
  { route: 'recordBowel', label: '排便', icon: '记', tint: 'sage' },
  { route: 'recordSymptoms', label: '症状', icon: '＋', tint: 'lilac' },
  { route: 'recordMood', label: '心情', icon: '♡', tint: 'yellow' },
  { route: 'recordActivity', label: '运动', icon: '↗', tint: 'sage' },
]

onShow(() => {
  if (!authorized.value) { visible = false; router?.requireAuthentication('today'); return }
  if (visible) return
  visible = true
  dashboardNow.value = new Date()
  const current = ++generation
  void loadTodayMedication(current)
  void loadTodayRisk(current)
  void loadNotificationCount(current)
  void loadLatestAdvice(current)
  void loadTodayTrend(current)
})
onHide(() => invalidatePageRequests())
onUnload(() => invalidatePageRequests())

function invalidatePageRequests() {
  visible = false
  generation += 1
  medicationLoading.value = false
  riskLoading.value = false
  notificationLoading.value = false
  adviceLoading.value = false
  trendLoading.value = false
}

function isCurrent(current: number) { return visible && generation === current && authorized.value }
async function loadTodayMedication(current = generation) {
  if (!medicationApi || !isCurrent(current) || medicationLoading.value) return
  medicationLoading.value = true
  if (!medicationLoaded.value) medicationState.value = 'loading'
  medicationMessage.value = ''; medicationRefreshError.value = ''
  try { const result = await medicationApi.listTodayCheckins(); if (!isCurrent(current)) return; medicationCheckins.value = result; medicationLoaded.value = true; medicationState.value = result.length ? 'ready' : 'empty' }
  catch { if (isCurrent(current)) { if (medicationLoaded.value) medicationRefreshError.value = '刷新失败，仍显示上次载入的打卡安排。'; else { medicationState.value = 'error'; medicationMessage.value = '暂时无法载入今日打卡安排；没有把失败显示为已完成或无计划。' } } }
  finally { if (isCurrent(current)) medicationLoading.value = false }
}
async function loadTodayRisk(current = generation) {
  if (!riskApi || !isCurrent(current) || riskLoading.value) return
  riskLoading.value = true
  if (!riskLoaded.value) riskState.value = 'loading'
  riskMessage.value = ''; riskRefreshError.value = ''
  try { const result = await riskApi.list({ limit: 3, unread_only: true }); if (!isCurrent(current)) return; riskAlerts.value = result.items; riskLoaded.value = true; riskState.value = result.items.length ? 'ready' : 'empty' }
  catch { if (isCurrent(current)) { if (riskLoaded.value) riskRefreshError.value = '刷新失败，仍显示上次载入的风险提示。'; else { riskState.value = 'error'; riskMessage.value = '暂时无法载入风险提示；加载失败不代表没有风险。' } } }
  finally { if (isCurrent(current)) riskLoading.value = false }
}
async function loadNotificationCount(current = generation) {
  if (!notificationApi || !isCurrent(current) || notificationLoading.value) return
  notificationLoading.value = true
  try { const result = await notificationApi.unreadCount(); if (!isCurrent(current)) return; notificationCount.value = result.count; notificationCountError.value = '' }
  catch { if (isCurrent(current)) notificationCountError.value = notificationCount.value === null ? '未读数暂不可用；未按失败推断为 0。' : '刷新失败，仍显示上次载入的未读数。' }
  finally { if (isCurrent(current)) notificationLoading.value = false }
}
async function loadLatestAdvice(current = generation) {
  if (!adviceApi || !isCurrent(current) || adviceLoading.value) return
  adviceLoading.value = true
  if (!adviceLoaded.value) adviceState.value = 'loading'
  adviceError.value = ''
  try { const page = await adviceApi.list({ limit: 1 }); if (!isCurrent(current)) return; advice.value = page.items[0] ?? null; adviceLoaded.value = true; adviceState.value = advice.value ? 'ready' : 'empty' }
  catch { if (isCurrent(current)) { adviceState.value = adviceLoaded.value ? (advice.value ? 'ready' : 'empty') : 'error'; adviceError.value = adviceLoaded.value ? '刷新失败，仍显示上次载入的建议状态。' : '暂时无法载入最近建议。' } }
  finally { if (isCurrent(current)) adviceLoading.value = false }
}
async function loadTodayTrend(current = generation) {
  if (!trendApi || !isCurrent(current) || trendLoading.value) return
  trendLoading.value = true
  if (!trendLoaded.value) trendState.value = 'loading'
  trendError.value = ''; trendRefreshError.value = ''
  const range = buildTodayTrendQuery(auth.profile?.timezone, dashboardNow.value)
  if (!range.query) { if (isCurrent(current)) { trendState.value = trendLoaded.value ? 'ready' : 'error'; (trendLoaded.value ? trendRefreshError : trendError).value = range.error ?? '今日范围暂不可用。'; trendLoading.value = false }; return }
  try { const result = await trendApi.get(range.query); if (!isCurrent(current)) return; trendMetrics.value = todayTrendMetrics(result); trendLoaded.value = true; trendState.value = 'ready' }
  catch { if (isCurrent(current)) { trendState.value = trendLoaded.value ? 'ready' : 'error'; (trendLoaded.value ? trendRefreshError : trendError).value = trendLoaded.value ? '刷新失败，仍显示上次载入的今日趋势。' : '暂时无法载入今日趋势。' } }
  finally { if (isCurrent(current)) trendLoading.value = false }
}
function riskLabel(severity: RiskAlert['severity']) { return severity === 'emergency' ? '紧急提示' : severity === 'seek_care' ? '尽快就医提示' : '关注提示' }
function riskIcon(severity: RiskAlert['severity']) { return severity === 'emergency' ? '!' : severity === 'seek_care' ? '△' : 'i' }
function adviceStatusLabel(status: Advice['status']) { return ({ new: '新建', read: '已读', archived: '已归档' })[status] }
function moodMissingConsentLabel(consent: string) { return consent === 'health_data_processing' ? '健康数据处理' : consent === 'mood_data_processing' ? '心情数据处理' : '其他所需授权' }
</script>

<style lang="scss" scoped>
.header { display: flex; align-items: center; justify-content: space-between; margin: 2px 2px 20px; }
.notification-trigger { position: relative; display: grid; width: 44px; height: 44px; margin-left: auto; margin-right: 8px; padding: 9px; place-items: center; border: 1px solid var(--gc-color-border); border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); }.bell-icon { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }.notification-badge { position: absolute; top: -2px; right: -3px; min-width: 17px; height: 17px; padding: 0 4px; border: 1px solid var(--gc-color-surface); border-radius: 10px; background: var(--gc-color-danger); color: white; font-size: 9px; line-height: 15px; text-align: center; }.notification-summary { display: flex; min-height: 64px; align-items: center; gap: 8px; }.notification-count { color: var(--gc-color-brand-strong); font-size: 24px; font-weight: var(--gc-font-weight-bold); }.notification-copy { color: var(--gc-color-muted); font-size: 12px; }.notification-error { display: flex; margin-left: auto; align-items: center; gap: 4px; color: var(--gc-color-danger); font-size: 10px; }.notification-retry { min-height: 44px; border: 0; background: transparent; color: var(--gc-color-brand-strong); font-size: 11px; }
.header-copy { display: flex; flex-direction: column; }
.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }
.title { margin-top: 3px; color: var(--gc-color-text); font-size: 28px; line-height: 1.25; font-weight: var(--gc-font-weight-bold); }
.profile-trigger { display: grid; width: 48px; height: 48px; padding: 2px; place-items: center; border: 0; border-radius: 50%; background: var(--gc-color-sage-pale); }
.welcome-card { position: relative; display: flex; min-height: 132px; align-items: center; justify-content: space-between; overflow: hidden; padding: 20px; border-radius: var(--gc-radius-lg); background: var(--gc-color-brand); color: var(--gc-color-on-brand); box-shadow: var(--gc-shadow-card); }
.welcome-copy { max-width: 78%; }.welcome-title { display: block; font-size: 19px; line-height: 1.35; font-weight: var(--gc-font-weight-semibold); }.welcome-subtitle { display: block; margin-top: 7px; color: rgba(255,255,255,.82); font-size: 13px; line-height: 1.5; }
.hero-mark { display: grid; width: 52px; height: 52px; flex: 0 0 52px; place-items: center; border: 1px solid rgba(255,255,255,.35); border-radius: 50%; background: rgba(255,255,255,.12); color: white; font-size: 27px; font-weight: 300; }
.section-heading { display: flex; align-items: baseline; justify-content: space-between; margin: 22px 2px 10px; }.section-heading--tight { margin-top: 20px; }.section-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.section-caption { color: var(--gc-color-muted); font-size: 10px; }
.panel { padding: 15px 16px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }.panel-top { display: flex; align-items: center; justify-content: space-between; }.panel-title { display: block; color: var(--gc-color-text); font-size: 14px; font-weight: var(--gc-font-weight-semibold); }.panel-kicker { color: var(--gc-color-muted); font-size: 9px; letter-spacing: .8px; }.summary-panel { min-height: 122px; }.data-panel { min-height: 106px; }
.quick-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }.quick-tile { display: flex; min-height: 84px; min-width: 0; padding: 8px 2px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-md); flex-direction: column; align-items: center; justify-content: center; gap: 6px; background: var(--gc-color-surface); }.quick-icon { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 13px; color: var(--gc-color-brand-strong); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.quick-icon--peach,.panel-icon--peach { background: var(--gc-color-peach); }.quick-icon--sage { background: var(--gc-color-sage-pale); }.quick-icon--lilac { background: var(--gc-color-lilac); color: var(--gc-color-purple); }.quick-icon--yellow { background: var(--gc-color-yellow); }.quick-label { color: var(--gc-color-text); font-size: 11px; line-height: 1.2; }
.text-link { min-height: 44px; padding: 0 3px; border: 0; background: transparent; color: var(--gc-color-brand); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }
.compact-panel { display: flex; min-height: 94px; align-items: flex-start; gap: 12px; }.panel-icon { display: grid; width: 38px; height: 38px; flex: 0 0 38px; place-items: center; border-radius: 13px; color: var(--gc-color-brand); font-size: 20px; }.panel-content { min-width: 0; flex: 1; }.compact-panel :deep(.data-status) { min-height: 42px; }
.medication-summary { display: flex; margin-top: 8px; flex-direction: column; gap: 5px; color: var(--gc-color-brand-strong); font-size: 12px; line-height: 1.5; }.medication-detail { color: var(--gc-color-muted); font-size: 10px; }
.risk-panel { display: flex; flex-direction: column; gap: 8px; }.risk-items { display: flex; flex-direction: column; gap: 8px; }.risk-item { display: flex; width: 100%; min-height: 72px; align-items: flex-start; gap: 10px; padding: 10px; border: 1px solid var(--gc-color-border); border-left: 5px solid var(--gc-color-brand); border-radius: 12px; background: var(--gc-color-surface); text-align: left; }.risk-item--seek_care { border-left-color: var(--gc-color-peach-strong, #B84E2A); }.risk-item--emergency { border: 2px solid var(--gc-color-danger); border-left-width: 7px; background: var(--gc-color-danger-pale); }.risk-symbol { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; border: 1px solid currentColor; border-radius: 50%; color: var(--gc-color-brand-strong); font-weight: var(--gc-font-weight-bold); }.risk-item--emergency .risk-symbol,.risk-item--emergency .risk-severity { color: var(--gc-color-danger); }.risk-copy { display: flex; min-width: 0; flex-direction: column; gap: 4px; }.risk-severity { color: var(--gc-color-brand-strong); font-size: 12px; font-weight: var(--gc-font-weight-bold); }.risk-message,.risk-action { color: var(--gc-color-text); font-size: 11px; line-height: 1.45; }.risk-action { font-weight: var(--gc-font-weight-semibold); }.risk-disclaimer { color: var(--gc-color-muted); font-size: 10px; line-height: 1.45; }
.advice-preview { display: flex; margin-top: 12px; flex-direction: column; gap: 7px; }.advice-status,.trend-title { color: var(--gc-color-brand-strong); font-size: 11px; font-weight: var(--gc-font-weight-semibold); }.advice-title { color: var(--gc-color-text); font-size: 13px; line-height: 1.45; }.advice-open,.trend-privacy { min-height: 44px; align-self: flex-start; padding: 0 12px; border: 1px solid var(--gc-color-border); border-radius: 12px; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 11px; }.card-refresh-error { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--gc-color-danger); font-size: 10px; line-height: 1.4; }.card-refresh-error button { min-width: 56px; min-height: 44px; border: 0; background: transparent; color: var(--gc-color-brand-strong); font-size: 11px; }.trend-metrics { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 8px; margin-top: 12px; }.trend-metric { display: flex; min-width: 0; padding: 10px; border: 1px solid var(--gc-color-border); border-radius: 12px; flex-direction: column; gap: 5px; }.trend-title { font-size: 10px; }.trend-line,.trend-note { color: var(--gc-color-muted); font-size: 10px; line-height: 1.45; overflow-wrap: anywhere; }.trend-privacy { min-height: 44px; padding: 0 8px; font-size: 10px; }
@media (max-width: 360px) { .tab-content { padding-right: 14px; padding-left: 14px; }.quick-grid { gap: 4px; }.quick-label { font-size: 10px; } }
</style>

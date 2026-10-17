<template>
  <view v-if="pageReady" class="trends-page" data-testid="trends-page" :data-owner-tab="ownerTab">
    <view class="shell">
      <view class="topbar"><button class="back" aria-label="返回" data-testid="trends-back" @click="goBack">‹</button><text class="topbar-title">健康趋势</text><button class="refresh" aria-label="刷新趋势" :disabled="busy" data-testid="trends-refresh" @click="reload(true)">↻</button></view>
      <view class="intro"><text class="eyebrow">YOUR HEALTH, IN CONTEXT</text><text class="title">趋势</text><text class="muted">展示本人结构化记录统计；不作诊断、病因或因果解释。</text></view>

      <view class="range-panel" data-testid="trend-range">
        <view class="range-heading"><text class="section-title">日期范围</text><text class="timezone">账户时区 · {{ timezone }}</text></view>
        <view class="quick-ranges" role="group" aria-label="快速日期范围">
          <button v-for="days in quickRanges" :key="days" class="quick-chip" :class="{ selected: selectedQuickRange === days }" :aria-pressed="selectedQuickRange === days" :disabled="busy" :data-testid="`trend-quick-${days}`" @click="setQuickRange(days)">{{ days }}天</button>
        </view>
        <view class="date-row">
          <view class="date-control"><text class="date-label">开始日期（含）</text><picker mode="date" :value="sinceDay" :disabled="busy" @change="setSince"><view class="date-picker" data-testid="trend-since">{{ sinceDay }}</view></picker></view>
          <view class="date-control"><text class="date-label">结束日期（含）</text><picker mode="date" :value="throughDay" :disabled="busy" @change="setThrough"><view class="date-picker" data-testid="trend-through">{{ throughDay }}</view></picker></view>
        </view>
        <view class="bucket-row" role="group" aria-label="趋势时间粒度">
          <button class="bucket-chip" :class="{ selected: bucket === 'day' }" :aria-pressed="bucket === 'day'" :disabled="busy" data-testid="trend-bucket-day" @click="setBucket('day')">按日</button>
          <button class="bucket-chip" :class="{ selected: bucket === 'week' }" :aria-pressed="bucket === 'week'" :disabled="busy" data-testid="trend-bucket-week" @click="setBucket('week')">按周</button>
        </view>
        <text class="range-note">请求使用账户时区对应的 UTC 半开区间 [开始, 结束次日)。</text>
        <text v-if="filterError" class="inline-error" role="alert" data-testid="trend-filter-error">{{ filterError }}</text>
      </view>

      <view v-if="loadState === 'loading' && !response" class="status-card"><DashboardDataStatus state="loading" test-id="trend-loading" /></view>
      <view v-else-if="loadState === 'error' && !response" class="status-card"><DashboardDataStatus state="error" :message="loadError" retryable :busy="busy" test-id="trend-error" @retry="reload(false)" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
      <template v-else-if="response">
        <view v-if="refreshError" class="refresh-error" role="alert" data-testid="trend-refresh-error"><text>{{ refreshError }}</text><button class="retry" :disabled="busy" data-testid="trend-refresh-retry" @click="reload(true)">重试</button><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view class="scope-note" data-testid="trend-scope-note"><text class="scope-title">{{ trendBucketLabel(response.bucket) }} · {{ response.from }} 至 {{ response.to }}</text><text class="scope-copy">统计按服务端返回的患者时区桶展示；各项分别呈现，不在客户端合并或重算。</text></view>
        <view class="metric-list" data-testid="trend-metrics">
          <view class="metric-card" data-testid="trend-activity">
            <view class="metric-heading"><view class="metric-icon metric-icon--sage" aria-hidden="true">↗</view><view><text class="metric-title">活动记录</text><text class="metric-subtitle">次数与时长</text></view></view>
            <view v-if="response.activity.has_data" class="bucket-list"><view v-for="(item, index) in response.activity.items" :key="`${item.bucket}-${index}`" class="bucket-row-item"><text>{{ trendBucketDate(item.bucket) }}</text><text>{{ item.count }} 次 · {{ item.duration_minutes }} 分钟</text></view></view>
            <text v-else class="metric-empty" data-testid="trend-activity-empty">此范围暂无活动记录。</text>
          </view>

          <view class="metric-card" data-testid="trend-stool">
            <view class="metric-heading"><view class="metric-icon metric-icon--peach" aria-hidden="true">记</view><view><text class="metric-title">排便记录</text><text class="metric-subtitle">记录次数与已确认 Bristol 分型</text></view></view>
            <view v-if="response.stool.has_data" class="bucket-list"><view v-for="(item, index) in response.stool.items" :key="`${item.bucket}-${index}`" class="bucket-row-item"><text>{{ trendBucketDate(item.bucket) }}</text><text>{{ item.count }} 次 · 已确认 {{ item.bristol_confirmed_count }} · 未知 {{ item.bristol_unknown_count }}</text></view></view>
            <text v-else class="metric-empty" data-testid="trend-stool-empty">此范围暂无排便记录。</text>
          </view>

          <view class="metric-card" data-testid="trend-symptom">
            <view class="metric-heading"><view class="metric-icon metric-icon--lilac" aria-hidden="true">＋</view><view><text class="metric-title">症状自评</text><text class="metric-subtitle">患者自评严重度与记录状态</text></view></view>
            <view v-if="response.symptom.has_data" class="bucket-list"><view v-for="(item, index) in response.symptom.items" :key="`${item.bucket}-${item.status}-${index}`" class="bucket-row-item"><text>{{ trendBucketDate(item.bucket) }} · {{ symptomStatusLabel(item.status) }}</text><text>{{ item.count }} 条 · 平均自评 {{ item.mean_severity ?? '未知' }}</text></view></view>
            <text v-else class="metric-empty" data-testid="trend-symptom-empty">此范围暂无症状记录。</text>
          </view>

          <view class="metric-card" data-testid="trend-diet">
            <view class="metric-heading"><view class="metric-icon metric-icon--yellow" aria-hidden="true">餐</view><view><text class="metric-title">饮食分类</text><text class="metric-subtitle">仅显示本人确认的分类</text></view></view>
            <view v-if="response.diet_confirmed_categories.has_data" class="bucket-list"><view v-for="(item, index) in response.diet_confirmed_categories.items" :key="`${item.bucket}-${item.category}-${index}`" class="bucket-row-item"><text>{{ trendBucketDate(item.bucket) }} · {{ item.category }}</text><text>{{ item.count }} 项</text></view></view>
            <text v-else class="metric-empty" data-testid="trend-diet-empty">此范围暂无已确认饮食分类。</text>
          </view>

          <view class="metric-card" data-testid="trend-medication">
            <view class="metric-heading"><view class="metric-icon metric-icon--peach" aria-hidden="true">药</view><view><text class="metric-title">用药打卡</text><text class="metric-subtitle">按服务端打卡状态统计</text></view></view>
            <view v-if="response.medication_checkins.has_data" class="bucket-list"><view v-for="(item, index) in response.medication_checkins.items" :key="`${item.bucket}-${item.status}-${index}`" class="bucket-row-item"><text>{{ trendBucketDate(item.bucket) }} · {{ medicationStatusLabel(item.status) }}</text><text>{{ item.count }} 次</text></view></view>
            <text v-else class="metric-empty" data-testid="trend-medication-empty">此范围暂无用药打卡。</text>
          </view>

          <view class="metric-card" data-testid="trend-mood">
            <view class="metric-heading"><view class="metric-icon metric-icon--lilac" aria-hidden="true">♡</view><view><text class="metric-title">心情等级</text><text class="metric-subtitle">患者自评记录统计，不含备注与标签</text></view></view>
            <template v-if="response.mood.availability === 'available'">
              <view v-if="response.mood.buckets.length" class="bucket-list"><view v-for="item in response.mood.buckets" :key="item.period_start" class="mood-bucket"><text class="mood-period">{{ item.period_start }} — {{ item.period_end }} · {{ item.record_count }} 条</text><view class="mood-levels"><text v-for="level in moodLevels" :key="level" class="mood-level">{{ level }}档 {{ item.mood_level_counts[level] }}</text></view></view></view>
              <text v-else class="metric-empty" data-testid="trend-mood-empty">授权有效；此范围暂无心情记录。</text>
            </template>
            <view v-else class="consent-required" role="status" data-testid="trend-mood-consent-required"><text>心情趋势暂不可用，需要以下授权：</text><text v-for="consent in response.mood.missing_consents" :key="consent">· {{ moodMissingConsentLabel(consent) }}</text><button class="privacy-link" data-testid="trend-mood-privacy-link" @click="router?.navigate('privacyCenter')">前往隐私中心</button></view>
          </view>
        </view>
      </template>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { inject, ref } from 'vue'
import { onBackPress, onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { appRouterKey, trendApiKey } from '../../api/context'
import { AppError } from '../../api/errors'
import type { TrendBucket, TrendResponse } from '../../api/openapiTypes'
import { buildTrendRange, dateInTimezone, isTrendResponseCurrent, moodMissingConsentLabel, shiftCalendarDate, trendBucketDate, trendBucketLabel } from '../../api/trendView'
import { canRenderRoute } from '../../navigation/routes'
import type { AppRouteName, AppTabName } from '../../navigation/routes'
import { useAuthStore } from '../../stores/auth'
import DashboardDataStatus from '../../components/DashboardDataStatus.vue'

const auth = useAuthStore()
const api = inject(trendApiKey)
const router = inject(appRouterKey)
const pageReady = ref(false)
const visible = ref(false)
const busy = ref(false)
const ownerTab = ref<AppTabName>('me')
const routeName = ref<AppRouteName>('trends')
const timezone = ref('UTC')
const sinceDay = ref('')
const throughDay = ref('')
const bucket = ref<TrendBucket>('day')
const selectedQuickRange = ref<number | null>(30)
const response = ref<TrendResponse | null>(null)
const loadState = ref<'loading' | 'ready' | 'error'>('loading')
const loadError = ref('')
const refreshError = ref('')
const filterError = ref('')
const requestId = ref('')
const quickRanges = [7, 30, 90] as const
const moodLevels = ['1', '2', '3', '4', '5'] as const
let generation = 0
let firstShowHandled = false

onLoad((options) => {
  ownerTab.value = options?.owner === 'analysis' ? 'analysis' : 'me'
  routeName.value = ownerTab.value === 'analysis' ? 'analysisTrends' : 'trends'
  if (!canRenderRoute(routeName.value, auth.state)) { router?.requireAuthentication(routeName.value); return }
  timezone.value = auth.profile?.timezone || 'UTC'
  const today = dateInTimezone(new Date(), timezone.value)
  throughDay.value = today
  sinceDay.value = shiftCalendarDate(today, -29)
  pageReady.value = true
  visible.value = true
  void reload(false)
})

onShow(() => {
  if (!pageReady.value) return
  if (!canRenderRoute(routeName.value, auth.state)) { router?.requireAuthentication(routeName.value); return }
  visible.value = true
  if (firstShowHandled) void reload(true)
  else firstShowHandled = true
})
onHide(() => { visible.value = false; generation += 1; busy.value = false })
onUnload(() => { visible.value = false; generation += 1; busy.value = false })
onBackPress(() => { goBack(); return true })

async function reload(preserve: boolean) {
  if (!pageReady.value || !visible.value || busy.value || !canRenderRoute(routeName.value, auth.state)) return
  if (!api) { loadState.value = 'error'; loadError.value = '趋势服务暂时不可用。'; return }
  const range = buildTrendRange(sinceDay.value, shiftCalendarDate(throughDay.value, 1), timezone.value)
  if (range.error) {
    filterError.value = range.error
    if (!preserve || !response.value) { loadState.value = 'error'; loadError.value = range.error }
    return
  }
  filterError.value = ''
  const requestGeneration = ++generation
  const keep = preserve && response.value !== null
  busy.value = true
  refreshError.value = ''
  requestId.value = ''
  if (!keep) { loadState.value = 'loading'; loadError.value = '' }
  try {
    const result = await api.get({ from: range.from, to: range.to, bucket: bucket.value })
    if (!isCurrent(requestGeneration)) return
    response.value = result
    loadState.value = 'ready'
  } catch (error) {
    if (!isCurrent(requestGeneration)) return
    capture(error)
    const message = friendlyError(error)
    if (keep) { refreshError.value = message; loadState.value = 'ready' }
    else { loadError.value = message; loadState.value = 'error' }
  } finally {
    if (isCurrent(requestGeneration)) busy.value = false
  }
}

function setQuickRange(days: number) {
  if (busy.value) return
  const today = dateInTimezone(new Date(), timezone.value)
  throughDay.value = today
  sinceDay.value = shiftCalendarDate(today, -(days - 1))
  selectedQuickRange.value = days
  response.value = null
  void reload(false)
}
function setSince(event: { detail?: { value?: string } }) {
  if (busy.value || !event.detail?.value) return
  sinceDay.value = event.detail.value; selectedQuickRange.value = null; response.value = null; void reload(false)
}
function setThrough(event: { detail?: { value?: string } }) {
  if (busy.value || !event.detail?.value) return
  throughDay.value = event.detail.value; selectedQuickRange.value = null; response.value = null; void reload(false)
}
function setBucket(value: TrendBucket) {
  if (busy.value || bucket.value === value) return
  bucket.value = value; response.value = null; void reload(false)
}
function isCurrent(requestGeneration: number) {
  return isTrendResponseCurrent(requestGeneration, generation, visible.value && pageReady.value, canRenderRoute(routeName.value, auth.state))
}
function goBack() { if (getCurrentPages().length > 1) router?.navigateBack(); else router?.switchTab(ownerTab.value) }
function capture(error: unknown) { requestId.value = error instanceof AppError ? error.requestId ?? error.problem?.request_id ?? '' : '' }
function friendlyError(error: unknown) {
  if (error instanceof AppError && error.kind === 'offline') return '当前离线，趋势未能载入；请检查连接后重试。'
  if (error instanceof AppError && error.status === 422) return '日期范围或时间粒度无效，请调整后重试。'
  return '趋势暂时无法载入，请稍后重试。'
}
function symptomStatusLabel(status: 'ongoing' | 'relieved') { return status === 'ongoing' ? '持续中' : '已缓解' }
function medicationStatusLabel(status: 'pending' | 'taken' | 'not_taken' | 'skipped') {
  return ({ pending: '待回应', taken: '已记录服用', not_taken: '未服用', skipped: '已跳过' } as const)[status]
}
</script>

<style lang="scss" scoped>
.trends-page{min-height:100vh;background:var(--gc-color-canvas)}.shell{width:100%;max-width:430px;min-height:100vh;margin:0 auto;padding:calc(env(safe-area-inset-top,0px) + 10px) 20px calc(env(safe-area-inset-bottom,0px) + 24px)}.topbar{display:flex;height:48px;align-items:center;justify-content:space-between}.back,.refresh{display:grid;width:44px;height:44px;padding:0;place-items:center;border:0;border-radius:14px;background:var(--gc-color-surface);color:var(--gc-color-brand-strong);font-size:26px}.refresh{font-size:21px}.refresh:disabled{opacity:.5}.topbar-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.intro{display:flex;margin:12px 2px 17px;flex-direction:column;gap:5px}.eyebrow{color:var(--gc-color-brand);font-size:10px;font-weight:var(--gc-font-weight-semibold);letter-spacing:1px}.title{color:var(--gc-color-text);font-size:27px;font-weight:var(--gc-font-weight-bold)}.muted,.range-note{color:var(--gc-color-muted);font-size:11px;line-height:1.55}.range-panel,.metric-card,.scope-note{margin-bottom:12px;padding:15px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);background:var(--gc-color-surface);box-shadow:var(--gc-shadow-card)}.range-heading,.date-row,.bucket-row,.quick-ranges{display:flex;align-items:center;justify-content:space-between;gap:8px}.section-title{color:var(--gc-color-text);font-size:14px;font-weight:var(--gc-font-weight-semibold)}.timezone{max-width:56%;overflow:hidden;color:var(--gc-color-muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.quick-ranges{justify-content:flex-start;margin:13px 0}.quick-chip,.bucket-chip{min-height:40px;padding:0 14px;border:1px solid var(--gc-color-border);border-radius:20px;background:var(--gc-color-surface);color:var(--gc-color-muted);font-size:12px}.quick-chip.selected,.bucket-chip.selected{border-color:var(--gc-color-brand);background:var(--gc-color-sage-pale);color:var(--gc-color-brand-strong)}.quick-chip:disabled,.bucket-chip:disabled{opacity:.55}.date-row{gap:10px}.date-control{display:flex;min-width:0;flex:1;flex-direction:column;gap:6px}.date-label{color:var(--gc-color-muted);font-size:10px}.date-picker{min-height:42px;padding:11px;border:1px solid var(--gc-color-border);border-radius:12px;color:var(--gc-color-text);font-size:12px}.bucket-row{justify-content:flex-start;margin:12px 0 5px}.range-note{display:block;margin-top:8px}.inline-error{display:block;margin-top:8px;color:var(--gc-color-danger);font-size:11px}.status-card{margin:18px 2px}.scope-note{display:flex;flex-direction:column;gap:5px;background:var(--gc-color-sage-pale)}.scope-title{color:var(--gc-color-brand-strong);font-size:11px;font-weight:var(--gc-font-weight-semibold);overflow-wrap:anywhere}.scope-copy{color:var(--gc-color-muted);font-size:10px;line-height:1.5}.metric-list{display:flex;flex-direction:column;gap:2px}.metric-card{padding:14px}.metric-heading{display:flex;align-items:center;gap:10px;margin-bottom:9px}.metric-icon{display:grid;width:38px;height:38px;flex:0 0 38px;place-items:center;border-radius:13px;background:var(--gc-color-sage-pale);color:var(--gc-color-brand);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.metric-icon--peach{background:var(--gc-color-peach);color:var(--gc-color-orange)}.metric-icon--lilac{background:var(--gc-color-lilac);color:var(--gc-color-purple)}.metric-icon--yellow{background:var(--gc-color-yellow);color:var(--gc-color-warning)}.metric-title{display:block;color:var(--gc-color-text);font-size:13px;font-weight:var(--gc-font-weight-semibold)}.metric-subtitle{display:block;margin-top:3px;color:var(--gc-color-muted);font-size:10px}.bucket-list{display:flex;flex-direction:column}.bucket-row-item{display:flex;min-height:38px;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--gc-color-border);color:var(--gc-color-text);font-size:10px}.bucket-row-item text:last-child{text-align:right}.metric-empty{display:block;padding:9px 0 3px;border-top:1px solid var(--gc-color-border);color:var(--gc-color-muted);font-size:11px}.mood-bucket{padding:9px 0;border-top:1px solid var(--gc-color-border)}.mood-period{color:var(--gc-color-text);font-size:10px}.mood-levels{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.mood-level{padding:5px 8px;border-radius:12px;background:var(--gc-color-lilac);color:var(--gc-color-purple);font-size:10px}.consent-required{display:flex;padding-top:9px;border-top:1px solid var(--gc-color-border);flex-direction:column;gap:7px;color:var(--gc-color-muted);font-size:11px;line-height:1.5}.privacy-link,.retry{min-height:44px;align-self:flex-start;padding:0 12px;border:1px solid var(--gc-color-border);border-radius:12px;background:var(--gc-color-surface);color:var(--gc-color-brand-strong);font-size:11px}.refresh-error{display:flex;margin-bottom:12px;padding:10px;align-items:center;justify-content:space-between;gap:8px;border:1px solid var(--gc-color-danger-border);border-radius:12px;background:var(--gc-color-danger-pale);color:var(--gc-color-danger);font-size:11px}.request-id{display:block;color:var(--gc-color-muted);font-size:10px}.all-empty{display:block;margin:8px 2px;color:var(--gc-color-muted);font-size:11px}.auth-pending{display:grid;min-height:100vh;place-items:center;color:var(--gc-color-muted)}
</style>

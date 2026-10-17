<template>
  <TabRoot active="today" :authorized="authorized" test-id="today-tab">
    <view class="header">
      <view class="header-copy">
        <text class="eyebrow">GUTCARE · {{ dateLabel }}</text>
        <text class="title">今日</text>
      </view>
      <button class="profile-trigger" aria-label="打开我的页面" data-testid="today-profile" @click="router?.switchTab('me')">
        <GcAvatar size="header" />
      </button>
    </view>

    <view class="welcome-card">
      <view class="welcome-copy">
        <text class="welcome-title">你好，{{ auth.profile?.nickname || 'GutCare 用户' }}</text>
        <text class="welcome-subtitle">照顾肠胃健康，从记录日常开始。</text>
      </view>
      <view class="hero-mark" aria-hidden="true"><text>+</text></view>
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">风险提示</text><button class="text-link" data-testid="today-risk-link" @click="router?.navigate('riskAlerts')">查看全部</button></view>
    <view class="panel risk-panel" data-testid="today-risk-alerts">
      <DashboardDataStatus v-if="riskState !== 'ready' || riskAlerts.length === 0" :state="riskState === 'ready' ? 'empty' : riskState" :message="riskMessage" :retryable="riskState === 'error'" :busy="riskLoading" test-id="today-risk-status" @retry="loadTodayRisk" />
      <view v-else class="risk-items">
        <button v-for="item in riskAlerts" :key="item.id" class="risk-item" :class="`risk-item--${item.severity}`" :data-testid="`today-risk-${item.id}`" @click="router?.navigateRiskAlertDetail(item.id)">
          <text class="risk-symbol" aria-hidden="true">{{ riskIcon(item.severity) }}</text>
          <view class="risk-copy"><text class="risk-severity">{{ riskLabel(item.severity) }} · {{ item.status === 'unread' ? '未查看' : '已查看' }}</text><text class="risk-message">{{ item.message }}</text><text class="risk-action">{{ item.recommended_action }}</text></view>
        </button>
      </view>
      <text class="risk-disclaimer">已查看或已重新评估不表示风险解除或确认安全。</text>
    </view>

    <view class="section-heading"><text class="section-title">今日概览</text><text class="section-caption">仅显示已连接的本人数据</text></view>
    <view class="panel summary-panel" data-testid="today-summary">
      <view class="panel-top"><text class="panel-title">今日健康摘要</text><text class="panel-kicker">TODAY</text></view>
      <DashboardDataStatus state="unavailable" test-id="summary-status" />
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
      <view class="panel-content"><text class="panel-title">按本人计划记录</text><DashboardDataStatus v-if="medicationState !== 'ready' || medicationCheckins.length === 0" :state="medicationState === 'ready' ? 'empty' : medicationState" :message="medicationMessage" :retryable="medicationState === 'error'" :busy="medicationLoading" test-id="medication-status" @retry="loadTodayMedication" /><view v-else class="medication-summary" data-testid="today-medication-summary"><text>{{ medicationCheckins.length }} 项今日打卡安排</text><text class="medication-detail">{{ medicationStatusSummary }}</text></view></view>
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">饮食记录</text><button class="text-link" data-testid="today-diet-link" @click="router?.navigate('recordDiet')">查看记录</button></view>
    <view class="panel data-panel" data-testid="today-diet">
      <view class="panel-top"><text class="panel-title">日常饮食</text><text class="panel-kicker">DIET</text></view>
      <DashboardDataStatus state="unavailable" test-id="diet-status" />
    </view>

    <view class="section-heading section-heading--tight"><text class="section-title">健康趋势</text><button class="text-link" data-testid="today-trends-link" @click="router?.navigate('trends')">查看趋势</button></view>
    <view class="panel data-panel" data-testid="today-trends">
      <view class="panel-top"><text class="panel-title">记录变化</text><text class="panel-kicker">TRENDS</text></view>
      <DashboardDataStatus state="unavailable" test-id="trend-status" />
    </view>
  </TabRoot>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { appRouterKey, medicationApiKey, riskApiKey } from '../../../api/context'
import type { AppRouteName } from '../../../navigation/routes'
import { canRenderRoute } from '../../../navigation/routes'
import { useAuthStore } from '../../../stores/auth'
import DashboardDataStatus from '../../../components/DashboardDataStatus.vue'
import GcAvatar from '../../../components/GcAvatar.vue'
import TabRoot from '../../../components/TabRoot.vue'
import type { MedicationCheckin } from '../../../api/openapiTypes'
import type { RiskAlert } from '../../../api/openapiTypes'

const auth = useAuthStore()
const router = inject(appRouterKey)
const medicationApi = inject(medicationApiKey)
const riskApi = inject(riskApiKey)
const authorized = computed(() => canRenderRoute('today', auth.state))
const medicationState = ref<'loading' | 'empty' | 'error' | 'unavailable' | 'ready'>(medicationApi ? 'loading' : 'unavailable')
const medicationLoading = ref(false)
const medicationMessage = ref('')
const medicationCheckins = ref<MedicationCheckin[]>([])
const medicationStatusSummary = computed(() => {
  const counts = { taken: 0, not_taken: 0, pending: 0, skipped: 0 }
  for (const checkin of medicationCheckins.value) counts[checkin.status] += 1
  return `已记录 ${counts.taken} · 待确认 ${counts.pending} · 本人记录未服用 ${counts.not_taken} · 已跳过 ${counts.skipped}`
})
const riskState = ref<'loading' | 'empty' | 'error' | 'unavailable' | 'ready'>(riskApi ? 'loading' : 'unavailable')
const riskLoading = ref(false)
const riskMessage = ref('')
const riskAlerts = ref<RiskAlert[]>([])
const dateLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date())
const quickActions: ReadonlyArray<{ route: AppRouteName; label: string; icon: string; tint: string }> = [
  { route: 'recordDiet', label: '饮食', icon: '餐', tint: 'peach' },
  { route: 'recordBowel', label: '排便', icon: '记', tint: 'sage' },
  { route: 'recordSymptoms', label: '症状', icon: '＋', tint: 'lilac' },
  { route: 'recordMood', label: '心情', icon: '♡', tint: 'yellow' },
  { route: 'recordActivity', label: '运动', icon: '↗', tint: 'sage' },
]

onShow(() => { if (!authorized.value) router?.requireAuthentication('today'); else { void loadTodayMedication(); void loadTodayRisk() } })

async function loadTodayMedication() {
  if (!medicationApi || !authorized.value || medicationLoading.value) return
  medicationLoading.value = true; medicationState.value = 'loading'; medicationMessage.value = ''
  try { medicationCheckins.value = await medicationApi.listTodayCheckins(); medicationState.value = medicationCheckins.value.length ? 'ready' : 'empty' }
  catch { medicationState.value = 'error'; medicationMessage.value = '暂时无法载入今日打卡安排；没有把失败显示为已完成或无计划。' }
  finally { medicationLoading.value = false }
}
async function loadTodayRisk() {
  if (!riskApi || !authorized.value || riskLoading.value) return
  riskLoading.value = true; riskState.value = 'loading'; riskMessage.value = ''
  try { riskAlerts.value = (await riskApi.list({ limit: 20, unread_only: true })).items; riskState.value = riskAlerts.value.length ? 'ready' : 'empty' }
  catch { riskState.value = 'error'; riskMessage.value = '暂时无法载入风险提示；加载失败不代表没有风险。' }
  finally { riskLoading.value = false }
}
function riskLabel(severity: RiskAlert['severity']) { return severity === 'emergency' ? '紧急提示' : severity === 'seek_care' ? '尽快就医提示' : '关注提示' }
function riskIcon(severity: RiskAlert['severity']) { return severity === 'emergency' ? '!' : severity === 'seek_care' ? '△' : 'i' }
</script>

<style lang="scss" scoped>
.header { display: flex; align-items: center; justify-content: space-between; margin: 2px 2px 20px; }
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
@media (max-width: 360px) { .tab-content { padding-right: 14px; padding-left: 14px; }.quick-grid { gap: 4px; }.quick-label { font-size: 10px; } }
</style>

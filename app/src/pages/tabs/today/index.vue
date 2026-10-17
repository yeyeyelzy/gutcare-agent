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
      <view class="panel-content"><text class="panel-title">按个人计划管理</text><DashboardDataStatus state="unavailable" test-id="medication-status" /></view>
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
import { computed, inject } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { appRouterKey } from '../../../api/context'
import type { AppRouteName } from '../../../navigation/routes'
import { canRenderRoute } from '../../../navigation/routes'
import { useAuthStore } from '../../../stores/auth'
import DashboardDataStatus from '../../../components/DashboardDataStatus.vue'
import GcAvatar from '../../../components/GcAvatar.vue'
import TabRoot from '../../../components/TabRoot.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const authorized = computed(() => canRenderRoute('today', auth.state))
const dateLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date())
const quickActions: ReadonlyArray<{ route: AppRouteName; label: string; icon: string; tint: string }> = [
  { route: 'recordDiet', label: '饮食', icon: '餐', tint: 'peach' },
  { route: 'recordBowel', label: '排便', icon: '记', tint: 'sage' },
  { route: 'recordSymptoms', label: '症状', icon: '＋', tint: 'lilac' },
  { route: 'recordMood', label: '心情', icon: '♡', tint: 'yellow' },
  { route: 'recordActivity', label: '运动', icon: '↗', tint: 'sage' },
]

onShow(() => { if (!authorized.value) router?.requireAuthentication('today') })
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
@media (max-width: 360px) { .tab-content { padding-right: 14px; padding-left: 14px; }.quick-grid { gap: 4px; }.quick-label { font-size: 10px; } }
</style>

<template>
  <TabRoot active="analysis" :authorized="authorized" test-id="analysis-tab">
    <view class="page-header">
      <text class="eyebrow">YOUR HEALTH, IN CONTEXT</text>
      <text class="title">分析</text>
      <text class="subtitle">查看由业务服务管理的分析任务、历史报告与建议。</text>
    </view>

    <button class="start-card" data-testid="analysis-start" @click="router?.navigate('analysisNew')">
      <view class="start-icon" aria-hidden="true">✦</view>
      <view class="start-copy"><text class="start-title">发起综合分析</text><text class="start-subtitle">先检查可用资料与授权，再创建分析任务。</text></view>
      <text class="chevron" aria-hidden="true">›</text>
    </button>

    <view class="section-row"><text class="section-title">分析空间</text></view>
    <view class="entry-list" data-testid="analysis-entry-list">
      <button v-for="item in entries" :key="item.route" class="entry-card" :data-testid="`analysis-${item.route}`" @click="router?.navigate(item.route)">
        <view class="entry-icon" :class="`entry-icon--${item.tint}`" aria-hidden="true"><text>{{ item.icon }}</text></view>
        <view class="entry-copy"><text class="entry-title">{{ item.title }}</text><text class="entry-description">{{ item.description }}</text></view>
        <text class="chevron" aria-hidden="true">›</text>
      </button>
    </view>

    <view class="safety-note" data-testid="analysis-safety-note"><text class="note-mark" aria-hidden="true">i</text><text class="note-copy">分析结果用于整理记录与证据，不替代专业诊疗建议。此版本不会开放自由 AI 聊天。</text></view>
  </TabRoot>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { appRouterKey } from '../../../api/context'
import type { AppRouteName } from '../../../navigation/routes'
import { canRenderRoute } from '../../../navigation/routes'
import { useAuthStore } from '../../../stores/auth'
import TabRoot from '../../../components/TabRoot.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const authorized = computed(() => canRenderRoute('analysis', auth.state))
const entries: ReadonlyArray<{ route: AppRouteName; title: string; description: string; icon: string; tint: string }> = [
  { route: 'analysisHistory', title: '分析历史', description: '查看本人既有分析任务', icon: '◷', tint: 'sage' },
  { route: 'analysisReports', title: '报告与结果', description: '打开已完成任务的报告与依据', icon: '▤', tint: 'peach' },
  { route: 'analysisAdvice', title: '个性化建议', description: '查看建议、适用范围与证据', icon: '✧', tint: 'lilac' },
  { route: 'analysisTrends', title: '健康趋势', description: '浏览本人结构化记录趋势', icon: '⌁', tint: 'yellow' },
]

onShow(() => { if (!authorized.value) router?.requireAuthentication('analysis') })
</script>

<style lang="scss" scoped>
.page-header { margin: 4px 2px 22px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: .9px; }.title { display: block; margin-top: 3px; font-size: 28px; line-height: 1.25; font-weight: var(--gc-font-weight-bold); }.subtitle { display: block; max-width: 320px; margin-top: 6px; color: var(--gc-color-muted); font-size: 13px; line-height: 1.5; }
.start-card { display: flex; min-height: 108px; align-items: center; gap: 13px; padding: 17px; border: 0; border-radius: var(--gc-radius-lg); background: var(--gc-color-brand); color: var(--gc-color-on-brand); text-align: left; box-shadow: var(--gc-shadow-card); }.start-icon { display: grid; width: 46px; height: 46px; flex: 0 0 46px; place-items: center; border: 1px solid rgba(255,255,255,.3); border-radius: 15px; background: rgba(255,255,255,.12); font-size: 23px; }.start-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 4px; }.start-title { font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.start-subtitle { color: rgba(255,255,255,.82); font-size: 11px; line-height: 1.45; }.chevron { color: var(--gc-color-placeholder); font-size: 25px; line-height: 1; }.start-card .chevron { color: rgba(255,255,255,.75); }
.section-row { margin: 23px 2px 10px; }.section-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.entry-list { display: flex; flex-direction: column; gap: 10px; }.entry-card { display: flex; min-height: 78px; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); text-align: left; }.entry-icon { display: grid; width: 44px; height: 44px; flex: 0 0 44px; place-items: center; border-radius: 14px; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 20px; }.entry-icon--peach { background: var(--gc-color-peach); color: var(--gc-color-orange); }.entry-icon--lilac { background: var(--gc-color-lilac); color: var(--gc-color-purple); }.entry-icon--yellow { background: var(--gc-color-yellow); color: var(--gc-color-warning); }.entry-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }.entry-title { color: var(--gc-color-text); font-size: 14px; font-weight: var(--gc-font-weight-semibold); }.entry-description { color: var(--gc-color-muted); font-size: 11px; line-height: 1.45; }
.safety-note { display: flex; margin-top: 16px; padding: 13px; align-items: flex-start; gap: 9px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-md); background: var(--gc-color-surface-soft); }.note-mark { display: grid; width: 20px; height: 20px; flex: 0 0 20px; place-items: center; border-radius: 50%; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 12px; font-weight: var(--gc-font-weight-bold); }.note-copy { color: var(--gc-color-muted); font-size: 11px; line-height: 1.55; }
</style>

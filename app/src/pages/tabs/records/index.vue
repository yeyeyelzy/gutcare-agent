<template>
  <TabRoot active="records" :authorized="authorized" test-id="records-tab">
    <view class="page-header">
      <text class="eyebrow">YOUR JOURNAL</text>
      <text class="title">记录</text>
      <text class="subtitle">用简单记录帮助你回顾日常变化。</text>
    </view>

    <view class="section-row"><text class="section-title">记录分类</text><text class="section-caption">5 类</text></view>
    <view class="category-list" data-testid="record-categories">
      <button v-for="item in categories" :key="item.route" class="category-card" :data-testid="`category-${item.route}`" @click="router?.navigate(item.route)">
        <view class="category-icon" :class="`category-icon--${item.tint}`" aria-hidden="true"><text>{{ item.icon }}</text></view>
        <view class="category-copy"><text class="category-title">{{ item.title }}</text><text class="category-detail">{{ item.detail }}</text></view>
        <text class="chevron" aria-hidden="true">›</text>
      </button>
    </view>

    <view class="section-row section-row--recent"><text class="section-title">最近记录</text><text class="section-caption">本人记录</text></view>
    <view class="recent-panel" data-testid="records-recent">
      <view class="empty-mark" aria-hidden="true">⌁</view>
      <text class="empty-title">记录列表尚未接入</text>
      <text class="empty-copy">服务接入前不会显示示例记录，也不会把未载入误报为“暂无记录”。</text>
    </view>
  </TabRoot>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { appRouterKey } from '../../../api/context'
import type { PlaceholderRouteName, RecordWorkspaceRouteName } from '../../../navigation/routes'
import { canRenderRoute } from '../../../navigation/routes'
import { useAuthStore } from '../../../stores/auth'
import TabRoot from '../../../components/TabRoot.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const authorized = computed(() => canRenderRoute('records', auth.state))
const categories: ReadonlyArray<{ route: PlaceholderRouteName | RecordWorkspaceRouteName; title: string; detail: string; icon: string; tint: string }> = [
  { route: 'recordDiet', title: '饮食', detail: '记录餐食与饮水', icon: '餐', tint: 'peach' },
  { route: 'recordBowel', title: '排便', detail: '记录排便情况', icon: '记', tint: 'sage' },
  { route: 'recordSymptoms', title: '症状', detail: '记录身体感受', icon: '＋', tint: 'lilac' },
  { route: 'recordMood', title: '心情', detail: '记录主观心情状态', icon: '♡', tint: 'yellow' },
  { route: 'recordActivity', title: '运动', detail: '记录日常活动', icon: '↗', tint: 'blue' },
]

onShow(() => { if (!authorized.value) router?.requireAuthentication('records') })
</script>

<style lang="scss" scoped>
.page-header { margin: 4px 2px 22px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.title { display: block; margin-top: 3px; font-size: 28px; line-height: 1.25; font-weight: var(--gc-font-weight-bold); }.subtitle { display: block; margin-top: 6px; color: var(--gc-color-muted); font-size: 13px; }
.section-row { display: flex; align-items: baseline; justify-content: space-between; margin: 0 2px 10px; }.section-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.section-caption { color: var(--gc-color-muted); font-size: 11px; }
.category-list { display: flex; flex-direction: column; gap: 10px; }.category-card { display: flex; min-height: 78px; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); text-align: left; box-shadow: var(--gc-shadow-card); }.category-icon { display: grid; width: 46px; height: 46px; flex: 0 0 46px; place-items: center; border-radius: 15px; background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); font-size: 18px; font-weight: var(--gc-font-weight-semibold); }.category-icon--peach { background: var(--gc-color-peach); }.category-icon--lilac { background: var(--gc-color-lilac); color: var(--gc-color-purple); }.category-icon--yellow { background: var(--gc-color-yellow); }.category-icon--blue { background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); }.category-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }.category-title { color: var(--gc-color-text); font-size: 14px; font-weight: var(--gc-font-weight-semibold); }.category-detail { color: var(--gc-color-muted); font-size: 11px; }.chevron { color: var(--gc-color-placeholder); font-size: 25px; line-height: 1; }
.section-row--recent { margin-top: 24px; }.recent-panel { display: flex; min-height: 188px; padding: 24px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); flex-direction: column; align-items: center; justify-content: center; background: var(--gc-color-surface); text-align: center; }.empty-mark { display: grid; width: 48px; height: 48px; margin-bottom: 11px; place-items: center; border-radius: 50%; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 26px; }.empty-title { color: var(--gc-color-text); font-size: 14px; font-weight: var(--gc-font-weight-semibold); }.empty-copy { max-width: 260px; margin-top: 6px; color: var(--gc-color-muted); font-size: 11px; line-height: 1.55; }
</style>

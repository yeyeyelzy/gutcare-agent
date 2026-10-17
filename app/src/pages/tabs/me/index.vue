<template>
  <TabRoot active="me" :authorized="authorized" test-id="me-tab">
    <view class="page-header">
      <text class="eyebrow">YOUR SPACE</text>
      <text class="title">我的</text>
    </view>

    <button class="profile-card" data-testid="me-profile" @click="router?.navigate('profile')">
      <GcAvatar size="profile" />
      <view class="profile-copy"><text class="profile-name">{{ auth.profile?.nickname || 'GutCare 用户' }}</text><text class="profile-detail">个人资料与账户安全</text><text class="profile-link">管理个人资料　›</text></view>
    </button>

    <view class="section-row"><text class="section-title">健康管理</text></view>
    <view class="entry-list" data-testid="me-entry-list">
      <button v-for="item in entries" :key="item.route" class="entry-card" :data-testid="`me-${item.route}`" @click="router?.navigate(item.route)">
        <view class="entry-icon" :class="`entry-icon--${item.tint}`" aria-hidden="true"><text>{{ item.icon }}</text></view>
        <view class="entry-copy"><text class="entry-title">{{ item.title }}</text><text class="entry-description">{{ item.route === 'notifications' ? `${notificationCount === null ? '未读数暂不可用' : `未读 ${notificationCount} 条`} · ${item.description}` : item.description }}</text></view>
        <text class="chevron" aria-hidden="true">›</text>
      </button>
    </view>

    <view class="account-note"><text class="note-title">仅限本人账户</text><text class="note-copy">个人资料、健康档案与记录由当前登录账户访问；未接入的页面不会显示示例信息。</text></view>
  </TabRoot>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { appRouterKey, notificationApiKey } from '../../../api/context'
import type { AppRouteName } from '../../../navigation/routes'
import { canRenderRoute } from '../../../navigation/routes'
import { useAuthStore } from '../../../stores/auth'
import GcAvatar from '../../../components/GcAvatar.vue'
import TabRoot from '../../../components/TabRoot.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const notificationApi = inject(notificationApiKey)
const notificationCount = ref<number | null>(null)
const authorized = computed(() => canRenderRoute('me', auth.state))
const entries: ReadonlyArray<{ route: AppRouteName; title: string; description: string; icon: string; tint: string }> = [
  { route: 'notifications', title: '站内通知', description: '查看本人通知与普通提醒偏好', icon: '◉', tint: 'yellow' },
  { route: 'healthArchive', title: '健康档案', description: '本人检查资料与已确认信息', icon: '▤', tint: 'peach' },
  { route: 'medications', title: '用药计划', description: '查看已确认的用药安排', icon: '＋', tint: 'sage' },
  { route: 'advice', title: '个性化建议', description: '查看建议与相关依据', icon: '✧', tint: 'lilac' },
  { route: 'trends', title: '健康趋势', description: '查看结构化记录的变化', icon: '⌁', tint: 'yellow' },
  { route: 'settings', title: '设置与隐私', description: '管理账户与隐私选项', icon: '⚙', tint: 'sage' },
]

onShow(() => { if (!authorized.value) router?.requireAuthentication('me'); else void loadNotificationCount() })
async function loadNotificationCount() { if (!notificationApi) return; try { notificationCount.value = (await notificationApi.unreadCount()).count } catch { /* Keep prior server value; never infer zero from failure. */ } }
</script>

<style lang="scss" scoped>
.page-header { margin: 4px 2px 20px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.title { display: block; margin-top: 3px; font-size: 28px; line-height: 1.25; font-weight: var(--gc-font-weight-bold); }
.profile-card { display: flex; width: 100%; min-height: 116px; align-items: center; gap: 15px; padding: 14px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); text-align: left; box-shadow: var(--gc-shadow-card); }.profile-copy { display: flex; min-width: 0; flex-direction: column; gap: 4px; }.profile-name { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.profile-detail { color: var(--gc-color-muted); font-size: 11px; }.profile-link { margin-top: 3px; color: var(--gc-color-brand); font-size: 11px; font-weight: var(--gc-font-weight-semibold); }
.section-row { margin: 23px 2px 10px; }.section-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.entry-list { display: flex; flex-direction: column; gap: 9px; }.entry-card { display: flex; min-height: 72px; align-items: center; gap: 12px; padding: 10px 13px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); text-align: left; }.entry-icon { display: grid; width: 42px; height: 42px; flex: 0 0 42px; place-items: center; border-radius: 14px; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 18px; }.entry-icon--peach { background: var(--gc-color-peach); color: var(--gc-color-orange); }.entry-icon--lilac { background: var(--gc-color-lilac); color: var(--gc-color-purple); }.entry-icon--yellow { background: var(--gc-color-yellow); color: var(--gc-color-warning); }.entry-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }.entry-title { color: var(--gc-color-text); font-size: 13px; font-weight: var(--gc-font-weight-semibold); }.entry-description { color: var(--gc-color-muted); font-size: 10px; line-height: 1.45; }.chevron { color: var(--gc-color-placeholder); font-size: 24px; line-height: 1; }
.account-note { display: flex; margin-top: 16px; padding: 14px; border-radius: var(--gc-radius-md); flex-direction: column; gap: 4px; background: var(--gc-color-sage-pale); }.note-title { color: var(--gc-color-brand-strong); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }.note-copy { color: var(--gc-color-muted); font-size: 11px; line-height: 1.55; }
</style>

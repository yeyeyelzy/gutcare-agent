<template>
  <view v-if="authorized" class="settings-page" data-testid="settings-hub">
    <view class="shell">
      <view class="topbar"><button class="back" aria-label="返回上一页" data-testid="settings-back" @click="goBack">‹</button><text class="topbar-title">设置</text><view class="spacer" /></view>
      <view class="intro"><text class="eyebrow">GUTCARE</text><text class="title">设置</text><text class="subtitle">管理个人资料、提醒偏好和隐私相关操作。</text></view>
      <view class="section">
        <text class="section-title">账户</text>
        <button class="row" data-testid="settings-profile" @click="openRow('profile')"><view class="row-copy"><text class="row-title">个人资料与账户</text><text class="row-detail">查看和编辑资料；退出登录位于个人资料页</text></view><text class="chevron">›</text></button>
        <button class="row" data-testid="settings-notifications" @click="openRow('notifications')"><view class="row-copy"><text class="row-title">通知偏好</text><text class="row-detail">管理站内提醒和静默时段</text></view><text class="chevron">›</text></button>
      </view>
      <view class="section">
        <text class="section-title">隐私与数据</text>
        <button class="row" data-testid="settings-consents" @click="openRow('consents')"><view class="row-copy"><text class="row-title">隐私与授权</text><text class="row-detail">查看服务端授权状态及当前告知</text></view><text class="chevron">›</text></button>
        <button class="row" data-testid="settings-privacy-center" @click="openRow('privacyCenter')"><view class="row-copy"><text class="row-title">隐私中心</text><text class="row-detail">了解账户数据权利与注销影响</text></view><text class="chevron">›</text></button>
        <button class="row" data-testid="settings-export" @click="openRow('export')"><view class="row-copy"><text class="row-title">个人数据导出</text><text class="row-detail">导出申请可用；原生文件保存能力尚未验收</text></view><text class="chevron">›</text></button>
        <button class="row" data-testid="settings-deletion" @click="openRow('deletion')"><view class="row-copy"><text class="row-title danger">账号注销</text><text class="row-detail">查看影响并确认不可撤销的注销申请</text></view><text class="chevron">›</text></button>
      </view>
      <view class="section about" data-testid="settings-about"><text class="section-title">关于</text><view class="version-row"><text class="row-title">应用版本</text><text class="version" data-testid="settings-version">{{ version }}</text></view></view>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" data-testid="settings-auth-pending">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import manifest from '../../manifest.json'
import { appRouterKey } from '../../api/context'
import { canRenderRoute } from '../../navigation/routes'
import { getSettingsAppVersion, openSettingsRow, returnFromSettings } from '../../navigation/settingsNavigation'
import { useAuthStore } from '../../stores/auth'

const router = inject(appRouterKey)
const auth = useAuthStore()
const authorized = computed(() => canRenderRoute('settings', auth.state))
const version = getSettingsAppVersion(manifest.versionName)
onShow(() => { if (!authorized.value) router?.requireAuthentication('settings') })
function openRow(row: string) { openSettingsRow(router, row) }
function goBack() { returnFromSettings(router, getCurrentPages().length) }
</script>

<style lang="scss" scoped>
.settings-page{min-height:100vh;background:var(--gc-color-canvas)}.shell{width:100%;max-width:430px;min-height:100vh;margin:0 auto;padding:calc(env(safe-area-inset-top,0px) + 10px) 20px calc(env(safe-area-inset-bottom,0px) + 28px)}.topbar{display:flex;min-height:48px;align-items:center;justify-content:space-between}.back{width:44px;height:44px;border:0;border-radius:14px;background:var(--gc-color-surface);color:var(--gc-color-text);font-size:27px}.topbar-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.spacer{width:44px}.intro{display:flex;margin:20px 2px 22px;flex-direction:column;gap:5px}.eyebrow{color:var(--gc-color-brand);font-size:10px;font-weight:var(--gc-font-weight-semibold);letter-spacing:1px}.title{color:var(--gc-color-text);font-size:27px;font-weight:var(--gc-font-weight-bold)}.subtitle,.row-detail{color:var(--gc-color-muted);font-size:11px;line-height:1.5}.section{display:flex;margin-bottom:17px;flex-direction:column;gap:8px}.section-title{margin:0 3px 2px;color:var(--gc-color-muted);font-size:11px;font-weight:var(--gc-font-weight-semibold)}.row,.version-row{display:flex;width:100%;min-height:68px;align-items:center;gap:12px;padding:11px 14px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);background:var(--gc-color-surface);text-align:left;box-shadow:var(--gc-shadow-card)}.row-copy{display:flex;min-width:0;flex:1;flex-direction:column;gap:3px}.row-title{color:var(--gc-color-text);font-size:13px;font-weight:var(--gc-font-weight-semibold)}.danger{color:var(--gc-color-danger)}.chevron{color:var(--gc-color-placeholder);font-size:24px}.version-row{justify-content:space-between}.version{color:var(--gc-color-muted);font-size:12px}.auth-pending{display:grid;min-height:100vh;place-items:center;color:var(--gc-color-muted)}
</style>

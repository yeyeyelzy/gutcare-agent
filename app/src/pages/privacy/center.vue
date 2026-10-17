<template>
  <view v-if="authorized" class="privacy-page" data-testid="privacy-center">
    <view class="topbar"><button class="back" aria-label="返回我的页面" data-testid="privacy-back" @click="router?.switchTab('me')">‹</button><text class="topbar-title">设置与隐私</text><view class="spacer" /></view>
    <view class="intro"><text class="eyebrow">PRIVACY & CONTROL</text><text class="title">隐私中心</text><text class="subtitle">查看并管理账户数据权利。注销账号与退出登录不同，注销请求不可撤销。</text></view>
    <view class="info-card"><text class="card-title">账号注销会发生什么</text><text class="copy">提交后账户立即冻结、全部登录会话和授权撤销，并取消未完成任务。后台清理通常在 30 天内完成；备份按最长 35 天轮转清理。受理不代表数据已物理删除。</text><text class="copy">进度可用一次性凭证在退出登录后查询。凭证只在首次成功响应显示一次，请勿截图、转发或粘贴到其他应用。</text></view>
    <view class="action-card export-card"><text class="card-title">个人数据导出</text><text class="copy">选择需要导出的数据类别。导出文件可能包含敏感健康信息；包含心情记录时请特别注意 S4 敏感级别。</text><GcButton label="管理数据导出" variant="secondary" test-id="privacy-export-open" @click="router?.navigate('privacyExports')" /></view>
    <view class="action-card"><text class="card-title">账号注销</text><text class="copy">如果你只是暂时离开，请使用个人资料中的“退出登录”。注销会永久删除账户相关业务数据，且不能取消或恢复。</text><GcButton label="继续了解注销影响" variant="danger" test-id="privacy-deletion-continue" @click="router?.navigate('accountDeletionConfirm')" /></view>
    <view class="footer-note">隐私授权的详细状态仍由各功能对应的服务端告知与设置流程管理。</view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { appRouterKey } from '../../api/context'
import { canRenderRoute } from '../../navigation/routes'
import { useAuthStore } from '../../stores/auth'
import GcButton from '../../components/GcButton.vue'

const router = inject(appRouterKey)
const auth = useAuthStore()
const authorized = computed(() => canRenderRoute('privacyCenter', auth.state))
onShow(() => { if (!authorized.value) router?.requireAuthentication('privacyCenter') })
</script>

<style lang="scss" scoped>
.privacy-page { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 28px); background: var(--gc-color-canvas); }
.topbar { display: flex; min-height: 48px; align-items: center; justify-content: space-between; margin-bottom: 18px; }.back { width: 44px; height: 44px; border-radius: 14px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 27px; }.topbar-title { color: var(--gc-color-text); font-weight: var(--gc-font-weight-semibold); }.spacer { width: 44px; }
.intro { display: flex; margin: 0 2px 20px; flex-direction: column; gap: 6px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.title { color: var(--gc-color-text); font-size: 27px; font-weight: var(--gc-font-weight-bold); }.subtitle,.copy { color: var(--gc-color-muted); font-size: 12px; line-height: 1.65; }
.info-card,.action-card { display: flex; margin-bottom: 14px; padding: 17px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); flex-direction: column; gap: 11px; box-shadow: var(--gc-shadow-card); }.action-card { border-color: var(--gc-color-danger-border); }.card-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.footer-note { padding: 8px 4px; color: var(--gc-color-muted); font-size: 11px; line-height: 1.5; }.auth-pending { padding: 40px; color: var(--gc-color-muted); text-align: center; }
</style>

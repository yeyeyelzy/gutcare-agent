<template>
  <view v-if="authorized" class="page" data-testid="deletion-confirm">
    <view class="topbar"><button class="back" aria-label="返回隐私中心" data-testid="deletion-confirm-back" @click="router?.navigateBack()">‹</button><text class="topbar-title">确认账号注销</text><view class="spacer" /></view>
    <view class="warning"><text class="title">此操作不可撤销</text><text class="copy">提交后账号会被冻结，登录会话和授权被撤销，后台按既定流程清理数据。注销请求已受理不代表物理删除完成，也不能取消。</text></view>
    <view class="card"><text class="copy">请确认这是你的决定。若只是暂时离开，请返回并选择退出登录。</text><button class="confirm-check" :aria-pressed="confirmed" data-testid="deletion-confirm-check" @click="confirmed = !confirmed"><text class="check">{{ confirmed ? '✓' : '○' }}</text><text>我理解注销不可取消，并确认提交注销请求</text></button></view>
    <view v-if="error" class="error" role="alert" aria-live="assertive" data-testid="deletion-confirm-error">{{ errorText }}</view>
    <GcButton label="提交注销请求" variant="danger" :busy="busy" :disabled="!confirmed || busy" test-id="deletion-confirm-submit" @click="submit" />
  </view>
  <view v-else class="pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { AppError } from '../../api/errors'
import { appRouterKey, privacyDeletionServiceKey } from '../../api/context'
import { canRenderRoute } from '../../navigation/routes'
import { useAuthStore } from '../../stores/auth'
import GcButton from '../../components/GcButton.vue'

const router = inject(appRouterKey)
const deletion = inject(privacyDeletionServiceKey)
const auth = useAuthStore()
const authorized = computed(() => canRenderRoute('accountDeletionConfirm', auth.state))
const confirmed = ref(false)
const busy = ref(false)
const error = ref<unknown>(null)
const errorText = computed(() => {
  if (error.value instanceof AppError && error.value.kind === 'offline') return '当前处于离线状态，尚未提交注销请求。请联网后重试。'
  if (error.value instanceof AppError && error.value.status === 429) return '操作过于频繁，请稍后再试。'
  if (error.value instanceof AppError && error.value.requestId) return `注销请求未能完成。请稍后重试；如问题持续，请联系支持并提供编号 ${error.value.requestId}。`
  return '注销请求未能完成。请检查网络后重试；当前尚未确认已受理。'
})
onShow(() => { if (!authorized.value) router?.requireAuthentication('accountDeletionConfirm') })

async function submit() {
  if (!deletion || !confirmed.value || busy.value) return
  busy.value = true
  error.value = null
  try { await deletion.requestAccountDeletion() }
  catch (cause) { error.value = cause }
  finally { busy.value = false }
}
</script>

<style lang="scss" scoped>
.page { box-sizing: border-box; width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); background: var(--gc-color-canvas); }
.topbar { display: flex; min-height: 48px; align-items: center; justify-content: space-between; margin-bottom: 22px; }.back { width: 44px; height: 44px; border-radius: 14px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 27px; }.topbar-title { color: var(--gc-color-text); font-weight: var(--gc-font-weight-semibold); }.spacer { width: 44px; }
.warning,.card { display: flex; margin-bottom: 16px; padding: 18px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); flex-direction: column; gap: 12px; }.warning { border-color: var(--gc-color-danger-border); background: var(--gc-color-danger-pale); }.title { color: var(--gc-color-danger); font-size: 21px; font-weight: var(--gc-font-weight-bold); }.copy { color: var(--gc-color-muted); font-size: 13px; line-height: 1.65; }.confirm-check { display: flex; min-height: 52px; align-items: center; padding: 8px 0; background: transparent; color: var(--gc-color-text); text-align: left; font-size: 13px; line-height: 1.5; }.check { margin-right: 10px; color: var(--gc-color-brand); font-size: 20px; }.error { margin: 12px 0; padding: 13px; border: 1px solid var(--gc-color-danger-border); border-radius: var(--gc-radius-md); background: var(--gc-color-danger-pale); color: var(--gc-color-danger); font-size: 12px; line-height: 1.55; }.pending { padding: 40px; color: var(--gc-color-muted); text-align: center; }
</style>

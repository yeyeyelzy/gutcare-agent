<template>
  <view v-if="authorized" class="page" data-testid="privacy-export-workspace">
    <view class="topbar"><button class="back" aria-label="返回隐私中心" data-testid="export-back" @click="router?.redirect('privacyCenter')">‹</button><text class="heading">个人数据导出</text><view class="spacer" /></view>
    <view class="intro"><text class="eyebrow">DATA PORTABILITY</text><text class="title">导出你的数据</text><text class="copy">选择类别后先预览，再明确确认开始处理。导出文件包含个人敏感信息，请妥善保管。</text></view>

    <view class="card">
      <text class="section-title">选择数据类别</text>
      <view class="category-grid">
        <button v-for="item in categories" :key="item.value" class="category" :class="{ selected: selected.has(item.value) }" :aria-pressed="selected.has(item.value)" :data-testid="`export-category-${item.value}`" @click="toggle(item.value)">{{ item.label }}<text v-if="selected.has(item.value)"> ✓</text></button>
      </view>
      <text v-if="selected.has('mood')" class="sensitive-note" role="note" data-testid="export-mood-warning">心情数据属于 S4 敏感信息；导出包可能包含本人填写的备注。请仅在安全设备保存。</text>
      <text v-if="createError" class="error" role="alert" data-testid="export-create-error">{{ createError }}</text>
      <GcButton :label="busy === 'preview' ? '正在生成预览…' : '生成导出预览'" :disabled="busy !== null || selected.size === 0" test-id="export-create-preview" @click="createPreview" />
    </view>

    <view v-if="preview" class="card preview" data-testid="export-preview">
      <text class="section-title">确认导出范围</text>
      <text class="copy">本次将包含：{{ labels(preview.categories) }}</text>
      <text class="copy">提交确认后，系统会将请求加入后台处理队列。创建预览不会启动导出。</text>
      <text v-if="actionError" class="error" role="alert" data-testid="export-action-error">{{ actionError }}</text>
      <view class="actions"><GcButton label="确认并开始处理" :disabled="busy !== null" test-id="export-confirm" @click="confirmPreview" /><GcButton label="取消预览" variant="secondary" :disabled="busy !== null" test-id="export-discard-preview" @click="discardPreview" /></view>
    </view>

    <view class="history-head"><text class="section-title">导出历史</text><button class="text-button" :disabled="busy !== null" data-testid="export-refresh" @click="refreshFromUi">刷新</button></view>
     <view v-if="loadError" class="error-box" role="alert" data-testid="export-list-error">{{ loadError }}<button class="text-button" data-testid="export-list-retry" @click="refreshFromUi">重试</button></view>
    <view v-if="loading && exports.length === 0" class="state" role="status" data-testid="export-loading">正在加载导出记录…</view>
    <view v-else-if="!loading && !loadError && exports.length === 0" class="state" data-testid="export-empty">还没有导出记录</view>
    <button v-for="item in exports" :key="item.export_id" class="history-item" :data-testid="`export-history-${item.export_id}`" @click="openDetail(item.export_id)">
      <view class="history-copy"><text class="history-status">{{ statusLabel(item.status) }}</text><text class="copy">{{ labels(item.categories) }}</text></view><text class="chevron">›</text>
    </button>

    <view v-if="detail" class="card detail" data-testid="export-detail">
      <view class="detail-head"><text class="section-title">导出详情</text><button class="text-button" :disabled="busy !== null" data-testid="export-detail-refresh" @click="openDetail(detail.export_id)">刷新详情</button></view>
      <text class="status-line">{{ statusLabel(detail.status) }}</text><text class="copy">数据类别：{{ labels(detail.categories) }}</text>
      <text v-if="detail.status === 'ready'" class="copy">文件可用时效受限。当前版本暂不支持将 ZIP 保存或分享至应用外；下载入口保持关闭，不会消费下载能力。</text>
      <text v-if="detailError" class="error" role="alert" data-testid="export-detail-error">{{ detailError }}</text>
      <view v-if="canConfirmPrivacyExport(detail.status)" class="actions"><GcButton label="确认并开始处理" :disabled="busy !== null" test-id="export-detail-confirm" @click="confirmDetail" /><GcButton label="取消预览" variant="secondary" :disabled="busy !== null" test-id="export-cancel" @click="cancelDetail" /></view>
      <GcButton v-else-if="canCancel(detail.status)" label="取消导出" variant="secondary" :disabled="busy !== null" test-id="export-cancel" @click="cancelDetail" />
    </view>
    <view v-if="detailLoading" class="state" role="status" data-testid="export-detail-loading">正在刷新导出详情…</view>
    <view class="footnote">导出失败、网络不可用与没有历史记录会分别显示，不会互相替代。服务端状态是导出处理进度，不表示文件已经保存到本机。</view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import GcButton from './GcButton.vue'
import { appRouterKey, privacyExportApiKey, privacyExportDownloadKey } from '../api/context'
import type { PrivacyExportCategory, PrivacyExportDetail, PrivacyExportStatus, PrivacyExportSummary } from '../api/openapiTypes'
import { canCancelPrivacyExport, canConfirmPrivacyExport } from '../api/privacyExportApi'
import { canRenderRoute } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'

const router = inject(appRouterKey)
const api = inject(privacyExportApiKey)
const downloadAdapter = inject(privacyExportDownloadKey)
const auth = useAuthStore()
const authorized = computed(() => canRenderRoute('privacyExports', auth.state))
const categories: { value: PrivacyExportCategory; label: string }[] = [
  { value: 'profile', label: '个人资料' }, { value: 'consents', label: '授权记录' },
  { value: 'medical_documents', label: '医疗文档' }, { value: 'files', label: '文件' },
  { value: 'diet', label: '饮食记录' }, { value: 'stool', label: '排便记录' },
  { value: 'symptoms', label: '症状记录' }, { value: 'mood', label: '心情记录（S4）' },
  { value: 'medication', label: '用药记录' }, { value: 'activity', label: '活动记录' },
  { value: 'analysis', label: '分析任务' }, { value: 'advice', label: '建议' },
  { value: 'alerts', label: '风险提示' }, { value: 'notifications', label: '站内通知' },
]
const selected = ref(new Set<PrivacyExportCategory>())
const preview = ref<null | { export_id: string; status: 'preview'; categories: PrivacyExportCategory[] }>(null)
const exports = ref<PrivacyExportSummary[]>([])
const detail = ref<PrivacyExportDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const busy = ref<null | 'preview' | 'confirm' | 'cancel'>(null)
const loadError = ref('')
const createError = ref('')
const actionError = ref('')
const detailError = ref('')
let hasShown = false
let visible = false
let generation = 0
let detailGeneration = 0

function toggle(category: PrivacyExportCategory) {
  const next = new Set(selected.value)
  if (next.has(category)) next.delete(category)
  else next.add(category)
  selected.value = next
}
function labels(values: PrivacyExportCategory[]) { return values.map((value) => categories.find((item) => item.value === value)?.label ?? '未知类别').join('、') }
function statusLabel(status: PrivacyExportStatus) {
  return ({ preview: '待确认预览', pending: '排队中', processing: '处理中', ready: '已就绪', failed: '处理失败', cancelled: '已取消', expired: '已过期' } as const)[status]
}
function canCancel(status: PrivacyExportStatus) { return canCancelPrivacyExport(status) }
function message(error: unknown) { return error instanceof Error ? error.message : '服务暂不可用，请稍后重试。' }

async function refresh(current = generation) {
  if (!authorized.value || !api || !visible) { if (!authorized.value) router?.requireAuthentication('privacyExports'); return }
  if (!isCurrentPage(current)) return
  loading.value = true
  loadError.value = ''
  try {
    const result = await api.list()
    if (isCurrentPage(current)) exports.value = result
  } catch (error) {
    if (isCurrentPage(current)) loadError.value = message(error)
  } finally {
    if (isCurrentPage(current)) loading.value = false
  }
}
function refreshFromUi() { void refresh(generation) }
async function createPreview() {
  if (!api || busy.value || selected.value.size === 0) return
  const current = generation
  busy.value = 'preview'; createError.value = ''
  try {
    const result = await api.createPreview([...selected.value])
    if (visible && current === generation) preview.value = result
  } catch (error) { if (visible && current === generation) createError.value = message(error) }
  finally { if (visible && current === generation) busy.value = null }
}
async function confirmPreview() {
  if (!preview.value || busy.value || !api) return
  const current = generation
  if (!isCurrentPage(current)) return
  const id = preview.value.export_id
  busy.value = 'confirm'; actionError.value = ''
  try {
    await api.confirm(id)
    if (!isCurrentPage(current)) return
    preview.value = null
    await openDetail(id, current)
    if (!isCurrentPage(current)) return
    await refresh(current)
  } catch (error) { if (isCurrentPage(current)) actionError.value = message(error) }
  finally { if (isCurrentPage(current)) busy.value = null }
}
async function discardPreview() {
  if (!preview.value || !api || busy.value) return
  const current = generation
  if (!isCurrentPage(current)) return
  const id = preview.value.export_id
  busy.value = 'cancel'; actionError.value = ''
  try {
    await api.cancel(id)
    if (!isCurrentPage(current)) return
    preview.value = null
    await refresh(current)
  } catch (error) { if (isCurrentPage(current)) actionError.value = message(error) }
  finally { if (isCurrentPage(current)) busy.value = null }
}
async function confirmDetail() {
  if (!detail.value || !isCurrentPage(generation)) return
  preview.value = { export_id: detail.value.export_id, status: 'preview', categories: [...detail.value.categories] }
  await confirmPreview()
}
async function cancelDetail() {
  if (!detail.value || !api || busy.value) return
  const current = generation
  if (!isCurrentPage(current)) return
  const id = detail.value.export_id
  busy.value = 'cancel'; detailError.value = ''
  try {
    await api.cancel(id)
    if (!isCurrentPage(current)) return
    await openDetail(id, current)
    if (!isCurrentPage(current)) return
    await refresh(current)
  } catch (error) { if (isCurrentPage(current)) detailError.value = message(error) }
  finally { if (isCurrentPage(current)) busy.value = null }
}
function isCurrentPage(current: number) { return visible && current === generation }
function clearDetail() {
  if (detail.value) detail.value.download_capability = null
  detail.value = null
}
function replaceDetail(value: PrivacyExportDetail) {
  if (detail.value && detail.value !== value) detail.value.download_capability = null
  detail.value = value
}
async function openDetail(id: string, current = generation) {
  if (!api || !isCurrentPage(current)) return
  const request = ++detailGeneration
  if (detail.value) detail.value.download_capability = null
  detailLoading.value = true
  detailError.value = ''
  try {
    const result = await api.get(id)
    if (isCurrentPage(current) && request === detailGeneration) replaceDetail(result)
    else result.download_capability = null
  } catch (error) { if (isCurrentPage(current) && request === detailGeneration) detailError.value = message(error) }
  finally { if (isCurrentPage(current) && request === detailGeneration) detailLoading.value = false }
}
function clearTransientState() {
  visible = false
  generation++
  detailGeneration++
  clearDetail()
  detailLoading.value = false
  preview.value = null
  busy.value = null
  downloadAdapter?.clearPageState()
}
onShow(() => {
  if (!authorized.value) { router?.requireAuthentication('privacyExports'); return }
  visible = true
  generation++
  // Only onShow owns the initial request; subsequent shows refresh after returning from another page.
  if (hasShown) void refresh()
  else { hasShown = true; void refresh() }
})
onHide(clearTransientState)
onUnload(clearTransientState)
</script>

<style lang="scss" scoped>
.page { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 28px); background: var(--gc-color-canvas); }
.topbar { display: flex; min-height: 48px; align-items: center; justify-content: space-between; margin-bottom: 18px; }.back { width: 44px; height: 44px; border-radius: 14px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 27px; }.heading { color: var(--gc-color-text); font-weight: var(--gc-font-weight-semibold); }.spacer { width: 44px; }
.intro { display: flex; margin: 0 2px 20px; flex-direction: column; gap: 6px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.title { color: var(--gc-color-text); font-size: 27px; font-weight: var(--gc-font-weight-bold); }.copy { color: var(--gc-color-muted); font-size: 12px; line-height: 1.65; }
.card { display: flex; margin-bottom: 14px; padding: 17px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); flex-direction: column; gap: 12px; box-shadow: var(--gc-shadow-card); }.section-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.category-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }.category { min-height: 44px; padding: 8px; border: 1px solid var(--gc-color-border); border-radius: 12px; background: var(--gc-color-canvas); color: var(--gc-color-text); font-size: 12px; text-align: left; }.category.selected { border-color: var(--gc-color-brand); background: var(--gc-color-brand-soft); }.sensitive-note { padding: 10px; border-radius: 10px; background: var(--gc-color-warning-soft); color: var(--gc-color-text); font-size: 12px; line-height: 1.55; }
.history-head,.detail-head { display: flex; align-items: center; justify-content: space-between; margin: 12px 2px; }.text-button { padding: 8px; color: var(--gc-color-brand); background: transparent; font-size: 12px; }.history-item { display: flex; width: 100%; min-height: 64px; margin-bottom: 8px; padding: 12px 14px; align-items: center; justify-content: space-between; border: 1px solid var(--gc-color-border); border-radius: 14px; background: var(--gc-color-surface); text-align: left; }.history-copy { display: flex; flex-direction: column; gap: 4px; }.history-status,.status-line { color: var(--gc-color-text); font-size: 13px; font-weight: var(--gc-font-weight-semibold); }.chevron { color: var(--gc-color-muted); font-size: 22px; }.state,.error-box { display: flex; margin-bottom: 10px; padding: 18px; border-radius: 12px; background: var(--gc-color-surface); color: var(--gc-color-muted); font-size: 13px; flex-direction: column; gap: 8px; }.error { color: var(--gc-color-danger); font-size: 12px; line-height: 1.5; }.actions { display: flex; gap: 8px; flex-wrap: wrap; }.footnote { padding: 10px 3px; color: var(--gc-color-muted); font-size: 11px; line-height: 1.55; }.auth-pending { padding: 40px; color: var(--gc-color-muted); text-align: center; }
</style>

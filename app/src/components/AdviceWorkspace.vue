<template>
  <view v-if="pageReady" class="advice-page" data-testid="advice-workspace">
    <view class="shell">
      <view class="topbar"><button class="back" aria-label="返回" data-testid="advice-back" @click="goBack">‹</button><text class="topbar-title">{{ isDetail ? '建议详情' : '个性化建议' }}</text><view class="spacer" /></view>
      <view class="intro"><text class="eyebrow">PATIENT ADVICE</text><text class="title">{{ isDetail ? '本人建议' : '个性化建议' }}</text><text class="subtitle">内容用于记录回顾，不构成诊断、处方、剂量调整或因果结论。</text></view>

      <template v-if="isDetail">
        <DashboardDataStatus v-if="loadState === 'loading'" state="loading" test-id="advice-detail-loading" />
        <view v-else-if="loadState === 'error'" class="status-card"><DashboardDataStatus state="error" :message="loadMessage" retryable :busy="busy" test-id="advice-detail-error" @retry="retryDetail" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text><button class="secondary" data-testid="advice-detail-back" @click="goBack">返回</button></view>
        <view v-else-if="detail" class="advice-card" data-testid="advice-detail">
          <view v-if="detail.risk_priority_context" class="risk-context" data-testid="advice-risk-priority"><text class="risk-mark" aria-hidden="true">!</text><view class="risk-copy"><text class="risk-title">{{ riskPriorityLabel(detail.risk_priority_context) }}</text><text class="muted">{{ riskPriorityStatusLabel(detail.risk_priority_context) }} · {{ formatDate(detail.risk_priority_context.triggered_at) }}</text><text class="muted">风险提示优先于本建议；状态不代表风险已解除或确认安全。</text></view><button class="text-action" data-testid="advice-open-risk" @click="openRisk(detail.risk_priority_context.alert_id)">查看风险提示</button></view>
          <view class="card-heading"><text class="category">{{ categoryLabel(detail.category) }}</text><text class="status">{{ adviceStatusLabel(detail.status) }}</text></view>
          <text class="advice-title">{{ detail.title }}</text><text class="advice-body">{{ detail.body }}</text>
          <view v-if="detail.basis_updated" class="basis-notice" role="status" data-testid="advice-basis-updated">相关依据已变化，请结合最新记录重新查看；此提示与建议已读/归档状态相互独立。</view>
          <view v-if="detailRefreshError" class="inline-error" role="alert" data-testid="advice-detail-refresh-error"><text>{{ detailRefreshError }}</text><button class="text-action" :disabled="busy" data-testid="advice-detail-refresh-retry" @click="retryDetail">重试刷新</button><text v-if="detailRequestId" class="request-id">请求编号：{{ detailRequestId }}</text></view>
          <view class="metadata"><text>适用范围：{{ detail.applicability.scope === 'general' ? '一般记录回顾' : '特定条件范围' }}</text><text>不确定性：{{ detail.uncertainty.level === 'low' ? '较低' : detail.uncertainty.level === 'moderate' ? '中等' : '较高' }}</text><text v-for="(reason, index) in detail.uncertainty.reasons" :key="`reason-${index}`">{{ reason }}</text><text v-for="(limitation, index) in detail.applicability.limitations" :key="`limitation-${index}`">适用限制：{{ limitation }}</text></view>
          <view v-if="detail.evidence.length" class="evidence-section"><text class="section-title">关联依据</text><view v-for="(item, index) in detail.evidence" :key="`evidence-${index}`" class="evidence-row" :data-testid="`advice-evidence-${index}`">
            <template v-if="item.evidence_type === 'patient'"><text v-if="adviceEvidenceLabel(item)" class="evidence-label">{{ adviceEvidenceLabel(item) }} · v{{ item.source_version }}</text><text v-else class="muted">此来源已删除或暂不支持安全跳转。</text><button v-if="adviceEvidenceCanNavigate(item)" class="text-action" :data-testid="`advice-evidence-open-${index}`" @click="openEvidence(item)">查看来源</button></template>
            <template v-else><text class="evidence-label">{{ item.title }} · {{ item.publisher }} · {{ item.knowledge_version }}</text><text v-if="knowledgeCitationHost(item)" class="muted">参考来源域名：{{ knowledgeCitationHost(item) }}（不会自动打开链接）</text><text v-else class="muted">未提供可安全展示的参考链接。</text></template>
          </view></view>
          <view class="actions"><button v-if="detail.status === 'new'" class="secondary" :disabled="busy" data-testid="advice-mark-read" @click="markRead">标记为已读</button><button v-if="detail.status !== 'archived'" class="secondary" :disabled="busy" data-testid="advice-archive" @click="confirmArchive">归档</button></view>
          <view class="feedback" data-testid="advice-feedback"><text class="section-title">对此建议的反馈</text><text class="muted">反馈只记录你对内容呈现的看法，不代表疗效。</text><view class="actions"><button v-for="choice in feedbackChoices" :key="choice.value" class="feedback-choice" :class="{ chosen: detail.feedback?.feedback_type === choice.value }" :disabled="busy" :data-testid="`advice-feedback-${choice.value}`" @click="submitFeedback(choice.value)">{{ choice.label }}</button></view></view>
          <view v-if="actionError" class="inline-error" role="alert" data-testid="advice-action-error"><text>{{ actionError }}</text><button class="text-action" :disabled="busy" data-testid="advice-action-retry" @click="retryDetail">刷新当前状态</button><text v-if="actionRequestId" class="request-id">请求编号：{{ actionRequestId }}</text></view>
          <text class="meta">更新时间：{{ formatDate(detail.created_at) }} · 版本 {{ detail.version }}</text>
        </view>
      </template>

      <template v-else>
        <view v-if="refreshError && items.length" class="refresh-error" role="alert" data-testid="advice-refresh-error"><text>{{ refreshError }}</text><button class="text-action" :disabled="busy" data-testid="advice-refresh-retry" @click="refreshList">重试刷新</button><text v-if="refreshRequestId" class="request-id">请求编号：{{ refreshRequestId }}</text></view>
        <DashboardDataStatus v-if="loadState === 'loading'" state="loading" test-id="advice-list-loading" />
        <view v-else-if="loadState === 'error'" class="status-card"><DashboardDataStatus state="error" :message="loadMessage" retryable :busy="busy" test-id="advice-list-error" @retry="loadList" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view v-else-if="items.length === 0" class="empty" data-testid="advice-empty"><text class="empty-mark" aria-hidden="true">✧</text><text class="advice-title">当前没有可显示的建议</text><text class="subtitle">空列表不代表健康状态判断。</text></view>
        <view v-else class="list" data-testid="advice-list">
          <button v-for="item in items" :key="item.id" class="advice-card advice-item" :data-testid="`advice-${item.id}`" @click="open(item.id)">
            <view v-if="item.risk_priority_context" class="risk-context compact"><text class="risk-mark" aria-hidden="true">!</text><view class="risk-copy"><text class="risk-title">{{ riskPriorityLabel(item.risk_priority_context) }}</text><text class="muted">{{ riskPriorityStatusLabel(item.risk_priority_context) }}</text></view></view>
            <view class="card-heading"><text class="category">{{ categoryLabel(item.category) }}</text><text class="status">{{ adviceStatusLabel(item.status) }}</text></view><text class="advice-title">{{ item.title }}</text><text class="advice-body body-preview">{{ item.body }}</text>
            <text v-if="item.basis_updated" class="basis-inline">相关依据已变化</text><text class="meta">{{ formatDate(item.created_at) }} · 查看详情 ›</text>
          </button>
          <view v-if="moreError" class="more-error" role="alert" data-testid="advice-more-error"><text>{{ moreError }}</text><button class="text-action" :disabled="busy" data-testid="advice-more-retry" @click="loadMore">重试载入</button><text v-if="moreRequestId" class="request-id">请求编号：{{ moreRequestId }}</text></view>
          <button v-else-if="cursor" class="secondary more" :disabled="busy" data-testid="advice-more" @click="loadMore">{{ busy ? '正在载入…' : '载入更多' }}</button>
        </view>
        <text class="privacy-note">建议正文不会写入通知预览、日志或埋点。</text>
      </template>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证本人会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { adviceApiKey, appRouterKey } from '../api/context'
import { AppError } from '../api/errors'
import type { Advice, AdviceEvidence } from '../api/openapiTypes'
import { adviceEvidenceCanNavigate, adviceEvidenceLabel, adviceStatusLabel, knowledgeCitationHost, riskPriorityLabel, riskPriorityStatusLabel } from '../api/adviceView'
import { canRenderRoute, isUuid } from '../navigation/routes'
import type { AppTabName } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import DashboardDataStatus from './DashboardDataStatus.vue'

const props = defineProps<{ mode: 'list' | 'detail'; routeName: 'advice' | 'analysisAdvice' | 'adviceDetail' }>()
const api = inject(adviceApiKey)
const router = inject(appRouterKey)
const auth = useAuthStore()
const isDetail = computed(() => props.mode === 'detail')
const items = ref<Advice[]>([])
const detail = ref<Advice | null>(null)
const cursor = ref<string | null>(null)
const ownerTab = ref<'analysis' | 'me'>(props.routeName === 'analysisAdvice' ? 'analysis' : 'me')
const from = ref<'list' | 'history' | 'external' | 'notification'>('external')
const notificationReturnId = ref<string | null>(null)
const adviceId = ref('')
const pageReady = ref(false)
const visible = ref(false)
const busy = ref(false)
const loadState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
const loadMessage = ref('')
const requestId = ref('')
const actionRequestId = ref('')
const detailRequestId = ref('')
const moreRequestId = ref('')
const refreshRequestId = ref('')
const actionError = ref('')
const detailRefreshError = ref('')
const moreError = ref('')
const refreshError = ref('')
let generation = 0
let firstShow = true
const feedbackChoices = [
  { value: 'helpful', label: '有帮助' }, { value: 'not_helpful', label: '没帮助' }, { value: 'not_applicable', label: '不适用' },
] as const

onLoad((options) => {
  ownerTab.value = options?.owner === 'analysis' ? 'analysis' : props.routeName === 'analysisAdvice' ? 'analysis' : 'me'
  if (options?.from === 'notification') {
    notificationReturnId.value = router?.takeAdviceNotificationReturn() ?? null
    from.value = notificationReturnId.value ? 'notification' : 'external'
  } else {
    from.value = options?.from === 'list' || options?.from === 'history' ? options.from : 'external'
  }
  if (!canRenderRoute(props.routeName, auth.state)) { router?.requireAuthentication(props.routeName); return }
  pageReady.value = true; visible.value = true
  if (isDetail.value) {
    adviceId.value = isUuid(options?.advice_id) ? options.advice_id : ''
    void loadDetail()
  } else void loadList()
})
onShow(() => {
  if (!pageReady.value) return
  visible.value = true
  if (!canRenderRoute(props.routeName, auth.state)) { router?.requireAuthentication(props.routeName); return }
  if (firstShow) { firstShow = false; return }
  if (!isDetail.value) void loadList(true)
  else if (detail.value) void loadDetail(true)
})
onHide(() => { visible.value = false; generation += 1; busy.value = false })
onUnload(() => { visible.value = false; generation += 1 })
onBackPress(() => { goBack(); return true })

async function loadList(preserve = false) {
  if (!api || !visible.value || !canRenderRoute(props.routeName, auth.state) || busy.value) return
  const requestGeneration = ++generation
  const keep = preserve && items.value.length > 0
  busy.value = true; if (!keep) loadState.value = 'loading'; requestId.value = ''; loadMessage.value = ''; moreError.value = ''
  if (keep) { refreshError.value = ''; refreshRequestId.value = '' }
  try {
    const page = await api.list({ limit: 20 })
    if (!isCurrent(requestGeneration)) return
    items.value = page.items; cursor.value = page.next_cursor; loadState.value = page.items.length ? 'ready' : 'empty'
  } catch (error) {
    if (!isCurrent(requestGeneration)) return
    capture(error)
    if (keep) { refreshError.value = '刷新失败，仍保留上次载入的建议；可重试。'; refreshRequestId.value = requestId.value; loadState.value = 'ready' }
    else { loadMessage.value = error instanceof AppError && error.kind === 'offline' ? '当前离线，建议未能载入；请重试。' : '暂时无法载入建议；失败不表示没有建议。'; loadState.value = 'error' }
  } finally { if (isCurrent(requestGeneration)) busy.value = false }
}
async function loadMore() {
  if (!api || !visible.value || !cursor.value || busy.value) return
  const requestGeneration = generation
  const currentCursor = cursor.value
  busy.value = true; moreError.value = ''; moreRequestId.value = ''
  try {
    const page = await api.list({ limit: 20, cursor: currentCursor })
    if (!isCurrent(requestGeneration)) return
    items.value = [...items.value, ...page.items]; cursor.value = page.next_cursor
  } catch (error) { if (isCurrent(requestGeneration)) { capture(error); moreRequestId.value = requestId.value; moreError.value = '后续建议暂时无法载入；现有内容与分页位置仍保留。' } }
  finally { if (isCurrent(requestGeneration)) busy.value = false }
}
async function loadDetail(preserve = false) {
  if (!api || !visible.value || !isUuid(adviceId.value) || !canRenderRoute(props.routeName, auth.state)) {
    loadState.value = 'error'; loadMessage.value = '此建议暂不可用。'; return
  }
  const requestGeneration = ++generation
  busy.value = true; if (!preserve || !detail.value) loadState.value = 'loading'; requestId.value = ''; loadMessage.value = ''; detailRefreshError.value = ''
  try { const result = await api.get(adviceId.value); if (!isCurrent(requestGeneration)) return; detail.value = result; loadState.value = 'ready' }
  catch (error) { if (!isCurrent(requestGeneration)) return; capture(error); loadMessage.value = error instanceof AppError && error.status === 404 ? '此建议不存在或当前不可用。' : error instanceof AppError && error.kind === 'offline' ? '当前离线，无法载入建议详情。' : '暂时无法载入建议详情；已有内容未被覆盖。'; if (!detail.value) loadState.value = 'error'; else { detailRefreshError.value = loadMessage.value; detailRequestId.value = requestId.value } }
  finally { if (isCurrent(requestGeneration)) busy.value = false }
}
async function mutate(action: 'read' | 'archive' | 'feedback', feedbackType?: 'helpful' | 'not_helpful' | 'not_applicable') {
  if (!api || !detail.value || busy.value || !visible.value) return
  const requestGeneration = generation
  const advice = detail.value
  busy.value = true; actionError.value = ''; actionRequestId.value = ''
  try {
    const next = action === 'read' ? await api.markRead(advice.id) : action === 'archive' ? await api.archive(advice.id) : null
    if (next) { if (!isCurrent(requestGeneration)) return; detail.value = next; return }
    if (!feedbackType) return
    await api.feedback(advice.id, { feedback_type: feedbackType, expected_version: advice.feedback?.version ?? 0 }, createIdempotencyKey())
    if (!isCurrent(requestGeneration)) return
    await loadDetail(true)
  } catch (error) { if (!isCurrent(requestGeneration)) return; capture(error); actionRequestId.value = requestId.value; actionError.value = error instanceof AppError && error.status === 409 ? '状态或反馈版本已变化；没有覆盖现有内容，也没有自动重新提交。请先刷新确认。' : '操作未完成，当前服务端状态未作推测；可刷新后再决定。' }
  finally { if (isCurrent(requestGeneration)) busy.value = false }
}
function markRead() { return mutate('read') }
function refreshList() { return loadList(true) }
function retryDetail() { return loadDetail(true) }
function submitFeedback(value: 'helpful' | 'not_helpful' | 'not_applicable') { return mutate('feedback', value) }
function confirmArchive() { uni.showModal({ title: '归档这条建议？', content: '归档只改变列表状态，不代表依据变化或健康状态结论。', success: (result) => { if (result.confirm) void mutate('archive') } }) }
function open(id: string) { router?.navigateAdviceDetail(id, ownerTab.value, 'list') }
function openRisk(id: string) { if (isUuid(id)) router?.navigateRiskAlertDetail(id) }
function openEvidence(item: AdviceEvidence) {
  if (!adviceEvidenceCanNavigate(item)) return
  router?.navigateAnalysisEvidence({ source_type: item.source_type, source_id: item.source_id, source_version: item.source_version, locator: item.locator ?? '', source_deleted: false }, ownerTab.value)
}
function goBack() { if (isDetail.value) router?.returnFromAdvice(ownerTab.value, from.value, notificationReturnId.value); else router?.switchTab(ownerTab.value) }
function capture(error: unknown) { if (error instanceof AppError) requestId.value = error.requestId ?? error.problem?.request_id ?? '' }
function isCurrent(requestGeneration: number) { return visible.value && generation === requestGeneration }
function createIdempotencyKey() { return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `advice-feedback-${Date.now()}-${Math.random().toString(36).slice(2)}` }
function categoryLabel(value: Advice['category']) { return ({ diet: '饮食回顾', lifestyle: '生活方式记录', record_management: '记录建议', medication_adherence: '用药计划记录', care_consultation: '就医沟通提示' })[value] }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date) }
</script>

<style lang="scss" scoped>
.advice-page{min-height:100vh;background:var(--gc-color-canvas)}.shell{width:100%;max-width:430px;min-height:100vh;margin:0 auto;padding:calc(env(safe-area-inset-top,0px) + 12px) 20px calc(env(safe-area-inset-bottom,0px) + 24px)}.topbar{display:flex;height:48px;align-items:center;gap:12px}.back{width:44px;height:44px;border:0;border-radius:50%;background:var(--gc-color-surface);color:var(--gc-color-text);font-size:28px}.topbar-title{font-size:14px;font-weight:var(--gc-font-weight-semibold)}.spacer{flex:1}.intro{display:flex;margin:18px 2px;flex-direction:column;gap:5px}.eyebrow{color:var(--gc-color-brand);font-size:10px;letter-spacing:1px}.title{font-size:25px;font-weight:var(--gc-font-weight-bold)}.subtitle,.meta,.muted{color:var(--gc-color-muted);font-size:12px;line-height:1.55}.list{display:flex;flex-direction:column;gap:12px}.advice-card,.status-card,.empty{padding:16px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);background:var(--gc-color-surface);box-shadow:var(--gc-shadow-card)}.advice-item{display:flex;width:100%;flex-direction:column;align-items:stretch;gap:10px;color:var(--gc-color-text);text-align:left}.card-heading{display:flex;align-items:center;justify-content:space-between}.category{color:var(--gc-color-brand-strong);font-size:12px;font-weight:var(--gc-font-weight-semibold)}.status{color:var(--gc-color-muted);font-size:11px}.advice-title{font-size:17px;line-height:1.45;font-weight:var(--gc-font-weight-semibold)}.advice-body{color:var(--gc-color-text);font-size:14px;line-height:1.7;white-space:pre-wrap}.body-preview{max-height:180px;overflow:hidden}.basis-inline{color:var(--gc-color-danger);font-size:12px}.advice-detail{display:flex;flex-direction:column;gap:14px}.risk-context{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid var(--gc-color-danger);border-radius:14px;background:var(--gc-color-danger-pale)}.risk-context.compact{padding:9px}.risk-mark{display:grid;width:28px;height:28px;flex:none;place-items:center;border:1px solid var(--gc-color-danger);border-radius:50%;color:var(--gc-color-danger);font-weight:700}.risk-copy{display:flex;flex:1;flex-direction:column;gap:2px}.risk-title{color:var(--gc-color-danger);font-size:12px;font-weight:var(--gc-font-weight-bold)}.basis-notice,.notice{padding:12px;border-radius:12px;background:#fff5e8;color:#82551a;font-size:12px;line-height:1.55}.metadata,.evidence-section,.feedback{display:flex;flex-direction:column;gap:8px}.metadata{color:var(--gc-color-muted);font-size:12px;line-height:1.55}.section-title{font-size:14px;font-weight:var(--gc-font-weight-semibold)}.evidence-row{display:flex;flex-direction:column;gap:6px;padding:10px;border:1px solid var(--gc-color-border);border-radius:12px}.evidence-label{font-size:12px;line-height:1.5}.actions{display:flex;flex-wrap:wrap;gap:8px}.secondary,.feedback-choice{min-height:44px;padding:0 14px;border:1px solid var(--gc-color-border);border-radius:14px;background:var(--gc-color-surface);color:var(--gc-color-brand-strong);font-size:13px}.feedback-choice.chosen{border-color:var(--gc-color-brand);background:#f0f2ff}.text-action{min-height:44px;padding:0 8px;border:0;background:transparent;color:var(--gc-color-brand-strong);font-size:12px}.meta{font-size:11px}.empty{display:flex;min-height:160px;align-items:center;justify-content:center;flex-direction:column;gap:10px;text-align:center}.empty-mark{font-size:28px;color:var(--gc-color-muted)}.more,.refresh-error,.more-error{align-self:stretch;padding:12px}.refresh-error,.more-error,.inline-error{border:1px solid var(--gc-color-danger);border-radius:12px;color:var(--gc-color-danger);font-size:12px}.request-id{display:block;color:var(--gc-color-muted);font-size:10px}.privacy-note{display:block;margin-top:14px;color:var(--gc-color-muted);font-size:10px}.auth-pending{display:grid;min-height:100vh;place-items:center;color:var(--gc-color-muted)}
</style>

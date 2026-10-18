<template>
  <view v-if="pageReady" class="analysis-page" :data-testid="`analysis-workspace-${mode}`">
    <view class="shell">
      <view class="topbar"><button class="back" :aria-label="`返回${ownerLabel}`" data-testid="analysis-back" @click="goBack">‹</button><text class="topbar-title">{{ title }}</text><view class="spacer" /></view>

      <template v-if="mode === 'new'">
        <view class="intro"><text class="eyebrow">F08 · ANALYSIS</text><text class="heading">发起分析</text><text class="copy">分析任务使用当前授权的已确认数据创建冻结快照。预览只反映当前时点，不保证与稍后创建的任务快照一致。</text></view>
        <view class="form-card">
          <text class="field-label">分析类型</text>
          <view class="choice-row" role="radiogroup" aria-label="分析类型">
            <button class="choice" :class="{ selected: analysisType === 'comprehensive_health_analysis' }" :aria-pressed="analysisType === 'comprehensive_health_analysis'" :disabled="busy" data-testid="analysis-type-comprehensive" @click="setAnalysisType('comprehensive_health_analysis')">综合分析</button>
            <button class="choice" :class="{ selected: analysisType === 'periodic_summary' }" :aria-pressed="analysisType === 'periodic_summary'" :disabled="busy" data-testid="analysis-type-periodic" @click="setAnalysisType('periodic_summary')">周期总结</button>
          </view>
          <text class="hint">周期总结需要明确日期范围；综合分析可不限定日期，也可提供完整范围。</text>
          <view class="date-row"><view class="date-field"><text class="field-label">开始日期（含，可选）</text><picker mode="date" :value="fromDay" :disabled="busy" @change="setFromDay"><view class="date-value" data-testid="analysis-from-day">{{ fromDay || '不限定' }}</view></picker></view><view class="date-field"><text class="field-label">结束日期（不含，可选）</text><picker mode="date" :value="untilDay" :disabled="busy" @change="setUntilDay"><view class="date-value" data-testid="analysis-until-day">{{ untilDay || '不限定' }}</view></picker></view></view>
          <text class="hint">时区：{{ timezone }}。明确范围按 UTC 半开区间 [开始, 结束) 发送；不会猜测缺失边界。</text>
          <view v-if="formError" class="field-error" role="alert" data-testid="analysis-form-error">{{ formError }}</view>
          <view class="actions"><GcButton label="查看当前数据预览" variant="secondary" :busy="busy && operation === 'preview'" :disabled="busy" test-id="analysis-preview" @click="loadPreview" /></view>
        </view>
        <view v-if="previewError" class="error-card" role="alert" data-testid="analysis-preview-error"><text>{{ previewError }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text><button class="text-action" :disabled="busy" data-testid="analysis-preview-retry" @click="loadPreview">重试预览</button></view>
        <view v-if="preview" class="preview-card" data-testid="analysis-preview-result">
          <text class="card-title">当前预览 · {{ analysisTypeLabel(preview.analysis_type) }}</text>
          <text class="preview-line">心情记录：范围内 {{ preview.mood_record_count_in_range }} 条 · 当前可纳入 {{ preview.mood_record_count_eligible }} 条</text>
          <text v-if="preview.mood_record_count_excluded_by_consent" class="preview-line">因心情专项授权未纳入 {{ preview.mood_record_count_excluded_by_consent }} 条</text>
          <text v-for="reason in preview.mood_exclusion_reasons" :key="reason" class="muted">{{ moodReasonLabel(reason) }}</text>
          <text class="notice">预览不是最终快照。提交时服务端会在同一授权栅栏内重新检查授权与记录；实际任务摘要以服务端返回为准。</text>
          <GcButton label="确认发起分析" :busy="busy && operation === 'create'" :disabled="busy || !previewMatchesCurrentRequest" test-id="analysis-create" @click="createTask" />
        </view>
        <view v-else class="preview-placeholder" data-testid="analysis-preview-placeholder"><text class="card-title">先查看当前预览</text><text class="muted">缺少授权或服务暂不可用时，页面会显示服务端错误；不会伪造授权或数据数量。</text></view>
        <text class="privacy-note">不会展示报告正文、原始模型输出或自由聊天内容；分析结果不构成诊断或处方。</text>
      </template>

      <template v-else-if="mode === 'history'">
        <view class="intro"><text class="eyebrow">YOUR TASKS</text><text class="heading">分析历史</text><text class="copy">仅显示本人任务的服务端状态与受控摘要。</text></view>
        <view v-if="refreshError" class="inline-error" role="alert" data-testid="analysis-refresh-error"><text>{{ refreshError }}</text><button class="text-action" :disabled="busy" data-testid="analysis-refresh-retry" @click="loadList(true)">重试刷新</button><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <DashboardDataStatus v-if="loadState === 'loading' && tasks.length === 0" state="loading" test-id="analysis-history-loading" />
        <view v-else-if="loadState === 'error' && tasks.length === 0" class="status-card"><DashboardDataStatus state="error" :message="loadError" retryable :busy="busy" test-id="analysis-history-error" @retry="loadList(false)" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view v-else-if="loadState === 'empty' && tasks.length === 0" class="empty" data-testid="analysis-history-empty"><text class="empty-mark" aria-hidden="true">◷</text><text class="card-title">暂无分析任务</text><text class="muted">空列表不代表数据状态或健康结论。</text><GcButton label="查看发起分析" variant="secondary" test-id="analysis-history-new" @click="router?.navigate('analysisNew')" /></view>
        <view v-else class="task-list" data-testid="analysis-history-list">
          <button v-for="task in tasks" :key="task.id" class="task-card" :data-testid="`analysis-task-${task.id}`" @click="router?.navigateAnalysisTaskDetail(task.id, ownerTab, true)">
            <view class="task-heading"><text class="card-title">{{ analysisTypeLabel(task.analysis_type) }}</text><text class="status-badge" :class="`status-badge--${task.status}`">{{ analysisStatusLabel(task.status) }}</text></view>
            <text class="muted">创建时间：{{ formatDate(task.created_at) }} · 第 {{ task.attempt }} 次尝试</text>
            <text class="muted">创建时实际纳入心情记录：{{ task.input_summary.included_mood_record_count }} 条</text>
            <text class="muted">{{ task.result ? '结果已生成（内容暂不在此列表展示）' : '当前无可展示结果内容' }}</text>
            <text v-if="task.error_code" class="error-code">{{ analysisErrorLabel(task.error_code) }}</text>
            <text class="task-open">查看服务端状态 ›</text>
          </button>
          <view v-if="moreError" class="inline-error" role="alert" data-testid="analysis-more-error"><text>{{ moreError }}</text><button class="text-action" :disabled="busy" data-testid="analysis-more-retry" @click="loadMore">重试载入</button><text v-if="moreRequestId" class="request-id">请求编号：{{ moreRequestId }}</text></view>
          <button v-else-if="cursor" class="more" :disabled="busy" data-testid="analysis-more" @click="loadMore">{{ busy ? '正在载入…' : '载入更多' }}</button>
        </view>
        <text class="privacy-note">不显示报告正文、原始输出、prompt、备注或诊断推断。</text>
      </template>

      <template v-else>
          <view v-if="loadState === 'loading'" class="status-card"><DashboardDataStatus state="loading" test-id="analysis-detail-loading" /></view>
        <view v-else-if="loadState === 'error'" class="status-card"><DashboardDataStatus state="error" :message="loadError" retryable :busy="busy" test-id="analysis-detail-error" @retry="loadDetail" /><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
          <view v-else-if="task" class="detail-card" data-testid="analysis-task-detail">
          <view class="intro"><text class="eyebrow">TASK DETAIL</text><text class="heading">{{ analysisTypeLabel(task.analysis_type) }}</text><text class="copy">实际状态：{{ analysisStatusLabel(task.status) }}</text></view>
          <view class="detail-row"><text class="field-label">任务编号</text><text class="detail-value">{{ task.id }}</text></view>
          <view class="detail-row"><text class="field-label">尝试次数</text><text class="detail-value">{{ task.attempt }}</text></view>
          <view v-if="task.retry_of" class="detail-row"><text class="field-label">重试来源</text><text class="detail-value">{{ task.retry_of }}</text></view>
          <view class="detail-row"><text class="field-label">创建时间</text><text class="detail-value">{{ formatDate(task.created_at) }}</text></view>
          <view class="detail-row"><text class="field-label">最近更新时间</text><text class="detail-value">{{ formatDate(task.updated_at) }}</text></view>
          <view class="detail-row"><text class="field-label">创建时实际纳入的心情记录</text><text class="detail-value">{{ task.input_summary.included_mood_record_count }} 条</text></view>
          <view v-if="task.status === 'needs_input'" class="notice" data-testid="analysis-needs-input">此任务已结束。补充或确认相关记录后，请新建分析任务；当前任务不能重试。</view>
          <view v-if="task.status === 'partial'" class="notice" data-testid="analysis-partial">部分完成：以下仅展示服务端返回的结构化内容。</view>
          <view v-if="task.status === 'succeeded'" class="notice" data-testid="analysis-succeeded">任务已完成。</view>
          <view v-if="detailRefreshError" class="inline-error" role="alert" data-testid="analysis-detail-refresh-error"><text>{{ detailRefreshError }}</text><button class="text-action" :disabled="busy" data-testid="analysis-detail-refresh-retry" @click="loadDetail">重试刷新</button><text v-if="detailRequestId" class="request-id">请求编号：{{ detailRequestId }}</text></view>
          <view v-if="actionError" class="inline-error" role="alert" data-testid="analysis-task-action-error"><text>{{ actionError }}</text><button v-if="actionShowSettings" class="text-action" data-testid="analysis-retry-settings" @click="router?.navigate('settings')">查看隐私授权设置</button><text v-if="actionRequestId" class="request-id">请求编号：{{ actionRequestId }}</text></view>
          <view v-if="task.status === 'failed' && task.error_code" class="error-card" role="status" data-testid="analysis-failed-reason">{{ analysisErrorLabel(task.error_code) }}</view>
          <view v-if="task.result && task.result.schema_version === '1.0'" class="result-card" data-testid="analysis-structured-result">
            <text class="card-title">结构化分析结果</text>
            <text class="notice">这是对记录的整理与分析，不是诊断或处方；不提供药物剂量调整或因果结论。</text>
            <view class="result-section"><text class="field-label">摘要</text><text class="result-copy">{{ task.result.summary }}</text></view>
            <view v-if="task.result.observations.length" class="result-section"><text class="field-label">观察</text><text v-for="(item, index) in task.result.observations" :key="`observation-${index}`" class="result-copy">{{ item }}</text></view>
            <view v-if="task.result.evidence.length" class="result-section"><text class="field-label">关联来源</text><view v-for="(item, index) in task.result.evidence" :key="`${item.source_type}-${item.source_id}-${index}`" class="evidence-row" :data-testid="`analysis-evidence-${index}`"><text class="result-copy">{{ evidenceLabel(item.source_type) }} · v{{ item.source_version }}<text v-if="analysisEvidenceLocatorLabel(item)"> · {{ analysisEvidenceLocatorLabel(item) }}</text></text><text v-if="item.source_deleted" class="muted">来源已删除，无法跳转。</text><button v-else-if="analysisEvidenceCanNavigate(item)" class="text-action" :data-testid="`analysis-evidence-open-${index}`" @click="openEvidence(item)">查看来源</button><text v-else class="muted">此来源暂不支持跳转。</text></view></view>
            <view v-if="task.result.uncertainties.length" class="result-section"><text class="field-label">不确定项</text><text v-for="(item, index) in task.result.uncertainties" :key="`uncertainty-${index}`" class="result-copy">{{ item }}</text></view>
            <view v-if="task.result.missing_data.length" class="result-section"><text class="field-label">缺少的数据</text><text v-for="(item, index) in task.result.missing_data" :key="`missing-${index}`" class="result-copy">{{ item }}</text></view>
          </view>
          <view v-else-if="task.result" class="notice" data-testid="analysis-result-version-unsupported">当前结果版本暂不支持展示。</view>
          <view v-else class="detail-row" data-testid="analysis-no-result"><text class="field-label">结果</text><text class="detail-value">当前任务没有可展示的结构化结果。</text></view>
          <view class="actions"><GcButton label="刷新任务状态" variant="secondary" :busy="busy && operation === 'detail'" :disabled="busy" test-id="analysis-detail-refresh" @click="loadDetail" /><GcButton v-if="task.status === 'pending' || task.status === 'processing'" label="取消任务" variant="secondary" :busy="busy && operation === 'cancel'" :disabled="busy" test-id="analysis-task-cancel" @click="confirmCancel" /><GcButton v-if="task.status === 'failed'" label="确认重试任务" variant="secondary" :busy="busy && operation === 'retry'" :disabled="busy" test-id="analysis-task-retry" @click="confirmRetry" /><GcButton :label="`返回${returnDestinationLabel}`" test-id="analysis-detail-back" @click="goBack" /></view>
        </view>
        <text class="privacy-note">任务详情不展示 prompt、模型原始输出、报告正文或证据内容。</text>
      </template>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证本人会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { analysisApiKey, appRouterKey } from '../api/context'
import { AppError } from '../api/errors'
import type { AnalysisResultEvidence, AnalysisTask, AnalysisTaskPreview, AnalysisTaskRequest } from '../api/openapiTypes'
import { AnalysisFirstShowGate, analysisErrorLabel, analysisEvidenceCanNavigate, analysisEvidenceLocatorLabel, analysisStatusLabel, analysisTaskActions, analysisTypeLabel, appendAnalysisPage, buildAnalysisRequest, failAnalysisAppend, isAnalysisResponseCurrent } from '../api/analysisView'
import { canRenderRoute, isUuid } from '../navigation/routes'
import type { AppTabName } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import DashboardDataStatus from './DashboardDataStatus.vue'
import GcButton from './GcButton.vue'

const props = defineProps<{ mode: 'new' | 'history' | 'detail' }>()
const routeName = computed(() => props.mode === 'new' ? 'analysisNew' : props.mode === 'history' ? 'analysisHistory' : 'analysisTaskDetail')
const auth = useAuthStore()
const api = inject(analysisApiKey)
const router = inject(appRouterKey)
const pageReady = ref(false)
const visible = ref(false)
const busy = ref(false)
const operation = ref<'preview' | 'create' | 'detail' | 'cancel' | 'retry' | ''>('')
const ownerTab = ref<AppTabName>('analysis')
const taskId = ref('')
const fromHistory = ref(false)
const task = ref<AnalysisTask | null>(null)
const tasks = ref<AnalysisTask[]>([])
const cursor = ref<string | null>(null)
const preview = ref<AnalysisTaskPreview | null>(null)
const previewKey = ref('')
const idempotencyKey = ref('')
const analysisType = ref<AnalysisTaskRequest['analysis_type']>('comprehensive_health_analysis')
const fromDay = ref('')
const untilDay = ref('')
const timezone = computed(() => auth.profile?.timezone ?? 'UTC')
const loadState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
const loadError = ref('')
const refreshError = ref('')
const moreError = ref('')
const previewError = ref('')
const formError = ref('')
const requestId = ref('')
const detailRequestId = ref('')
const actionRequestId = ref('')
const detailRefreshError = ref('')
const actionError = ref('')
const actionShowSettings = ref(false)
const retryIdempotencyKey = ref('')
const retryKeyTaskId = ref('')
const moreRequestId = ref('')
const firstShow = new AnalysisFirstShowGate()
const ownerLabel = computed(() => ownerTab.value === 'me' ? '我的' : '分析')
const returnDestinationLabel = computed(() => fromHistory.value ? `${ownerTab.value === 'me' ? '我的' : '分析'}历史` : ownerLabel.value)
const title = computed(() => props.mode === 'new' ? '发起分析' : props.mode === 'history' ? '分析历史' : '分析任务详情')
const requestBuild = computed(() => buildAnalysisRequest(analysisType.value, fromDay.value, untilDay.value, timezone.value))
const previewMatchesCurrentRequest = computed(() => Boolean(preview.value) && previewKey.value === requestFingerprint())
let generation = 0
let pollTimer: ReturnType<typeof setTimeout> | null = null

onLoad((options) => {
  if (!canRenderRoute(routeName.value as 'analysisNew' | 'analysisHistory' | 'analysisTaskDetail', auth.state)) { router?.requireAuthentication(routeName.value as 'analysisNew' | 'analysisHistory' | 'analysisTaskDetail'); return }
  pageReady.value = true; visible.value = true
  ownerTab.value = options?.owner === 'me' ? 'me' : 'analysis'
  fromHistory.value = options?.from === 'history'
  if (props.mode === 'detail') {
    taskId.value = isUuid(options?.task_id) ? options.task_id : ''
    if (taskId.value) void loadDetail()
    else { loadState.value = 'error'; loadError.value = '任务标识无效或当前不可用。' }
  } else if (props.mode === 'history') void loadList(false)
})
onShow(() => {
  if (!pageReady.value) return
  if (!canRenderRoute(routeName.value as 'analysisNew' | 'analysisHistory' | 'analysisTaskDetail', auth.state)) { router?.requireAuthentication(routeName.value as 'analysisNew' | 'analysisHistory' | 'analysisTaskDetail'); return }
  visible.value = true
  if (!firstShow.shouldRefresh()) return
  if (props.mode === 'new' && preview.value) void loadPreview()
  if (props.mode === 'history') void loadList(true)
  if (props.mode === 'detail' && taskId.value) void loadDetail()
})
onHide(() => { visible.value = false; generation += 1; stopPolling(); busy.value = false; operation.value = '' })
onUnload(() => { visible.value = false; generation += 1; stopPolling() })
onBackPress(() => { goBack(); return true })

async function loadPreview() {
  if (!api || busy.value || !authorized()) return
  const built = requestBuild.value
  if (built.error) { formError.value = built.error; return }
  const fingerprint = JSON.stringify(built.body)
  busy.value = true; operation.value = 'preview'; previewError.value = ''; formError.value = ''; requestId.value = ''
  const requestGeneration = ++generation
  try {
    const result = await api.preview(built.body)
    if (!isCurrent(requestGeneration)) return
    preview.value = result; previewKey.value = fingerprint; previewError.value = ''
  } catch (error) {
    if (!isCurrent(requestGeneration)) return
    capture(error); previewError.value = friendlyError(error, '当前无法获取数据预览；未将失败解释为无数据。')
  } finally { if (isCurrent(requestGeneration)) { busy.value = false; operation.value = '' } }
}

async function createTask() {
  if (!api || busy.value || !authorized() || !previewMatchesCurrentRequest.value) return
  const body = requestBuild.value.body
  busy.value = true; operation.value = 'create'; formError.value = ''; requestId.value = ''
  const requestGeneration = ++generation
  if (!idempotencyKey.value) idempotencyKey.value = createIdempotencyKey()
  try {
    const accepted = await api.create(body, idempotencyKey.value)
    if (!isCurrent(requestGeneration)) return
    task.value = accepted.task
    router?.navigateAnalysisTaskDetail(accepted.task.id, ownerTab.value)
  } catch (error) {
    if (!isCurrent(requestGeneration)) return
    capture(error); formError.value = friendlyError(error, '任务未能确认受理；请检查请求编号后重试。')
  } finally { if (isCurrent(requestGeneration)) { busy.value = false; operation.value = '' } }
}

async function loadList(preserve: boolean) {
  if (!api || busy.value || !authorized()) return
  const keep = preserve && tasks.value.length > 0
  const requestGeneration = ++generation
  busy.value = true; moreError.value = ''; moreRequestId.value = ''; requestId.value = ''
  if (!keep) { loadState.value = 'loading'; loadError.value = ''; refreshError.value = '' }
  try {
    const page = await api.list({ limit: 20 })
    if (!isCurrent(requestGeneration)) return
    tasks.value = page.items; cursor.value = page.next_cursor; loadState.value = tasks.value.length ? 'ready' : 'empty'; refreshError.value = ''
  } catch (error) {
    if (!isCurrent(requestGeneration)) return
    capture(error)
    if (keep) { refreshError.value = friendlyError(error, '刷新失败，现有任务仍保留；可重试。'); loadState.value = 'ready' }
    else { loadError.value = friendlyError(error, '暂时无法载入分析历史。'); loadState.value = 'error' }
  } finally { if (isCurrent(requestGeneration)) busy.value = false }
}

async function loadMore() {
  if (!api || !cursor.value || busy.value || !authorized()) return
  const requestGeneration = ++generation; const requestedCursor = cursor.value
  busy.value = true; moreError.value = ''; moreRequestId.value = ''
  try {
    const page = await api.list({ limit: 20, cursor: requestedCursor })
    if (!isCurrent(requestGeneration)) return
    const next = appendAnalysisPage({ items: tasks.value, cursor: cursor.value, error: '', requestId: '' }, page)
    tasks.value = next.items; cursor.value = next.cursor
  } catch (error) {
    if (!isCurrent(requestGeneration)) return
    capture(error)
    const failed = failAnalysisAppend({ items: tasks.value, cursor: cursor.value, error: '', requestId: '' }, friendlyError(error, '后续任务暂时无法载入；已有项目和游标已保留。'), errorRequestId(error))
    tasks.value = failed.items; cursor.value = failed.cursor; moreError.value = failed.error; moreRequestId.value = failed.requestId
  } finally { if (isCurrent(requestGeneration)) busy.value = false }
}

async function loadDetail() {
  if (!api || !taskId.value || busy.value || !authorized()) { if (!taskId.value) { loadState.value = 'error'; loadError.value = '任务标识无效或当前不可用。' }; return }
  stopPolling()
  const requestGeneration = ++generation
  busy.value = true; operation.value = 'detail'; loadState.value = task.value ? 'ready' : 'loading'; detailRefreshError.value = ''; detailRequestId.value = ''; requestId.value = ''
  try { const result = await api.get(taskId.value); if (!isCurrent(requestGeneration)) return; task.value = result; loadState.value = 'ready'; detailRefreshError.value = ''; schedulePolling(result.status) }
  catch (error) { if (!isCurrent(requestGeneration)) return; detailRequestId.value = errorRequestId(error); const message = friendlyError(error, '任务不存在或当前不可用。'); if (task.value) { detailRefreshError.value = message; loadState.value = 'ready'; schedulePolling(task.value.status) } else { capture(error); loadError.value = message; loadState.value = 'error' } }
  finally { if (isCurrent(requestGeneration)) { busy.value = false; operation.value = '' } }
}

function confirmCancel() {
  if (!task.value || busy.value || !analysisTaskActions(task.value.status).canCancel) return
  const dialogGeneration = generation
  uni.showModal({ title: '取消分析任务？', content: '确认后将请求服务端取消此任务；取消结果以服务端状态为准。', confirmText: '确认取消', cancelText: '继续等待', success: (result) => { if (result.confirm && visible.value && generation === dialogGeneration) void cancelTask() } })
}

async function cancelTask() {
  if (!api || !visible.value || !task.value || busy.value || !analysisTaskActions(task.value.status).canCancel || !authorized()) return
  stopPolling(); const requestGeneration = ++generation; busy.value = true; operation.value = 'cancel'; actionError.value = ''; actionRequestId.value = ''
  try { const result = await api.cancel(task.value.id); if (!isCurrent(requestGeneration)) return; task.value = result; actionShowSettings.value = false; schedulePolling(result.status) }
  catch (error) { if (!isCurrent(requestGeneration)) return; actionRequestId.value = errorRequestId(error); actionShowSettings.value = false; actionError.value = friendlyError(error, '取消未能确认；任务状态保持原样，请刷新后再决定。'); schedulePolling(task.value.status) }
  finally { if (isCurrent(requestGeneration)) { busy.value = false; operation.value = '' } }
}

function confirmRetry() {
  if (!task.value || busy.value || !analysisTaskActions(task.value.status).canRetry) return
  const dialogGeneration = generation
  uni.showModal({ title: '重试分析任务？', content: '将由服务端按原任务快照与当前授权规则决定是否受理；应用不会重建快照或自动重提。', confirmText: '确认重试', cancelText: '暂不重试', success: (result) => { if (result.confirm && visible.value && generation === dialogGeneration) void retryTask() } })
}

async function retryTask() {
  if (!api || !visible.value || !task.value || busy.value || !analysisTaskActions(task.value.status).canRetry || !authorized()) return
  stopPolling(); const requestGeneration = ++generation; const sourceId = task.value.id; busy.value = true; operation.value = 'retry'; actionError.value = ''; actionRequestId.value = ''
  if (retryKeyTaskId.value !== sourceId) { retryKeyTaskId.value = sourceId; retryIdempotencyKey.value = createIdempotencyKey() }
  try { const accepted = await api.retry(sourceId, retryIdempotencyKey.value); if (!isCurrent(requestGeneration)) return; retryIdempotencyKey.value = ''; retryKeyTaskId.value = ''; actionShowSettings.value = false; router?.navigateAnalysisTaskDetail(accepted.task.id, ownerTab.value, fromHistory.value) }
  catch (error) { if (!isCurrent(requestGeneration)) return; actionRequestId.value = errorRequestId(error); actionShowSettings.value = error instanceof AppError && error.status === 409 && error.code === 'CONSENT_REQUIRED'; actionError.value = actionShowSettings.value ? '服务端拒绝了本次重试，因为当前授权不满足任务要求。请查看隐私授权设置；任务与冻结快照未在本地修改。' : friendlyError(error, '重试未能确认受理；任务未被本地改写，请刷新后再决定。') }
  finally { if (isCurrent(requestGeneration)) { busy.value = false; operation.value = '' } }
}

function schedulePolling(status: AnalysisTask['status']) {
  stopPolling()
  if (props.mode !== 'detail' || !visible.value || !pageReady.value || !analysisTaskActions(status).shouldPoll) return
  pollTimer = setTimeout(() => { pollTimer = null; if (visible.value && pageReady.value && !busy.value) void loadDetail() }, 15000)
}
function stopPolling() { if (pollTimer !== null) { clearTimeout(pollTimer); pollTimer = null } }
function openEvidence(evidence: AnalysisResultEvidence) { if (!analysisEvidenceCanNavigate(evidence)) return; router?.navigateAnalysisEvidence(evidence, ownerTab.value) }
function evidenceLabel(type: AnalysisResultEvidence['source_type']) {
  const labels: Record<AnalysisResultEvidence['source_type'], string> = { confirmed_medical_fact: '已确认医疗事实', diet_record: '饮食记录', stool_record: '排便记录', symptom_record: '症状记录', mood_record: '心情记录', medication_plan: '用药计划', medication_checkin: '用药打卡', risk_alert: '风险提示' }
  return labels[type]
}

function setAnalysisType(value: AnalysisTaskRequest['analysis_type']) { if (analysisType.value === value) return; analysisType.value = value; resetPreview() }
function setFromDay(event: { detail?: { value?: string } }) { if (event.detail?.value) { fromDay.value = event.detail.value; resetPreview() } }
function setUntilDay(event: { detail?: { value?: string } }) { if (event.detail?.value) { untilDay.value = event.detail.value; resetPreview() } }
function resetPreview() { preview.value = null; previewKey.value = ''; idempotencyKey.value = ''; previewError.value = ''; formError.value = ''; generation += 1; busy.value = false }
function requestFingerprint() { const built = requestBuild.value; return built.error ? '' : JSON.stringify(built.body) }
function authorized() { if (canRenderRoute(routeName.value as 'analysisNew' | 'analysisHistory' | 'analysisTaskDetail', auth.state)) return true; router?.requireAuthentication(routeName.value as 'analysisNew' | 'analysisHistory' | 'analysisTaskDetail'); return false }
function isCurrent(requestGeneration: number) { return isAnalysisResponseCurrent(requestGeneration, generation, visible.value && pageReady.value, authorized()) }
function capture(error: unknown) { requestId.value = errorRequestId(error) }
function errorRequestId(error: unknown) { return error instanceof AppError ? error.requestId ?? error.problem?.request_id ?? '' : '' }
function friendlyError(error: unknown, fallback: string) { if (!(error instanceof AppError)) return fallback; if (error.status === 404) return '分析服务或任务当前不可用。'; if (error.status === 409) return '授权或任务状态不满足当前操作；未创建或修改任务。'; if (error.status === 422) return '请求范围或字段不符合服务端要求，请检查后重试。'; if (error.kind === 'offline' || error.kind === 'network' || error.kind === 'timeout') return '当前网络不可用；已有数据不会被覆盖，请重试。'; if (error.status && error.status >= 500) return '分析服务暂时不可用；失败不代表无数据。'; return fallback }
function moodReasonLabel(reason: string) { return reason === 'mood_data_processing_missing' ? '缺少心情数据处理授权。' : '缺少心情智能共享授权。' }
function formatDate(value: string) { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) }
function createIdempotencyKey() { return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `analysis-${Date.now()}-${Math.random().toString(36).slice(2)}` }
function goBack() {
  if (props.mode === 'detail') { router?.returnFromAnalysisTask(ownerTab.value, fromHistory.value); return }
  router?.switchTab(ownerTab.value)
}
</script>

<style lang="scss" scoped>
.analysis-page { min-height: 100vh; background: var(--gc-color-canvas); }.shell { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 28px); }.topbar { display: flex; height: 48px; align-items: center; justify-content: space-between; }.back { display: grid; width: 44px; height: 44px; padding: 0; place-items: center; border: 0; border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 28px; line-height: 1; }.topbar-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.spacer { width: 44px; }.intro { display: flex; margin: 20px 2px 14px; flex-direction: column; gap: 6px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.heading { color: var(--gc-color-text); font-size: 22px; font-weight: var(--gc-font-weight-bold); }.copy,.muted,.hint { color: var(--gc-color-muted); font-size: 12px; line-height: 1.6; }.form-card,.preview-card,.preview-placeholder,.detail-card,.empty,.status-card,.error-card,.result-card { display: flex; margin-top: 12px; padding: 17px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); flex-direction: column; gap: 11px; background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }.field-label { display: block; color: var(--gc-color-text); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }.choice-row { display: flex; gap: 9px; }.choice { min-height: 46px; flex: 1; border: 1px solid var(--gc-color-border); border-radius: 14px; background: var(--gc-color-surface); color: var(--gc-color-muted); font-size: 12px; }.choice.selected { border-color: var(--gc-color-brand); background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); font-weight: var(--gc-font-weight-semibold); }.date-row { display: flex; gap: 10px; }.date-field { min-width: 0; flex: 1; }.date-value { min-height: 46px; margin-top: 6px; padding: 13px 10px; border: 1px solid var(--gc-color-border); border-radius: 12px; color: var(--gc-color-text); font-size: 12px; }.actions { display: flex; flex-direction: column; gap: 9px; }.card-title { color: var(--gc-color-text); font-size: 14px; font-weight: var(--gc-font-weight-semibold); }.preview-line { color: var(--gc-color-text); font-size: 12px; }.notice { padding: 10px; border-radius: 11px; background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); font-size: 11px; line-height: 1.55; }.result-section,.evidence-row { display: flex; flex-direction: column; gap: 7px; }.result-copy { color: var(--gc-color-text); font-size: 12px; line-height: 1.65; overflow-wrap: anywhere; }.field-error,.error-code { color: var(--gc-color-danger); font-size: 12px; line-height: 1.5; }.request-id { color: var(--gc-color-muted); font-size: 10px; overflow-wrap: anywhere; }.text-action { min-height: 44px; border: 0; background: transparent; color: var(--gc-color-brand-strong); font-size: 12px; text-decoration: underline; }.task-list { display: flex; margin-top: 15px; flex-direction: column; gap: 10px; }.task-card { display: flex; width: 100%; padding: 15px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); flex-direction: column; align-items: stretch; gap: 7px; background: var(--gc-color-surface); text-align: left; box-shadow: var(--gc-shadow-card); }.task-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }.status-badge { padding: 6px 9px; border-radius: 999px; background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); font-size: 10px; }.status-badge--failed { background: var(--gc-color-peach); color: var(--gc-color-danger); }.task-open { align-self: flex-end; color: var(--gc-color-brand); font-size: 11px; }.more { min-height: 46px; border: 1px solid var(--gc-color-border); border-radius: 14px; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); }.inline-error { display: flex; margin-top: 12px; padding: 12px; border-radius: 12px; flex-direction: column; gap: 6px; background: var(--gc-color-peach); color: var(--gc-color-danger); font-size: 12px; }.detail-row { display: flex; padding: 10px 0; border-bottom: 1px solid var(--gc-color-border); flex-direction: column; gap: 5px; }.detail-value { color: var(--gc-color-text); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }.privacy-note { display: block; margin: 18px 3px; color: var(--gc-color-muted); font-size: 10px; line-height: 1.5; }.auth-pending { display: grid; min-height: 100vh; place-items: center; color: var(--gc-color-muted); }
</style>

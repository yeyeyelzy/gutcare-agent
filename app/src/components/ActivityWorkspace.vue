<template>
  <view v-if="pageReady" class="activity-page" data-testid="activity-workspace">
    <view class="activity-shell">
      <view class="topbar">
        <button class="back-button" aria-label="返回记录" data-testid="activity-back" @click="goBack">‹</button>
        <text class="topbar-title">{{ title }}</text>
        <button v-if="view === 'list'" class="add-button" aria-label="新增活动记录" data-testid="activity-add" @click="startCreate">＋</button>
        <view v-else class="topbar-spacer" />
      </view>

      <view v-if="loadState === 'loading'" class="status-panel" role="status" aria-live="polite" aria-busy="true">
        <DashboardDataStatus state="loading" test-id="activity-loading" />
      </view>
      <view v-else-if="loadState === 'error'" class="status-panel" role="alert">
        <DashboardDataStatus state="error" :message="loadMessage" :retryable="true" :busy="busy" test-id="activity-error" @retry="reload" />
        <text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
      </view>

      <template v-else-if="view === 'list'">
        <view class="intro"><text class="eyebrow">YOUR MOVEMENT</text><text class="page-title">运动记录</text><text class="subtitle">记录你完成的日常活动与主观感受。</text></view>
        <view v-if="records.length === 0" class="empty-card" data-testid="activity-empty">
          <view class="empty-mark" aria-hidden="true">↗</view><text class="card-title">此范围内暂无记录</text>
          <text class="muted">没有记录不代表没有活动。</text><GcButton label="新增活动记录" test-id="activity-empty-add" @click="startCreate" />
        </view>
        <view v-else class="record-list" data-testid="activity-list">
          <button v-for="record in records" :key="record.id" class="record-card" :data-testid="`activity-${record.id}`" @click="openRecord(record.id)">
            <view class="card-top"><text class="card-date">{{ formatDate(record.occurred_at) }}</text><text class="version">第 {{ record.record_version }} 版</text></view>
            <text class="record-summary">{{ summary(record) }}</text><text class="card-foot">{{ record.duration_minutes }} 分钟　›</text>
          </button>
          <GcButton v-if="cursor" label="载入更多" variant="secondary" :busy="busy" :disabled="busy" test-id="activity-more" @click="loadMore" />
          <view v-if="moreError" class="problem-card" role="alert" aria-live="polite" data-testid="activity-more-error">
            <text>{{ moreError }}</text><text v-if="moreRequestId" class="request-id">请求编号：{{ moreRequestId }}</text>
            <GcButton label="重试载入更多" variant="secondary" :busy="busy" :disabled="busy" test-id="activity-more-retry" @click="loadMore" />
          </view>
        </view>
      </template>

      <template v-else-if="view === 'detail' && current">
        <view class="detail-card" data-testid="activity-detail">
          <text class="eyebrow">本人记录</text><text class="detail-date">{{ formatDate(current.occurred_at) }}</text>
          <text class="record-summary record-summary--detail">{{ summary(current) }}</text><view class="detail-divider" />
          <text class="detail-label">开始时间</text><text class="detail-value">{{ current.occurred_at }}</text>
          <text class="detail-label">活动类型</text><text class="detail-value">{{ activityLabel(current.activity_type) }}{{ current.description ? `：${current.description}` : '' }}</text>
          <text class="detail-label">强度</text><text class="detail-value">{{ intensityLabel(current.intensity) }}</text>
          <text class="detail-label">主观感受</text><text class="detail-value">{{ feelingLabel(current.subjective_feeling) }}</text>
          <text class="detail-label">时长</text><text class="detail-value">{{ current.duration_minutes }} 分钟</text>
          <text class="detail-label">记录版本</text><text class="detail-value">{{ current.record_version }}</text>
        </view>
        <view v-if="problemMessage" class="problem-card" role="alert"><text>{{ problemMessage }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text><button v-if="conflict" class="inline-action" data-testid="activity-conflict-reload-detail" @click="openRecord(current.id)">重新载入最新记录</button></view>
        <view class="actions"><GcButton label="编辑" test-id="activity-edit" @click="startEdit" /><GcButton label="删除记录" variant="danger" test-id="activity-delete" @click="deletePrompt = true" /></view>
      </template>

      <template v-else-if="view === 'form'">
        <view class="intro intro--form"><text class="eyebrow">{{ editing ? 'EDIT ENTRY' : 'NEW ENTRY' }}</text><text class="page-title">{{ editing ? '编辑活动' : '新增活动' }}</text><text class="subtitle">仅记录本人确认的信息；感受为主观自述。</text></view>
        <view v-if="problemMessage && !conflict" class="problem-card" role="alert"><text>{{ problemMessage }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text></view>
        <view v-if="conflict" class="conflict-review" role="status" aria-live="polite" data-testid="activity-conflict-review">
          <text class="conflict-title">记录已在其他位置更新</text>
          <text class="conflict-copy">本次修改尚未提交。请对照保留的草稿与服务器最新记录，选择如何继续；不会自动覆盖或重新提交。</text>
          <text class="conflict-label">本地草稿（未提交）</text><text class="conflict-value" data-testid="activity-conflict-draft">{{ draftSummary }}</text>
          <text class="conflict-label">服务器最新记录</text>
          <view v-if="conflictLoadState === 'loading'" role="status" data-testid="activity-conflict-loading">正在读取最新记录…</view>
          <template v-else-if="conflictLatest"><text class="conflict-value" data-testid="activity-conflict-latest">版本 {{ conflictLatest.record_version }} · {{ summary(conflictLatest) }} · {{ conflictLatest.duration_minutes }} 分钟 · {{ formatDate(conflictLatest.occurred_at) }}</text></template>
          <view v-else class="conflict-load-error" role="alert"><text>{{ conflictLoadMessage }}</text><text v-if="conflictLoadRequestId" class="request-id">请求编号：{{ conflictLoadRequestId }}</text><button class="inline-action" data-testid="activity-conflict-retry-load" @click="loadConflictLatest">重试读取最新记录</button></view>
          <text v-if="requestId" class="request-id">冲突请求编号：{{ requestId }}</text>
          <view class="actions">
            <GcButton label="放弃草稿并载入最新记录" variant="secondary" :disabled="busy || !conflictLatest" test-id="activity-conflict-discard" @click="discardConflictAndLoadLatest" />
            <GcButton label="保留草稿并使用最新版本继续" :disabled="busy || !conflictLatest" test-id="activity-conflict-rebase" @click="keepDraftWithLatestVersion" />
          </view>
        </view>
        <view v-if="conflictRebased" class="rebase-note" role="status" data-testid="activity-conflict-rebased">草稿已保留，当前基于服务器最新版本。检查内容后，点“确认以最新版本保存”才会提交。</view>
        <view class="form-card">
          <view class="field-block"><text class="field-label">活动类型 <text class="required">*</text></text><picker :range="activityLabels" @change="setActivityType"><view class="picker-control">{{ activityLabels[activityValues.indexOf(draft.activityType)] }}</view></picker></view>
          <view v-if="draft.activityType === 'other'" class="field-block"><text class="field-label">活动描述 <text class="required">*</text></text><input v-model="draft.description" class="input-control" maxlength="160" placeholder="1–160 字" aria-label="其他活动描述" data-testid="activity-description" /><text v-if="formErrorField === 'description'" class="field-error" role="alert">{{ formError }}</text></view>
          <view class="field-block"><text class="field-label">开始日期与时间 <text class="required">*</text></text><picker mode="date" :value="draft.date" @change="setDate"><view class="picker-control">{{ draft.date || '选择日期' }}</view></picker><picker mode="time" :value="draft.time" @change="setTime"><view class="picker-control">{{ draft.time || '选择时间' }}</view></picker><text v-if="formErrorField === 'date'" class="field-error" role="alert">{{ formError }}</text></view>
          <view class="field-block"><text class="field-label">时长（分钟） <text class="required">*</text></text><input v-model="draft.duration" class="input-control" type="number" inputmode="numeric" min="1" max="1440" aria-label="活动时长，分钟，1到1440" data-testid="activity-duration" /><text class="field-hint">填写 1–1440 分钟。</text><text v-if="formErrorField === 'duration'" class="field-error" role="alert">{{ formError }}</text></view>
          <view class="field-block"><text class="field-label">活动强度 <text class="required">*</text></text><view class="choice-grid"><button v-for="(label, index) in intensityLabels" :key="label" class="choice" :class="{ 'choice--selected': draft.intensity === intensityValues[index] }" :aria-pressed="draft.intensity === intensityValues[index]" @click="draft.intensity = intensityValues[index]!">{{ label }}</button></view></view>
          <view class="field-block"><text class="field-label">活动后的主观感受 <text class="required">*</text></text><view class="choice-grid"><button v-for="(label, index) in feelingLabels" :key="label" class="choice" :class="{ 'choice--selected': draft.feeling === feelingValues[index] }" :aria-pressed="draft.feeling === feelingValues[index]" @click="draft.feeling = feelingValues[index]!">{{ label }}</button></view></view>
          <view class="form-actions"><GcButton :label="editing ? (conflictRebased ? '确认以最新版本保存' : '保存修改') : '保存记录'" :busy="busy" :disabled="busy || conflict" test-id="activity-save" @click="save" /><GcButton label="取消" variant="secondary" :disabled="busy" test-id="activity-cancel" @click="cancelForm" /></view>
          <text class="privacy-note">不会提交患者编号、设备来源或 AI 来源。活动感受仅为本人自述，不代表临床测量。</text>
        </view>
      </template>

      <view v-if="deletePrompt" class="modal-backdrop" role="presentation" @click.self="deletePrompt = false"><view class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="activity-delete-title" data-testid="activity-delete-confirm"><text id="activity-delete-title" class="card-title">删除这条活动记录？</text><text class="muted">删除后会立即从列表中隐藏。</text><view class="modal-actions"><GcButton label="取消" variant="secondary" :disabled="busy" test-id="activity-delete-cancel" @click="deletePrompt = false" /><GcButton label="确认删除" variant="danger" :busy="busy" :disabled="busy" test-id="activity-delete-action" @click="removeRecord" /></view></view></view>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, reactive, ref } from 'vue'
import { onBackPress, onLoad, onShow } from '@dcloudio/uni-app'
import { AppError } from '../api/errors'
import { activityApiKey, appRouterKey } from '../api/context'
import { discardActivityConflictDraft, keepActivityConflictDraft, loadActivityConflictLatest } from '../api/activityConflict'
import type { ActivityRecord } from '../api/openapiTypes'
import { activityToDraft, buildActivityWrite, EMPTY_ACTIVITY_DRAFT } from '../api/activityForm'
import type { ActivityDraft } from '../api/activityForm'
import { appendRecordPage, clearRecordPageError, failRecordPage, initialRecordPageState } from '../api/recordPagination'
import { canRenderRoute } from '../navigation/routes'
import type { ActivityWorkspaceRouteName } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import DashboardDataStatus from './DashboardDataStatus.vue'
import GcButton from './GcButton.vue'

const props = defineProps<{ routeName: ActivityWorkspaceRouteName }>()
const auth = useAuthStore()
const router = inject(appRouterKey)
const api = inject(activityApiKey)
const pageReady = ref(false)
const busy = ref(false)
const view = ref<'list' | 'detail' | 'form'>('list')
const loadState = ref<'loading' | 'ready' | 'error'>('loading')
const records = ref<ActivityRecord[]>([])
const current = ref<ActivityRecord | null>(null)
const cursor = ref<string | null>(null)
const editing = ref(false)
const editingId = ref('')
const deletePrompt = ref(false)
const problemMessage = ref('')
const moreError = ref('')
const moreRequestId = ref('')
const requestId = ref('')
const loadMessage = ref('暂时无法载入活动记录，请稍后重试。')
const conflict = ref(false)
const conflictLatest = ref<ActivityRecord | null>(null)
const conflictLoadState = ref<'idle' | 'loading' | 'error'>('idle')
const conflictLoadMessage = ref('')
const conflictLoadRequestId = ref('')
const conflictRebased = ref(false)
const formError = ref('')
const formErrorField = ref<keyof ActivityDraft | ''>('')
const draft = reactive<ActivityDraft>({ ...EMPTY_ACTIVITY_DRAFT, ...localNow() })
const activityValues = ['walking', 'jogging', 'cycling', 'other'] as const
const activityLabels = ['步行', '慢跑', '骑行', '其他']
const intensityValues = ['low', 'moderate', 'high'] as const
const intensityLabels = ['较轻', '中等', '较强']
const feelingValues = ['better', 'same', 'worse'] as const
const feelingLabels = ['感觉更好', '感觉相同', '感觉较差']
const title = computed(() => view.value === 'list' ? '运动记录' : view.value === 'detail' ? '活动详情' : editing.value ? '编辑活动' : '新增活动')
const draftSummary = computed(() => `${activityLabel(draft.activityType)}${draft.description.trim() ? `：${draft.description.trim()}` : ''} · ${draft.duration || '—'} 分钟 · ${intensityLabel(draft.intensity)} · ${feelingLabel(draft.feeling)} · ${draft.date || '未选日期'} ${draft.time || ''}`)

onLoad((options) => {
  if (!canRenderRoute(props.routeName, auth.state)) { router?.requireAuthentication(props.routeName); return }
  pageReady.value = true
  const id = typeof options?.id === 'string' && /^[0-9a-f-]{36}$/i.test(options.id) ? options.id : ''
  void (id ? openRecord(id) : reload())
})
onShow(() => { if (pageReady.value && !canRenderRoute(props.routeName, auth.state)) router?.requireAuthentication(props.routeName) })
onBackPress(() => { goBack(); return true })

function localNow(): Pick<ActivityDraft, 'date' | 'time'> {
  const now = new Date()
  return { date: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`, time: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}` }
}
function setDate(event: { detail?: { value?: string } }) { if (event.detail?.value) draft.date = event.detail.value }
function setTime(event: { detail?: { value?: string } }) { if (event.detail?.value) draft.time = event.detail.value }
function setActivityType(event: { detail?: { value?: string | number } }) { draft.activityType = activityValues[Number(event.detail?.value)] ?? 'walking'; if (draft.activityType !== 'other') draft.description = '' }
function clearErrors() { problemMessage.value = ''; requestId.value = ''; conflict.value = false; conflictLatest.value = null; conflictLoadState.value = 'idle'; conflictLoadMessage.value = ''; conflictLoadRequestId.value = ''; conflictRebased.value = false; moreError.value = ''; moreRequestId.value = '' }
async function reload() {
  if (!api || !canRenderRoute(props.routeName, auth.state)) return
  loadState.value = 'loading'; clearErrors()
  try { const page = await api.list({ limit: 30 }); records.value = page.items; cursor.value = page.next_cursor ?? null; view.value = 'list'; loadState.value = 'ready' }
  catch (error) { applyProblem(error); loadMessage.value = error instanceof AppError && error.kind === 'offline' ? '当前处于离线状态，活动记录未能载入。' : '暂时无法载入活动记录，请稍后重试。'; loadState.value = 'error' }
}
async function loadMore() {
  if (!api || !cursor.value || busy.value) return
  const state = clearRecordPageError(initialRecordPageState(records.value, cursor.value)); moreError.value = ''; moreRequestId.value = ''; busy.value = true
  try { const page = await api.list({ limit: 30, cursor: state.cursor ?? undefined }); const next = appendRecordPage(state, page); records.value = next.items; cursor.value = next.cursor }
  catch (error) { applyProblem(error); const failed = failRecordPage(state, problemMessage.value, requestId.value); records.value = failed.items; cursor.value = failed.cursor; moreError.value = failed.error; moreRequestId.value = failed.requestId }
  finally { busy.value = false }
}
async function openRecord(id: string) {
  if (!api || !canRenderRoute(props.routeName, auth.state)) return
  loadState.value = 'loading'; clearErrors()
  try { current.value = await api.get(id); view.value = 'detail'; loadState.value = 'ready' }
  catch (error) { applyProblem(error); loadMessage.value = '暂时无法载入这条活动记录。'; loadState.value = 'error' }
}
function startCreate() { current.value = null; editing.value = false; editingId.value = ''; Object.assign(draft, EMPTY_ACTIVITY_DRAFT, localNow()); formError.value = ''; formErrorField.value = ''; clearErrors(); view.value = 'form' }
function startEdit() { if (!current.value) return; editing.value = true; editingId.value = current.value.id; Object.assign(draft, activityToDraft(current.value)); formError.value = ''; formErrorField.value = ''; clearErrors(); view.value = 'form' }
function cancelForm() { clearErrors(); view.value = current.value ? 'detail' : 'list' }
async function save() {
  if (!api || busy.value || !canRenderRoute(props.routeName, auth.state)) return
  const explicitRebase = conflictRebased.value
  clearErrors(); conflictRebased.value = explicitRebase; formError.value = ''; formErrorField.value = ''
  const result = buildActivityWrite(draft)
  if (!result.ok) { formError.value = result.message; formErrorField.value = result.field; return }
  if (editing.value && (!current.value || !editingId.value)) { formError.value = '记录尚未载入完成，请重新打开后再编辑。'; return }
  busy.value = true
  try {
    current.value = editing.value
      ? await api.update(editingId.value, { ...result.body, record_version: current.value!.record_version })
      : await api.create(result.body)
    conflictRebased.value = false; view.value = 'detail'; await refreshListAfterWrite()
  } catch (error) {
    applyProblem(error)
    if (isVersionConflict(error) && editing.value && editingId.value) await loadConflictLatest()
  }
  finally { busy.value = false }
}
async function refreshListAfterWrite() { if (!api) return; try { const page = await api.list({ limit: 30 }); records.value = page.items; cursor.value = page.next_cursor ?? null } catch { /* Keep the successful detail visible. */ } }
async function removeRecord() {
  if (!api || !current.value || busy.value || !canRenderRoute(props.routeName, auth.state)) return
  busy.value = true; clearErrors()
  try { const removed = current.value; await api.delete(removed.id, removed.record_version); records.value = records.value.filter((record) => record.id !== removed.id); current.value = null; deletePrompt.value = false; view.value = 'list'; loadState.value = 'ready'; await reload() }
  catch (error) { deletePrompt.value = false; applyProblem(error) }
  finally { busy.value = false }
}
async function loadConflictLatest() {
  if (!api || !editingId.value || conflictLoadState.value === 'loading') return
  conflictLoadState.value = 'loading'; conflictLoadMessage.value = ''; conflictLoadRequestId.value = ''; conflictLatest.value = null
  try { conflictLatest.value = await loadActivityConflictLatest(api, editingId.value); conflictLoadState.value = 'idle' }
  catch (error) {
    conflictLoadState.value = 'error'
    conflictLoadMessage.value = error instanceof AppError && error.status === 404 ? '记录已不可用，请勿继续提交。' : '暂时无法读取服务器最新记录；草稿仍保留。'
    conflictLoadRequestId.value = error instanceof AppError ? error.requestId ?? '' : ''
  }
}
function discardConflictAndLoadLatest() {
  const latest = conflictLatest.value
  if (!latest) return
  const resolved = discardActivityConflictDraft(latest)
  current.value = resolved.record; Object.assign(draft, resolved.draft); editingId.value = latest.id
  conflict.value = false; conflictLatest.value = null; conflictLoadState.value = 'idle'; conflictRebased.value = false
  problemMessage.value = ''; requestId.value = ''; formError.value = ''; formErrorField.value = ''
}
function keepDraftWithLatestVersion() {
  const latest = conflictLatest.value
  if (!latest) return
  const resolved = keepActivityConflictDraft({ ...draft }, latest)
  current.value = resolved.record; Object.assign(draft, resolved.draft); editingId.value = latest.id
  conflict.value = false; conflictLatest.value = null; conflictLoadState.value = 'idle'; conflictRebased.value = true
  problemMessage.value = ''; requestId.value = ''; formError.value = ''; formErrorField.value = ''
}
function goBack() { if (deletePrompt.value) { deletePrompt.value = false; return }; if (view.value === 'form') { cancelForm(); return }; if (view.value === 'detail') { clearErrors(); void reload(); return }; router?.switchTab('records') }
function applyProblem(error: unknown) {
  if (isVersionConflict(error)) { conflict.value = true; conflictLatest.value = null; conflictLoadState.value = 'idle'; conflictRebased.value = false; problemMessage.value = '记录已在其他位置更新。草稿已保留，尚未提交。' }
  else if (error instanceof AppError && error.status === 422) problemMessage.value = '部分内容未通过校验，请检查后重试。'
  else if (error instanceof AppError && error.status === 429) problemMessage.value = '操作过于频繁，请稍后再试。'
  else if (error instanceof AppError && error.status && error.status >= 500) problemMessage.value = '服务暂时不可用，已保留当前内容，请稍后重试。'
  else if (error instanceof AppError && ['offline', 'network', 'timeout'].includes(error.kind)) problemMessage.value = '网络暂不可用，已保留当前内容；恢复连接后可重试。'
  else if (error instanceof AppError && error.status === 404) problemMessage.value = '活动记录暂时无法找到，可能已被删除。'
  else problemMessage.value = '操作未完成，请稍后重试。'
  requestId.value = error instanceof AppError ? error.requestId ?? '' : ''
}
function isVersionConflict(error: unknown): error is AppError { return error instanceof AppError && error.status === 409 && error.code === 'RECORD_VERSION_CONFLICT' }
function formatDate(value: string) { return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }
function activityLabel(value: ActivityRecord['activity_type']) { return ({ walking: '步行', jogging: '慢跑', cycling: '骑行', other: '其他' })[value] }
function intensityLabel(value: ActivityRecord['intensity']) { return ({ low: '较轻', moderate: '中等', high: '较强' })[value] }
function feelingLabel(value: ActivityRecord['subjective_feeling']) { return ({ better: '感觉更好', same: '感觉相同', worse: '感觉较差' })[value] }
function summary(record: ActivityRecord) { return `${activityLabel(record.activity_type)}${record.description ? ` · ${record.description}` : ''} · ${intensityLabel(record.intensity)} · ${feelingLabel(record.subjective_feeling)}` }
</script>

<style lang="scss" scoped>
.activity-page { min-height: 100vh; background: var(--gc-color-canvas); }.activity-shell { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); }.topbar { display: flex; height: 48px; align-items: center; justify-content: space-between; }.back-button,.add-button { display: grid; width: 44px; height: 44px; padding: 0; place-items: center; border: 0; border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 25px; }.topbar-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.topbar-spacer { width: 44px; }.intro { display: flex; flex-direction: column; margin: 23px 2px 18px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.page-title { margin-top: 4px; color: var(--gc-color-text); font-size: 27px; font-weight: var(--gc-font-weight-bold); line-height: 1.25; }.subtitle,.muted { margin-top: 5px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.55; }.empty-card,.detail-card,.form-card,.record-card,.problem-card,.status-panel,.conflict-review { padding: 20px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }.empty-card { display: flex; min-height: 235px; flex-direction: column; align-items: center; justify-content: center; gap: 6px; text-align: center; }.empty-mark { display: grid; width: 48px; height: 48px; margin-bottom: 8px; place-items: center; border-radius: 50%; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 24px; }.card-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.empty-card :deep(.gc-button) { width: 100%; margin-top: 12px; }.record-list { display: flex; flex-direction: column; gap: 10px; }.record-card { display: flex; min-height: 104px; flex-direction: column; gap: 8px; text-align: left; }.card-top { display: flex; justify-content: space-between; gap: 12px; }.card-date { color: var(--gc-color-brand-strong); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }.version,.card-foot { color: var(--gc-color-muted); font-size: 11px; }.record-summary { color: var(--gc-color-text); font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; }.card-foot { align-self: flex-end; }.detail-card { display: flex; margin-top: 20px; flex-direction: column; gap: 8px; }.detail-date { color: var(--gc-color-text); font-size: 20px; font-weight: var(--gc-font-weight-bold); }.record-summary--detail { margin: 6px 0; }.detail-divider { height: 1px; margin: 6px 0; background: var(--gc-color-border); }.detail-label { margin-top: 5px; color: var(--gc-color-muted); font-size: 11px; }.detail-value { color: var(--gc-color-text); font-size: 13px; overflow-wrap: anywhere; }.problem-card { display: flex; margin-top: 12px; flex-direction: column; gap: 7px; border-color: var(--gc-color-danger-border); background: var(--gc-color-danger-pale); color: var(--gc-color-danger); font-size: 12px; line-height: 1.55; }.request-id { color: var(--gc-color-muted); font-size: 10px; overflow-wrap: anywhere; }.inline-action { min-height: 44px; padding: 0 8px; border: 0; background: transparent; color: var(--gc-color-brand-strong); font-size: 12px; text-decoration: underline; }.actions,.form-actions { display: flex; margin-top: 14px; flex-direction: column; gap: 10px; }.intro--form { margin-bottom: 14px; }.field-block { display: flex; margin-bottom: 17px; flex-direction: column; gap: 7px; }.field-label { color: var(--gc-color-text); font-size: 13px; font-weight: var(--gc-font-weight-semibold); }.required,.field-error { color: var(--gc-color-danger); }.picker-control,.input-control { display: flex; min-height: 50px; align-items: center; padding: 0 13px; border: 1px solid var(--gc-color-border); border-radius: 13px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 14px; }.choice-grid { display: flex; flex-wrap: wrap; gap: 8px; }.choice { min-height: 44px; padding: 0 13px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-pill); background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 12px; }.choice--selected { border-color: var(--gc-color-brand); background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); }.field-hint,.field-error { font-size: 11px; line-height: 1.5; }.privacy-note { display: block; margin-top: 13px; color: var(--gc-color-muted); font-size: 10px; line-height: 1.6; }.conflict-review { display: flex; margin-top: 12px; flex-direction: column; gap: 8px; border-color: var(--gc-color-danger-border); background: var(--gc-color-danger-pale); }.conflict-title { color: var(--gc-color-danger); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.conflict-copy,.conflict-load-error,.conflict-label { color: var(--gc-color-text); font-size: 12px; line-height: 1.6; }.conflict-label { margin-top: 5px; color: var(--gc-color-muted); font-weight: var(--gc-font-weight-semibold); }.conflict-value { color: var(--gc-color-text); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }.rebase-note { margin-top: 12px; padding: 12px 14px; border-radius: 12px; background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); font-size: 12px; line-height: 1.6; }.modal-backdrop { position: fixed; inset: 0; z-index: var(--gc-layer-overlay); display: grid; padding: 24px; place-items: center; background: rgba(25, 39, 32, .38); }.confirm-modal { width: 100%; max-width: 360px; padding: 24px; border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-overlay); }.modal-actions { display: flex; margin-top: 18px; flex-direction: column; gap: 8px; }.status-panel { margin-top: 24px; }.auth-pending { display: grid; min-height: 100vh; place-items: center; color: var(--gc-color-muted); }
</style>

<template>
  <view v-if="pageReady" class="mood-page" data-testid="mood-workspace">
    <view class="mood-shell">
      <view class="topbar">
        <button class="back-button" :aria-label="backLabel" data-testid="mood-back" @click="goBack">‹</button>
        <text class="topbar-title">{{ title }}</text>
        <button v-if="view === 'list'" class="add-button" aria-label="新增心情记录" data-testid="mood-add" @click="startCreate">＋</button>
        <view v-else class="topbar-spacer" />
      </view>

      <view v-if="loadState === 'loading'" class="status-panel" role="status" aria-live="polite" aria-busy="true">
        <DashboardDataStatus state="loading" test-id="mood-loading" />
      </view>
      <view v-else-if="loadState === 'error'" class="status-panel" role="alert">
        <DashboardDataStatus state="error" :message="loadMessage" :retryable="true" :busy="busy" test-id="mood-error" @retry="reload" />
        <text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
      </view>

      <template v-else-if="view === 'list'">
        <view class="intro"><text class="eyebrow">YOUR JOURNAL</text><text class="page-title">心情记录</text><text class="subtitle">记录当时的主观感受，供自己回顾。</text></view>
        <view v-if="records.length === 0" class="empty-card" data-testid="mood-empty">
          <view class="empty-mark" aria-hidden="true">♡</view>
          <text class="card-title">此范围内暂无心情记录</text>
          <text class="muted">没有记录不代表没有感受。</text>
          <GcButton label="新增心情记录" test-id="mood-empty-add" @click="startCreate" />
        </view>
        <view v-else class="mood-list" data-testid="mood-list">
          <button v-for="record in records" :key="record.id" class="mood-card" :data-testid="`mood-${record.id}`" @click="openRecord(record.id)">
            <view class="card-top"><text class="card-date">{{ formatDate(record.occurred_at) }}</text><text class="version">第 {{ record.record_version }} 版</text></view>
            <text class="mood-summary">{{ moodLabel(record.mood_level) }}</text>
            <text class="card-foot">本人记录　›</text>
          </button>
          <GcButton v-if="nextCursor" label="载入更多" variant="secondary" :busy="busy" :disabled="busy" test-id="mood-more" @click="loadMore" />
          <view v-if="moreErrorMessage" class="problem-card" role="alert" aria-live="polite" data-testid="mood-more-error">
            <text>{{ moreErrorMessage }}</text><text v-if="moreRequestId" class="request-id">请求编号：{{ moreRequestId }}</text>
            <GcButton label="重试载入更多" variant="secondary" :busy="busy" :disabled="busy" test-id="mood-more-retry" @click="loadMore" />
          </view>
        </view>
      </template>

      <template v-else-if="view === 'detail' && currentRecord">
        <view class="detail-card" data-testid="mood-detail">
          <text class="eyebrow">本人心情记录</text>
          <text class="detail-date">{{ formatDate(currentRecord.occurred_at) }}</text>
          <text class="detail-mood">{{ moodLabel(currentRecord.mood_level) }}</text>
          <view class="detail-divider" />
          <text class="detail-label">发生时间</text><text class="detail-value">{{ currentRecord.occurred_at }}</text>
          <text class="detail-label">备注</text><text class="detail-note" data-testid="mood-note-detail">{{ currentRecord.note || '未填写备注' }}</text>
          <text class="detail-label">记录版本</text><text class="detail-value">{{ currentRecord.record_version }}</text>
        </view>
        <view v-if="problemMessage" class="problem-card" role="alert"><text>{{ problemMessage }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text><GcButton v-if="conflict" label="重新载入最新版本" variant="secondary" test-id="mood-conflict-reload-detail" @click="openRecord(currentRecord.id)" /></view>
        <view class="actions"><GcButton label="编辑" test-id="mood-edit" @click="startEdit" /><GcButton label="删除记录" variant="danger" test-id="mood-delete" @click="deletePrompt = true" /></view>
      </template>

      <template v-else-if="view === 'form'">
        <view class="intro intro--form"><text class="eyebrow">{{ isEditing ? 'EDIT ENTRY' : 'NEW ENTRY' }}</text><text class="page-title">{{ isEditing ? '编辑心情记录' : '记录心情' }}</text><text class="subtitle">选择最接近当时感受的一项；这不是临床量表。</text></view>
        <view v-if="problemMessage" class="problem-card" role="alert" data-testid="mood-form-error">
          <text>{{ problemMessage }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
          <GcButton v-if="consentRequired" label="前往隐私授权设置" variant="secondary" test-id="mood-consent-settings" @click="openConsentSettings" />
          <GcButton v-if="conflict" label="载入最新版本（保留本次草稿）" variant="secondary" test-id="mood-conflict-reload" @click="reloadConflict" />
        </view>
        <view v-if="conflict && latestConflictRecord" class="conflict-card" data-testid="mood-conflict-review">
          <text class="conflict-title">服务器已有更新版本</text>
          <text class="conflict-copy">最新记录：{{ moodLabel(latestConflictRecord.mood_level) }} · {{ formatDate(latestConflictRecord.occurred_at) }}</text>
          <text class="conflict-copy">你的草稿：{{ draft.level ? moodLabel(draft.level) : '尚未选择' }} · {{ draft.date }} {{ draft.time }}</text>
          <text class="conflict-copy">你的备注：{{ draft.note || '未填写备注' }}</text>
          <GcButton label="确认基于最新版本保存我的草稿" :busy="busy" :disabled="busy" test-id="mood-conflict-confirm" @click="confirmConflictSave" />
        </view>
        <view class="form-card">
          <view class="field-block">
            <text class="field-label">发生日期与时间 <text class="required">*</text></text>
            <picker mode="date" :value="draft.date" @change="setDate"><view class="picker-control" aria-label="选择发生日期">{{ draft.date || '选择日期' }}</view></picker>
            <picker mode="time" :value="draft.time" @change="setTime"><view class="picker-control" aria-label="选择发生时间">{{ draft.time || '选择时间' }}</view></picker>
            <text v-if="formErrorField === 'date'" class="field-error" role="alert">{{ formError }}</text>
          </view>
          <view class="field-block">
            <text class="field-label">当时的心情 <text class="required">*</text></text>
            <view class="mood-options" role="group" aria-label="选择心情等级">
              <button v-for="option in moodOptions" :key="option.level" class="mood-option" :class="{ 'mood-option--selected': draft.level === option.level }" :aria-pressed="draft.level === option.level" :data-testid="`mood-level-${option.level}`" @click="draft.level = option.level">
                <text class="mood-face" aria-hidden="true">{{ faceForLevel(option.level) }}</text><text>{{ option.label }}</text>
              </button>
            </view>
            <text v-if="formErrorField === 'level'" class="field-error" role="alert">{{ formError }}</text>
            <text class="field-hint">愉快 5 · 平静 4 · 一般 3 · 低落 2 · 烦躁 1</text>
          </view>
          <view class="field-block"><text class="field-label">备注（可选，仅本人详情可见）</text><textarea v-model="draft.note" class="textarea" maxlength="500" placeholder="写下想留给自己的内容" aria-label="心情备注" data-testid="mood-note-input" /><text v-if="formErrorField === 'note'" class="field-error" role="alert">{{ formError }}</text></view>
          <text class="privacy-note">标签功能暂不开放。记录新建和修改需要健康数据处理及心情数据处理授权；不要求智能共享授权。</text>
          <view class="form-actions"><GcButton :label="isEditing ? '保存修改' : '保存记录'" :busy="busy" :disabled="busy" test-id="mood-save" @click="save" /><GcButton label="取消" variant="secondary" :disabled="busy" test-id="mood-cancel" @click="cancelForm" /></view>
        </view>
      </template>

      <view v-if="deletePrompt" class="modal-backdrop" role="presentation" @click.self="deletePrompt = false">
        <view class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="mood-delete-title" data-testid="mood-delete-confirm">
          <text id="mood-delete-title" class="card-title">删除这条心情记录？</text><text class="muted">删除会立即隐藏该记录；此操作不可撤销。</text>
          <view class="modal-actions"><GcButton label="取消" variant="secondary" :disabled="busy" test-id="mood-delete-cancel" @click="deletePrompt = false" /><GcButton label="确认删除" variant="danger" :busy="busy" :disabled="busy" test-id="mood-delete-action" @click="removeRecord" /></view>
        </view>
      </view>
    </view>
  </view>
  <view v-else class="auth-pending" role="status" aria-live="polite">正在验证会话…</view>
</template>

<script setup lang="ts">
import { computed, inject, reactive, ref } from 'vue'
import { onBackPress, onLoad, onShow } from '@dcloudio/uni-app'
import { AppError } from '../api/errors'
import { appRouterKey, consentApiKey, moodApiKey } from '../api/context'
import type { MoodDetail, MoodSummary } from '../api/openapiTypes'
import { buildMoodPatch, buildMoodWrite, createMoodDraft, MOOD_OPTIONS, moodLabel, moodToDraft } from '../api/moodForm'
import { appendRecordPage, clearRecordPageError, failRecordPage, initialRecordPageState } from '../api/recordPagination'
import { canRenderRoute } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import DashboardDataStatus from './DashboardDataStatus.vue'
import GcButton from './GcButton.vue'

const auth = useAuthStore()
const router = inject(appRouterKey)
const api = inject(moodApiKey)
const consentApi = inject(consentApiKey)
const pageReady = ref(false)
const busy = ref(false)
const view = ref<'list' | 'detail' | 'form'>('list')
const loadState = ref<'loading' | 'ready' | 'error'>('loading')
const records = ref<MoodSummary[]>([])
const currentRecord = ref<MoodDetail | null>(null)
const nextCursor = ref<string | null>(null)
const problemMessage = ref('')
const loadMessage = ref('暂时无法载入心情记录，请检查网络后重试。')
const requestId = ref('')
const moreErrorMessage = ref('')
const moreRequestId = ref('')
const conflict = ref(false)
const conflictLoaded = ref(false)
const consentRequired = ref(false)
const latestConflictRecord = ref<MoodDetail | null>(null)
const formError = ref('')
const formErrorField = ref<'date' | 'time' | 'level' | 'note' | ''>('')
const isEditing = ref(false)
const editingId = ref('')
const deletePrompt = ref(false)
const draft = reactive(createMoodDraft('', ''))
const moodOptions = MOOD_OPTIONS
const title = computed(() => view.value === 'list' ? '心情记录' : view.value === 'detail' ? '心情详情' : isEditing.value ? '编辑心情' : '记录心情')
const backLabel = computed(() => view.value === 'list' ? '返回记录' : '返回上一页')

onLoad((options) => {
  if (!canRenderRoute('recordMood', auth.state)) {
    router?.requireAuthentication('recordMood')
    return
  }
  pageReady.value = true
  const id = typeof options?.id === 'string' && /^[0-9a-f-]{36}$/i.test(options.id) ? options.id : ''
  void (id ? openRecord(id) : reload())
})

onShow(() => { if (pageReady.value && !canRenderRoute('recordMood', auth.state)) router?.requireAuthentication('recordMood') })
onBackPress(() => { goBack(); return true })

function localNow() {
  const now = new Date()
  return createMoodDraft(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`,
    `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`,
  )
}
function clearProblem() {
  problemMessage.value = ''; requestId.value = ''; conflict.value = false; conflictLoaded.value = false
  consentRequired.value = false; latestConflictRecord.value = null; moreErrorMessage.value = ''; moreRequestId.value = ''
}
function setDate(event: { detail?: { value?: string } }) { if (event.detail?.value) draft.date = event.detail.value }
function setTime(event: { detail?: { value?: string } }) { if (event.detail?.value) draft.time = event.detail.value }
function faceForLevel(level: number) { return ({ 5: '☺', 4: '🙂', 3: '😐', 2: '🙁', 1: '☹' } as Record<number, string>)[level] ?? '○' }
function formatDate(value: string) { return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }

async function reload() {
  if (!api || !canRenderRoute('recordMood', auth.state)) return
  loadState.value = 'loading'; clearProblem()
  try {
    const page = await api.list({ limit: 30 })
    records.value = page.items; nextCursor.value = page.next_cursor ?? null
    loadState.value = 'ready'; view.value = 'list'
  } catch (error) { applyLoadError(error); loadState.value = 'error' }
}
async function loadMore() {
  if (!api || !nextCursor.value || busy.value) return
  const starting = clearRecordPageError(initialRecordPageState(records.value, nextCursor.value))
  moreErrorMessage.value = ''; moreRequestId.value = ''; busy.value = true
  try {
    const page = await api.list({ limit: 30, cursor: starting.cursor ?? undefined })
    const updated = appendRecordPage(starting, page)
    records.value = updated.items; nextCursor.value = updated.cursor
  } catch (error) {
    applyProblem(error)
    const failed = failRecordPage(starting, problemMessage.value, requestId.value)
    records.value = failed.items; nextCursor.value = failed.cursor
    moreErrorMessage.value = failed.error; moreRequestId.value = failed.requestId
  } finally { busy.value = false }
}
async function openRecord(id: string) {
  if (!api || !canRenderRoute('recordMood', auth.state)) return
  clearProblem(); loadState.value = 'loading'
  try { currentRecord.value = await api.get(id); view.value = 'detail'; loadState.value = 'ready' }
  catch (error) { applyLoadError(error); loadState.value = 'error' }
}
function startCreate() {
  currentRecord.value = null; isEditing.value = false; editingId.value = ''
  Object.assign(draft, localNow()); clearProblem(); formError.value = ''; formErrorField.value = ''; view.value = 'form'
}
function startEdit() {
  if (!currentRecord.value) return
  Object.assign(draft, moodToDraft(currentRecord.value)); isEditing.value = true; editingId.value = currentRecord.value.id
  clearProblem(); formError.value = ''; formErrorField.value = ''; view.value = 'form'
}
function cancelForm() {
  if (currentRecord.value) { Object.assign(draft, createMoodDraft('', '')); view.value = 'detail' }
  else { Object.assign(draft, createMoodDraft('', '')); view.value = 'list' }
  clearProblem(); formError.value = ''; formErrorField.value = ''
}

let submittedSignature = ''
let submittedKey = ''
function getIdempotencyKey(body: unknown): string {
  const signature = JSON.stringify(body)
  if (signature !== submittedSignature) {
    submittedSignature = signature
    submittedKey = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
  }
  return submittedKey
}
async function save() {
  if (!api || busy.value || !canRenderRoute('recordMood', auth.state)) return
  if (conflict.value) {
    problemMessage.value = conflictLoaded.value
      ? '已载入最新版本；请核对后使用“确认基于最新版本保存我的草稿”。'
      : '请先载入服务器最新版本并核对，再决定是否保存本次草稿。'
    return
  }
  clearProblem(); formError.value = ''; formErrorField.value = ''
  const built = buildMoodWrite(draft)
  if (!built.ok) { formError.value = built.message; formErrorField.value = built.field; return }
  if (isEditing.value && (!editingId.value || !currentRecord.value)) { formError.value = '记录尚未载入完成，请重新打开后再编辑。'; return }
  busy.value = true
  try {
    if (!consentApi) {
      consentRequired.value = true
      problemMessage.value = '当前无法核验健康数据处理与心情数据处理授权；为保护资料，本次未提交，草稿已保留。'
      return
    }
    let consentStatuses
    try { consentStatuses = await consentApi.list() }
    catch {
      consentRequired.value = true
      problemMessage.value = '暂时无法核验健康数据处理与心情数据处理授权；本次未提交，草稿已保留。请稍后重试或前往隐私授权设置查看。'
      return
    }
    const requiredConsents = ['health_data_processing', 'mood_data_processing']
    if (requiredConsents.some((type) => !consentStatuses.some((status) => status.consent_type === type && status.granted))) {
      consentRequired.value = true
      problemMessage.value = '新增和修改心情记录需要“健康数据处理”与“心情数据处理”两项授权。请在隐私设置阅读服务端当前告知并分别选择；草稿已保留。不要求 mood_ai_sharing 或 third_party_ai。'
      return
    }
    if (isEditing.value) {
      const patch = buildMoodPatch(draft, currentRecord.value!.record_version)
      if (!patch.ok) { formError.value = patch.message; formErrorField.value = patch.field; return }
      currentRecord.value = await api.update(editingId.value, patch.body)
    } else {
      currentRecord.value = await api.create(built.body, getIdempotencyKey(built.body))
    }
    submittedSignature = ''; submittedKey = ''; consentRequired.value = false; conflict.value = false
    Object.assign(draft, createMoodDraft('', ''))
    view.value = 'detail'; await reloadListAfterWrite()
  } catch (error) {
    applyProblem(error)
    if (error instanceof AppError && error.status === 409 && error.code === 'RECORD_VERSION_CONFLICT') {
      conflict.value = true; conflictLoaded.value = false; latestConflictRecord.value = null
    }
  } finally { busy.value = false }
}
async function reloadListAfterWrite() {
  if (!api) return
  try { const page = await api.list({ limit: 30 }); records.value = page.items; nextCursor.value = page.next_cursor ?? null }
  catch { /* Saved detail remains visible; the list refresh is retryable on return. */ }
}
async function reloadConflict() {
  if (!api || !editingId.value) return
  busy.value = true
  try {
    latestConflictRecord.value = await api.get(editingId.value)
    currentRecord.value = latestConflictRecord.value; conflictLoaded.value = true
    problemMessage.value = '已载入最新服务器版本；核对两侧信息后再明确确认保存。'
    requestId.value = ''
  } catch (error) { applyProblem(error) } finally { busy.value = false }
}
async function confirmConflictSave() { conflict.value = false; await save() }
async function removeRecord() {
  if (!api || !currentRecord.value || busy.value || !canRenderRoute('recordMood', auth.state)) return
  busy.value = true; clearProblem()
  try {
    await api.delete(currentRecord.value.id, currentRecord.value.record_version)
    const deletedId = currentRecord.value.id
    records.value = records.value.filter((record) => record.id !== deletedId)
    deletePrompt.value = false; currentRecord.value = null; view.value = 'list'
    await reloadListAfterWrite()
  } catch (error) { deletePrompt.value = false; applyProblem(error) } finally { busy.value = false }
}
function goBack() {
  if (deletePrompt.value) { deletePrompt.value = false; return }
  if (view.value === 'form') { cancelForm(); return }
  if (view.value === 'detail') { clearProblem(); void reload(); return }
  router?.switchTab('records')
}
function openConsentSettings() { router?.navigate('settings') }
function applyLoadError(error: unknown) {
  if (error instanceof AppError) {
    requestId.value = error.requestId ?? ''
    if (error.status === 404) loadMessage.value = '记录暂时无法找到，可能已被删除。'
    else if (['offline', 'network', 'timeout'].includes(error.kind)) loadMessage.value = '网络暂不可用，请恢复连接后重试。'
    else if (error.status === 401) loadMessage.value = '登录状态已失效，请重新登录。'
    else if (error.status && error.status >= 500) loadMessage.value = '服务暂时不可用，请稍后重试。'
    else loadMessage.value = '暂时无法载入心情记录，请稍后重试。'
  } else { requestId.value = ''; loadMessage.value = '暂时无法载入心情记录，请稍后重试。' }
}
function applyProblem(error: unknown) {
  requestId.value = error instanceof AppError ? error.requestId ?? '' : ''
  conflict.value = false; conflictLoaded.value = false; consentRequired.value = false
  if (error instanceof AppError && error.status === 409 && error.code === 'CONSENT_REQUIRED') {
    consentRequired.value = true
    problemMessage.value = '新增和修改心情记录需要“健康数据处理”与“心情数据处理”两项授权。查看或删除本人已有记录仍可使用；此处不要求 mood_ai_sharing 或 third_party_ai 智能共享授权。草稿已保留。'
  } else if (error instanceof AppError && error.status === 409 && error.code === 'RECORD_VERSION_CONFLICT') {
    problemMessage.value = '记录已在其他位置更新。本次草稿未覆盖服务器内容；载入最新版本并核对后再决定。'
  } else if (error instanceof AppError && error.status === 409) problemMessage.value = '请求与当前记录状态冲突，请检查后重试。'
  else if (error instanceof AppError && error.status === 422) problemMessage.value = '记录字段未通过校验，请检查后重试。'
  else if (error instanceof AppError && error.status === 429) problemMessage.value = '操作过于频繁，请稍后再试。'
  else if (error instanceof AppError && error.status && error.status >= 500) problemMessage.value = '服务暂时不可用，请稍后重试。'
  else if (error instanceof AppError && ['offline', 'network', 'timeout'].includes(error.kind)) problemMessage.value = '网络暂不可用；当前草稿已保留，恢复连接后可重试。'
  else if (error instanceof AppError && error.status === 404) problemMessage.value = '记录暂时无法找到，可能已被删除。'
  else problemMessage.value = '操作未完成，请稍后重试。'
}
</script>

<style lang="scss" scoped>
.mood-page { min-height: 100vh; background: var(--gc-color-canvas); }.mood-shell { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); }.topbar { display: flex; height: 48px; align-items: center; justify-content: space-between; }.back-button,.add-button { display: grid; width: 44px; height: 44px; padding: 0; place-items: center; border: 0; border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 25px; }.add-button { font-size: 24px; }.topbar-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.topbar-spacer { width: 44px; }.intro { display: flex; flex-direction: column; margin: 23px 2px 18px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.page-title { margin-top: 4px; color: var(--gc-color-text); font-size: 27px; font-weight: var(--gc-font-weight-bold); line-height: 1.25; }.subtitle,.muted { margin-top: 5px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.55; }.empty-card,.detail-card,.form-card,.mood-card,.problem-card,.conflict-card,.status-panel { padding: 20px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }.empty-card { display: flex; min-height: 235px; flex-direction: column; align-items: center; justify-content: center; gap: 6px; text-align: center; }.empty-mark { display: grid; width: 48px; height: 48px; margin-bottom: 8px; place-items: center; border-radius: 50%; background: var(--gc-color-yellow); color: var(--gc-color-brand); font-size: 24px; }.card-title,.conflict-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.empty-card :deep(.gc-button) { width: 100%; margin-top: 12px; }.mood-list { display: flex; flex-direction: column; gap: 10px; }.mood-card { display: flex; min-height: 104px; flex-direction: column; gap: 8px; text-align: left; }.card-top { display: flex; justify-content: space-between; gap: 12px; }.card-date { color: var(--gc-color-brand-strong); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }.version,.card-foot { color: var(--gc-color-muted); font-size: 11px; }.mood-summary { color: var(--gc-color-text); font-size: 17px; font-weight: var(--gc-font-weight-semibold); }.card-foot { align-self: flex-end; }.detail-card { display: flex; margin-top: 20px; flex-direction: column; gap: 8px; }.detail-date { color: var(--gc-color-text); font-size: 19px; font-weight: var(--gc-font-weight-bold); }.detail-mood { color: var(--gc-color-brand-strong); font-size: 22px; font-weight: var(--gc-font-weight-semibold); }.detail-divider { height: 1px; margin: 6px 0; background: var(--gc-color-border); }.detail-label { margin-top: 5px; color: var(--gc-color-muted); font-size: 11px; }.detail-value,.detail-note { color: var(--gc-color-text); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; white-space: pre-wrap; }.problem-card { display: flex; margin-top: 12px; flex-direction: column; gap: 7px; border-color: var(--gc-color-danger-border); background: var(--gc-color-danger-pale); color: var(--gc-color-danger); font-size: 12px; line-height: 1.55; }.request-id { color: var(--gc-color-muted); font-size: 10px; overflow-wrap: anywhere; }.conflict-card { display: flex; margin-top: 10px; flex-direction: column; gap: 9px; border-color: var(--gc-color-warning-border); background: var(--gc-color-warning-pale); }.conflict-copy { color: var(--gc-color-text); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }.actions,.form-actions { display: flex; margin-top: 14px; flex-direction: column; gap: 10px; }.intro--form { margin-bottom: 14px; }.field-block { display: flex; margin-bottom: 18px; flex-direction: column; gap: 8px; }.field-label { color: var(--gc-color-text); font-size: 13px; font-weight: var(--gc-font-weight-semibold); }.required,.field-error { color: var(--gc-color-danger); }.picker-control { display: flex; min-height: 50px; align-items: center; padding: 0 13px; border: 1px solid var(--gc-color-border); border-radius: 13px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 14px; }.mood-options { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 7px; }.mood-option { display: flex; min-height: 78px; padding: 7px 2px; border: 1px solid var(--gc-color-border); border-radius: 15px; flex-direction: column; align-items: center; justify-content: center; gap: 6px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 10px; }.mood-option--selected { border: 2px solid var(--gc-color-brand); background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); }.mood-face { font-size: 23px; line-height: 1; }.textarea { width: 100%; min-height: 92px; padding: 12px; border: 1px solid var(--gc-color-border); border-radius: 13px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 14px; line-height: 1.5; }.field-hint,.field-error { font-size: 11px; line-height: 1.5; }.privacy-note { display: block; margin: 8px 0 12px; color: var(--gc-color-muted); font-size: 10px; line-height: 1.6; }.modal-backdrop { position: fixed; inset: 0; z-index: var(--gc-layer-overlay); display: grid; padding: 24px; place-items: center; background: rgba(25, 39, 32, .38); }.confirm-modal { width: 100%; max-width: 360px; padding: 24px; border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-overlay); }.modal-actions { display: flex; margin-top: 18px; flex-direction: column; gap: 8px; }.status-panel { margin-top: 24px; }.auth-pending { display: grid; min-height: 100vh; place-items: center; color: var(--gc-color-muted); }
</style>

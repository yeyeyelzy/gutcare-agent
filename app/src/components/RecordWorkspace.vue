<template>
  <view v-if="pageReady" class="record-page" :data-testid="`record-workspace-${kind}`">
    <view class="record-shell">
      <view class="topbar">
        <button class="back-button" :aria-label="backLabel" data-testid="record-back" @click="goBack">‹</button>
        <text class="topbar-title">{{ titleForView }}</text>
        <button v-if="view === 'list'" class="add-button" aria-label="新增记录" data-testid="record-add" @click="startCreate">＋</button>
        <view v-else class="topbar-spacer" />
      </view>

      <view v-if="loadState === 'loading'" class="status-panel" role="status" aria-live="polite" aria-busy="true">
        <DashboardDataStatus state="loading" test-id="record-loading" />
      </view>
      <view v-else-if="loadState === 'error'" class="status-panel" role="alert">
        <DashboardDataStatus state="error" :message="loadMessage" :retryable="true" :busy="busy" test-id="record-error" @retry="reload" />
        <text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text>
      </view>

      <template v-else-if="view === 'list'">
        <view class="intro"><text class="eyebrow">YOUR JOURNAL</text><text class="page-title">{{ sectionTitle }}</text><text class="subtitle">仅显示本人提交的记录。</text></view>
        <view v-if="records.length === 0" class="empty-card" data-testid="record-empty">
          <view class="empty-mark" aria-hidden="true">○</view>
          <text class="card-title">此范围内暂无记录</text>
          <text class="muted">没有记录不代表没有发生。</text>
          <GcButton label="新增记录" test-id="record-empty-add" @click="startCreate" />
        </view>
        <view v-else class="record-list" data-testid="record-list">
          <button v-for="record in records" :key="record.id" class="record-card" :data-testid="`record-${record.id}`" @click="openRecord(record.id)">
            <view class="card-top"><text class="card-date">{{ formatDate(record.occurred_at) }}</text><text class="version">第 {{ record.record_version }} 版</text></view>
            <text class="record-summary">{{ summarize(record) }}</text>
            <text class="card-foot">{{ kind === 'symptom' ? statusLabel(record) : '本人记录' }}　›</text>
          </button>
          <GcButton v-if="nextCursor" label="载入更多" variant="secondary" :busy="busy" :disabled="busy" test-id="record-more" @click="loadMore" />
          <view v-if="moreErrorMessage" class="problem-card pagination-problem" role="alert" aria-live="polite" data-testid="record-more-error">
            <text>{{ moreErrorMessage }}</text>
            <text v-if="moreRequestId" class="request-id">请求编号：{{ moreRequestId }}</text>
            <GcButton label="重试载入更多" variant="secondary" :busy="busy" :disabled="busy" test-id="record-more-retry" @click="loadMore" />
          </view>
        </view>
      </template>

      <template v-else-if="view === 'detail' && currentRecord">
        <view class="detail-card" data-testid="record-detail">
          <text class="eyebrow">本人记录</text>
          <text class="detail-date">{{ formatDate(currentRecord.occurred_at) }}</text>
          <text class="record-summary record-summary--detail">{{ summarize(currentRecord) }}</text>
          <view class="detail-divider" />
          <text class="detail-label">发生时间</text><text class="detail-value">{{ currentRecord.occurred_at }}</text>
          <text class="detail-label">记录版本</text><text class="detail-value">{{ currentRecord.record_version }}</text>
          <template v-if="kind === 'symptom'">
            <text class="detail-label">状态</text><text class="detail-value">{{ currentSymptomStatus === 'relieved' ? '已缓解' : '仍持续' }}</text>
            <text class="detail-label">状态变更历史</text>
            <view v-if="historyState === 'loading'" role="status">正在载入状态历史…</view>
            <view v-else-if="historyState === 'error'" class="history-error" role="alert">状态历史暂不可用。<button class="inline-action" @click="loadHistory">重试</button></view>
            <view v-else class="history-list" data-testid="symptom-history">
              <text v-for="(event, index) in statusHistory?.events ?? []" :key="`${event.record_version}-${index}`" class="history-event">{{ event.status === 'relieved' ? '已缓解' : '仍持续' }} · {{ formatDate(event.changed_at) }} · 版本 {{ event.record_version }}</text>
            </view>
          </template>
        </view>
        <view v-if="problemMessage" class="problem-card" role="alert"><text>{{ problemMessage }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text><button v-if="conflict" class="inline-action" data-testid="conflict-reload-detail" @click="openRecord(currentRecord.id)">重新载入最新记录</button></view>
        <view class="actions"><GcButton label="编辑" test-id="record-edit" @click="startEdit" /><GcButton label="删除记录" variant="danger" test-id="record-delete" @click="deletePrompt = true" /></view>
      </template>

      <template v-else-if="view === 'form'">
        <view class="intro intro--form"><text class="eyebrow">{{ isEditing ? 'EDIT ENTRY' : 'NEW ENTRY' }}</text><text class="page-title">{{ isEditing ? '编辑记录' : `新增${sectionTitle}` }}</text><text class="subtitle">填写你确认的信息；不需要上传图片。</text></view>
        <view v-if="problemMessage" class="problem-card" role="alert"><text>{{ problemMessage }}</text><text v-if="requestId" class="request-id">请求编号：{{ requestId }}</text><button v-if="conflict" class="inline-action" data-testid="conflict-reload" @click="reloadConflict">重新载入最新记录</button></view>
        <view class="form-card">
          <view class="field-block">
            <text class="field-label">发生日期与时间 <text class="required">*</text></text>
            <picker mode="date" :value="draft.date" @change="setDate"><view class="picker-control" aria-label="选择发生日期">{{ draft.date || '选择日期' }}</view></picker>
            <picker mode="time" :value="draft.time" @change="setTime"><view class="picker-control" aria-label="选择发生时间">{{ draft.time || '选择时间' }}</view></picker>
            <text v-if="formErrorField === 'date'" class="field-error" role="alert">{{ formError }}</text>
          </view>

          <template v-if="kind === 'diet'">
            <view class="field-block"><text class="field-label">餐次（可选）</text><picker :range="mealLabels" @change="setMeal"><view class="picker-control">{{ draft.mealType ? mealLabels[mealValues.indexOf(draft.mealType)] : '选择餐次' }}</view></picker></view>
            <view class="field-block"><text class="field-label">饮食描述</text><textarea v-model="draft.description" class="textarea" maxlength="4000" placeholder="例如：米饭、蔬菜" aria-label="饮食描述" data-testid="diet-description" /></view>
            <view class="field-block"><text class="field-label">食物项（可选，每行一项）</text><textarea v-model="draft.itemNames" class="textarea" maxlength="4000" placeholder="每行填写一项食物" aria-label="食物项，每行一项" data-testid="diet-items" /></view>
            <text v-if="formErrorField === 'description'" class="field-error" role="alert">{{ formError }}</text>
          </template>

          <template v-else-if="kind === 'bowel'">
            <view class="field-block"><text class="field-label">Bristol 类型（可选）</text><picker :range="bristolLabels" @change="setBristol"><view class="picker-control">{{ draft.bristol || '未确定' }}</view></picker><text class="field-hint">选择 1–7；未确定时可留空。</text></view>
            <view class="field-block"><text class="field-label">备注（可选）</text><textarea v-model="draft.bowelNotes" class="textarea" maxlength="1000" placeholder="只记录你确认的情况" aria-label="排便备注" data-testid="bowel-notes" /></view>
            <text v-if="formErrorField === 'bristol'" class="field-error" role="alert">{{ formError }}</text>
          </template>

          <template v-else>
            <view class="field-block"><text class="field-label">症状（选择 1–30 项） <text class="required">*</text></text><view class="choice-grid"><button v-for="option in symptomOptions" :key="option.code" class="choice" :class="{ 'choice--selected': draft.symptomCodes.includes(option.code) }" :aria-pressed="draft.symptomCodes.includes(option.code)" :data-testid="`symptom-${option.code}`" @click="toggleSymptom(option.code)">{{ option.label }}</button></view><text v-if="formErrorField === 'symptomCodes'" class="field-error" role="alert">{{ formError }}</text></view>
            <view v-if="draft.symptomCodes.includes('other')" class="field-block"><text class="field-label">其他症状描述 <text class="required">*</text></text><input v-model="draft.otherDescription" class="input-control" maxlength="160" placeholder="最多 160 字" aria-label="其他症状描述" data-testid="symptom-other" /><text v-if="formErrorField === 'otherDescription'" class="field-error" role="alert">{{ formError }}</text></view>
            <view class="field-block"><text class="field-label">主观严重程度（0–10，可选）</text><input v-model="draft.severity" class="input-control" type="number" aria-label="主观严重程度，0到10" data-testid="symptom-severity" /><text class="field-hint">这是你的主观评分，不是疾病风险等级。</text><text v-if="formErrorField === 'severity'" class="field-error" role="alert">{{ formError }}</text></view>
            <view class="field-block"><text class="field-label">持续时间（分钟，可选）</text><input v-model="draft.duration" class="input-control" type="number" aria-label="持续时间，分钟" data-testid="symptom-duration" /><text v-if="formErrorField === 'duration'" class="field-error" role="alert">{{ formError }}</text></view>
            <view class="field-block"><text class="field-label">当前状态</text><view class="choice-grid"><button class="choice" :class="{ 'choice--selected': draft.symptomStatus === 'ongoing' }" :aria-pressed="draft.symptomStatus === 'ongoing'" @click="draft.symptomStatus = 'ongoing'">仍持续</button><button class="choice" :class="{ 'choice--selected': draft.symptomStatus === 'relieved' }" :aria-pressed="draft.symptomStatus === 'relieved'" @click="draft.symptomStatus = 'relieved'">已缓解</button></view></view>
            <view class="field-block"><text class="field-label">备注（可选）</text><textarea v-model="draft.notes" class="textarea" maxlength="2000" placeholder="避免填写无关隐私信息" aria-label="症状备注" data-testid="symptom-notes" /></view>
          </template>
          <view class="form-actions"><GcButton :label="isEditing ? '保存修改' : '保存记录'" :busy="busy" :disabled="busy" test-id="record-save" @click="save" /><GcButton label="取消" variant="secondary" :disabled="busy" test-id="record-cancel" @click="cancelForm" /></view>
          <text class="privacy-note">记录仅保存你填写的信息。系统不会从文字推断诊断或病因。</text>
        </view>
      </template>

      <view v-if="deletePrompt" class="modal-backdrop" role="presentation" @click.self="deletePrompt = false">
        <view class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete-title" data-testid="delete-confirm">
          <text id="delete-title" class="card-title">删除这条记录？</text><text class="muted">删除后会立即从列表和后续记录视图中隐藏。</text>
          <view class="modal-actions"><GcButton label="取消" variant="secondary" :disabled="busy" test-id="delete-cancel" @click="deletePrompt = false" /><GcButton label="确认删除" variant="danger" :busy="busy" :disabled="busy" test-id="delete-confirm-action" @click="removeRecord" /></view>
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
import { appRouterKey, recordsApiKey } from '../api/context'
import type { HealthRecord, RecordType } from '../api/openapiTypes'
import { buildRecordWrite, EMPTY_RECORD_DRAFT, recordToDraft, SYMPTOM_OPTIONS } from '../api/recordForm'
import type { RecordDraft, SymptomCode } from '../api/recordForm'
import { appendRecordPage, clearRecordPageError, failRecordPage, initialRecordPageState } from '../api/recordPagination'
import { canRenderRoute } from '../navigation/routes'
import type { RecordWorkspaceRouteName } from '../navigation/routes'
import { useAuthStore } from '../stores/auth'
import DashboardDataStatus from './DashboardDataStatus.vue'
import GcButton from './GcButton.vue'

const props = defineProps<{ kind: 'diet' | 'bowel' | 'symptom'; recordType: RecordType; routeName: RecordWorkspaceRouteName }>()
const auth = useAuthStore()
const router = inject(appRouterKey)
const api = inject(recordsApiKey)
const pageReady = ref(false)
const busy = ref(false)
const view = ref<'list' | 'detail' | 'form'>('list')
const loadState = ref<'loading' | 'ready' | 'error'>('loading')
const records = ref<HealthRecord[]>([])
const currentRecord = ref<HealthRecord | null>(null)
const nextCursor = ref<string | null>(null)
const statusHistory = ref<{ symptom_record_id: string; current_status: 'ongoing' | 'relieved'; events: Array<{ status: 'ongoing' | 'relieved'; record_version: number; changed_at: string }> } | null>(null)
const historyState = ref<'loading' | 'ready' | 'error'>('ready')
const deletePrompt = ref(false)
const problemMessage = ref('')
const moreErrorMessage = ref('')
const moreRequestId = ref('')
const loadMessage = ref('暂时无法载入记录，请检查网络后重试。')
const requestId = ref('')
const conflict = ref(false)
const formError = ref('')
const formErrorField = ref<keyof RecordDraft | ''>('')
const isEditing = ref(false)
const editingId = ref('')
const draft = reactive<RecordDraft>({ ...EMPTY_RECORD_DRAFT, ...localNow() })
const mealValues = ['breakfast', 'lunch', 'dinner', 'snack', 'other'] as const
const mealLabels = ['早餐', '午餐', '晚餐', '加餐', '其他']
const bristolLabels = ['未确定', '1', '2', '3', '4', '5', '6', '7']
const symptomOptions = SYMPTOM_OPTIONS
const sectionTitle = computed(() => ({ diet: '饮食记录', bowel: '排便记录', symptom: '症状记录' }[props.kind]))
const titleForView = computed(() => view.value === 'list' ? sectionTitle.value : view.value === 'detail' ? '记录详情' : isEditing.value ? '编辑记录' : `新增${sectionTitle.value}`)
const backLabel = computed(() => view.value === 'list' ? '返回记录' : '返回上一页')
const currentSymptomStatus = computed(() => statusHistory.value?.current_status ?? (currentRecord.value?.payload as { symptom_status?: string } | undefined)?.symptom_status)

onLoad((options) => {
  if (!canRenderRoute(props.routeName, auth.state)) {
    router?.requireAuthentication(props.routeName)
    return
  }
  pageReady.value = true
  const id = typeof options?.id === 'string' && /^[0-9a-f-]{36}$/i.test(options.id) ? options.id : ''
  void (id ? openRecord(id) : reload())
})

onShow(() => { if (pageReady.value && !canRenderRoute(props.routeName, auth.state)) router?.requireAuthentication(props.routeName) })
onBackPress(() => { goBack(); return true })

function localNow(): Pick<RecordDraft, 'date' | 'time'> {
  const now = new Date()
  return { date: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`, time: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}` }
}
function setDate(event: { detail?: { value?: string } }) { if (event.detail?.value) draft.date = event.detail.value }
function setTime(event: { detail?: { value?: string } }) { if (event.detail?.value) draft.time = event.detail.value }
function setMeal(event: { detail?: { value?: string | number } }) { const index = Number(event.detail?.value); draft.mealType = mealValues[index] ?? '' }
function setBristol(event: { detail?: { value?: string | number } }) { const index = Number(event.detail?.value); draft.bristol = index > 0 ? String(index) : '' }
function clearProblem() { problemMessage.value = ''; requestId.value = ''; conflict.value = false; moreErrorMessage.value = ''; moreRequestId.value = '' }

async function reload() {
  if (!api || !canRenderRoute(props.routeName, auth.state)) return
  loadState.value = 'loading'; clearProblem()
  try {
    const result = await api.list(props.recordType, { limit: 30 })
    records.value = result.items
    nextCursor.value = result.next_cursor ?? null
    loadState.value = 'ready'; view.value = 'list'
  } catch (error) { applyLoadError(error); loadState.value = 'error' }
}
async function loadMore() {
  if (!api || !nextCursor.value || busy.value) return
  const startingState = clearRecordPageError(initialRecordPageState(records.value, nextCursor.value))
  moreErrorMessage.value = ''; moreRequestId.value = ''
  busy.value = true
  try {
    const result = await api.list(props.recordType, { limit: 30, cursor: startingState.cursor ?? undefined })
    const updated = appendRecordPage(startingState, result)
    records.value = updated.items
    nextCursor.value = updated.cursor
  } catch (error) {
    applyProblem(error)
    const failed = failRecordPage(startingState, problemMessage.value, requestId.value)
    records.value = failed.items
    nextCursor.value = failed.cursor
    moreErrorMessage.value = failed.error
    moreRequestId.value = failed.requestId
  } finally { busy.value = false }
}
async function openRecord(id: string) {
  if (!api || !canRenderRoute(props.routeName, auth.state)) return
  loadState.value = 'loading'; clearProblem()
  try {
    currentRecord.value = await api.get(props.recordType, id)
    view.value = 'detail'; loadState.value = 'ready'
    if (props.kind === 'symptom') void loadHistory()
  } catch (error) { applyLoadError(error); loadState.value = 'error' }
}
async function loadHistory() {
  if (!api || !currentRecord.value || props.kind !== 'symptom') return
  historyState.value = 'loading'
  try { statusHistory.value = await api.symptomStatusHistory(currentRecord.value.id); historyState.value = 'ready' }
  catch { statusHistory.value = null; historyState.value = 'error' }
}
async function startCreate() {
  currentRecord.value = null; isEditing.value = false; editingId.value = ''; resetDraft(); clearProblem(); view.value = 'form'
}
function startEdit() {
  if (!currentRecord.value) return
  isEditing.value = true; editingId.value = currentRecord.value.id
  Object.assign(draft, recordToDraft(props.recordType, currentRecord.value)); clearProblem(); view.value = 'form'
}
function resetDraft() { Object.assign(draft, EMPTY_RECORD_DRAFT, localNow()); formError.value = ''; formErrorField.value = '' }
function cancelForm() { clearProblem(); view.value = currentRecord.value ? 'detail' : 'list' }
function toggleSymptom(code: SymptomCode) { draft.symptomCodes = draft.symptomCodes.includes(code) ? draft.symptomCodes.filter((value) => value !== code) : [...draft.symptomCodes, code] }

let submittedSignature = ''
let submittedKey = ''
function idempotencyKey(body: unknown): string {
  const signature = JSON.stringify(body)
  if (signature !== submittedSignature) {
    submittedSignature = signature
    submittedKey = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
  }
  return submittedKey
}
async function save() {
  if (!api || busy.value || !canRenderRoute(props.routeName, auth.state)) return
  clearProblem(); formError.value = ''; formErrorField.value = ''
  const result = buildRecordWrite(props.recordType, draft)
  if (!result.ok) { formError.value = result.message; formErrorField.value = result.field; return }
  if (isEditing.value && (!editingId.value || !currentRecord.value)) {
    formError.value = '记录尚未加载完成，请重新打开后再编辑。'; return
  }
  busy.value = true
  try {
    currentRecord.value = isEditing.value && editingId.value
      ? await api.update(props.recordType, editingId.value, { ...result.body, record_version: currentRecord.value!.record_version })
      : await api.create(props.recordType, result.body, idempotencyKey(result.body))
    submittedSignature = ''; submittedKey = ''
    view.value = 'detail'; await reloadListAfterWrite()
    if (props.kind === 'symptom') void loadHistory()
  } catch (error) { applyProblem(error) } finally { busy.value = false }
}
async function reloadListAfterWrite() {
  if (!api) return
  try { const page = await api.list(props.recordType, { limit: 30 }); records.value = page.items; nextCursor.value = page.next_cursor ?? null }
  catch { /* Keep the successful detail visible; list can be refreshed on return. */ }
}
async function removeRecord() {
  if (!api || !currentRecord.value || busy.value || !canRenderRoute(props.routeName, auth.state)) return
  busy.value = true; clearProblem()
  try {
    await api.delete(props.recordType, currentRecord.value.id, currentRecord.value.record_version)
    deletePrompt.value = false; currentRecord.value = null; view.value = 'list'; await reload()
  } catch (error) { deletePrompt.value = false; applyProblem(error) } finally { busy.value = false }
}
async function reloadConflict() {
  if (!editingId.value) return
  const id = editingId.value; clearProblem(); view.value = 'detail'; await openRecord(id)
}
function goBack() {
  if (deletePrompt.value) { deletePrompt.value = false; return }
  if (view.value === 'form') { cancelForm(); return }
  if (view.value === 'detail') { clearProblem(); void reload(); return }
  router?.switchTab('records')
}
function applyLoadError(error: unknown) {
  applyProblem(error)
  loadMessage.value = error instanceof AppError && error.kind === 'offline' ? '当前处于离线状态，记录未能载入。' : '暂时无法载入记录，请稍后重试。'
}
function applyProblem(error: unknown) {
  if (error instanceof AppError && error.status === 409 && error.code === 'RECORD_VERSION_CONFLICT') {
    conflict.value = true
    problemMessage.value = '记录已在其他位置更新。当前内容未覆盖服务器数据；请重新载入后再决定是否编辑。'
  } else if (error instanceof AppError && error.status === 422) problemMessage.value = '部分内容未通过校验，请检查填写后重试。'
  else if (error instanceof AppError && error.status === 429) problemMessage.value = '操作过于频繁，请稍后再试。'
  else if (error instanceof AppError && error.status && error.status >= 500) problemMessage.value = '服务暂时不可用，已保留当前内容，请稍后重试。'
  else if (error instanceof AppError && ['offline', 'network', 'timeout'].includes(error.kind)) problemMessage.value = '网络暂不可用，已保留当前内容；恢复连接后可重试。'
  else if (error instanceof AppError && error.status === 404) problemMessage.value = '记录暂时无法找到，可能已被删除。'
  else problemMessage.value = '操作未完成，请稍后重试。'
  requestId.value = error instanceof AppError ? error.requestId ?? '' : ''
}
function formatDate(value: string) { return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }
function summarize(record: HealthRecord): string {
  const payload = record.payload as Record<string, unknown>
  if (props.kind === 'diet') {
    const text = typeof payload.text_description === 'string' ? payload.text_description : ''
    const items = Array.isArray(payload.items) ? payload.items.map((item) => typeof item === 'object' && item && 'name' in item ? String(item.name) : '').filter(Boolean).join('、') : ''
    return text || items || '饮食记录'
  }
  if (props.kind === 'bowel') return typeof payload.bristol_type === 'number' ? `Bristol ${payload.bristol_type} 型` : '排便记录（类型未确定）'
  const items = Array.isArray(payload.items) ? payload.items.map((item) => {
    if (typeof item !== 'object' || !item || !('symptom_code' in item)) return ''
    return symptomOptions.find((option) => option.code === item.symptom_code)?.label ?? '症状'
  }).filter(Boolean).join('、') : ''
  return items || '症状记录'
}
function statusLabel(record: HealthRecord) { return (record.payload as { symptom_status?: string }).symptom_status === 'relieved' ? '已缓解' : '仍持续' }
</script>

<style lang="scss" scoped>
.record-page { min-height: 100vh; background: var(--gc-color-canvas); }.record-shell { width: 100%; max-width: 430px; min-height: 100vh; margin: 0 auto; padding: calc(env(safe-area-inset-top, 0px) + 10px) 20px calc(env(safe-area-inset-bottom, 0px) + 24px); }.topbar { display: flex; height: 48px; align-items: center; justify-content: space-between; }.back-button,.add-button { display: grid; width: 44px; height: 44px; padding: 0; place-items: center; border: 0; border-radius: 50%; background: var(--gc-color-surface); color: var(--gc-color-brand-strong); font-size: 25px; }.add-button { font-size: 24px; }.topbar-title { color: var(--gc-color-text); font-size: 15px; font-weight: var(--gc-font-weight-semibold); }.topbar-spacer { width: 44px; }.intro { display: flex; flex-direction: column; margin: 23px 2px 18px; }.eyebrow { color: var(--gc-color-brand); font-size: 10px; font-weight: var(--gc-font-weight-semibold); letter-spacing: 1px; }.page-title { margin-top: 4px; color: var(--gc-color-text); font-size: 27px; font-weight: var(--gc-font-weight-bold); line-height: 1.25; }.subtitle,.muted { margin-top: 5px; color: var(--gc-color-muted); font-size: 12px; line-height: 1.55; }.empty-card,.detail-card,.form-card,.record-card,.problem-card,.status-panel { padding: 20px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-card); }.empty-card { display: flex; min-height: 235px; flex-direction: column; align-items: center; justify-content: center; gap: 6px; text-align: center; }.empty-mark { display: grid; width: 48px; height: 48px; margin-bottom: 8px; place-items: center; border-radius: 50%; background: var(--gc-color-sage-pale); color: var(--gc-color-brand); font-size: 24px; }.card-title { color: var(--gc-color-text); font-size: 16px; font-weight: var(--gc-font-weight-semibold); }.empty-card :deep(.gc-button) { width: 100%; margin-top: 12px; }.record-list { display: flex; flex-direction: column; gap: 10px; }.record-card { display: flex; min-height: 104px; flex-direction: column; gap: 8px; text-align: left; }.card-top { display: flex; justify-content: space-between; gap: 12px; }.card-date { color: var(--gc-color-brand-strong); font-size: 12px; font-weight: var(--gc-font-weight-semibold); }.version,.card-foot { color: var(--gc-color-muted); font-size: 11px; }.record-summary { color: var(--gc-color-text); font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; }.card-foot { align-self: flex-end; }.detail-card { display: flex; margin-top: 20px; flex-direction: column; gap: 8px; }.detail-date { color: var(--gc-color-text); font-size: 20px; font-weight: var(--gc-font-weight-bold); }.record-summary--detail { margin: 6px 0; }.detail-divider { height: 1px; margin: 6px 0; background: var(--gc-color-border); }.detail-label { margin-top: 5px; color: var(--gc-color-muted); font-size: 11px; }.detail-value { color: var(--gc-color-text); font-size: 13px; overflow-wrap: anywhere; }.history-list { display: flex; flex-direction: column; gap: 7px; }.history-event { color: var(--gc-color-text); font-size: 12px; }.history-error,.problem-card { color: var(--gc-color-danger); font-size: 12px; line-height: 1.55; }.problem-card { display: flex; margin-top: 12px; flex-direction: column; gap: 7px; border-color: var(--gc-color-danger-border); background: var(--gc-color-danger-pale); }.request-id { color: var(--gc-color-muted); font-size: 10px; overflow-wrap: anywhere; }.inline-action { min-height: 44px; padding: 0 8px; border: 0; background: transparent; color: var(--gc-color-brand-strong); font-size: 12px; text-decoration: underline; }.actions,.form-actions { display: flex; margin-top: 14px; flex-direction: column; gap: 10px; }.intro--form { margin-bottom: 14px; }.field-block { display: flex; margin-bottom: 17px; flex-direction: column; gap: 7px; }.field-label { color: var(--gc-color-text); font-size: 13px; font-weight: var(--gc-font-weight-semibold); }.required,.field-error { color: var(--gc-color-danger); }.picker-control,.input-control { display: flex; min-height: 50px; align-items: center; padding: 0 13px; border: 1px solid var(--gc-color-border); border-radius: 13px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 14px; }.textarea { width: 100%; min-height: 92px; padding: 12px; border: 1px solid var(--gc-color-border); border-radius: 13px; background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 14px; line-height: 1.5; }.field-hint,.field-error { font-size: 11px; line-height: 1.5; }.choice-grid { display: flex; flex-wrap: wrap; gap: 8px; }.choice { min-height: 44px; padding: 0 13px; border: 1px solid var(--gc-color-border); border-radius: var(--gc-radius-pill); background: var(--gc-color-surface); color: var(--gc-color-text); font-size: 12px; }.choice--selected { border-color: var(--gc-color-brand); background: var(--gc-color-sage-pale); color: var(--gc-color-brand-strong); }.privacy-note { display: block; margin-top: 13px; color: var(--gc-color-muted); font-size: 10px; line-height: 1.6; }.modal-backdrop { position: fixed; inset: 0; z-index: var(--gc-layer-overlay); display: grid; padding: 24px; place-items: center; background: rgba(25, 39, 32, .38); }.confirm-modal { width: 100%; max-width: 360px; padding: 24px; border-radius: var(--gc-radius-lg); background: var(--gc-color-surface); box-shadow: var(--gc-shadow-overlay); }.modal-actions { display: flex; margin-top: 18px; flex-direction: column; gap: 8px; }.status-panel { margin-top: 24px; }.auth-pending { display: grid; min-height: 100vh; place-items: center; color: var(--gc-color-muted); }
</style>

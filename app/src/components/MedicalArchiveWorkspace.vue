<template>
  <view v-if="authorized" class="archive-page">
    <view class="archive-shell">
      <view class="topbar">
        <button class="back-button" aria-label="返回" data-testid="medical-archive-back" @click="goBack">‹</button>
        <text class="topbar-title">{{ isDetail ? '检查报告详情' : '健康档案' }}</text>
        <view class="topbar-spacer" />
      </view>

      <template v-if="isDetail">
        <view v-if="detailLoading && !document" class="state-panel" role="status" data-testid="medical-document-loading">正在读取档案…</view>
        <view v-else-if="detailError && !document" class="state-panel" data-testid="medical-document-error">
          <text class="state-title">暂时无法读取档案</text><text class="state-copy">{{ detailError }}</text>
          <GcButton label="重试" test-id="medical-document-retry" @click="loadDetail" />
        </view>
        <view v-else-if="document" class="document-detail" data-testid="medical-document-detail">
          <view class="detail-card">
            <view class="file-mark" aria-hidden="true">▤</view>
            <text class="document-title">{{ document.original_name }}</text>
            <text class="status-line">{{ documentTypeLabel(document.document_type) }} · {{ fileStatusLabel(document.file_status) }}</text>
            <view class="detail-row"><text class="detail-label">处理方式</text><text class="detail-value">{{ document.processing_mode === 'store_only' ? '仅存储' : '提交解析' }}</text></view>
            <view class="detail-row"><text class="detail-label">解析状态</text><text class="detail-value">{{ parseStatusLabel(document.parse_status) }}</text></view>
            <view v-if="document.processing_mode === 'analyze'" class="detail-row"><text class="detail-label">解析结果</text><text class="detail-value" data-testid="medical-document-parse-outcome">{{ parseOutcomeLabel(document) || '等待解析结果' }}</text></view>
            <view v-if="document.processing_mode === 'analyze' && parseReasonLabel(document)" class="detail-row"><text class="detail-label">结果说明</text><text class="detail-value">{{ parseReasonLabel(document) }}</text></view>
            <view class="detail-row"><text class="detail-label">医疗机构</text><text class="detail-value">{{ document.hospital_name || '未填写' }}</text></view>
            <view class="detail-row"><text class="detail-label">报告日期</text><text class="detail-value">{{ document.document_date || '未填写' }}</text></view>
            <view class="detail-row detail-row--notes"><text class="detail-label">备注</text><text class="detail-value">{{ document.notes || '未填写' }}</text></view>
          </view>
          <text v-if="detailError" class="inline-error" role="alert" data-testid="medical-document-detail-refresh-error">{{ detailError }}</text>
          <MedicalCandidateReview
            v-if="candidateSectionVisible"
            :key="candidatePanelGeneration"
            :candidates="candidates"
            :loading="candidateLoading"
            :error="candidateError"
            :conflict-message="candidateConflict"
            :busy-candidate-id="busyCandidateId"
            @refresh="refreshCandidatesForPage"
            @decide="decideCandidate"
          />
          <view class="action-stack">
            <GcButton label="预览文件" :busy="previewBusy" :disabled="document.file_status !== 'available' || previewBusy" test-id="medical-document-preview" @click="preview" />
            <GcButton label="删除档案" variant="danger" :busy="deleting" :disabled="document.file_status !== 'available' || deleting" test-id="medical-document-delete" @click="confirmDelete" />
          </view>
          <text class="safety-note">解析结果仅供本人逐项核对；候选不代表已确认事实。此页面不会自动生成诊断或处方。</text>
        </view>
      </template>

      <template v-else>
        <view class="page-intro"><text class="eyebrow">YOUR HEALTH FILES</text><text class="page-title">健康档案</text><text class="page-subtitle">安全保存本人医疗资料；提交解析不会自动确认任何医疗事实。</text></view>
        <view class="upload-card" data-testid="medical-document-upload">
          <text class="section-title">添加医疗资料</text>
          <text class="section-caption">PDF ≤ 20 MiB；JPEG/PNG ≤ 10 MiB。服务器仍会校验真实文件内容与安全扫描。</text>
          <GcButton :label="selectedFile ? '重新选择文件' : '选择文件'" variant="secondary" :disabled="uploadBusy" test-id="medical-document-pick" @click="pickFile" />
          <view v-if="selectedFile" class="selected-file" data-testid="medical-document-selected-file"><text class="selected-file-name">{{ selectedFile.name }}</text><text class="selected-file-meta">{{ formatBytes(selectedFile.sizeBytes) }} · {{ mimeLabel(selectedFile.contentType) }}</text></view>
          <view class="field"><text class="field-label">资料类型</text><picker :range="documentTypeLabels" :value="typeIndex" @change="onTypeChange"><view class="picker-value" data-testid="medical-document-type">{{ documentTypeLabels[typeIndex] }}　⌄</view></picker></view>
          <view class="field"><text class="field-label">医疗机构（选填）</text><input v-model="hospitalName" maxlength="160" class="input" aria-label="医疗机构" data-testid="medical-document-hospital" /></view>
          <view class="field"><text class="field-label">报告日期（选填）</text><picker mode="date" :value="documentDate || undefined" @change="onDateChange"><view class="picker-value" data-testid="medical-document-date">{{ documentDate || '选择日期' }}　⌄</view></picker></view>
          <view class="field"><text class="field-label">备注（选填）</text><textarea v-model="notes" maxlength="1000" class="notes-input" aria-label="备注" data-testid="medical-document-notes" /></view>
          <view class="mode-group" role="group" aria-label="处理方式">
            <button class="mode-option" :class="{ 'mode-option--selected': processingMode === 'store_only' }" data-testid="medical-document-mode-store" @click="processingMode = 'store_only'"><text class="mode-title">仅存储</text><text class="mode-copy">保存文件，不提交解析。</text></button>
            <button class="mode-option" :class="{ 'mode-option--selected': processingMode === 'analyze' }" data-testid="medical-document-mode-analyze" @click="processingMode = 'analyze'"><text class="mode-title">提交解析</text><text class="mode-copy">需当前健康数据与第三方 AI 授权。</text></button>
          </view>
          <text class="privacy-note">未授权时后端会拒绝提交解析；APP 不会连接 Agent。解析结果需要本人逐字段确认后才成为事实。</text>
          <view v-if="uploadError" class="inline-error" role="alert" data-testid="medical-document-upload-error">{{ uploadError }}</view>
          <view v-if="uploadBusy" class="upload-progress" role="status" data-testid="medical-document-upload-progress">{{ uploadStep }}</view>
          <GcButton label="安全上传并保存档案" :busy="uploadBusy" :disabled="uploadBusy || !selectedFile" test-id="medical-document-save" @click="saveDocument" />
        </view>

        <view class="list-heading"><text class="section-title">本人档案</text><view class="list-actions"><button class="refresh-button" data-testid="medical-fact-conflicts-open" @click="router?.navigate('medicalFactConflicts')">待核对冲突</button><button class="refresh-button" :disabled="listLoading" data-testid="medical-document-refresh" @click="loadFirstPage">刷新</button></view></view>
        <view v-if="listLoading && documents.length === 0" class="state-panel" role="status" data-testid="medical-document-list-loading">正在载入档案…</view>
        <view v-else-if="listError && documents.length === 0" class="state-panel" data-testid="medical-document-list-error"><text class="state-title">档案暂不可用</text><text class="state-copy">{{ listError }}</text><GcButton label="重试" test-id="medical-document-list-retry" @click="loadFirstPage" /></view>
        <view v-else-if="documents.length === 0" class="state-panel" data-testid="medical-document-empty"><text class="empty-mark" aria-hidden="true">▤</text><text class="state-title">暂无医疗档案</text><text class="state-copy">添加本人检查资料后，这里会显示真实档案。</text></view>
        <view v-else class="document-list" data-testid="medical-document-list">
          <text v-if="listError" class="inline-error" role="alert" data-testid="medical-document-refresh-error">{{ listError }}</text>
          <button v-for="item in documents" :key="item.id" class="document-row" :class="{ 'document-row--deleting': item.file_status === 'deleting' }" :disabled="item.file_status === 'deleting'" :data-testid="`medical-document-row-${item.id}`" @click="router?.navigateMedicalDocumentDetail(item.id)">
            <view class="row-icon" aria-hidden="true">▤</view><view class="row-copy"><text class="row-title">{{ item.original_name }}</text><text class="row-meta">{{ documentTypeLabel(item.document_type) }} · {{ item.document_date || '日期未填写' }}</text><text class="row-status">{{ item.file_status === 'deleting' ? '正在删除' : parseStatusLabel(item.parse_status) }}</text></view><text class="chevron" aria-hidden="true">›</text>
          </button>
          <text v-if="appendError" class="inline-error" role="alert" data-testid="medical-document-append-error">{{ appendError }}</text>
          <GcButton v-if="nextCursor" label="加载更多" variant="secondary" :busy="appendLoading" :disabled="appendLoading" test-id="medical-document-load-more" @click="loadMore" />
        </view>
      </template>
      <text v-if="!isDetail" class="safety-note safety-note--bottom">档案仅对当前登录账户开放。删除会立即从档案列表和预览中隐藏。</text>
    </view>
  </view>
  <view v-else class="archive-startup" role="status" data-testid="medical-archive-auth-gate">正在确认登录状态…</view>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { onBackPress, onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { medicalDocumentPreviewKey, medicalDocumentsApiKey } from '../api/context'
import { useAuthStore } from '../stores/auth'
import { AppError } from '../api/errors'
import { pickMedicalFile, preflightMedicalFile, bytesMatchDeclaredSize } from '../api/medicalDocumentFiles'
import { nativeMedicalFilePicker } from '../api/medicalDocumentNativePicker'
import { canRenderRoute } from '../navigation/routes'
import { appRouterKey } from '../api/context'
import type { MedicalCandidateDecision, MedicalDocument, MedicalDocumentCreate, MedicalFieldCandidate } from '../api/openapiTypes'
import { parseOutcomeLabel as getParseOutcomeLabel, parseReasonLabel as getParseReasonLabel, safeCandidateForDisplay } from '../api/medicalCandidateReview'
import GcButton from './GcButton.vue'
import MedicalCandidateReview from './MedicalCandidateReview.vue'

const api = inject(medicalDocumentsApiKey)
const previewAdapter = inject(medicalDocumentPreviewKey)
const router = inject(appRouterKey)
const auth = useAuthStore()
const routeDocumentId = ref('')
const isDetail = computed(() => Boolean(routeDocumentId.value))
const authorized = computed(() => canRenderRoute(isDetail.value ? 'medicalDocumentDetail' : 'healthArchive', auth.state))
const documents = ref<MedicalDocument[]>([])
const document = ref<MedicalDocument | null>(null)
const candidates = ref<MedicalFieldCandidate[]>([])
const nextCursor = ref<string | null>(null)
const listLoading = ref(false)
const appendLoading = ref(false)
const detailLoading = ref(false)
const uploadBusy = ref(false)
const previewBusy = ref(false)
const deleting = ref(false)
const listError = ref('')
const appendError = ref('')
const detailError = ref('')
const candidateError = ref('')
const candidateConflict = ref('')
const candidateLoading = ref(false)
const busyCandidateId = ref<string | null>(null)
const candidatePanelGeneration = ref(0)
const uploadError = ref('')
const selectedFile = ref<Awaited<ReturnType<typeof pickMedicalFile>> | null>(null)
const hospitalName = ref('')
const documentDate = ref('')
const notes = ref('')
const processingMode = ref<'store_only' | 'analyze'>('store_only')
const documentTypes: MedicalDocument['document_type'][] = ['outpatient_record', 'discharge_summary', 'diagnosis_certificate', 'lab_report', 'prescription', 'other']
const documentTypeLabels = ['门诊记录', '出院小结', '诊断证明', '检验报告', '处方', '其他']
const typeIndex = ref(3)
let cursor: string | null = null
let pageGeneration = 0
let active = false
let previewVisible = false
let uploadIdempotencyKey = ''
let activeUpload: { uploadId: string; uploadUrl: string; uploaded: boolean; fileObjectId: string | null; file: NonNullable<typeof selectedFile.value> } | null = null
let documentCreateAttempted = false
let candidateNeedsRefresh = false
let detailNeedsRefresh = false
const candidateSectionVisible = computed(() => Boolean(document.value && document.value.processing_mode === 'analyze' && (document.value.parse_outcome === 'extracted' || document.value.parse_status === 'needs_confirmation' || document.value.parse_status === 'confirmed')))

const isCurrent = (generation: number) => active && pageGeneration === generation

onLoad((options) => {
  routeDocumentId.value = typeof options?.document_id === 'string' ? options.document_id : ''
  const routeName = isDetail.value ? 'medicalDocumentDetail' : 'healthArchive'
  if (!canRenderRoute(routeName, auth.state)) {
    if (isDetail.value && isUuid(routeDocumentId.value)) router?.returnToStore.saveMedicalDocumentTarget(routeDocumentId.value)
    router?.requireAuthentication(routeName)
    return
  }
  if (isDetail.value) {
    if (!isUuid(routeDocumentId.value)) { detailError.value = '档案编号无效。'; return }
    void loadDetail()
  } else void loadFirstPage()
})
onShow(() => {
  if (!authorized.value) {
    router?.requireAuthentication(isDetail.value ? 'medicalDocumentDetail' : 'healthArchive')
    return
  }
  active = true
  if (previewVisible) { previewVisible = false; void previewAdapter?.clear() }
  if (isDetail.value && !document.value && !detailLoading.value && !detailError.value) void loadDetail()
  else if (isDetail.value && document.value && detailNeedsRefresh) void loadDetail()
  else if (isDetail.value && document.value && candidateNeedsRefresh && candidateSectionVisible.value) void refreshCandidatesForPage()
  else if (!isDetail.value && documents.value.length > 0) void loadFirstPage()
})
onHide(() => {
  active = false
  pageGeneration++
  if (!previewVisible) void previewAdapter?.clear()
  listLoading.value = false; appendLoading.value = false; detailLoading.value = false
  uploadBusy.value = false; previewBusy.value = false; deleting.value = false
  candidatePanelGeneration.value++
  candidates.value = []; candidateError.value = ''; candidateConflict.value = ''; candidateLoading.value = false; busyCandidateId.value = null
  candidateNeedsRefresh = true
  detailNeedsRefresh = true
  const oldFile = selectedFile.value
  selectedFile.value = null
  activeUpload = null
  uploadIdempotencyKey = ''
  if (oldFile) void nativeMedicalFilePicker.cleanup(oldFile.path)
})
onUnload(() => {
  active = false
  pageGeneration++
  candidatePanelGeneration.value++
  candidates.value = []; candidateError.value = ''; candidateConflict.value = ''; candidateLoading.value = false; busyCandidateId.value = null
  const oldFilePath = selectedFile.value?.path || activeUpload?.file.path
  selectedFile.value = null
  if (oldFilePath) void nativeMedicalFilePicker.cleanup(oldFilePath)
  if (activeUpload?.file.path) void nativeMedicalFilePicker.cleanup(activeUpload.file.path)
  activeUpload = null
  void previewAdapter?.clear()
})
onBackPress(() => { goBack(); return true })

async function loadFirstPage() {
  if (!api || isDetail.value || listLoading.value) return
  const generation = ++pageGeneration
  active = true
  listLoading.value = documents.value.length === 0
  listError.value = ''
  appendError.value = ''
  cursor = null
  try {
    const result = await api.list({ limit: 20 })
    if (!isCurrent(generation)) return
    documents.value = result.items.filter((item) => item.file_status !== 'deleting')
    nextCursor.value = result.next_cursor
    cursor = result.next_cursor
  } catch (error) {
    if (!isCurrent(generation)) return
    listError.value = userError(error, '档案列表暂不可用，请检查网络后重试。')
  } finally { if (isCurrent(generation)) listLoading.value = false }
}

async function loadMore() {
  if (!api || !cursor || appendLoading.value) return
  const generation = pageGeneration
  appendLoading.value = true
  appendError.value = ''
  try {
    const result = await api.list({ cursor, limit: 20 })
    if (!isCurrent(generation)) return
    const known = new Set(documents.value.map((item) => item.id))
    documents.value = [...documents.value, ...result.items.filter((item) => item.file_status !== 'deleting' && !known.has(item.id))]
    nextCursor.value = result.next_cursor
    cursor = result.next_cursor
  } catch (error) {
    if (!isCurrent(generation)) return
    appendError.value = userError(error, '追加档案暂不可用，已保留现有列表。')
  } finally { if (isCurrent(generation)) appendLoading.value = false }
}

async function loadDetail() {
  if (!api || !routeDocumentId.value || detailLoading.value) return
  const generation = ++pageGeneration
  active = true
  detailLoading.value = !document.value
  detailError.value = ''
  try {
    const result = await api.get(routeDocumentId.value)
    if (!isCurrent(generation)) return
    document.value = result
    detailNeedsRefresh = false
    if (shouldLoadCandidates(result)) await loadCandidates(result.id, generation)
    else clearCandidateState()
  } catch (error) {
    if (!isCurrent(generation)) return
    detailError.value = userError(error, '档案暂不可用，请重试。')
    if (isNotFound(error)) { clearSensitiveDetail(); document.value = null; detailError.value = '档案不存在或当前不可用。' }
  } finally { if (isCurrent(generation)) detailLoading.value = false }
}

async function loadCandidates(documentId: string, generation: number) {
  if (!api || !isCurrent(generation)) return
  candidateLoading.value = candidates.value.length === 0
  candidateError.value = ''
  candidateNeedsRefresh = false
  try {
    const result = await api.listCandidates(documentId)
    if (!isCurrent(generation)) return
    candidates.value = result.map(safeCandidateForDisplay)
  } catch (error) {
    if (!isCurrent(generation)) return
    if (isNotFound(error)) {
      clearSensitiveDetail()
      document.value = null
      detailError.value = '档案不存在或当前不可用。'
      return
    }
    candidateError.value = userError(error, '字段候选暂不可用；已保留当前显示内容。')
  } finally { if (isCurrent(generation)) candidateLoading.value = false }
}

async function refreshCandidatesForPage() {
  if (!api || !document.value || !candidateSectionVisible.value || candidateLoading.value) return
  const generation = ++pageGeneration
  active = true
  await loadCandidates(document.value.id, generation)
}

async function decideCandidate(candidate: MedicalFieldCandidate, decision: MedicalCandidateDecision['decision'], value: unknown) {
  if (!api || !active || busyCandidateId.value !== null || candidate.review_status !== 'pending') return
  const generation = pageGeneration
  busyCandidateId.value = candidate.id
  candidateError.value = ''
  candidateConflict.value = ''
  try {
    const body: MedicalCandidateDecision = { decision, record_version: candidate.record_version, value }
    await api.decideCandidate(candidate.id, body, createIdempotencyKey())
    if (!isCurrent(generation)) return
    busyCandidateId.value = null
    await loadDetail()
  } catch (error) {
    if (!isCurrent(generation)) return
    if (isNotFound(error)) {
      clearSensitiveDetail()
      document.value = null
      detailError.value = '档案或候选不存在或当前不可用。'
    } else if (error instanceof AppError && error.status === 409) {
      candidateConflict.value = '候选已发生变化；当前决定未自动重发。请查看重新读取的状态后，再由你决定下一步。'
      await reloadAfterCandidateConflict(generation)
    } else candidateError.value = userError(error, '该字段暂未提交，请检查网络后刷新状态。')
  } finally { if (isCurrent(generation)) busyCandidateId.value = null }
}

async function reloadAfterCandidateConflict(generation: number) {
  if (!api || !document.value || !isCurrent(generation)) return
  candidateLoading.value = true
  try {
    const currentDocument = await api.get(document.value.id)
    if (!isCurrent(generation)) return
    const latestCandidates = shouldLoadCandidates(currentDocument) ? await api.listCandidates(currentDocument.id) : []
    if (!isCurrent(generation)) return
    document.value = currentDocument
    candidates.value = latestCandidates.map(safeCandidateForDisplay)
    candidateError.value = ''
    candidateNeedsRefresh = false
  } catch (error) {
    if (!isCurrent(generation)) return
    if (isNotFound(error)) {
      clearSensitiveDetail()
      document.value = null
      detailError.value = '档案或候选不存在或当前不可用。'
    } else candidateError.value = userError(error, '暂时无法读取最新候选；当前界面已保留且不会自动重发。请稍后手动刷新。')
  } finally { if (isCurrent(generation)) candidateLoading.value = false }
}

function shouldLoadCandidates(value: MedicalDocument) {
  return value.file_status === 'available' && value.processing_mode === 'analyze' && (value.parse_outcome === 'extracted' || value.parse_status === 'needs_confirmation' || value.parse_status === 'confirmed')
}
function clearCandidateState() {
  candidates.value = []; candidateError.value = ''; candidateConflict.value = ''; candidateLoading.value = false; busyCandidateId.value = null; candidateNeedsRefresh = false
}
function clearSensitiveDetail() { clearCandidateState(); candidatePanelGeneration.value++ }

async function pickFile() {
  uploadError.value = ''
  try {
    const previousPath = selectedFile.value?.path
    const next = await pickMedicalFile(nativeMedicalFilePicker)
    if (previousPath) void nativeMedicalFilePicker.cleanup(previousPath)
    selectedFile.value = next
    activeUpload = null
    uploadIdempotencyKey = ''
    documentCreateAttempted = false
  } catch (error) { uploadError.value = error instanceof Error ? error.message : '无法选择该文件。' }
}

async function saveDocument() {
  if (!api || uploadBusy.value || !selectedFile.value) return
  let generation = pageGeneration
  uploadBusy.value = true
  uploadError.value = ''
  try {
    const file = selectedFile.value
    const { contentType } = preflightMedicalFile(file.name, file.sizeBytes)
    if (!activeUpload) activeUpload = { uploadId: '', uploadUrl: '', uploaded: false, fileObjectId: null, file }
    if (!uploadIdempotencyKey) uploadIdempotencyKey = createIdempotencyKey()
    if (!activeUpload.uploadId) {
      const session = await api.createUpload({ purpose: 'medical_document', file_name: file.name, content_type: contentType, size_bytes: file.sizeBytes }, uploadIdempotencyKey)
      if (!isCurrent(generation) || !activeUpload) return
      activeUpload.uploadId = session.upload_id
      activeUpload.uploadUrl = session.upload_url
    }
    if (!activeUpload.uploaded) {
      setUploadStep('正在安全读取文件…')
      const bytes = await nativeMedicalFilePicker.read(file.path)
      if (!isCurrent(generation) || !activeUpload) return
      if (!bytesMatchDeclaredSize(bytes, file.sizeBytes)) throw new Error('文件大小发生变化，请重新选择文件。')
      setUploadStep('正在上传到受保护网关…')
      await api.upload(activeUpload.uploadUrl, bytes, contentType)
      if (!isCurrent(generation) || !activeUpload) return
      activeUpload.uploaded = true
      activeUpload.uploadUrl = ''
      void nativeMedicalFilePicker.cleanup(file.path)
      activeUpload.file.path = ''
      if (selectedFile.value) selectedFile.value.path = ''
    }
    if (!activeUpload.fileObjectId) {
      setUploadStep('服务器正在校验文件并进行安全扫描…')
      try {
        const fileObject = await api.completeUpload(activeUpload.uploadId)
        if (!isCurrent(generation) || !activeUpload) return
        activeUpload.fileObjectId = fileObject.id
      } catch (error) {
        if (error instanceof AppError && error.status === 503) throw new Error('扫描服务暂不可用；文件尚未完成，可稍后重试。')
        throw error
      }
    }
    if (documentCreateAttempted) {
      await loadFirstPage()
      if (!active) return
      generation = pageGeneration
      if (!activeUpload) return
      if (documents.value.some((item) => item.file_object_id === activeUpload?.fileObjectId)) {
        resetDraft(); uploadError.value = ''; uni.showToast({ title: '档案已保存', icon: 'success' }); return
      }
      throw new Error('档案创建结果暂无法确认。已刷新列表；为避免重复创建，请先核对档案列表。')
    }
    const documentType = documentTypes[typeIndex.value]
    if (!documentType) throw new Error('请选择资料类型。')
    documentCreateAttempted = true
    setUploadStep('正在保存档案信息…')
    const payload: MedicalDocumentCreate = {
      file_object_id: activeUpload.fileObjectId,
      document_type: documentType,
      hospital_name: hospitalName.value.trim() || null,
      document_date: documentDate.value || null,
      notes: notes.value.trim() || null,
      processing_mode: processingMode.value,
    }
    try {
      const created = await api.create(payload)
      if (!isCurrent(generation)) return
      documents.value = [created, ...documents.value.filter((item) => item.id !== created.id)]
      void nativeMedicalFilePicker.cleanup(file.path)
      resetDraft()
      uni.showToast({ title: '档案已保存', icon: 'success' })
    } catch (error) {
      if (isUncertainNetworkFailure(error)) {
        await loadFirstPage()
        if (!active) return
        generation = pageGeneration
        if (documents.value.some((item) => item.file_object_id === activeUpload?.fileObjectId)) {
          resetDraft(); uni.showToast({ title: '档案已保存', icon: 'success' }); return
        }
        throw new Error('档案创建结果暂无法确认。已刷新列表；为避免重复创建，请先核对档案列表。')
      }
      documentCreateAttempted = false
      throw error
    }
  } catch (error) { if (isCurrent(generation)) uploadError.value = userError(error, '上传未完成，文件不会显示为可用档案。请检查后重试。') }
  finally { if (isCurrent(generation)) uploadBusy.value = false }
}

function setUploadStep(_step: string) { uploadStep.value = _step }
const uploadStep = ref('')

async function preview() {
  if (!api || !previewAdapter || !document.value || previewBusy.value || document.value.file_status !== 'available') return
  const generation = pageGeneration
  previewBusy.value = true
  detailError.value = ''
  try {
    const grant = await api.createDownloadGrant(document.value.file_object_id)
    if (!isCurrent(generation)) { grant.download_url = ''; return }
    const auth = useAuthStore()
    const filePath = await previewAdapter.download(grant, auth.accessToken ?? '')
    if (!isCurrent(generation)) { await previewAdapter.remove(filePath); return }
    previewVisible = true
    const isPdf = document.value.original_name.toLowerCase().endsWith('.pdf')
    if (isPdf) {
      uni.openDocument({ filePath, fileType: 'pdf', showMenu: false,
        fail: () => { previewVisible = false; detailError.value = '无法打开该文件，请稍后重试。'; void previewAdapter.remove(filePath) },
      })
    } else {
      uni.previewImage({ urls: [filePath], current: filePath,
        fail: () => { previewVisible = false; detailError.value = '无法打开该文件，请稍后重试。'; void previewAdapter.remove(filePath) },
      })
    }
  } catch (error) { detailError.value = userError(error, '文件预览暂不可用，请稍后重试。') }
  finally { previewBusy.value = false }
}

function confirmDelete() {
  if (!document.value || deleting.value || document.value.file_status !== 'available') return
  uni.showModal({ title: '删除医疗档案？', content: '删除后会立即从列表和预览中隐藏。此操作不能在 APP 中撤销。', confirmText: '删除', confirmColor: '#B84D46', success: (result) => { if (result.confirm) void deleteDocument() } })
}
async function deleteDocument() {
  if (!api || !document.value || deleting.value) return
  const current = document.value
  const generation = pageGeneration
  deleting.value = true
  detailError.value = ''
  try {
    await api.delete(current.id)
    if (!isCurrent(generation)) return
    document.value = { ...current, file_status: 'deleting' }
    uni.showToast({ title: '档案已隐藏', icon: 'success' })
    router?.navigateBack()
  } catch (error) { if (isCurrent(generation)) detailError.value = userError(error, '暂时无法删除档案，请稍后重试。') }
  finally { if (isCurrent(generation)) deleting.value = false }
}

function resetDraft() {
  if (selectedFile.value) void nativeMedicalFilePicker.cleanup(selectedFile.value.path)
  selectedFile.value = null; activeUpload = null; uploadIdempotencyKey = ''; documentCreateAttempted = false
  hospitalName.value = ''; documentDate.value = ''; notes.value = ''; processingMode.value = 'store_only'; typeIndex.value = 3
}
function goBack() { if (isDetail.value) router?.navigateBack(); else router?.switchTab('records') }
function onTypeChange(event: { detail?: { value?: string } }) { const value = Number(event.detail?.value); if (Number.isInteger(value) && value >= 0 && value < documentTypes.length) typeIndex.value = value }
function onDateChange(event: { detail?: { value?: string } }) { if (typeof event.detail?.value === 'string') documentDate.value = event.detail.value }
function documentTypeLabel(value: MedicalDocument['document_type']) { return documentTypeLabels[documentTypes.indexOf(value)] ?? '医疗资料' }
function parseStatusLabel(value: MedicalDocument['parse_status']) { return ({ not_requested: '仅存储', pending: '等待解析', processing: '正在解析', needs_confirmation: '待本人核对', confirmed: '已逐项确认', failed: '解析未完成' } as const)[value] }
function parseOutcomeLabel(value: MedicalDocument) { return getParseOutcomeLabel(value) }
function parseReasonLabel(value: MedicalDocument) { return getParseReasonLabel(value) }
function fileStatusLabel(value: MedicalDocument['file_status']) { return value === 'deleting' ? '正在删除' : '文件可用' }
function mimeLabel(value: string) { return value === 'application/pdf' ? 'PDF' : value === 'image/jpeg' ? 'JPEG' : 'PNG' }
function formatBytes(value: number) { return `${(value / (1024 * 1024)).toFixed(value >= 1024 * 1024 ? 1 : 2)} MiB` }
function userError(error: unknown, fallback: string) {
  if (error instanceof AppError) return error.status === 404 ? '档案不存在或当前不可用。' : error.status === 409 ? '档案状态已变化，请刷新后重试。' : error.status === 413 ? '文件超过服务器允许的大小。' : error.status === 415 ? '服务器不接受该文件格式。' : error.status === 422 ? '文件内容未通过校验或当前授权不足，请核对文件和授权设置。' : error.status === 503 ? '文件存储或安全扫描暂不可用，请稍后重试。' : error.message
  return error instanceof Error ? error.message : fallback
}
function isNotFound(error: unknown) { return error instanceof AppError && error.status === 404 }
function isUncertainNetworkFailure(error: unknown) { return error instanceof AppError && ['network', 'offline', 'timeout'].includes(error.kind) }
function createIdempotencyKey() { return globalThis.crypto?.randomUUID?.() ?? `f02-${Date.now()}-${Math.random().toString(36).slice(2)}` }
function isUuid(value: string) { return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value) }
</script>

<style lang="scss" scoped>
.archive-page{min-height:100vh;background:var(--gc-color-canvas)}.archive-shell{width:100%;max-width:430px;min-height:100vh;margin:0 auto;padding:calc(env(safe-area-inset-top,0px) + 10px) 20px calc(env(safe-area-inset-bottom,0px) + 24px)}.topbar{display:flex;height:48px;align-items:center;justify-content:space-between}.back-button{display:grid;width:44px;height:44px;padding:0;place-items:center;border:0;border-radius:50%;background:var(--gc-color-surface);color:var(--gc-color-brand-strong);font-size:28px;line-height:1}.topbar-title{color:var(--gc-color-text);font-size:15px;font-weight:var(--gc-font-weight-semibold)}.topbar-spacer{width:44px}.page-intro{margin:18px 2px 18px}.eyebrow{color:var(--gc-color-brand);font-size:10px;font-weight:var(--gc-font-weight-semibold);letter-spacing:1px}.page-title{display:block;margin-top:4px;color:var(--gc-color-text);font-size:27px;font-weight:var(--gc-font-weight-bold)}.page-subtitle,.section-caption{display:block;margin-top:6px;color:var(--gc-color-muted);font-size:12px;line-height:1.55}.upload-card,.detail-card{margin:10px 0 22px;padding:18px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);background:var(--gc-color-surface);box-shadow:var(--gc-shadow-card)}.section-title{color:var(--gc-color-text);font-size:16px;font-weight:var(--gc-font-weight-semibold)}.section-caption{margin-bottom:12px}.selected-file{display:flex;margin:12px 0;padding:12px;border-radius:14px;flex-direction:column;gap:4px;background:var(--gc-color-sage-pale)}.selected-file-name{overflow-wrap:anywhere;color:var(--gc-color-text);font-size:13px;font-weight:var(--gc-font-weight-semibold)}.selected-file-meta{color:var(--gc-color-muted);font-size:11px}.field{margin:15px 0}.field-label,.detail-label{display:block;margin-bottom:6px;color:var(--gc-color-muted);font-size:11px}.input,.picker-value,.notes-input{box-sizing:border-box;width:100%;min-height:46px;padding:12px;border:1px solid var(--gc-color-border);border-radius:13px;background:var(--gc-color-canvas);color:var(--gc-color-text);font-size:13px}.notes-input{min-height:82px}.mode-group{display:flex;gap:9px}.mode-option{display:flex;min-height:82px;flex:1;padding:12px;border:1px solid var(--gc-color-border);border-radius:14px;flex-direction:column;align-items:flex-start;justify-content:center;gap:5px;background:var(--gc-color-surface);text-align:left}.mode-option--selected{border-color:var(--gc-color-brand);background:var(--gc-color-sage-pale)}.mode-title{color:var(--gc-color-text);font-size:12px;font-weight:var(--gc-font-weight-semibold)}.mode-copy,.privacy-note,.safety-note{color:var(--gc-color-muted);font-size:10px;line-height:1.5}.privacy-note{display:block;margin:10px 0 14px}.upload-progress{margin:10px 0;color:var(--gc-color-brand-strong);font-size:12px}.inline-error{display:block;margin:12px 0;padding:12px;border:1px solid var(--gc-color-danger-border);border-radius:12px;background:var(--gc-color-danger-pale);color:var(--gc-color-danger);font-size:12px;line-height:1.5}.list-heading{display:flex;align-items:center;justify-content:space-between;margin:22px 2px 10px}.refresh-button{min-width:52px;min-height:44px;padding:0 10px;border:1px solid var(--gc-color-border);border-radius:12px;background:var(--gc-color-surface);color:var(--gc-color-brand);font-size:12px}.state-panel{display:flex;min-height:160px;padding:22px;border:1px solid var(--gc-color-border);border-radius:var(--gc-radius-lg);flex-direction:column;align-items:center;justify-content:center;gap:8px;background:var(--gc-color-surface);text-align:center}.state-title{color:var(--gc-color-text);font-size:14px;font-weight:var(--gc-font-weight-semibold)}.state-copy{max-width:280px;color:var(--gc-color-muted);font-size:11px;line-height:1.5}.empty-mark,.file-mark{display:grid;width:50px;height:50px;place-items:center;border-radius:17px;background:var(--gc-color-peach);color:var(--gc-color-orange);font-size:23px}.document-list{display:flex;flex-direction:column;gap:9px}.document-row{display:flex;min-height:82px;align-items:center;gap:11px;padding:12px;border:1px solid var(--gc-color-border);border-radius:16px;background:var(--gc-color-surface);text-align:left}.document-row--deleting{opacity:.56}.row-icon{display:grid;width:42px;height:42px;flex:0 0 42px;place-items:center;border-radius:14px;background:var(--gc-color-peach);color:var(--gc-color-orange);font-size:18px}.row-copy{display:flex;min-width:0;flex:1;flex-direction:column;gap:4px}.row-title{overflow:hidden;color:var(--gc-color-text);font-size:12px;font-weight:var(--gc-font-weight-semibold);text-overflow:ellipsis;white-space:nowrap}.row-meta,.row-status{color:var(--gc-color-muted);font-size:10px}.chevron{color:var(--gc-color-placeholder);font-size:23px}.document-detail{margin-top:16px}.detail-card{display:flex;flex-direction:column;align-items:flex-start;gap:10px}.document-title{max-width:100%;overflow-wrap:anywhere;color:var(--gc-color-text);font-size:16px;font-weight:var(--gc-font-weight-semibold)}.status-line{color:var(--gc-color-muted);font-size:11px}.detail-row{display:flex;width:100%;justify-content:space-between;gap:16px;padding-top:10px;border-top:1px solid var(--gc-color-border)}.detail-row--notes{align-items:flex-start}.detail-label{flex:0 0 70px;margin:0}.detail-value{color:var(--gc-color-text);font-size:12px;text-align:right;overflow-wrap:anywhere}.action-stack{display:flex;flex-direction:column;gap:10px}.safety-note{display:block;margin:16px 4px;text-align:center}.safety-note--bottom{margin-top:20px}
.list-actions{display:flex;gap:7px}
</style>
